"""Supply side of ChargeScape London: public EV charge point locations and official counts.

One fetch function per source. Every function is idempotent: if its output already exists it is
returned untouched, so the module can be re-run safely (and cheaply for the Overpass API).

Sources
-------
* ``fetch_osm``               OpenStreetMap ``amenity=charging_station`` via the Overpass API for the
                              Greater London administrative area (relation 175342, admin_level 5).
* ``fetch_ocm``               Open Charge Map v3 POI API. Probed WITHOUT an API key; if the API refuses
                              (401/403) the refusal is recorded and the source is skipped.
* ``fetch_dft_evci``          DfT official statistics "Electric vehicle charging infrastructure
                              statistics" data tables (EVCI0101, EVCI0102, EVCI0201, EVCI9001; ODS).
* ``fetch_london_datastore``  London Datastore / GLA "Electric Vehicle Charging Site" (TfL rapid
                              charging points, GeoPackage, 2019).
* ``fetch_ncr_archive``       National Chargepoint Registry (closed 28 Nov 2024): the last complete
                              CSV capture held by the Internet Archive (25 May 2021).

Run from the repository root::

    PYTHONPATH=src python -m chargescape.data.chargepoints
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from chargescape.utils.http import UA, download, get_json
from chargescape.utils.paths import INTERIM, RAW, ensure_dirs

RAW_DIR = RAW / "chargepoints"
OUT_DIR = INTERIM / "chargepoints"

#: Greater London bounding box as (south, west, north, east); matches the Nominatim bbox of relation 175342.
BBOX = (51.28, -0.51, 51.70, 0.33)
LONDON_BOROUGH_CODES = {f"E09{n:06d}" for n in range(1, 34)}  # E09000001 .. E09000033 (incl. City of London)
LONDON_REGION_CODE = "E12000007"
COMPARATOR_CODES = {LONDON_REGION_CODE: "region", "E92000001": "country", "K02000001": "country"}
BNG = "EPSG:27700"
WGS84 = "EPSG:4326"


def _log(msg: str) -> None:
    print(f"[chargepoints] {msg}", flush=True)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------------------
# 1. OpenStreetMap via Overpass
# --------------------------------------------------------------------------------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
#: Area 3600175342 = OSM relation 175342 "Greater London" (boundary=administrative, admin_level=5).
OVERPASS_QUERY = """[out:json][timeout:180];
area(3600175342)->.london;
(
  node["amenity"="charging_station"](area.london);
  way["amenity"="charging_station"](area.london);
  relation["amenity"="charging_station"](area.london);
);
out center tags;
"""
OSM_RAW = RAW_DIR / "osm_charging_stations_overpass.json"
OSM_OUT = OUT_DIR / "osm_charging_stations.parquet"
#: Plain tags copied to their own column (":" becomes "_"). socket:* tags are handled separately.
OSM_TAGS = [
    "name",
    "operator",
    "brand",
    "network",
    "ref",
    "capacity",
    "charging_station:output",
    "maxpower",
    "fee",
    "access",
    "opening_hours",
    "motorcar",
    "bicycle",
    "check_date",
    "authentication:app",
    "authentication:membership_card",
    "authentication:none",
    "payment:contactless",
    "payment:app",
]
_KW_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kwh|kva|kw|w)?", re.I)
_INT_RE = re.compile(r"\d+")


def parse_kw(value: Any) -> float | None:
    """Parse OSM power strings ('22 kW', '7.4kW', '50000 W', '2x22kW', '7 kW;50 kW') to the max kW."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    best: float | None = None
    for m in _KW_RE.finditer(str(value)):
        num = float(m.group(1).replace(",", "."))
        unit = (m.group(2) or "kw").lower()
        if unit == "kwh":
            continue
        if unit == "w":
            num /= 1000.0
        if 0 < num <= 1000 and (best is None or num > best):
            best = num
    return best


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    m = _INT_RE.search(str(value))
    return int(m.group(0)) if m else None


