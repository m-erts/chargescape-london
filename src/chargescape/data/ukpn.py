"""UK Power Networks open data: Optimise Prime, Low Carbon London EV trials, DFES + network headroom.

Sources
-------
1. UKPN Open Data Portal (Opendatasoft, CC BY 4.0 unless stated):
   https://ukpowernetworks.opendatasoft.com/api/explore/v2.1/catalog/datasets
   * Anonymous access: catalog + /exports/{parquet,csv} work; the /records API returns 403 and
     export-time `where`/`refine` filters silently return 0 rows -> we download full exports and
     filter client-side.  Geo columns arrive as WKB bytes (EPSG:4326).
   * `ukpn-optimise-prime` has 0 records on the portal; the data lives in an Azure Blob container
     whose public read/list SAS URL is printed in the dataset description.  We parse it at run
     time (it rotates yearly) and pull the small tables in full plus one partition of each large
     table (container total = 164 GB / 1,027 files).
2. London Datastore (GLA), dataset 2y5k8 "Low Carbon London Electric Vehicle Load Profiles"
   (author UK Power Networks, CC BY): residential + commercial 10-min meter readings 2013-14,
   public charge-point sessions from four suppliers.

Outputs
-------
data/raw/ukpn/catalog/*.json                     catalog + per-dataset metadata snapshots
data/raw/ukpn/ods/{dataset_id}.parquet           full ODS parquet exports (as served)
data/raw/ukpn/optimise_prime/**                  blob listing, guidance docs, downloaded CSVs
data/raw/ukpn/low_carbon_london/**               zip + extracted trial files
data/interim/ukpn/*.parquet                      tidy (Geo)Parquet, London flag/filter applied
data/raw/ukpn/dfes/*.xlsx  -> data/interim/ukpn/dfes2026_*.parquet   DFES 2026 LSOA workbooks (DSO site)
data/raw/ukpn/headroom/*.geojson -> data/interim/ukpn/headroom_*.parquet  primary substation headroom (GLA LAEP hub ArcGIS)
data/interim/ukpn/optimise_prime/*.parquet       + _schema_report.json
data/interim/ukpn/low_carbon_london/*.parquet    + _schema_report.json

Run:  PYTHONPATH=src python -m chargescape.data.ukpn            (everything)
      PYTHONPATH=src python -m chargescape.data.ukpn ods|dfes|headroom|op|lcl (one part)
Idempotent: every download is skipped when the file exists; interim files are rebuilt from raw.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd
import requests
import shapely

from chargescape.utils.http import UA, download, get_json
from chargescape.utils.paths import INTERIM, RAW

ODS = "https://ukpowernetworks.opendatasoft.com/api/explore/v2.1/catalog/datasets"
RAW_UKPN = RAW / "ukpn"
RAW_CAT = RAW_UKPN / "catalog"
RAW_ODS = RAW_UKPN / "ods"
RAW_OP = RAW_UKPN / "optimise_prime"
RAW_LCL = RAW_UKPN / "low_carbon_london"
OUT = INTERIM / "ukpn"
OUT_OP = OUT / "optimise_prime"
OUT_LCL = OUT / "low_carbon_london"

# dataset_id -> (interim short name, column used to flag London, rule)
#   rule "E09"  : column holds an ONS LAD code, London == startswith("E09")
#   rule "LPN"  : column holds licence area / DNO, London == value contains "LPN" or "London"
#   rule None   : no London flag (small reference tables)
ODS_DATASETS: dict[str, tuple[str, str | None, str | None]] = {
    "ukpn-dfes-network-headroom-report": ("dfes_nshr_substation_headroom", "licencearea", "LPN"),
    "ukpn-dfes-by-local-authorities": ("dfes_lad_forecasts", "lad22cd", "E09"),
    "ukpn-low-carbon-technologies-lsoa": ("lct_connected_by_lsoa", "local_authority_code", "E09"),
    "ukpn-low-carbon-technologies-secondary": ("lct_connected_by_secondary", "licencearea", "LPN"),
    "low-carbon-technologies": ("lct_connected_by_primary", "licencearea", "LPN"),
    "ukpn-secondary-sites": ("secondary_sites", "localauthoritycode", "E09"),
    "ukpn-secondary-site-utilisation": ("secondary_site_utilisation", None, None),
    "ukpn_secondary_postcode_area": ("secondary_supply_areas", "dno", "LPN"),
    "ukpn_primary_postcode_area": ("primary_supply_areas_headroom", "licencearea", "LPN"),
    "ukpn-capacity-heatmap": ("ltds_capacity_heatmap", "area", "LPN"),
    "ukpn-primary-transformers": ("primary_transformers", "dno", "LPN"),
    "ukpn-grid-supply-points-overview": ("gsp_overview", "dno", "LPN"),
    "ukpn-standard-profiles-electricity-demand": ("standard_demand_profiles", None, None),
    "ukpn-local-authorities": ("local_authorities", "lad24cd", "E09"),
    "ukpn-lpn-area-operational-boundaries": ("lpn_operational_boundaries", None, None),
}
# very large geo tables: keep only London rows in interim (raw export is kept in full)
LONDON_ONLY = {
    "ukpn_secondary_postcode_area",
    "ukpn-secondary-sites",
    "ukpn-low-carbon-technologies-secondary",
}

GEO_COLS = ("geo_shape", "geometry_wkt_epsg4326")
POINT_COLS = ("geo_point_2d", "geo_point", "spatial_coordinates", "geopoint")


# ============================================================================ helpers
def _log(msg: str) -> None:
    print(f"[ukpn] {msg}", flush=True)


def _stream(url: str, dest: Path, *, timeout: int = 900) -> Path:
    """download() wrapper that reports size/time for big exports."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    t = time.time()
    download(url, dest, timeout=timeout)
    _log(f"downloaded {dest.relative_to(RAW)} ({dest.stat().st_size / 1e6:.1f} MB, {time.time() - t:.0f}s)")
    return dest


