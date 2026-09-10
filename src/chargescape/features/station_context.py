"""Station-level context features for the "utilisation transfer" experiment.

One row per charging station / site with *identical* OSM, road and population features for
  * four cities with open session logs (dundee, pkc, palo_alto, boulder) -> features + utilisation targets
  * the London charging sites in data/processed/charging_sites.parquet   -> features only (targets NaN)

Feature groups (radii in metres, computed in a local metric CRS: EPSG:27700 UK, 26910 Palo Alto, 26913 Boulder)
  poi_<group>_{300,800}      OSM POI counts by group (food, retail, hotel, leisure, parking, fuel, office,
                             health_edu, car); tag lists in POI_GROUPS, identical for every city
  parking_capacity_{300,800} summed `capacity` tag of the amenity=parking features in the radius (untagged -> 0)
  dist_motorway_m            distance to the nearest highway=motorway|trunk way
  dist_primary_m             distance to the nearest highway=primary|secondary way
  dist_rail_m                distance to the nearest railway=station|halt (London: TfL/NaPTAN rail stations)
  pop_1km                    WorldPop 2020 1 km "ppp_2020_1km_Aggregated" population inside a 1 km buffer:
                             rasterio.mask on the WGS84 buffer, pixel values weighted by the pixel area fraction
                             inside the buffer (pop_source = worldpop_ppp_2020_1km; fallback = OSM building
                             count within 1 km, pop_source = osm_buildings_1km)
  poi_edge_flag              True when the 800 m buffer leaves the area the POI table covers (London only)
  targets (4 cities only)    n_sessions, first_ts, last_ts, active_days (calendar span first->last session,
                             inclusive), days_with_sessions, sessions_per_day, kwh_per_day, median_energy_kwh,
                             median_duration_min, share_weekend, peak_hour; stations with < 60 active days dropped

Sources
  4 cities  Overpass API, two queries per city: `pois` (all POI groups in one union, `out center`) and
            `roads_rail` (motorway/trunk/primary/secondary ways with `out geom` + railway stations with
            `out center`). Raw JSON is cached under data/raw/context/<city>/<name>.json (+ .meta.json with the
            query text, endpoint and OSM base timestamp) and never re-fetched.
            Etiquette: before every live query /api/status is polled and the client sleeps until a slot is
            free (+3 s); one query in flight at a time; [timeout:180]; 30/60/120 s back-off on 429/502/503/504
            and on Overpass "runtime error" remarks; then the next mirror.
  London    data/interim/osm/pois.parquet, london_major_roads.parquet and data/interim/transit/tfl_stations.parquet
            (no Overpass calls).
  WorldPop  rasters cached under data/raw/context/worldpop/.

Run:   PYTHONPATH=src python -m chargescape.features.station_context [--cities dundee london] [--force]
Idempotent: per-city outputs data/interim/context/<city>_station_features.parquet are reused unless --force;
all Overpass JSON and rasters are cached on disk.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import shapely
from rasterio.mask import mask as rio_mask
from shapely.geometry import LineString, Point, box

from chargescape.utils.http import UA, download
from chargescape.utils.paths import INTERIM, PROCESSED, RAW

log = logging.getLogger("chargescape.features.station_context")

WGS84 = 4326
RAW_CTX = RAW / "context"
INTERIM_CTX = INTERIM / "context"
OUT_PATH = PROCESSED / "station_features.small.parquet"
REPORT_PATH = INTERIM_CTX / "context_build_report.json"
SESSIONS_DIR = INTERIM / "sessions_open"
LONDON_SITES = PROCESSED / "charging_sites.parquet"
LONDON_POIS = INTERIM / "osm" / "pois.parquet"
LONDON_MAJOR_ROADS = INTERIM / "osm" / "london_major_roads.parquet"
LONDON_RAIL = INTERIM / "transit" / "tfl_stations.parquet"
LONDON_BOUNDARY = INTERIM / "osm" / "greater_london_boundary.parquet"

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OVERPASS_TIMEOUT = 180  # [timeout:] inside the query and the HTTP read timeout
OVERPASS_BACKOFF_S = (30, 60, 120)  # after 429 / 502 / 503 / 504 / runtime error, per endpoint
OVERPASS_RETRY_STATUS = {429, 502, 503, 504}
SLOT_MARGIN_S = 3.0  # extra seconds after /api/status says a slot is free
SLOT_MAX_WAIT_S = 900
_OVERPASS_LOCK = threading.Lock()  # exactly one query in flight

WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/{cc}/{lc}_ppp_2020_1km_Aggregated.tif"
)

CITIES: dict[str, dict[str, Any]] = {
    "dundee": {"crs": 27700, "country": "GBR", "kind": "sessions"},
    "pkc": {"crs": 27700, "country": "GBR", "kind": "sessions"},
    "palo_alto": {"crs": 26910, "country": "USA", "kind": "sessions"},
    "boulder": {"crs": 26913, "country": "USA", "kind": "sessions"},
    "london": {"crs": 27700, "country": "GBR", "kind": "sites"},
}
SESSION_CITIES = [c for c, v in CITIES.items() if v["kind"] == "sessions"]
RADII = (300, 800)
POP_RADIUS_M = 1000
MIN_ACTIVE_DAYS = 60
POI_PAD_KM = 2.0  # bbox padding around the city's stations for the POI query (> max radius)
ROAD_PAD_KM = 15.0  # motorways/trunks are sparse -> wider box (primary/secondary share the query)
RAIL_PAD_KM = 40.0  # Boulder and rural Perth & Kinross have no railway station nearby
ENERGY_MAX_KWH = 500.0  # a single-vehicle session above this is a logging error (Dundee has a 1.6 GWh row)
DURATION_MAX_MIN = 7 * 1440  # sessions longer than a week / negative durations are back-office artefacts
RAPID_KW = 50.0
RAIL_VALUES = ("station", "halt")

# group -> [(osm key, allowed values | None = any value)]. The same lists drive the Overpass query for the
# four cities and the mapping of the London POI table (built with the same rules, see data/osm.py).
# shop=clothes is deliberately absent: the London table does not carry it, and cross-city consistency wins.
POI_GROUPS: dict[str, list[tuple[str, tuple[str, ...] | None]]] = {
    "food": [("amenity", ("restaurant", "cafe", "fast_food", "pub", "bar"))],
    "retail": [
        (
            "shop",
            (
                "supermarket",
                "mall",
                "department_store",
                "convenience",
                "doityourself",
                "furniture",
                "electronics",
            ),
        )
    ],
    "hotel": [("tourism", ("hotel", "hostel", "guest_house", "motel"))],
    "leisure": [
        ("leisure", ("fitness_centre", "sports_centre", "stadium")),
        ("amenity", ("cinema", "theatre")),
        ("tourism", ("attraction", "museum")),
    ],
    "parking": [("amenity", ("parking",))],
    "fuel": [("amenity", ("fuel",))],
    "office": [("office", None)],
    "health_edu": [("amenity", ("hospital", "clinic", "university", "college", "school"))],
    "car": [("shop", ("car", "car_repair")), ("amenity", ("car_wash", "car_rental"))],
}
ROAD_CLASSES: dict[str, tuple[str, ...]] = {
    "motorway": ("motorway", "trunk"),
    "primary": ("primary", "secondary"),
}

ID_COLS = [
    "city",
    "station_id",
    "station_name",
    "lat",
    "lon",
    "power_kw",
    "n_ports",
    "is_rapid",
    "source",
    "year",
    "operator",
]
TARGET_COLS = [
    "n_sessions",
    "first_ts",
    "last_ts",
    "active_days",
    "days_with_sessions",
    "sessions_per_day",
    "kwh_per_day",
    "median_energy_kwh",
    "median_duration_min",
    "share_weekend",
    "peak_hour",
]


def feature_columns() -> list[str]:
    cols = [f"poi_{g}_{r}" for r in RADII for g in POI_GROUPS]
    cols += [f"parking_capacity_{r}" for r in RADII]
    cols += ["dist_motorway_m", "dist_primary_m", "dist_rail_m", "pop_1km", "pop_source", "poi_edge_flag"]
    return cols


def numeric_feature_columns() -> list[str]:
    return [c for c in feature_columns() if c not in ("pop_source", "poi_edge_flag")]


# ----------------------------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _to_capacity(v: Any) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return float("nan")
    m = re.search(r"\d+", str(v).replace(",", ""))
    return float(m.group()) if m else float("nan")


def _bbox(points_wgs: gpd.GeoSeries, crs: int, pad_km: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) in WGS84: metric bounding box of the points padded by pad_km."""
    minx, miny, maxx, maxy = points_wgs.to_crs(crs).total_bounds
    pad = pad_km * 1000.0
    b = gpd.GeoSeries([box(minx - pad, miny - pad, maxx + pad, maxy + pad)], crs=crs).to_crs(WGS84)
    w, s, e, n = b.total_bounds
    return (round(float(s), 5), round(float(w), 5), round(float(n), 5), round(float(e), 5))