def _osm_elements_to_gdf(data: dict[str, Any]) -> gpd.GeoDataFrame:
    """Flatten Overpass elements (nodes + way/relation centroids) into a WGS84 GeoDataFrame."""
    rows: list[dict[str, Any]] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        if el["type"] == "node":
            lat, lon = el["lat"], el["lon"]
        else:
            centre = el.get("center")
            if not centre:
                continue
            lat, lon = centre["lat"], centre["lon"]
        rec: dict[str, Any] = {"osm_type": el["type"], "osm_id": el["id"], "lat": lat, "lon": lon}
        for t in OSM_TAGS:
            rec[t.replace(":", "_")] = tags.get(t)
        socket_total = 0
        any_socket = False
        outputs: list[float] = []
        for k, v in tags.items():
            if not k.startswith("socket:"):
                continue
            parts = k.split(":")
            if len(parts) == 2:  # socket:<type> = count
                n = _to_int(v)
                rec[f"socket_{parts[1]}"] = n
                if n is not None:
                    socket_total += n
                    any_socket = True
            elif len(parts) == 3 and parts[2] == "output":  # socket:<type>:output = power
                kw = parse_kw(v)
                rec[f"socket_{parts[1]}_output_kw"] = kw
                if kw is not None:
                    outputs.append(kw)
        candidates = [parse_kw(tags.get("charging_station:output")), parse_kw(tags.get("maxpower")), *outputs]
        candidates = [c for c in candidates if c is not None]
        rec["max_power_kw"] = max(candidates) if candidates else None
        rec["n_sockets"] = socket_total if any_socket else None
        rec["capacity_int"] = _to_int(tags.get("capacity"))
        rec["tags_json"] = json.dumps(tags, ensure_ascii=False, sort_keys=True)
        rows.append(rec)
    df = pd.DataFrame(rows)
    fixed = [
        "osm_type",
        "osm_id",
        "lat",
        "lon",
        *[t.replace(":", "_") for t in OSM_TAGS],
        "max_power_kw",
        "n_sockets",
        "capacity_int",
    ]
    socket_cols = sorted(c for c in df.columns if c.startswith("socket_"))
    df = df[[*fixed, *socket_cols, "tags_json"]]
    df["source"] = "osm"
    df["osm_data_timestamp"] = data.get("osm3s", {}).get("timestamp_osm_base")
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=WGS84)


def fetch_osm() -> Path:
    """Download OSM charging stations for Greater London (one Overpass query) and save GeoParquet."""
    if OSM_OUT.exists():
        _log(f"OSM: {OSM_OUT.relative_to(RAW.parent.parent)} exists, skipping")
        return OSM_OUT
    if OSM_RAW.exists():
        data = json.loads(OSM_RAW.read_text())
        _log(f"OSM: reusing raw Overpass response {OSM_RAW.name}")
    else:
        _log("OSM: querying Overpass (single query, timeout 180 s) ...")
        data = get_json(OVERPASS_URL, {"data": OVERPASS_QUERY}, timeout=240)
        OSM_RAW.parent.mkdir(parents=True, exist_ok=True)
        OSM_RAW.write_text(json.dumps(data))
        _log(
            f"OSM: saved raw JSON ({OSM_RAW.stat().st_size / 1e6:.2f} MB, {len(data.get('elements', []))} elements)"
        )
    gdf = _osm_elements_to_gdf(data)
    s, w, n, e = BBOX
    gdf = gdf[gdf["lat"].between(s, n) & gdf["lon"].between(w, e)].reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OSM_OUT, index=False)
    _log(f"OSM: wrote {len(gdf)} features -> {OSM_OUT}")
    return OSM_OUT


# --------------------------------------------------------------------------------------------------
# 2. Open Charge Map
# --------------------------------------------------------------------------------------------------
OCM_URL = "https://api.openchargemap.io/v3/poi/"
OCM_REF_URL = "https://api.openchargemap.io/v3/referencedata/"
OCM_RAW_DIR = RAW_DIR / "ocm"
OCM_STATUS = RAW_DIR / "ocm_api_status.json"
OCM_OUT = OUT_DIR / "ocm_london.parquet"
OCM_MAX = 10000


def _ocm_headers() -> dict[str, str]:
    h = {"User-Agent": UA}
    key = os.environ.get("OCM_API_KEY")  # optional; never registered for by this project
    if key:
        h["X-API-Key"] = key
    return h


def _ocm_bbox_param(south: float, west: float, north: float, east: float) -> str:
    return f"({south},{west}),({north},{east})"


def _ocm_fetch_tile(south: float, west: float, north: float, east: float, depth: int = 0) -> list[dict]:
    """Fetch one bbox tile; if it saturates ``maxresults`` split it into four (OCM has no offset paging)."""
    params = {
        "output": "json",
        "countrycode": "GB",
        "boundingbox": _ocm_bbox_param(south, west, north, east),
        "maxresults": OCM_MAX,
        "compact": "true",
        "verbose": "false",
    }
    r = requests.get(OCM_URL, params=params, headers=_ocm_headers(), timeout=180)
    r.raise_for_status()
    pois = r.json()
    OCM_RAW_DIR.mkdir(parents=True, exist_ok=True)
    (OCM_RAW_DIR / f"tile_d{depth}_{south:.4f}_{west:.4f}_{north:.4f}_{east:.4f}.json").write_text(
        json.dumps(pois)
    )
    time.sleep(1.0)
    if len(pois) >= OCM_MAX and depth < 6:
        mid_lat, mid_lon = (south + north) / 2, (west + east) / 2
        pois = []
        for s_, w_, n_, e_ in [
            (south, west, mid_lat, mid_lon),
            (south, mid_lon, mid_lat, east),
            (mid_lat, west, north, mid_lon),
            (mid_lat, mid_lon, north, east),
        ]:
            pois.extend(_ocm_fetch_tile(s_, w_, n_, e_, depth + 1))
    return pois