def dataset_meta(ds_id: str) -> dict:
    RAW_CAT.mkdir(parents=True, exist_ok=True)
    p = RAW_CAT / f"{ds_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    r = requests.get(f"{ODS}/{ds_id}", headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    p.write_text(json.dumps(r.json(), indent=1))
    return r.json()


def snapshot_catalog() -> list[dict]:
    """Full catalog listing (138 datasets on 2026-09-10) -> catalog_full.json."""
    p = RAW_CAT / "catalog_full.json"
    if p.exists():
        return json.loads(p.read_text())
    allds, off = [], 0
    while True:
        j = get_json(ODS, {"limit": 100, "offset": off})
        allds += j["results"]
        off += 100
        if off >= j["total_count"]:
            break
    RAW_CAT.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(allds))
    return allds


def _wkb_to_geoseries(col: pd.Series):
    import geopandas as gpd

    vals = col.where(col.notna(), None)
    geoms = [shapely.from_wkb(v) if isinstance(v, bytes | bytearray) else None for v in vals]
    return gpd.GeoSeries(geoms, index=col.index, crs="EPSG:4326")


def london_flag(df: pd.DataFrame, col: str | None, rule: str | None) -> pd.Series:
    if col is None or col not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="boolean")
    s = df[col].astype("string")
    if rule == "E09":
        return s.str.startswith("E09").fillna(False).astype("boolean")
    return s.str.upper().str.contains("LPN|LONDON", regex=True).fillna(False).astype("boolean")