def _bbox_str(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(str(x) for x in bbox)


# ---------------------------------------------------------------------------------------------- overpass
def _slot_wait(status_text: str) -> float:
    """Seconds this IP has to wait before sending a query, parsed from /api/status (0 = a slot is free).

    Formats seen on overpass-api.de: "N slots available now.", one or more "Slot available after: <ts>, in N
    seconds." lines, and a "Currently running queries" table (pid<TAB>space<TAB>time<TAB>start) that lists our
    own queries still executing - when only that is present every slot is busy, so poll again in 10 s.
    """
    m = re.search(r"(\d+) slots? available now", status_text)
    if m and int(m.group(1)) > 0:
        return 0.0
    waits = [int(w) for w in re.findall(r"in (-?\d+) seconds", status_text)]
    if waits:
        return max(min(waits), 0) + SLOT_MARGIN_S
    running = re.findall(r"^\d+\s+\d+\s+\d+\s+\S+", status_text, flags=re.M)
    return 10.0 if running else 0.0


def _wait_for_slot(endpoint: str) -> None:
    """Overpass etiquette: poll <endpoint>/../status until this IP has a free slot, then wait 3 s more."""
    status_url = endpoint.rsplit("/", 1)[0] + "/status"
    host = status_url.split("/")[2]
    waited = 0.0
    while waited < SLOT_MAX_WAIT_S:
        try:
            txt = requests.get(status_url, headers={"User-Agent": UA}, timeout=30).text
        except requests.RequestException as e:  # mirrors without a status page: short fixed pause
            log.info("overpass: status of %s unavailable (%s); pausing 5 s", host, type(e).__name__)
            time.sleep(5)
            return
        w = _slot_wait(txt)
        if w <= 0:
            return
        log.info("overpass: no free slot at %s, sleeping %.0f s", host, w)
        time.sleep(w)
        waited += w
    log.warning("overpass: no slot freed at %s within %d s; sending anyway", host, SLOT_MAX_WAIT_S)


def overpass(city: str, name: str, query: str, meta: dict[str, Any] | None = None) -> dict:
    """Run an Overpass query, cached as data/raw/context/<city>/<name>.json (+ .meta.json).

    Cached responses are returned without any network access. Live queries wait for a free slot, hold a lock
    so only one request is in flight, back off 30/60/120 s on 429/502/503/504 or a runtime-error remark, and
    fall through to the next mirror when an endpoint keeps failing.
    """
    cache = RAW_CTX / city / f"{name}.json"
    if cache.exists() and cache.stat().st_size > 0:
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            log.warning("%s is not valid JSON; re-fetching", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    last = ""
    for endpoint in OVERPASS_ENDPOINTS:
        host = endpoint.split("/")[2]
        for attempt, backoff in enumerate(OVERPASS_BACKOFF_S, start=1):
            with _OVERPASS_LOCK:
                _wait_for_slot(endpoint)
                t0 = time.time()
                try:
                    r = requests.post(
                        endpoint,
                        data={"data": query},
                        headers={"User-Agent": UA},
                        timeout=(30, OVERPASS_TIMEOUT + 60),
                    )
                except requests.RequestException as e:
                    r, last = None, f"{type(e).__name__}"
            if r is not None and r.status_code == 200:
                try:
                    data = r.json()
                except ValueError:
                    data, last = None, "response is not JSON"
                if data is not None:
                    remark = str(data.get("remark", ""))
                    if "runtime error" in remark.lower():
                        last = remark.strip()
                    else:
                        n = len(data.get("elements", []))
                        cache.write_text(json.dumps(data))
                        m = {
                            "endpoint": endpoint,
                            "query": query,
                            "retrieved_utc": _now(),
                            "osm_base": data.get("osm3s", {}).get("timestamp_osm_base"),
                            "n_elements": n,
                            "seconds": round(time.time() - t0, 1),
                            "bytes": len(r.content),
                            **(meta or {}),
                        }
                        cache.with_suffix(".meta.json").write_text(json.dumps(m, indent=1))
                        if remark:
                            log.warning("overpass %s/%s remark: %s", city, name, remark)
                        log.info(
                            "overpass %s/%s: %d elements, %.1f MB in %.1fs via %s",
                            city,
                            name,
                            n,
                            len(r.content) / 1e6,
                            m["seconds"],
                            host,
                        )
                        time.sleep(1.0)
                        return data
            elif r is not None:
                if r.status_code not in OVERPASS_RETRY_STATUS:
                    raise RuntimeError(
                        f"Overpass {host} HTTP {r.status_code} for {city}/{name}: {r.text[:300]}"
                    )
                last = f"HTTP {r.status_code}"
            log.warning(
                "overpass %s/%s attempt %d at %s failed (%s); backing off %d s",
                city,
                name,
                attempt,
                host,
                last,
                backoff,
            )
            time.sleep(backoff)
    raise RuntimeError(f"Overpass failed for {city}/{name}: {last}")


def _points_from_elements(data: dict) -> gpd.GeoDataFrame:
    """Nodes -> their coordinates; ways/relations -> Overpass `out center` centroid. Tags kept as dicts."""
    rows = []
    for el in data.get("elements", []):
        if el.get("type") == "node":
            lon, lat = el.get("lon"), el.get("lat")
        else:
            c = el.get("center") or {}
            lon, lat = c.get("lon"), c.get("lat")
        if lon is None or lat is None:
            continue
        rows.append(
            {
                "osm_type": el["type"],
                "osm_id": el["id"],
                "tags": el.get("tags") or {},
                "geometry": Point(lon, lat),
            }
        )
    gdf = gpd.GeoDataFrame(
        rows, columns=["osm_type", "osm_id", "tags", "geometry"], geometry="geometry", crs=WGS84
    )
    return gdf.drop_duplicates(["osm_type", "osm_id"]).reset_index(drop=True)


def _lines_from_elements(data: dict) -> gpd.GeoDataFrame:
    """Ways returned with `out geom` -> LineStrings with their highway tag."""
    rows = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        pts = [(p["lon"], p["lat"]) for p in el["geometry"] if p and "lon" in p]
        if len(pts) < 2:
            continue
        rows.append(
            {
                "osm_id": el["id"],
                "highway": (el.get("tags") or {}).get("highway"),
                "geometry": LineString(pts),
            }
        )
    return gpd.GeoDataFrame(rows, columns=["osm_id", "highway", "geometry"], geometry="geometry", crs=WGS84)


# ------------------------------------------------------------------------------------------- POI sources
def _poi_selectors() -> list[tuple[str, tuple[str, ...] | None]]:
    """POI_GROUPS merged by OSM key -> one `nwr` selector per key (5 union members cover all 9 groups)."""
    merged: dict[str, set[str] | None] = {}
    for rules in POI_GROUPS.values():
        for key, vals in rules:
            if vals is None:
                merged[key] = None
            elif merged.get(key, set()) is not None:
                merged.setdefault(key, set()).update(vals)
    return [(k, None if v is None else tuple(sorted(v))) for k, v in sorted(merged.items())]


def _poi_query(bbox: tuple[float, float, float, float]) -> str:
    """One union query for every POI group; the regex also matches multi-valued tags ("cafe;bar")."""
    parts = []
    for key, vals in _poi_selectors():
        sel = f'["{key}"]' if vals is None else f'["{key}"~"(^|;)({"|".join(vals)})(;|$)"]'
        parts.append(f"  nwr{sel}({_bbox_str(bbox)});")
    return f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n(\n" + "\n".join(parts) + "\n);\nout center;"


def _groups_for_tags(tags: dict[str, Any]) -> list[str]:
    """All POI groups an OSM tag dict belongs to (an element may sit in several, as in the London table)."""
    out = []
    for group, rules in POI_GROUPS.items():
        for key, vals in rules:
            raw = tags.get(key)
            if raw is None or raw == "":
                continue
            parts = [v.strip() for v in str(raw).split(";") if v.strip()]
            if parts and (vals is None or any(p in vals for p in parts)):
                out.append(group)
                break
    return out


def fetch_city_pois(city: str, stations_wgs: gpd.GeoDataFrame, crs: int) -> gpd.GeoDataFrame:
    """POIs (WGS84 points with `group`, `capacity`) from one cached Overpass query per city."""
    bbox = _bbox(stations_wgs.geometry, crs, POI_PAD_KM)
    meta = {"bbox_swne": bbox, "pad_km": POI_PAD_KM, "groups": list(POI_GROUPS)}
    pts = _points_from_elements(overpass(city, "pois", _poi_query(bbox), meta))
    pts["group"] = pts["tags"].map(_groups_for_tags)
    pts = pts.explode("group", ignore_index=True).dropna(subset=["group"])
    cap = pts["tags"].map(lambda t: _to_capacity(t.get("capacity")))
    pts["capacity"] = np.where(pts["group"] == "parking", cap, np.nan)
    cols = ["osm_type", "osm_id", "group", "capacity", "geometry"]
    return gpd.GeoDataFrame(pts[cols].reset_index(drop=True), geometry="geometry", crs=WGS84)


def _london_group(category: str, subcategory: str) -> str | None:
    """Map data/osm.py POI categories onto the groups used here (drops building=office and amenity=taxi,
    which the four-city tag lists do not query)."""
    if category in ("food", "hotel", "leisure", "parking", "fuel"):
        return category
    if category in ("retail", "supermarket"):
        return "retail"
    if category in ("health", "education"):
        return "health_edu"
    if category == "office":
        return None if subcategory == "building_office" else "office"
    if category == "car":
        return None if subcategory == "taxi" else "car"
    return None


def load_london_pois() -> gpd.GeoDataFrame:
    p = gpd.read_parquet(LONDON_POIS, columns=["osm_id", "category", "subcategory", "capacity", "geometry"])
    p["group"] = [_london_group(c, s) for c, s in zip(p["category"], p["subcategory"], strict=True)]
    p = p.dropna(subset=["group"]).copy()
    p["capacity"] = np.where(p["group"] == "parking", p["capacity"].map(_to_capacity), np.nan)
    return gpd.GeoDataFrame(p[["osm_id", "group", "capacity", "geometry"]], geometry="geometry", crs=p.crs)


# ------------------------------------------------------------------------------------ road / rail sources
def _roads_rail_query(bbox_roads, bbox_rail) -> str:
    hw = "|".join(v for vals in ROAD_CLASSES.values() for v in vals)
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n"
        f'way["highway"~"^({hw})$"]({_bbox_str(bbox_roads)});\nout geom;\n'
        f'nwr["railway"~"^({"|".join(RAIL_VALUES)})$"]({_bbox_str(bbox_rail)});\nout center;'
    )


def fetch_city_roads_rail(
    city: str, stations_wgs: gpd.GeoDataFrame, crs: int
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Major-road LineStrings and railway-station points (WGS84) from one cached Overpass query per city."""
    b_roads = _bbox(stations_wgs.geometry, crs, ROAD_PAD_KM)
    b_rail = _bbox(stations_wgs.geometry, crs, RAIL_PAD_KM)
    meta = {
        "bbox_roads_swne": b_roads,
        "road_pad_km": ROAD_PAD_KM,
        "bbox_rail_swne": b_rail,
        "rail_pad_km": RAIL_PAD_KM,
    }
    data = overpass(city, "roads_rail", _roads_rail_query(b_roads, b_rail), meta)
    lines = _lines_from_elements(data)
    rail_els = [e for e in data.get("elements", []) if (e.get("tags") or {}).get("railway") in RAIL_VALUES]
    rail = _points_from_elements({"elements": rail_els})
    return lines, rail


def _road_class(lines: gpd.GeoDataFrame, cls: str) -> gpd.GeoDataFrame:
    """Rows whose highway tag (possibly 'a|b' from the osmnx graph) contains one of the class values."""
    vals = set(ROAD_CLASSES[cls])
    hw = lines["highway"].astype(str).str.split("|")
    return lines.loc[hw.map(lambda hs: any(h in vals for h in hs))].reset_index(drop=True)


def load_london_roads() -> gpd.GeoDataFrame:
    return gpd.read_parquet(LONDON_MAJOR_ROADS, columns=["highway", "geometry"])


def load_london_rail() -> gpd.GeoDataFrame:
    """TfL / NaPTAN rail stations (tube, DLR, Overground, Elizabeth line, tram, National Rail)."""
    t = pd.read_parquet(LONDON_RAIL, columns=["id", "lat", "lon"]).dropna(subset=["lat", "lon"])
    return gpd.GeoDataFrame(t[["id"]], geometry=gpd.points_from_xy(t["lon"], t["lat"]), crs=WGS84)


# ---------------------------------------------------------------------------------------------- features
def poi_features(stations_m: gpd.GeoDataFrame, pois_m: gpd.GeoDataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=stations_m.index)
    pois_m = pois_m[["group", "capacity", "geometry"]]
    for r in RADII:
        buf = gpd.GeoDataFrame(geometry=stations_m.geometry.buffer(r), crs=stations_m.crs)
        j = gpd.sjoin(buf, pois_m, how="inner", predicate="intersects")
        counts = j.groupby([j.index, "group"]).size().unstack(fill_value=0)
        for g in POI_GROUPS:
            col = (
                counts[g].reindex(out.index).fillna(0)
                if g in counts.columns
                else pd.Series(0, index=out.index)
            )
            out[f"poi_{g}_{r}"] = col.astype(int)
        cap = j.loc[j["group"] == "parking"].groupby(level=0)["capacity"].sum()
        out[f"parking_capacity_{r}"] = cap.reindex(out.index).fillna(0.0)
    return out


def nearest_distance(stations_m: gpd.GeoDataFrame, feats_m: gpd.GeoDataFrame | None) -> pd.Series:
    if feats_m is None or feats_m.empty:
        return pd.Series(np.nan, index=stations_m.index, dtype="float64")
    right = gpd.GeoDataFrame(geometry=feats_m.geometry.reset_index(drop=True), crs=feats_m.crs)
    j = gpd.sjoin_nearest(stations_m[["geometry"]], right, how="left", distance_col="d")
    return j.groupby(level=0)["d"].min().reindex(stations_m.index)


def worldpop_raster(country: str) -> Path | None:
    """Download (once) the WorldPop 2020 1 km aggregated raster for GBR / USA; None when it cannot be fetched."""
    url = WORLDPOP_URL.format(cc=country, lc=country.lower())
    try:
        return download(url, RAW_CTX / "worldpop" / Path(url).name, timeout=600, retries=3)
    except RuntimeError as e:
        log.error("WorldPop raster unavailable (%s); falling back to OSM building counts", e)
        return None


def population_within(stations_m: gpd.GeoDataFrame, raster: Path, radius_m: int = POP_RADIUS_M) -> pd.Series:
    """Population inside a `radius_m` buffer: rasterio.mask (all_touched) on the WGS84 buffer, then each
    touched pixel contributes value x (pixel area inside the buffer / pixel area). Nodata/negative -> 0;
    a buffer entirely outside the raster -> NaN."""
    bufs = stations_m.geometry.buffer(radius_m).to_crs(WGS84)
    vals = np.full(len(bufs), np.nan)
    with rasterio.open(raster) as src:
        nodata = src.nodata
        for k, poly in enumerate(bufs.values):
            if poly is None or poly.is_empty:
                continue
            try:
                arr, tr = rio_mask(src, [poly], crop=True, all_touched=True, filled=True, nodata=0)
            except ValueError:  # shapes do not overlap the raster
                continue
            a = arr[0].astype("float64")
            if nodata is not None:
                a[a == nodata] = 0.0
            a[~np.isfinite(a) | (a < 0)] = 0.0
            rows, cols = np.nonzero(a)
            if len(rows) == 0:
                vals[k] = 0.0
                continue
            x0 = tr.c + cols * tr.a
            y0 = tr.f + rows * tr.e  # tr.e < 0: y0 is the top edge
            pix = shapely.box(x0, y0 + tr.e, x0 + tr.a, y0)
            frac = shapely.area(shapely.intersection(pix, poly)) / abs(tr.a * tr.e)
            vals[k] = float((a[rows, cols] * frac).sum())
    return pd.Series(vals, index=stations_m.index)


def buildings_within(
    city: str,
    stations_wgs: gpd.GeoDataFrame,
    stations_m: gpd.GeoDataFrame,
    crs: int,
    radius_m: int = POP_RADIUS_M,
) -> pd.Series:
    """Fallback for pop_1km: number of OSM building features (centroids) within `radius_m`. London has no
    offline building layer, so it returns NaN there rather than issuing Overpass calls."""
    if CITIES[city]["kind"] != "sessions":
        return pd.Series(np.nan, index=stations_m.index, dtype="float64")
    bbox = _bbox(stations_wgs.geometry, crs, radius_m / 1000.0 + 0.5)
    q = f'[out:json][timeout:{OVERPASS_TIMEOUT}];\nnwr["building"]({_bbox_str(bbox)});\nout center;'
    pts = _points_from_elements(overpass(city, "buildings", q, {"bbox_swne": bbox})).to_crs(crs)
    buf = gpd.GeoDataFrame(geometry=stations_m.geometry.buffer(radius_m), crs=stations_m.crs)
    j = gpd.sjoin(buf, pts[["geometry"]], how="inner", predicate="intersects")
    return j.groupby(level=0).size().reindex(stations_m.index).fillna(0).astype("float64")


# ---------------------------------------------------------------------------------------------- stations
def session_targets(city: str) -> pd.DataFrame:
    """Per-station utilisation targets + session-derived attributes (power, observed ports, port types)."""
    cols = ["station_id", "start_ts", "duration_min", "energy_kwh", "power_kw", "port_type", "connector"]
    s = pd.read_parquet(SESSIONS_DIR / f"{city}_sessions.parquet", columns=cols).dropna(subset=["start_ts"])
    s["station_id"] = s["station_id"].astype(str)
    s["energy_ok"] = s["energy_kwh"].where((s["energy_kwh"] > 0) & (s["energy_kwh"] <= ENERGY_MAX_KWH))
    s["dur_ok"] = s["duration_min"].where((s["duration_min"] > 0) & (s["duration_min"] <= DURATION_MAX_MIN))
    s["weekend"] = s["start_ts"].dt.dayofweek >= 5
    s["hour"] = s["start_ts"].dt.hour
    s["day"] = s["start_ts"].dt.normalize()
    g = s.groupby("station_id")
    t = pd.DataFrame(
        {
            "n_sessions": g.size(),
            "first_ts": g["start_ts"].min(),
            "last_ts": g["start_ts"].max(),
            "days_with_sessions": g["day"].nunique(),
            "kwh_total": g["energy_ok"].sum(min_count=1),
            "median_energy_kwh": g["energy_ok"].median(),
            "median_duration_min": g["dur_ok"].median(),
            "share_weekend": g["weekend"].mean(),
            "peak_hour": g["hour"].agg(lambda h: int(h.value_counts().sort_index().idxmax())),
            "power_kw_sessions": g["power_kw"].max(),
            "n_ports_obs": g["connector"].nunique(),
            "port_types": g["port_type"].agg(lambda v: sorted({str(x).strip().lower() for x in v.dropna()})),
        }
    )
    t["active_days"] = (t["last_ts"].dt.normalize() - t["first_ts"].dt.normalize()).dt.days + 1
    t["sessions_per_day"] = t["n_sessions"] / t["active_days"]
    t["kwh_per_day"] = t["kwh_total"] / t["active_days"]
    t["n_ports_obs"] = t["n_ports_obs"].where(t["n_ports_obs"] > 0)
    return t


_AC_TYPES = {"ac", "level 1", "level 2", "level1", "level2"}
_RAPID_TYPES = {"rapid", "ultra_rapid", "ultra-rapid", "dc"}


def _is_rapid(power_kw: float, port_types: list[str] | float) -> bool | None:
    if pd.notna(power_kw):
        return bool(power_kw >= RAPID_KW)
    types = set(port_types) if isinstance(port_types, list | tuple | set) else set()
    if types and types <= _AC_TYPES:
        return False
    if types & _RAPID_TYPES:
        return True
    return None


def load_stations(city: str) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Station table (WGS84 points, RangeIndex) with ID_COLS (+ TARGET_COLS for session cities)."""
    info: dict[str, Any] = {}
    if CITIES[city]["kind"] == "sites":
        s = gpd.read_parquet(LONDON_SITES)
        known = s["max_kw"].notna()
        rapid = pd.array(
            np.where(known, s["max_kw"] >= RAPID_KW, np.where(s["is_rapid"].astype(bool), True, None)),
            dtype="boolean",
        )
        df = pd.DataFrame(
            {
                "city": city,
                "station_id": s["site_id"].astype(str),
                "station_name": pd.Series([None] * len(s), dtype="string"),
                "lat": s.geometry.y,
                "lon": s.geometry.x,
                "power_kw": s["max_kw"].astype("float64"),
                "n_ports": s["n_ports"].astype("float64"),
                "is_rapid": rapid,
                "source": s["source"].astype("string"),
                "year": s["year"].astype("Int64"),
                "operator": s["operator"].astype("string"),
            }
        )
        info["n_sites"] = int(len(df))
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=WGS84)
        return gdf.reset_index(drop=True), info

    st = pd.read_parquet(SESSIONS_DIR / f"{city}_stations.parquet")
    st["station_id"] = st["station_id"].astype(str)
    n0 = len(st)
    st = st.dropna(subset=["lat", "lon"]).drop_duplicates("station_id")
    info["n_stations_raw"] = int(n0)
    info["n_dropped_no_coords"] = int(n0 - len(st))
    t = session_targets(city)
    st = st.drop(columns=[c for c in t.columns if c in st.columns])  # e.g. the table's own n_sessions
    st = st.merge(t, left_on="station_id", right_index=True, how="left")
    keep = st["active_days"].fillna(0) >= MIN_ACTIVE_DAYS
    info["n_dropped_lt_min_active_days"] = int((~keep).sum())
    st = st.loc[keep].reset_index(drop=True)  # positional Series below must line up with st
    power = st[["power_kw", "power_kw_sessions"]].max(axis=1, skipna=True)
    df = pd.DataFrame(
        {
            "city": city,
            "station_id": st["station_id"].astype(str),
            "station_name": st["station_name"].astype("string"),
            "lat": st["lat"].astype("float64"),
            "lon": st["lon"].astype("float64"),
            "power_kw": power.astype("float64"),
            "n_ports": st["n_ports_obs"].astype("float64"),
            "is_rapid": pd.array(
                [_is_rapid(p, pt) for p, pt in zip(power, st["port_types"], strict=True)], dtype="boolean"
            ),
            "source": pd.Series([None] * len(st), dtype="string"),
            "year": pd.array([None] * len(st), dtype="Int64"),
            "operator": pd.Series([None] * len(st), dtype="string"),
        }
    )
    for c in TARGET_COLS:
        df[c] = st[c].to_numpy()
    info["n_stations_kept"] = int(len(df))
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=WGS84)
    return gdf.reset_index(drop=True), info