def _ocm_to_frame(pois: list[dict], ref: dict[str, Any] | None) -> pd.DataFrame:
    """Normalise OCM POIs (compact or verbose) to the project schema."""
    ref = ref or {}

    def lookup(kind: str, id_: Any) -> str | None:
        for item in ref.get(kind, []) or []:
            if item.get("ID") == id_:
                return item.get("Title")
        return None

    rows = []
    for p in pois:
        addr = p.get("AddressInfo") or {}
        conns = p.get("Connections") or []
        powers = [c.get("PowerKW") for c in conns if c.get("PowerKW") is not None]
        levels = [c.get("LevelID") for c in conns if c.get("LevelID") is not None]
        rows.append(
            {
                "ocm_id": p.get("ID"),
                "lat": addr.get("Latitude"),
                "lon": addr.get("Longitude"),
                "operator": (p.get("OperatorInfo") or {}).get("Title")
                or lookup("Operators", p.get("OperatorID")),
                "usage_type": (p.get("UsageType") or {}).get("Title")
                or lookup("UsageTypes", p.get("UsageTypeID")),
                "status": (p.get("StatusType") or {}).get("Title")
                or lookup("StatusTypes", p.get("StatusTypeID")),
                "n_points": p.get("NumberOfPoints"),
                "connections": json.dumps(
                    [
                        {
                            k: c.get(k)
                            for k in (
                                "ConnectionTypeID",
                                "PowerKW",
                                "Quantity",
                                "LevelID",
                                "CurrentTypeID",
                                "StatusTypeID",
                            )
                        }
                        for c in conns
                    ]
                ),
                "max_power_kw": max(powers) if powers else None,
                "level": max(levels) if levels else None,
                "date_created": p.get("DateCreated"),
                "date_last_verified": p.get("DateLastVerified"),
            }
        )
    df = pd.DataFrame(rows).drop_duplicates("ocm_id")
    df["source"] = "ocm"
    return df


def fetch_ocm() -> Path | None:
    """Probe Open Charge Map without an API key; download London POIs if permitted, else record the refusal."""
    if OCM_OUT.exists():
        _log(f"OCM: {OCM_OUT.name} exists, skipping")
        return OCM_OUT
    if OCM_STATUS.exists() and "X-API-Key" not in _ocm_headers():
        prev = json.loads(OCM_STATUS.read_text())
        if prev.get("http_status") in (401, 403):
            _log(
                f"OCM: probe on {prev.get('checked_at')} returned HTTP {prev['http_status']} (API key required); "
                "skipping. Set OCM_API_KEY to retry."
            )
            return None
    probe = {
        "output": "json",
        "countrycode": "GB",
        "boundingbox": _ocm_bbox_param(*BBOX),
        "maxresults": 1,
        "compact": "true",
        "verbose": "false",
    }
    r = requests.get(OCM_URL, params=probe, headers=_ocm_headers(), timeout=60)
    status = {
        "checked_at": _now(),
        "url": r.url,
        "http_status": r.status_code,
        "api_key_used": "X-API-Key" in _ocm_headers(),
        "response_head": r.text[:300],
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OCM_STATUS.write_text(json.dumps(status, indent=2))
    if r.status_code in (401, 403):
        _log(f"OCM: HTTP {r.status_code} without API key -> skipped. Message: {r.text[:120]!r}")
        return None
    r.raise_for_status()
    _log("OCM: API answered without a key; tiling the bbox ...")
    try:
        ref = requests.get(OCM_REF_URL, params={"output": "json"}, headers=_ocm_headers(), timeout=120).json()
        (OCM_RAW_DIR / "referencedata.json").write_text(json.dumps(ref))
    except Exception as exc:  # noqa: BLE001
        _log(f"OCM: reference data unavailable ({exc}); ids will not be resolved to names")
        ref = None
    pois = _ocm_fetch_tile(*BBOX)
    df = _ocm_to_frame(pois, ref)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OCM_OUT, index=False)
    _log(f"OCM: wrote {len(df)} POIs -> {OCM_OUT}")
    return OCM_OUT