# ============================================================================ A3. ODS datasets
def build_ods() -> dict[str, dict]:
    """Download the parquet export of each dataset and write tidy (Geo)Parquet to data/interim/ukpn."""
    import geopandas as gpd

    OUT.mkdir(parents=True, exist_ok=True)
    RAW_ODS.mkdir(parents=True, exist_ok=True)
    report = {}
    for ds_id, (short, lcol, rule) in ODS_DATASETS.items():
        full = dataset_meta(ds_id)
        meta = full["metas"]["default"]
        base_rep = {
            "title": meta.get("title"),
            "licence": meta.get("license"),
            "modified": meta.get("modified"),
            "records_portal": meta.get("records_count"),
            "data_visible_anonymous": full.get("data_visible"),
        }
        if full.get("data_visible") is False:
            # Portal setting: metadata public, data only for signed-in users. Anonymous /records -> 403,
            # anonymous exports -> header-only files. We do not register accounts, so we stop here.
            report[ds_id] = {**base_rep, "status": "registration required (data_visible=false)"}
            _log(f"{short:34s} REGISTRATION REQUIRED - data_visible=false on portal; skipped")
            (RAW_ODS / f"{ds_id}.parquet").unlink(missing_ok=True)  # drop any header-only stub
            (OUT / f"{short}.parquet").unlink(missing_ok=True)
            continue
        raw_p = _stream(f"{ODS}/{ds_id}/exports/parquet", RAW_ODS / f"{ds_id}.parquet")
        df = pd.read_parquet(raw_p)
        n_raw = len(df)
        df["is_london"] = london_flag(df, lcol, rule)
        if ds_id in LONDON_ONLY:
            df = df[df.is_london.fillna(False).astype(bool)].copy()
        # geometry: polygon/line WKB -> geometry ; point WKB -> lon/lat (+ geometry if no shape col)
        geom = None
        for c in GEO_COLS:
            if c in df.columns:
                geom = _wkb_to_geoseries(df.pop(c))
                break
        for c in POINT_COLS:
            if c in df.columns and df[c].map(lambda v: isinstance(v, bytes | bytearray)).any():
                pts = _wkb_to_geoseries(df.pop(c))
                df["lon"] = pts.x.astype("float64")
                df["lat"] = pts.y.astype("float64")
                if geom is None:
                    geom = pts
                break
        if "year" in df.columns and str(df["year"].dtype).startswith("datetime"):
            df["year"] = df["year"].dt.year.astype("Int16")
        out_p = OUT / f"{short}.parquet"
        if geom is not None:
            gdf = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
            gdf.to_parquet(out_p, index=False)
        else:
            df.to_parquet(out_p, index=False)
        n_ldn = int(df.is_london.fillna(False).astype(bool).sum()) if lcol else None
        report[ds_id] = {
            **base_rep,
            "status": "downloaded",
            "rows_raw_export": n_raw,
            "rows_interim": int(len(df)),
            "rows_london": n_ldn,
            "interim": str(out_p.relative_to(INTERIM)),
            "size_mb": round(out_p.stat().st_size / 1e6, 2),
            "columns": list(df.columns) + (["geometry"] if geom is not None else []),
        }
        _log(
            f"{short:34s} raw={n_raw:>8,} interim={len(df):>8,} london={n_ldn} -> {out_p.name} ({report[ds_id]['size_mb']} MB)"
        )
    (OUT / "_ods_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# ============================================================================ A1. Optimise Prime
OP_DATASET = "ukpn-optimise-prime"
OP_CONTAINER_RE = re.compile(r"(https://[a-z0-9]+\.blob\.core\.windows\.net/optimiseprime)\?(sv=[^\s<\"']+)")

# tables downloaded in full (all partitions) - everything under ~100 MB per table
OP_FULL_PREFIXES = (
    "WS1/Table 06",
    "WS1/Table 8",
    "WS2/Table 10",
    "WS2/Table 11",
    "WS2/Table 12",
    "WS2/Table 13",
    "WS2/Table 14",
    "WS2/Table 20",
    "WS2/Table 24",
    "WS2/Table 25",
    "WS2/Table 26",
    "WS2/Table 27",
    "WS2/Table 28",
    "WS2/Table 29",
    "WS2/Table 30",
    "WS2/Table 31",
    "WS2/Table 32",
    "WS3/Table 33",
)
# large tables (>1 GB each): one partition inside the core trial period (Jul-2021..Jun-2022)
OP_SAMPLE_FILES = (
    "bg_trips_202110.csv",  # WS1 Table 07  (50 monthly files, 10.9 GB)
    "brand_a_charging_202110.csv",  # WS2 Table 15  (25 files, 2.0 GB)
    "brand_a_consumption_202110.csv",  # WS2 Table 15  (25 files, 0.9 GB)
    "brand_b_measures_202110.csv",  # WS2 Table 16/17 (22 files, 3.7 GB)
    "brand_c_ev_202111.csv",  # WS2 Table 18  (7 files, 0.3 GB) - no Oct-21 file
    "building_load_measures_202110.csv",  # WS2 Table 19  (25 files, 5.0 GB)
    "nortech_ihost_measurements_20211013.csv",  # WS2 Table 21/22 (733 daily files, 133.5 GB)
)
OP_SAMPLE_MAX_MB = 600  # anything bigger under Table 23 (profiled_connections) is skipped


def op_container() -> tuple[str, str]:
    """Return (account_url, sas_query) parsed from the public dataset description."""
    desc = dataset_meta(OP_DATASET)["metas"]["default"].get("description") or ""
    m = OP_CONTAINER_RE.search(html.unescape(desc))
    if not m:
        raise RuntimeError("Optimise Prime SAS URL not found in dataset description - access method changed?")
    return m.group(1), m.group(2)


def op_list_blobs(force: bool = False) -> list[dict]:
    RAW_OP.mkdir(parents=True, exist_ok=True)
    p = RAW_OP / "_blob_listing.json"
    if p.exists() and not force:
        return json.loads(p.read_text())
    acct, sas = op_container()
    blobs, marker = [], None
    while True:
        url = f"{acct}?restype=container&comp=list&{sas}" + (f"&marker={marker}" if marker else "")
        r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for b in root.iter("Blob"):
            pr = b.find("Properties")
            blobs.append(
                {
                    "name": b.findtext("Name"),
                    "size": int(pr.findtext("Content-Length") or 0),
                    "modified": pr.findtext("Last-Modified"),
                    "content_type": pr.findtext("Content-Type"),
                }
            )
        marker = root.findtext("NextMarker")
        if not marker:
            break
    p.write_text(json.dumps(blobs, indent=1))
    return blobs


def op_download_attachments() -> None:
    d = dataset_meta(OP_DATASET)
    for a in d.get("attachments") or []:
        name = a["title"].replace(" ", "_")
        if name.endswith(".png"):
            continue
        _stream(a["url"], RAW_OP / "docs" / name)


def op_select(blobs: list[dict]) -> list[dict]:
    sel = []
    for b in blobs:
        if b["size"] == 0:
            continue
        fn = b["name"].rsplit("/", 1)[-1]
        if b["name"].startswith(OP_FULL_PREFIXES) or fn in OP_SAMPLE_FILES:
            sel.append(b)
        elif b["name"].startswith("WS2/Table 23") and b["size"] < 5e6:  # small config partitions only
            sel.append(b)
    return sel


def op_download() -> list[Path]:
    acct, sas = op_container()
    blobs = op_list_blobs()
    sel = op_select(blobs)
    total = sum(b["size"] for b in sel) / 1e9
    _log(
        f"Optimise Prime: container has {len([b for b in blobs if b['size']])} files / "
        f"{sum(b['size'] for b in blobs) / 1e9:.1f} GB; selecting {len(sel)} files / {total:.2f} GB"
    )
    paths = []
    for b in sel:
        dest = RAW_OP / b["name"]
        url = f"{acct}/{urllib.parse.quote(b['name'])}?{sas}"
        paths.append(_stream(url, dest, timeout=1800))
    return paths


def _read_op_csv(p: Path, **kw) -> pd.DataFrame:
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        head = f.readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    return pd.read_csv(p, sep=sep, low_memory=False, encoding="utf-8-sig", **kw)


def _parse_kafka_table(paths: list[Path]) -> pd.DataFrame:
    """Tables 10-14/23-26 are Kafka-style change logs: offset;timestamp;key;message(JSON).
    Return one row per message with the JSON flattened, ordered by timestamp."""
    rows = []
    for p in sorted(paths):
        df = _read_op_csv(p)
        for _, r in df.iterrows():
            try:
                msg = json.loads(r["message"])
            except Exception:  # noqa: BLE001
                msg = {"_raw": r["message"]}
            rec = {
                "_offset": r["offset"],
                "_ts": pd.to_datetime(r["timestamp"], unit="ms", utc=True),
                "_key": r["key"],
                "_file": p.name,
            }
            rec.update({k: (json.dumps(v) if isinstance(v, dict | list) else v) for k, v in msg.items()})
            rows.append(rec)
    out = pd.DataFrame(rows)
    return out.sort_values("_ts").reset_index(drop=True) if len(out) else out


def _latest_state(log: pd.DataFrame) -> pd.DataFrame:
    if not len(log):
        return log
    last = log.groupby("_key", sort=False).tail(1)
    if "IsDeleted" in last.columns:
        last = last[last["IsDeleted"].astype(str).str.lower() != "true"]
    return last.reset_index(drop=True)


def _ts_span(s: pd.Series) -> tuple[str | None, str | None]:
    t = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
    return (str(t.min()), str(t.max())) if t.notna().any() else (None, None)


def _profile(df: pd.DataFrame, name: str, source_files: list[str], full: bool) -> dict:
    """Schema profile used by the report: dtypes, time span, id cardinalities, key numeric stats."""
    prof = {
        "table": name,
        "source_files": source_files,
        "complete_table": full,
        "rows": int(len(df)),
        "columns": {c: str(t) for c, t in df.dtypes.items()},
        "time_span": {},
        "cardinality": {},
        "numeric": {},
    }
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in ("time", "date", "utc", "_ts")) and df[c].dtype != bool:
            lo, hi = _ts_span(df[c].astype(str).head(2_000_000))
            if lo:
                prof["time_span"][c] = [lo, hi]
        if any(k in lc for k in ("id", "serial", "device", "charger", "vehicle", "depot", "borough", "tag")):
            prof["cardinality"][c] = int(df[c].nunique())
        if pd.api.types.is_numeric_dtype(df[c]) and any(
            k in lc
            for k in ("kwh", "kw", "minutes", "miles", "power", "energy", "wh", "value", "soc", "level")
        ):
            d = df[c].dropna()
            if len(d):
                prof["numeric"][c] = {
                    "n": int(len(d)),
                    "mean": float(d.mean()),
                    "p05": float(d.quantile(0.05)),
                    "p50": float(d.median()),
                    "p95": float(d.quantile(0.95)),
                    "max": float(d.max()),
                }
    return prof