def _cast_targets(df: pd.DataFrame) -> pd.DataFrame:
    for c in TARGET_COLS:
        if c not in df.columns:
            df[c] = pd.NaT if c in ("first_ts", "last_ts") else np.nan
    for c in ("n_sessions", "active_days", "days_with_sessions", "peak_hour"):
        df[c] = pd.array(df[c], dtype="Int64")
    return df


# ------------------------------------------------------------------------------------------------- build
def build_station_features(city: str, force: bool = False) -> pd.DataFrame:
    """Features (+ targets) for one city; cached in data/interim/context/<city>_station_features.parquet."""
    if city not in CITIES:
        raise KeyError(f"unknown city {city!r}; choose from {list(CITIES)}")
    cfg = CITIES[city]
    out = INTERIM_CTX / f"{city}_station_features.parquet"
    if out.exists() and not force:
        log.info("%s: reusing %s", city, out)
        return pd.read_parquet(out)
    INTERIM_CTX.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    crs = int(cfg["crs"])
    st, info = load_stations(city)
    st_m = st.to_crs(crs)
    log.info("%s: %d stations, crs %d", city, len(st), crs)

    # 1. POIs
    pois = load_london_pois() if city == "london" else fetch_city_pois(city, st, crs)
    feats = poi_features(st_m, pois.to_crs(crs))
    info["n_pois_by_group"] = {k: int(v) for k, v in pois["group"].value_counts().sort_index().items()}

    # 2. roads + rail
    if city == "london":
        lines, rail = load_london_roads(), load_london_rail()
    else:
        lines, rail = fetch_city_roads_rail(city, st, crs)
    for cls in ROAD_CLASSES:
        sub = _road_class(lines, cls)
        feats[f"dist_{cls}_m"] = nearest_distance(st_m, sub.to_crs(crs) if len(sub) else None)
        info[f"n_ways_{cls}"] = int(len(sub))
    feats["dist_rail_m"] = nearest_distance(st_m, rail.to_crs(crs) if len(rail) else None)
    info["n_rail_stations"] = int(len(rail))

    # 3. population
    raster = worldpop_raster(cfg["country"])
    if raster is not None:
        feats["pop_1km"] = population_within(st_m, raster)
        feats["pop_source"] = "worldpop_ppp_2020_1km"
        info["pop_source"] = {"worldpop_raster": raster.name}
    else:
        feats["pop_1km"] = buildings_within(city, st, st_m, crs)
        feats["pop_source"] = np.where(feats["pop_1km"].notna(), "osm_buildings_1km", "none")
        info["pop_source"] = {"fallback": "osm_buildings_1km"}
    feats["pop_source"] = feats["pop_source"].astype("string")

    # 4. coverage flag (London POI table is clipped to the Greater London boundary)
    if city == "london" and LONDON_BOUNDARY.exists():
        boundary = gpd.read_parquet(LONDON_BOUNDARY).to_crs(crs).union_all()
        feats["poi_edge_flag"] = ~st_m.geometry.buffer(max(RADII)).within(boundary)
    else:
        feats["poi_edge_flag"] = False
    info["n_poi_edge_flag"] = int(feats["poi_edge_flag"].sum())

    df = _cast_targets(pd.concat([pd.DataFrame(st.drop(columns="geometry")), feats], axis=1))
    df = df[ID_COLS + feature_columns() + TARGET_COLS]
    df.to_parquet(out, index=False)
    info["seconds"] = round(time.time() - t0, 1)
    info["built_utc"] = _now()
    (INTERIM_CTX / f"{city}_build_info.json").write_text(json.dumps(info, indent=1))
    log.info("%s: %d rows -> %s (%.0fs)", city, len(df), out, info["seconds"])
    return df