# --------------------------------------------------------------------------------------------------
# 3. DfT electric vehicle charging infrastructure statistics (ODS tables)
# --------------------------------------------------------------------------------------------------
DFT_PAGE = "https://www.gov.uk/government/statistical-data-sets/electric-vehicle-charging-infrastructure-statistics-data-tables-evci"
DFT_DIR = RAW_DIR / "dft_evci"
DFT_TABLES: dict[str, tuple[str, str]] = {
    # table id: (title on GOV.UK, direct asset URL) -- release of 27 August 2026, data as at 1 July 2026
    "EVCI0101": (
        "Public EV chargers by country and region: United Kingdom, 1 July 2026",
        "https://assets.publishing.service.gov.uk/media/6a8ed778df4246cf45e4654d/evci0101_2026-07_EV_chargers_by_region_and_country_UK.ods",
    ),
    "EVCI0102": (
        "Public EV chargers by local authority: United Kingdom, 1 July 2026",
        "https://assets.publishing.service.gov.uk/media/6a8ed78af5b35599aec18df8/evci0102_2026-07_EV_chargers_by_local_authority_UK.ods",
    ),
    "EVCI0201": (
        "Public EV chargers by power band: United Kingdom, 1 July 2026",
        "https://assets.publishing.service.gov.uk/media/6a8ed7e53b22fb169dc18e1d/evci0201_2026-07_EV_chargers_by_power_band_UK.ods",
    ),
    "EVCI9001": (
        "Public EV charging devices: United Kingdom, 1 July 2026 (historic tables)",
        "https://assets.publishing.service.gov.uk/media/6a8c0284a8f84a582b84280a/evci9001_2026-07_EV_charging_devices_UK.ods",
    ),
}
DFT_OUT = OUT_DIR / "dft_evci_london_la.parquet"
DFT_UK_POWER_OUT = OUT_DIR / "dft_evci_uk_power_band.parquet"
_ODS_NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def read_ods(path: Path) -> dict[str, list[list[Any]]]:
    """Minimal ODS reader (stdlib only, no odfpy): sheet name -> list of rows of cell values.

    Numeric cells become ``float``; everything else is the cell text (``None`` when empty).
    Repeated empty rows/columns (ODS run-length encoding) are truncated.
    """
    t, o, x = (f"{{{_ODS_NS[k]}}}" for k in ("table", "office", "text"))
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    sheets: dict[str, list[list[Any]]] = {}
    for tbl in root.iter(f"{t}table"):
        rows: list[list[Any]] = []
        for row in tbl.iter(f"{t}table-row"):
            cells: list[Any] = []
            for cell in row:
                if cell.tag not in (f"{t}table-cell", f"{t}covered-table-cell"):
                    continue
                rep = min(int(cell.get(f"{t}number-columns-repeated", "1")), 1000)
                vtype, vraw = cell.get(f"{o}value-type"), cell.get(f"{o}value")
                text = " ".join("".join(p.itertext()) for p in cell.iter(f"{x}p")).strip()
                if vtype in ("float", "percentage", "currency") and vraw is not None:
                    val: Any = float(vraw)
                else:
                    val = text or None
                cells.extend([val] * rep)
            while cells and cells[-1] is None:
                cells.pop()
            for _ in range(min(int(row.get(f"{t}number-rows-repeated", "1")), 100)):
                rows.append(list(cells))
        while rows and not rows[-1]:
            rows.pop()
        sheets[tbl.get(f"{t}name")] = rows
    return sheets


def _sheet_df(rows: list[list[Any]]) -> pd.DataFrame:
    """Turn a DfT-style sheet (title lines, then a header row with >= 3 cells) into a DataFrame."""
    hdr = next(i for i, r in enumerate(rows) if len(r) >= 3)
    header = [str(c).strip() if c is not None else f"col{j}" for j, c in enumerate(rows[hdr])]
    width = len(header)
    body = [(r + [None] * width)[:width] for r in rows[hdr + 1 :] if r]
    return pd.DataFrame(body, columns=header)


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.replace({"[x]": None, "[z]": None, "[c]": None, "[low]": None}), errors="coerce"
    )


_PERIOD_RE = re.compile(r"^([A-Za-z]{3})[A-Za-z]*-(\d{2})")


def _period_to_date(label: str) -> pd.Timestamp | None:
    m = _PERIOD_RE.match(str(label).strip())
    if not m:
        return None
    return pd.Timestamp(datetime.strptime(f"{m.group(1)} 20{m.group(2)}", "%b %Y"))


def _tidy_long(df: pd.DataFrame, table: str, file: str) -> pd.DataFrame:
    """EVCI0101e / EVCI0102e long sheets -> project schema (London boroughs + comparators)."""
    code_col = next(c for c in df.columns if c.lower().endswith("code"))
    name_col = df.columns[list(df.columns).index(code_col) + 1]
    out = pd.DataFrame(
        {
            "area_code": df[code_col],
            "area_name": df[name_col],
            "date": pd.to_datetime(df["Date"], format="%d %B %Y", errors="coerce"),
            "period_label": df["Date"],
            "measure": df["Key"],
            "value": _num(df["Value"]),
            "notes": df.get("Notes"),
            "source_table": table,
            "source_file": file,
        }
    )
    out["geography"] = np.where(
        out["area_code"].isin(LONDON_BOROUGH_CODES), "local_authority", out["area_code"].map(COMPARATOR_CODES)
    )
    return out[out["geography"].notna()]


def _tidy_wide_history(df: pd.DataFrame, measure: str, table: str, file: str) -> pd.DataFrame:
    """EVCI9001 tables 1a/1b/2a/2b (LA x quarter, wide) -> long rows for London + comparators."""
    code_col, name_col = df.columns[0], df.columns[1]
    keep = df[df[code_col].isin(LONDON_BOROUGH_CODES | set(COMPARATOR_CODES))]
    long = keep.melt(id_vars=[code_col, name_col], var_name="period_label", value_name="value")
    out = pd.DataFrame(
        {
            "area_code": long[code_col],
            "area_name": long[name_col],
            "date": long["period_label"].map(_period_to_date),
            "period_label": long["period_label"],
            "measure": measure,
            "value": _num(long["value"]),
            "notes": None,
            "source_table": table,
            "source_file": file,
        }
    )
    out["geography"] = np.where(
        out["area_code"].isin(LONDON_BOROUGH_CODES), "local_authority", out["area_code"].map(COMPARATOR_CODES)
    )
    return out