def build_optimise_prime() -> dict:
    OUT_OP.mkdir(parents=True, exist_ok=True)
    op_download_attachments()
    paths = op_download()
    by_table: dict[str, list[Path]] = {}
    for p in paths:
        parts = p.relative_to(RAW_OP).parts
        if len(parts) >= 3:  # WS?/Table ../file
            by_table.setdefault("/".join(parts[:2]), []).append(p)
    blobs = op_list_blobs()
    n_all: dict[str, int] = {}
    for b in blobs:
        if b["size"] and b["name"].endswith(".csv"):
            k = "/".join(b["name"].split("/")[:2])
            n_all[k] = n_all.get(k, 0) + 1
    report: dict[str, dict] = {
        "container": {"files": len([b for b in blobs if b["size"]]), "bytes": sum(b["size"] for b in blobs)},
        "tables": {},
    }

    def emit(df: pd.DataFrame, short: str, table: str, files: list[Path]) -> None:
        full = len([f for f in files if f.suffix == ".csv"]) >= n_all.get(table, 0)
        p = OUT_OP / f"{short}.parquet"
        df.to_parquet(p, index=False)
        prof = _profile(df, short, [f.name for f in files], full)
        prof["interim"] = str(p.relative_to(INTERIM))
        prof["source_table"] = table
        report["tables"][short] = prof
        _log(f"OP {short:32s} rows={len(df):>10,} cols={df.shape[1]:>3} full_table={full} <- {table}")

    for table, files in sorted(by_table.items()):
        csvs = sorted(f for f in files if f.suffix == ".csv")
        if not csvs:
            continue
        key = table.split("–")[-1].strip().lower().replace(" ", "_")
        if table.startswith(
            (
                "WS2/Table 10",
                "WS2/Table 11",
                "WS2/Table 12",
                "WS2/Table 13",
                "WS2/Table 14",
                "WS2/Table 23",
                "WS2/Table 24",
                "WS2/Table 25",
                "WS2/Table 26",
            )
        ):
            log = _parse_kafka_table(csvs)
            emit(log, f"assets_log_{key}" if table < "WS2/Table 23" else f"trial_config_{key}", table, csvs)
            if table < "WS2/Table 23":
                emit(_latest_state(log), f"assets_{key}", table, csvs)
            continue
        frames = []
        for f in csvs:
            d = _read_op_csv(f)
            d["_file"] = f.name
            frames.append(d)
        df = pd.concat(frames, ignore_index=True)
        # light typing for the tables that matter most
        if key == "bg-fleet-charging":
            for c in ("start_date_time", "end_date_time"):
                df[c] = pd.to_datetime(df[c], format="%Y/%m/%d %H:%M:%S.%f", errors="coerce")
            df = df.drop_duplicates(["charger_id", "transaction_id", "start_date_time"])
            df["total_kwh"] = pd.to_numeric(df["total_kwh"], errors="coerce")
            # source quirks: a handful of 2014-dated rows, negative/absurd plug durations, >100 kWh
            # "sessions" (Vivaro-e battery is 50/75 kWh). Keep raw values, expose a validity flag.
            df["is_valid"] = (
                (df.start_date_time >= "2020-06-01")
                & df.total_kwh.between(0, 100)
                & (df.plug_duration_minutes.isna() | df.plug_duration_minutes.between(0, 7 * 24 * 60))
            )
        elif key == "load_profile_data_table":
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d/%m/%Y %H:%M", errors="coerce")
        elif key == "depot_load_data_table":
            df["ev_load_timestamp"] = pd.to_datetime(df["ev_load_timestamp"], errors="coerce", utc=True)
        elif key == "bg-trips":
            for c in ("start_timestamp_utc", "end_timestamp_utc"):
                df[c] = pd.to_datetime(df[c], format="%Y/%m/%d %H:%M:%S.%f", errors="coerce")
            df["start_area"] = df["start_post_code"].astype(str).str.extract(r"^([A-Z]{1,2})")[0]
        elif key == "aggregated_shift_telematics_data":
            for c in ("start_timestamp_utc", "end_timestamp_utc"):
                df[c] = pd.to_datetime(df[c], dayfirst=True, errors="coerce")
        short = {
            "bg-fleet-charging": "ws1_bg_home_charging_sessions",
            "bg-trips": "ws1_bg_trips_sample",
            "aggregated_shift_telematics_data": "ws1_bg_shift_telematics",
            "network_impact_by_borough": "ws3_phv_network_impact_by_borough",
            "load_profile_data_table": "ws2_depot_hourly_load_profiles",
            "depot_load_data_table": "ws2_depot_load",
            "ev_details_by_site": "ws2_ev_details_by_site",
            "cp_count": "ws2_cp_counts",
            "enacted_flexibility_product_a": "ws2_enacted_flex_product_a",
            "enacted_flexibility_product_b": "ws2_enacted_flex_product_b",
            "building-catalog": "ws2_building_catalog",
            "brand-a-charging": "ws2_telematics_brand_a_charging_sample",
            "brand-a-consumption": "ws2_telematics_brand_a_consumption_sample",
            "brand-b-measures": "ws2_telematics_brand_b_measures_sample",
            "brand-c-ev": "ws2_telematics_brand_c_sample",
            "building-load-measures": "ws2_building_load_1min_sample",
            "nortech-ihost-measurements": "ws2_chargepoint_measurements_sample",
        }.get(key, key.replace("-", "_"))
        emit(df, short, table, csvs)
    # readme files shipped with tables 27-32 and WS3
    notes = {}
    for p in RAW_OP.rglob("*"):
        if p.suffix.lower() in (".md", ".txt") and p.stat().st_size < 200_000:
            notes[str(p.relative_to(RAW_OP))] = p.read_text(errors="replace")
    report["readmes"] = notes
    (OUT_OP / "_schema_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# ============================================================================ A2. Low Carbon London
LCL_ZIP_URL = (
    "https://data.london.gov.uk/download/2y5k8/c869f8ac-33d3-4cf9-bf28-d89c61bbc7a2/EV%20Load%20Profiles.zip"
)
LCL_COLMAP = {
    "SerialNo": "meter_serial",
    "ReadingDate": "reading_time",
    "Import Wh Total": "import_kwh",
    "Export Wh Total": "export_kwh",
    "Current Main Maximum": "current_max_a",
    "Current Main Minimum": "current_min_a",
    "Current Main Avg": "current_avg_a",
    "Voltage Total": "voltage_v",
    "Active Power Total (Watts)": "active_power_w",
    "Apparant Power Total (VA)": "apparent_power_va",
    "Reactive Power Total (vars)": "reactive_power_var",
    "Q1 Wh Total": "q1_kwh",
    "Q2 Wh Total": "q2_kwh",
    "Q3 Wh Total": "q3_kwh",
    "Q4 Wh Total": "q4_kwh",
}


def _extract_all(zp: Path, dest: Path) -> None:
    """Extract a zip and any nested zips (LCL ships 3 zips inside one)."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)
    for inner in list(dest.rglob("*.zip")):
        tgt = inner.with_suffix("")
        if not tgt.exists():
            with zipfile.ZipFile(inner) as z:
                z.extractall(tgt)


def _read_lcl_meter_csv(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p, skipinitialspace=True, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=LCL_COLMAP)
    keep = [c for c in LCL_COLMAP.values() if c in df.columns]
    df = df[keep].copy()
    df["meter_serial"] = df["meter_serial"].astype(str).str.strip()
    # "dd/mm/yyyy HH:MM:SS" and bare "dd/mm/yyyy " (== midnight)
    raw = df["reading_time"].astype(str).str.strip()
    ts = pd.to_datetime(raw, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    miss = ts.isna()
    if miss.any():
        ts[miss] = pd.to_datetime(raw[miss], format="%d/%m/%Y", errors="coerce")
    df["reading_time"] = ts
    for c in keep[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    return df


def build_low_carbon_london() -> dict:
    OUT_LCL.mkdir(parents=True, exist_ok=True)
    zp = _stream(LCL_ZIP_URL, RAW_LCL / "EV_Load_Profiles.zip", timeout=900)
    ex = RAW_LCL / "extracted"
    if not any(ex.rglob("*.csv")):
        _extract_all(zp, ex)
    report: dict[str, dict] = {}
    for trial in ("Residential", "Commercial"):
        csvs = sorted(p for p in ex.rglob(f"EV {trial} trials/**/*.csv"))
        frames = [_read_lcl_meter_csv(p) for p in csvs]
        df = (
            pd.concat(frames, ignore_index=True)
            .sort_values(["meter_serial", "reading_time"])
            .reset_index(drop=True)
        )
        p = OUT_LCL / f"lcl_ev_{trial.lower()}_10min.parquet"
        df.to_parquet(p, index=False)
        prof = _profile(df, p.stem, [c.name for c in csvs], True)
        prof["interim"] = str(p.relative_to(INTERIM))
        prof["meters"] = int(df.meter_serial.nunique())
        prof["time_span"]["reading_time"] = [str(df.reading_time.min()), str(df.reading_time.max())]
        report[p.stem] = prof
        _log(
            f"LCL {p.stem:28s} rows={len(df):>10,} meters={df.meter_serial.nunique()} span={df.reading_time.min():%Y-%m-%d}..{df.reading_time.max():%Y-%m-%d}"
        )
    # public charge point sessions (4 suppliers, one sheet each)
    xl = next(ex.rglob("CNO data.xlsx"))
    frames = []
    for sh in pd.ExcelFile(xl).sheet_names:
        d = pd.read_excel(xl, sheet_name=sh)
        d.columns = [str(c).strip() for c in d.columns]
        d["supplier"] = sh.strip()
        frames.append(d)
    pub = pd.concat(frames, ignore_index=True).rename(
        columns={
            "Charging Event": "event_id",
            "User ID": "user_id",
            "SL ID": "chargepoint_id",
            "Total kWh": "kwh",
            "Price": "price",
        }
    )
    pub["start_time"] = pd.to_datetime(
        pub["Start Date"].astype(str).str[:10] + " " + pub["Start Time"].astype(str), errors="coerce"
    )
    pub["end_time"] = pd.to_datetime(
        pub["End Date"].astype(str).str[:10] + " " + pub["End Time"].astype(str), errors="coerce"
    )
    pub["duration_min"] = (pub.end_time - pub.start_time).dt.total_seconds() / 60
    pub["kwh"] = pd.to_numeric(pub["kwh"], errors="coerce")
    for c in ("user_id", "chargepoint_id", "price"):
        pub[c] = pub[c].astype("string")
    pub = pub[
        [
            "supplier",
            "event_id",
            "user_id",
            "chargepoint_id",
            "start_time",
            "end_time",
            "duration_min",
            "kwh",
            "price",
        ]
    ]
    p = OUT_LCL / "lcl_ev_public_sessions.parquet"
    pub.to_parquet(p, index=False)
    prof = _profile(pub, p.stem, [xl.name], True)
    prof["interim"] = str(p.relative_to(INTERIM))
    prof["by_supplier"] = (
        pub.groupby("supplier")
        .agg(
            sessions=("event_id", "size"),
            users=("user_id", "nunique"),
            chargepoints=("chargepoint_id", "nunique"),
            kwh_median=("kwh", "median"),
            start=("start_time", "min"),
            end=("start_time", "max"),
        )
        .astype(str)
        .to_dict("index")
    )
    report[p.stem] = prof
    _log(
        f"LCL {p.stem:28s} rows={len(pub):>10,} users={pub.user_id.nunique()} cps={pub.chargepoint_id.nunique()}"
    )
    # commercial participants lookup
    part = next(ex.rglob("Commercial Trial participants.xlsx"))
    pt = pd.read_excel(part)
    pt.columns = [str(c).strip().lower().replace(" ", "_").replace(".", "") for c in pt.columns]
    pt = pt.loc[:, ~pt.columns.str.startswith("unnamed")]
    p = OUT_LCL / "lcl_commercial_participants.parquet"
    pt.to_parquet(p, index=False)
    report[p.stem] = {
        "rows": int(len(pt)),
        "columns": list(pt.columns),
        "interim": str(p.relative_to(INTERIM)),
    }
    report["_notes"] = {
        "survey_xls": [str(x.relative_to(RAW_LCL)) for x in ex.rglob("*.xls")],
        "survey_note": "legacy .xls survey workbooks left in raw (xlrd not installed); not needed for the demand model",
    }
    (OUT_LCL / "_schema_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# ============================================================================ A3b. DFES 2026 LSOA workbooks
# The portal copies of DFES need a login (data_visible=false).  UKPN's DSO site publishes the same
# 2026 DFES as open Excel workbooks (CC BY 4.0 per the workbook cover sheet), one per technology,
# at LSOA (2021) resolution for the whole UKPN area, pathways x 2024..2050.
DFES_BASE = "https://d1lf1oz5vvdb9r.cloudfront.net/app/uploads/2026/03/"
DFES_PAGE = "https://dso.ukpowernetworks.co.uk/distribution-future-energy-scenarios"
DFES_WORKBOOKS: dict[str, list[str]] = {
    "UKPN-electric-car-van-scenarios-LSOA-UPDATED.xlsx": ["cars", "vans"],
    "UKPN-electric-taxi-phv-scenarios-LSOA-UPDATED.xlsx": ["PHV", "Taxi"],
    "UKPN-electric-HGV-Bus-Coach-Minibus-scenarios-LSOA-UPDATED.xlsx": ["HGV", "Bus", "Coach", "Minibus"],
    "UKPN-domestic-connection-count-scenarios-LSOA-UPDATED.xlsx": ["Domestic connection counts"],
}
# LSOA -> licence area / LAD / GSP lookups used by UKPN's own DFES map (GitHub, MIT-licensed repo)
DFES_MAP_BASE = "https://raw.githubusercontent.com/UK-Power-Networks/DFES-visualisation/main/2026-DFES/data/"
DFES_MAPPINGS = ("lsoa2dno.json", "lsoa2lad-compact.json", "gsp2lsoa.json")
RAW_DFES = RAW_UKPN / "dfes"
DFES_COLS = {
    "LSOA21CD": "lsoa21cd",
    "LSOA21NM": "lsoa21nm",
    "MSOA21CD": "msoa21cd",
    "LAD22CD": "lad22cd",
    "LAD22NM": "lad22nm",
    "Proportion served by EPN": "share_epn",
    "Proportion served by LPN": "share_lpn",
    "Proportion served by SPN": "share_spn",
    "Majority Licence area": "licence_area",
    "Scenario World": "pathway",
    "Scenario": "scenario",
    "Parameter": "parameter",
    "Unit": "unit",
}


def build_dfes() -> dict:
    """DSO-site DFES 2026 workbooks -> London LSOA table (wide by year) + UKPN LAD aggregate."""
    OUT.mkdir(parents=True, exist_ok=True)
    for m in DFES_MAPPINGS:
        _stream(DFES_MAP_BASE + m, RAW_DFES / m)
    frames = []
    for wb, sheets in DFES_WORKBOOKS.items():
        p = _stream(DFES_BASE + wb, RAW_DFES / wb, timeout=900)
        xl = pd.ExcelFile(p)
        for sh in sheets:
            df = xl.parse(sh)
            df.columns = [str(c).strip() for c in df.columns]
            years = [c for c in df.columns if c.isdigit()]
            out = df[[c for c in DFES_COLS if c in df.columns]].rename(columns=DFES_COLS)
            for c in DFES_COLS.values():
                if c not in out.columns:
                    out[c] = pd.NA
            out["technology"] = sh.lower().replace(" ", "_")
            out["workbook"] = wb
            for y in years:
                out[f"y{y}"] = pd.to_numeric(df[y], errors="coerce").astype("float32")
            frames.append(out)
            _log(f"DFES {wb[5:45]:40s} sheet={sh:28s} rows={len(df):>7,} years={years[0]}-{years[-1]}")
    allx = pd.concat(frames, ignore_index=True)
    allx["is_london"] = allx.lad22cd.astype("string").str.startswith("E09").fillna(False).astype(bool)
    ycols = [c for c in allx.columns if c.startswith("y") and c[1:].isdigit()]
    ldn = allx[allx.is_london].drop(columns=["is_london"]).reset_index(drop=True)
    p_ldn = OUT / "dfes2026_lsoa_london_ev.parquet"
    ldn.to_parquet(p_ldn, index=False)
    keys = ["lad22cd", "lad22nm", "pathway", "scenario", "parameter", "unit", "technology"]
    lad = allx.groupby(keys, dropna=False)[ycols].sum(min_count=1).reset_index()
    lad["is_london"] = lad.lad22cd.astype("string").str.startswith("E09").fillna(False).astype(bool)
    p_lad = OUT / "dfes2026_lad_ukpn_ev.parquet"
    lad.to_parquet(p_lad, index=False)
    # LSOA -> licence area lookup (all three UKPN areas) from UKPN's own mapping
    l2d = json.loads((RAW_DFES / "lsoa2dno.json").read_text())
    look = pd.DataFrame(
        [(code, dno) for dno, codes in l2d.items() for code in codes], columns=["lsoa21cd", "licence_area"]
    )
    look.to_parquet(OUT / "dfes2026_lsoa_licence_area.parquet", index=False)
    # headline check: London BEV cars, ElectricEngagement pathway
    ee = ldn[(ldn.parameter == "BEV Cars") & (ldn.pathway == "ElectricEngagement")]
    head = {y: float(ee[f"y{y}"].sum()) for y in (2024, 2026, 2030, 2035, 2040, 2050) if f"y{y}" in ee}
    rep = {
        "source_page": DFES_PAGE,
        "workbooks": list(DFES_WORKBOOKS),
        "licence": "UK Power Networks Distribution Future Energy Scenarios (C) 2024 by UK Power Networks, CC BY 4.0 (workbook cover sheet)",
        "rows_all_ukpn": int(len(allx)),
        "lsoas_all_ukpn": int(allx.lsoa21cd.nunique()),
        "rows_london": int(len(ldn)),
        "lsoas_london": int(ldn.lsoa21cd.nunique()),
        "pathways": sorted(allx.pathway.dropna().unique().tolist()),
        "scenarios": sorted(allx.scenario.dropna().unique().tolist()),
        "parameters": sorted(allx.parameter.dropna().unique().tolist()),
        "technologies": sorted(allx.technology.unique().tolist()),
        "years": [int(ycols[0][1:]), int(ycols[-1][1:])],
        "london_bev_cars_electric_engagement": head,
        "outputs": {
            str(p_ldn.relative_to(INTERIM)): round(p_ldn.stat().st_size / 1e6, 2),
            str(p_lad.relative_to(INTERIM)): round(p_lad.stat().st_size / 1e6, 2),
        },
    }
    (OUT / "_dfes_report.json").write_text(json.dumps(rep, indent=1))
    _log(f"DFES London LSOAs={rep['lsoas_london']} rows={rep['rows_london']:,} | BEV cars (EE): {head}")
    return rep


# ============================================================================ A3c. Primary substation headroom (GLA LAEP hub)
# The portal's substation headroom tables need a login, but the GLA republishes UKPN's primary
# substation headroom for the London LAEP area as public ArcGIS feature services (CC BY 4.0, owner
# GLAGIS, "using UK Power Networks data").  We page through the REST API anonymously.
ARCGIS_ITEMS = "https://www.arcgis.com/sharing/rest/content/items/{item}?f=json"
HEADROOM_LAYERS: dict[str, tuple[str, str]] = {
    # short name: (ArcGIS item id, layer URL)
    "headroom_primary_areas_summer2026": (
        "8f79458dd7c04e09a534a900550f0de4",
        "https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/UKPN%20Primary%20Substation%20Distribution%20Areas%20(Summer%202026)/FeatureServer/0",
    ),
    "headroom_primary_areas_march2026": (
        "d68db93824a44ef9801806ce5b5a682c",
        "https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/UKPN%20Primary%20Substations%20Demand%20Headroom/FeatureServer/0",
    ),
    "headroom_primary_areas_baseline_dec2024": (
        "5ef3f8160bee40a5ac57d4c3fcee2bfb",
        "https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/Primary_Substation_Demand_Headroom/FeatureServer/0",
    ),
    "headroom_demand_forecast_nshr2023": (
        "383199f6296742a19150dc637d6854cd",
        "https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/UKPN_Demand_Headroom_Forecast/FeatureServer/0",
    ),
    "headroom_generation_forecast_nshr2023": (
        "316151597e034563a4bd7188aad1557d",
        "https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/UKPN_Generation_Headroom_Forecast/FeatureServer/0",
    ),
}
RAW_HEADROOM = RAW_UKPN / "headroom"


def _arcgis_geojson(layer_url: str, dest: Path, page: int = 1000) -> dict:
    """Page through an ArcGIS FeatureServer layer and cache the merged GeoJSON (EPSG:4326)."""
    if dest.exists() and dest.stat().st_size > 0:
        return json.loads(dest.read_text())
    feats, offset = [], 0
    while True:
        r = requests.get(
            f"{layer_url}/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "outSR": 4326,
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page,
            },
            headers={"User-Agent": UA},
            timeout=180,
        )
        r.raise_for_status()
        js = r.json()
        if "error" in js:
            raise RuntimeError(f"ArcGIS error for {layer_url}: {js['error']}")
        feats += js.get("features", [])
        if not js.get("properties", {}).get("exceededTransferLimit") and len(js.get("features", [])) < page:
            break
        offset += page
    out = {"type": "FeatureCollection", "features": feats}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out))
    return out


def build_headroom() -> dict:
    import geopandas as gpd

    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for short, (item, url) in HEADROOM_LAYERS.items():
        meta_p = RAW_HEADROOM / f"{short}.item.json"
        if not meta_p.exists():
            meta_p.parent.mkdir(parents=True, exist_ok=True)
            meta_p.write_text(
                json.dumps(
                    requests.get(
                        ARCGIS_ITEMS.format(item=item), headers={"User-Agent": UA}, timeout=60
                    ).json(),
                    indent=1,
                )
            )
        item_meta = json.loads(meta_p.read_text())
        gj = _arcgis_geojson(url, RAW_HEADROOM / f"{short}.geojson")
        gdf = gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4326")
        gdf.columns = [c.lower() for c in gdf.columns]
        dno_col = next((c for c in ("dno", "pn") if c in gdf.columns), None)
        if dno_col:
            gdf["is_lpn"] = gdf[dno_col].astype(str).str.upper().eq("LPN")
        p = OUT / f"{short}.parquet"
        gdf.to_parquet(p, index=False)
        lic = re.sub(r"<[^>]+>", " ", item_meta.get("licenseInfo") or "").strip()
        report[short] = {
            "title": item_meta.get("title"),
            "owner": item_meta.get("owner"),
            "item_id": item,
            "layer_url": url,
            "licence": lic[:120],
            "modified_ms": item_meta.get("modified"),
            "rows": int(len(gdf)),
            "lpn_rows": int(gdf["is_lpn"].sum()) if dno_col else None,
            "geometry": str(gdf.geom_type.mode().iat[0]) if len(gdf) else None,
            "columns": [c for c in gdf.columns if c != "geometry"],
            "interim": str(p.relative_to(INTERIM)),
            "size_mb": round(p.stat().st_size / 1e6, 2),
        }
        _log(
            f"HEADROOM {short:42s} rows={len(gdf):>5} lpn={report[short]['lpn_rows']} geom={report[short]['geometry']} -> {p.name}"
        )
    (OUT / "_headroom_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


# ============================================================================ main
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parts = set(argv) or {"ods", "dfes", "headroom", "op", "lcl"}
    OUT.mkdir(parents=True, exist_ok=True)
    cat = snapshot_catalog()
    _log(f"catalog snapshot: {len(cat)} datasets -> {RAW_CAT / 'catalog_full.json'}")
    if "ods" in parts:
        build_ods()
    if "dfes" in parts:
        build_dfes()
    if "headroom" in parts:
        build_headroom()
    if "op" in parts:
        build_optimise_prime()
    if "lcl" in parts:
        build_low_carbon_london()
    return 0


if __name__ == "__main__":
    sys.exit(main())