def _spearman_table(df: pd.DataFrame, cols: list[str], min_n: int = 10) -> pd.DataFrame:
    from scipy.stats import spearmanr

    rows = []
    for c in cols:
        x = df[[c, "sessions_per_day"]].astype("float64").dropna()
        if len(x) >= min_n and x[c].nunique() > 1:
            rho, p = spearmanr(x[c], x["sessions_per_day"])
            rows.append((c, round(float(rho), 3), round(float(p), 4), len(x)))
    t = pd.DataFrame(rows, columns=["feature", "spearman_rho", "p", "n"])
    return t.sort_values("spearman_rho", key=abs, ascending=False).reset_index(drop=True)


def _summary(df: pd.DataFrame) -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 60)
    print("\n== rows per city ==")
    print(df["city"].value_counts().reindex(list(CITIES)).to_string())
    feats = feature_columns()
    print("\n== share missing per city (feature + target columns with any NaN) ==")
    na = df.groupby("city")[feats + TARGET_COLS].apply(lambda x: x.isna().mean().round(3)).T
    print(na.loc[na.sum(axis=1) > 0].to_string())
    num = numeric_feature_columns() + ["power_kw", "n_ports"]
    print("\n== feature distributions (all cities) ==")
    print(df[num].describe().T.round(1).to_string())
    print("\n== per-city medians ==")
    print(df.groupby("city")[num].median().T.round(1).to_string())
    print("\n== targets (session cities, medians) ==")
    tc = [c for c in TARGET_COLS if c not in ("first_ts", "last_ts")]
    print(df.dropna(subset=["n_sessions"]).groupby("city")[tc].median().T.round(2).to_string())
    d = df[df["city"] == "dundee"]
    if len(d) >= 10:
        print("\n== Dundee: Spearman(sessions_per_day, feature), top 10 by |rho| ==")
        print(_spearman_table(d, num).head(10).to_string(index=False))
    pooled = df[df["city"].isin(SESSION_CITIES)]
    if len(pooled) >= 10:
        print("\n== pooled 4 cities: Spearman(sessions_per_day, feature), top 10 by |rho| ==")
        print(_spearman_table(pooled, num).head(10).to_string(index=False))


def main(argv: list[str] | None = None) -> pd.DataFrame:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cities", nargs="+", default=list(CITIES), choices=list(CITIES))
    ap.add_argument("--force", action="store_true", help="rebuild per-city feature parquets")
    ap.add_argument("--quiet", action="store_true", help="skip the summary printout")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    frames = [build_station_features(c, force=args.force) for c in args.cities]
    df = pd.concat(frames, ignore_index=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    report = {
        "built_utc": _now(),
        "output": str(OUT_PATH.relative_to(PROCESSED.parent.parent)),
        "n_rows": int(len(df)),
        "rows_per_city": {k: int(v) for k, v in df["city"].value_counts().items()},
        "columns": list(df.columns),
        "cities": {
            c: json.loads((INTERIM_CTX / f"{c}_build_info.json").read_text())
            for c in args.cities
            if (INTERIM_CTX / f"{c}_build_info.json").exists()
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=1))
    log.info("wrote %s (%d rows, %d cols); report %s", OUT_PATH, len(df), df.shape[1], REPORT_PATH)
    if not args.quiet:
        _summary(df)
    return df


if __name__ == "__main__":
    main()