def fetch_dft_evci() -> Path:
    """Download the DfT EVCI ODS tables and extract London boroughs + Greater London (+ England/UK) rows."""
    if DFT_OUT.exists():
        _log(f"DfT: {DFT_OUT.name} exists, skipping")
        return DFT_OUT
    files: dict[str, Path] = {}
    for tid, (title, url) in DFT_TABLES.items():
        files[tid] = download(url, DFT_DIR / url.rsplit("/", 1)[-1])
        _log(f"DfT: {tid} '{title}' -> {files[tid].name} ({files[tid].stat().st_size / 1e3:.0f} kB)")
    parts: list[pd.DataFrame] = []
    s0101 = read_ods(files["EVCI0101"])
    parts.append(_tidy_long(_sheet_df(s0101["EVCI0101e"]), "EVCI0101e", files["EVCI0101"].name))
    s0102 = read_ods(files["EVCI0102"])
    parts.append(_tidy_long(_sheet_df(s0102["EVCI0102e"]), "EVCI0102e", files["EVCI0102"].name))
    s9001 = read_ods(files["EVCI9001"])
    hist = {
        "1a": "EV charging devices (historic quarterly series)",
        "1b": "50kW+ EV charging devices (historic quarterly series; 25kW+ before Oct-23)",
        "2a": "EV charging devices per 100k population (historic quarterly series)",
        "2b": "50kW+ EV charging devices per 100k population (historic quarterly series; 25kW+ before Oct-23)",
    }
    for sheet, measure in hist.items():
        parts.append(
            _tidy_wide_history(_sheet_df(s9001[sheet]), measure, f"EVCI9001_{sheet}", files["EVCI9001"].name)
        )
    la = pd.concat(parts, ignore_index=True)
    la = la[
        [
            "area_code",
            "area_name",
            "geography",
            "date",
            "period_label",
            "measure",
            "value",
            "notes",
            "source_table",
            "source_file",
        ]
    ].sort_values(["source_table", "measure", "date", "area_code"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    la.to_parquet(DFT_OUT, index=False)
    _log(f"DfT: wrote {len(la)} rows ({la['area_code'].nunique()} areas) -> {DFT_OUT}")
    # UK-level power bands (the only power-band split DfT publishes; not available per local authority)
    s0201 = read_ods(files["EVCI0201"])
    pb = _sheet_df(s0201["EVCI0201b"])
    pb = pd.DataFrame(
        {
            "date": pd.to_datetime(pb["Date"], format="%d %B %Y", errors="coerce"),
            "period_label": pb["Date"],
            "power_band": pb["Power Band"],
            "value": _num(pb["Value"]),
            "notes": pb.get("Notes"),
            "source_table": "EVCI0201b",
            "source_file": files["EVCI0201"].name,
        }
    )
    pb.to_parquet(DFT_UK_POWER_OUT, index=False)
    _log(f"DfT: wrote {len(pb)} UK power-band rows -> {DFT_UK_POWER_OUT}")
    return DFT_OUT


# --------------------------------------------------------------------------------------------------
# 4. London Datastore (GLA) -- TfL rapid charging points, 2019
# --------------------------------------------------------------------------------------------------
LDS_DATASET_ID = "2lzpg"  # "Electric Vehicle Charging Site", GLA Environment Team
LDS_META_URL = f"https://data.london.gov.uk/api/action/package_show?id={LDS_DATASET_ID}"
LDS_URL = "https://data.london.gov.uk/download/2lzpg/8ef9c743-c01d-4329-8239-8f858ff4de53/Rapid_charging_points.gpkg"
LDS_DIR = RAW_DIR / "london_datastore"
LDS_RAW = LDS_DIR / "Rapid_charging_points.gpkg"
LDS_OUT = OUT_DIR / "london_datastore_rapid_charging_points_2019.parquet"


def fetch_london_datastore() -> Path:
    """Download the only open charge point *location* dataset on the London Datastore and normalise it."""
    if LDS_OUT.exists():
        _log(f"LDS: {LDS_OUT.name} exists, skipping")
        return LDS_OUT
    LDS_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = LDS_DIR / f"{LDS_DATASET_ID}_package_show.json"
    if not meta_path.exists():
        try:
            meta_path.write_text(json.dumps(get_json(LDS_META_URL), indent=1))
        except Exception as exc:  # noqa: BLE001
            _log(f"LDS: metadata request failed ({exc}); continuing")
    download(LDS_URL, LDS_RAW)
    g = gpd.read_file(LDS_RAW)
    # The GeoPackage carries a non-EPSG "unnamed" Transverse Mercator (Airy 1830, OSTN02) definition that is
    # British National Grid in all parameters; declare it as EPSG:27700 explicitly, then reproject.
    g = g.set_crs(BNG, allow_override=True).to_crs(WGS84)
    g = g.rename(
        columns={
            "longtitude": "longitude_src",
            "latitude": "latitude_src",
            "numberrcpoints": "n_rapid_points",
            "taxipublicuses": "use_type",
            "sitename": "site_name",
            "siteid": "site_id",
        }
    )
    for c in ("easting", "northing", "latitude_src", "longitude_src"):
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g["n_rapid_points"] = pd.to_numeric(g["n_rapid_points"], errors="coerce").astype("Int64")
    g["use_type"] = g["use_type"].str.strip().str.replace("Public Use", "Public use")
    g["borough"] = g["borough"].str.strip()
    g["lon"] = g.geometry.x
    g["lat"] = g.geometry.y
    g["snapshot_date"] = pd.to_datetime(g["runtime"], format="%m/%d/%Y", errors="coerce")
    g["source"] = "london_datastore_tfl_rapid_2019"
    g = g[
        [
            "site_id",
            "site_name",
            "borough",
            "use_type",
            "n_rapid_points",
            "url",
            "snapshot_date",
            "easting",
            "northing",
            "latitude_src",
            "longitude_src",
            "lat",
            "lon",
            "source",
            "geometry",
        ]
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    g.to_parquet(LDS_OUT, index=False)
    _log(f"LDS: wrote {len(g)} rapid charging sites -> {LDS_OUT}")
    return LDS_OUT


# --------------------------------------------------------------------------------------------------
# 5. National Chargepoint Registry -- Wayback Machine snapshot (registry closed 28 Nov 2024)
# --------------------------------------------------------------------------------------------------
NCR_WAYBACK_TS = "20210525024631"  # last complete HTTP 200 text/csv capture of the full registry
NCR_URL = f"https://web.archive.org/web/{NCR_WAYBACK_TS}id_/https://chargepoints.dft.gov.uk/api/retrieve/registry/format/csv"
NCR_DIR = RAW_DIR / "ncr_archive"
NCR_RAW = NCR_DIR / f"ncr_registry_wayback_{NCR_WAYBACK_TS[:8]}.csv"
NCR_OUT = OUT_DIR / "ncr_archive_london_2021.parquet"
NCR_BASE_COLS = [
    "chargeDeviceID",
    "reference",
    "name",
    "latitude",
    "longitude",
    "town",
    "county",
    "postcode",
    "uprn",
    "deviceOwnerName",
    "deviceControllerName",
    "deviceNetworks",
    "chargeDeviceStatus",
    "publishStatus",
    "dateCreated",
    "dateUpdated",
    "attribution",
    "paymentRequired",
    "subscriptionRequired",
    "onStreetFlag",
    "locationType",
    "access24Hours",
    "accessRestrictionFlag",
]
_CONN_RE = re.compile(r"^connector(\d+)(.+)$")


def fetch_ncr_archive() -> Path:
    """Download the archived NCR CSV (May 2021) and keep the Greater London bbox subset as GeoParquet."""
    if NCR_OUT.exists():
        _log(f"NCR: {NCR_OUT.name} exists, skipping")
        return NCR_OUT
    download(NCR_URL, NCR_RAW, timeout=300)
    _log(f"NCR: raw snapshot {NCR_RAW.name} ({NCR_RAW.stat().st_size / 1e6:.1f} MB)")
    # A couple of rows contain unquoted newlines; the python engine skips them (reported below).
    df = pd.read_csv(NCR_RAW, dtype=str, engine="python", on_bad_lines="skip", encoding_errors="replace")
    n_uk = len(df)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    s, w, n, e = BBOX
    df = df[df["latitude"].between(s, n) & df["longitude"].between(w, e)].copy()
    conn_cols: dict[int, dict[str, str]] = {}
    for c in df.columns:
        m = _CONN_RE.match(c)
        if m:
            conn_cols.setdefault(int(m.group(1)), {})[m.group(2)] = c

    def connectors(row: pd.Series) -> list[dict[str, Any]]:
        out = []
        for i in sorted(conn_cols):
            cols = conn_cols[i]
            ctype = row.get(cols.get("Type", ""), None)
            if ctype is None or (isinstance(ctype, float) and np.isnan(ctype)):
                continue
            kw = pd.to_numeric(row.get(cols.get("RatedOutputKW", ""), None), errors="coerce")
            out.append(
                {
                    "n": i,
                    "type": ctype,
                    "rated_kw": None if pd.isna(kw) else float(kw),
                    "status": row.get(cols.get("Status", ""), None),
                    "charge_method": row.get(cols.get("ChargeMethod", ""), None),
                }
            )
        return out

    conns = df.apply(connectors, axis=1)
    df["n_connectors"] = conns.map(len)
    df["max_rated_kw"] = conns.map(
        lambda cs: max([c["rated_kw"] for c in cs if c["rated_kw"] is not None], default=np.nan)
    )
    df["connector_types"] = conns.map(lambda cs: json.dumps(sorted({c["type"] for c in cs})))
    df["connectors_json"] = conns.map(json.dumps)
    df["snapshot_date"] = pd.Timestamp(datetime.strptime(NCR_WAYBACK_TS[:8], "%Y%m%d"))
    df["source"] = "ncr_wayback_2021"
    keep = [c for c in NCR_BASE_COLS if c in df.columns] + [
        "n_connectors",
        "max_rated_kw",
        "connector_types",
        "connectors_json",
        "snapshot_date",
        "source",
    ]
    g = gpd.GeoDataFrame(df[keep], geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs=WGS84)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    g.to_parquet(NCR_OUT, index=False)
    _log(f"NCR: {n_uk} UK rows parsed, {len(g)} inside the London bbox -> {NCR_OUT}")
    return NCR_OUT


# --------------------------------------------------------------------------------------------------
# Verification / quality report
# --------------------------------------------------------------------------------------------------
LAMPPOST_RE = re.compile(
    r"ubitricity|char\.?gy|connected kerb|shell recharge|trojan|surecharge|siemens|city ev", re.I
)


def _describe(name: str, path: Path) -> gpd.GeoDataFrame | pd.DataFrame | None:
    if not path.exists():
        print(f"\n== {name}: MISSING ({path})")
        return None
    df = (
        gpd.read_parquet(path)
        if name not in ("dft_evci_london_la", "dft_evci_uk_power_band", "ocm_london")
        else pd.read_parquet(path)
    )
    print(f"\n== {name}: {path.relative_to(RAW.parent.parent)}  ({path.stat().st_size / 1e3:.0f} kB)")
    print(f"   rows={len(df)}  cols={df.shape[1]}")
    if isinstance(df, gpd.GeoDataFrame):
        print(f"   crs={df.crs.to_string()}  bbox(w,s,e,n)={np.round(df.total_bounds, 4).tolist()}")
    print(f"   columns={list(df.columns)}")
    return df


def _near_dupes(
    a: gpd.GeoDataFrame, b: gpd.GeoDataFrame, label_a: str, label_b: str, dist_m: float = 50
) -> None:
    a_m, b_m = (
        a.to_crs(BNG)[["geometry"]].reset_index(drop=True),
        b.to_crs(BNG)[["geometry"]].reset_index(drop=True),
    )
    j = gpd.sjoin_nearest(a_m, b_m, how="inner", max_distance=dist_m, distance_col="d")
    print(
        f"   {label_a} points with a {label_b} point within {dist_m:.0f} m: "
        f"{j.index.nunique()}/{len(a_m)} ({j.index.nunique() / len(a_m):.1%}); "
        f"{label_b} points matched: {j['index_right'].nunique()}/{len(b_m)} ({j['index_right'].nunique() / len(b_m):.1%})"
    )


def report() -> None:
    """Print row counts, CRS, bbox, columns and a short quality note for every output."""
    print("\n" + "=" * 100 + "\nQUALITY REPORT\n" + "=" * 100)
    osm = _describe("osm_charging_stations", OSM_OUT)
    ocm = _describe("ocm_london", OCM_OUT)
    dft = _describe("dft_evci_london_la", DFT_OUT)
    _describe("dft_evci_uk_power_band", DFT_UK_POWER_OUT)
    lds = _describe("london_datastore_rapid_charging_points_2019", LDS_OUT)
    ncr = _describe("ncr_archive_london_2021", NCR_OUT)
    if OCM_STATUS.exists():
        print(f"\n== OCM API probe: {json.loads(OCM_STATUS.read_text())}")

    if osm is not None:
        print("\n-- OSM quality")
        print(f"   node/way split: {osm['osm_type'].value_counts().to_dict()}")
        print(f"   share with power info (max_power_kw): {osm['max_power_kw'].notna().mean():.1%}")
        has_op = osm[["operator", "brand", "network"]].notna().any(axis=1)
        print(
            f"   share with operator|brand|network: {has_op.mean():.1%}  (operator alone {osm['operator'].notna().mean():.1%})"
        )
        print(
            f"   share with capacity: {osm['capacity_int'].notna().mean():.1%}; with any socket:* count: {osm['n_sockets'].notna().mean():.1%}"
        )
        print(
            f"   share with fee tag: {osm['fee'].notna().mean():.1%}; access tag: {osm['access'].notna().mean():.1%}"
        )
        pw = osm["max_power_kw"].dropna()
        if len(pw):
            bands = pd.cut(
                pw,
                [0, 7.9, 21.9, 49.9, 149.9, 1000],
                labels=["<8 kW", "8-22 kW", "22-50 kW", "50-150 kW", "150+ kW"],
            )
            print(f"   power bands (where known): {bands.value_counts().sort_index().to_dict()}")
        op = osm["operator"].fillna(osm["brand"]).fillna(osm["network"])
        print(f"   top operators/brands: {op.value_counts().head(12).to_dict()}")
        lamp = op.fillna("").str.contains(LAMPPOST_RE)
        print(
            f"   on-street/lamp-post style operators (ubitricity, char.gy, Connected Kerb, Shell Recharge, Trojan, SureCharge, Siemens, City EV): "
            f"{lamp.sum()} features = {lamp.mean():.1%} of all, {lamp.sum() / has_op.sum():.1%} of those with an operator"
        )
        cap = osm["capacity_int"].fillna(osm["n_sockets"])
        print(
            f"   sum of capacity/sockets where known: {int(cap.sum())} over {cap.notna().sum()} features (median {cap.median()})"
        )
        dup = osm.round({"lat": 5, "lon": 5}).duplicated(["lat", "lon"]).sum()
        print(f"   exact coordinate duplicates within OSM: {dup}")

    if osm is not None and ocm is not None:
        print("\n-- OSM vs OCM proximity")
        ocm_g = gpd.GeoDataFrame(ocm, geometry=gpd.points_from_xy(ocm["lon"], ocm["lat"]), crs=WGS84)
        _near_dupes(osm, ocm_g, "OSM", "OCM")
    elif osm is not None:
        print(
            "\n-- OSM vs OCM proximity: OCM not available (API key required); using archived NCR 2021 and TfL rapid 2019 instead"
        )
        if ncr is not None:
            _near_dupes(osm, ncr, "OSM(2026)", "NCR(2021)")
        if lds is not None:
            _near_dupes(osm, lds, "OSM(2026)", "TfL-rapid(2019)")
            rapid = osm[osm["max_power_kw"] >= 50]
            if len(rapid):
                _near_dupes(lds, rapid, "TfL-rapid(2019)", "OSM>=50kW(2026)")

    if ncr is not None:
        print("\n-- NCR 2021 (London bbox) quality")
        print(f"   status: {ncr['chargeDeviceStatus'].value_counts().to_dict()}")
        print(
            f"   share with rated kW: {ncr['max_rated_kw'].notna().mean():.1%}; share <=7.4 kW: {(ncr['max_rated_kw'] <= 7.4).mean():.1%}; share >=50 kW: {(ncr['max_rated_kw'] >= 50).mean():.1%}"
        )
        ctrl = ncr["deviceControllerName"].fillna(ncr["deviceNetworks"])
        print(f"   top controllers: {ctrl.value_counts().head(8).to_dict()}")
        print(f"   lamp-post style controllers share: {ctrl.fillna('').str.contains(LAMPPOST_RE).mean():.1%}")

    if dft is not None:
        print("\n-- DfT EVCI, 1 July 2026 (Zapmap-sourced official statistics)")
        cur = dft[
            (dft["source_table"] == "EVCI0102e")
            & (dft["date"] == dft[dft["source_table"] == "EVCI0102e"]["date"].max())
        ]
        wide = cur.pivot_table(index="area_name", columns="measure", values="value")
        wide["rapid_share"] = wide["50kW+ EV chargers"] / wide["EV chargers"]
        print(
            f"   boroughs covered: {len(wide)}; London total (sum of boroughs): {int(wide['EV chargers'].sum())} chargers, "
            f"{int(wide['50kW+ EV chargers'].sum())} at 50kW+"
        )
        print(
            "   top 5 boroughs by chargers:\n"
            + wide["EV chargers"].sort_values(ascending=False).head(5).to_string()
        )
        print(
            "   top 5 boroughs by 50kW+ chargers:\n"
            + wide["50kW+ EV chargers"].sort_values(ascending=False).head(5).to_string()
        )
        print(
            "   top 5 / bottom 3 boroughs by chargers per 100k:\n"
            + wide["EV chargers per 100k"].sort_values(ascending=False).head(5).round(0).to_string()
            + "\n   ...\n"
            + wide["EV chargers per 100k"].sort_values().head(3).round(0).to_string()
        )
        print(
            "   highest / lowest 50kW+ share:\n"
            + wide["rapid_share"].sort_values(ascending=False).head(3).round(3).to_string()
            + "\n   ...\n"
            + wide["rapid_share"].sort_values().head(3).round(3).to_string()
        )
        reg = dft[(dft["source_table"] == "EVCI0101e")]
        reg = reg[reg["date"] == reg["date"].max()].pivot_table(
            index="area_name", columns="measure", values="value"
        )
        print("   London vs England vs UK (latest quarter):\n" + reg.round(1).to_string())
        hist = dft[(dft["source_table"] == "EVCI9001_1a") & (dft["area_code"] == LONDON_REGION_CODE)].dropna(
            subset=["value"]
        )
        if len(hist):
            first, last = hist.sort_values("date").iloc[[0, -1]].itertuples()
            print(
                f"   London devices history: {int(first.value)} ({first.period_label}) -> {int(last.value)} ({last.period_label})"
            )


def main() -> None:
    """Run every fetcher (idempotent), then print the quality report."""
    ensure_dirs()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: dict[str, str] = {}
    for fn in (fetch_osm, fetch_ocm, fetch_dft_evci, fetch_london_datastore, fetch_ncr_archive):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures[fn.__name__] = f"{type(exc).__name__}: {exc}"
            _log(f"{fn.__name__} FAILED: {failures[fn.__name__]}")
    report()
    if failures:
        print(f"\nFAILED STEPS: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
