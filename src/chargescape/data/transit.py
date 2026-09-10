"""Public-transport context layers for Greater London: TfL stations, NaPTAN bus stops, cycle-hire docks.

Sources (no account / key needed):
  * TfL Unified API (anonymous, rate-limited)  -> "Powered by TfL Open Data" (OGL v2/v3 + TfL terms)
      /StopPoint/Mode/{mode}  one call per rail mode (the combined 6-mode call times out server-side)
      /BikePoint              Santander Cycles docking stations (activity / amenity proxy)
  * NaPTAN (DfT, OGL v3) CSV download, ATCO area 490 = London (bus stops)

Artefacts:
  data/raw/transit/tfl_stoppoints_{mode}.json      raw StopPoint responses (cache)
  data/raw/transit/tfl_bikepoints.json             raw BikePoint response
  data/raw/transit/naptan_atco490_london.csv       raw NaPTAN CSV
  data/interim/transit/tfl_stations.parquet        one row per station (id, name, modes, lat, lon, ...)
  data/interim/transit/naptan_bus_stops_london.parquet
  data/interim/transit/tfl_bikepoints.parquet
  data/interim/transit/transit_build_report.json

Usage: PYTHONPATH=src python -m chargescape.data.transit [--force] [--only stations bus bikepoints]
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

from chargescape.utils.http import UA, download
from chargescape.utils.paths import INTERIM, RAW

log = logging.getLogger("chargescape.data.transit")

TFL_BASE = "https://api.tfl.gov.uk"
TFL_MODES = ("tube", "dlr", "overground", "elizabeth-line", "tram", "national-rail")
STATION_STOP_TYPES = (
    "NaptanMetroStation",
    "NaptanRailStation",
)  # station level, not platforms/entrances/hubs
NAPTAN_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv&atcoAreaCodes=490"
BUS_STOP_TYPES = ("BCT", "BCS", "BCQ")  # on-street bus/coach stop, bus station bay, variable bay
BBOX_LONDON = (-0.51, 51.28, 0.33, 51.70)  # minx, miny, maxx, maxy (fallback if OSM boundary missing)

RAW_TRANSIT = RAW / "transit"
INTERIM_TRANSIT = INTERIM / "transit"
STATIONS_PATH = INTERIM_TRANSIT / "tfl_stations.parquet"
BUS_STOPS_PATH = INTERIM_TRANSIT / "naptan_bus_stops_london.parquet"
BIKEPOINTS_PATH = INTERIM_TRANSIT / "tfl_bikepoints.parquet"
NAPTAN_CSV_PATH = RAW_TRANSIT / "naptan_atco490_london.csv"
REPORT_PATH = INTERIM_TRANSIT / "transit_build_report.json"
BOUNDARY_PATH = INTERIM / "osm" / "greater_london_boundary.parquet"
CRS_WGS84 = "EPSG:4326"


# --------------------------------------------------------------------------------------
def _tfl_get(
    path: str,
    params: dict | None = None,
    *,
    cache_path: Path | None = None,
    force: bool = False,
    timeout: int = 180,
    attempts: int = 6,
) -> Any:
    """Anonymous GET against the TfL Unified API with 429/5xx back-off and a raw-JSON file cache."""
    if cache_path is not None and cache_path.exists() and not force:
        return json.loads(cache_path.read_text())
    url = TFL_BASE + path
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 30 * (i + 1)))
                log.warning("TfL 429 on %s - backing off %ds", path, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                log.warning("TfL %s on %s - retry %d/%d", r.status_code, path, i + 1, attempts)
                time.sleep(15 * (i + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
            return data
        except requests.RequestException as e:
            last = e
            log.warning("TfL request error on %s (%s) - retry %d/%d", path, type(e).__name__, i + 1, attempts)
            time.sleep(15 * (i + 1))
    raise RuntimeError(f"TfL request failed for {path}: {last}")


def _london_polygon():
    if BOUNDARY_PATH.exists():
        return gpd.read_parquet(BOUNDARY_PATH).geometry.iloc[0], "osm_boundary"
    return box(*BBOX_LONDON), "bbox"


# --------------------------------------------------------------------------------------
# C1. TfL stations
# --------------------------------------------------------------------------------------
def fetch_tfl_stations(force: bool = False) -> gpd.GeoDataFrame:
    """Rail-based TfL StopPoints (tube, DLR, Overground, Elizabeth line, tram, National Rail), station level."""
    INTERIM_TRANSIT.mkdir(parents=True, exist_ok=True)
    if STATIONS_PATH.exists() and not force:
        gdf = gpd.read_parquet(STATIONS_PATH)
        log.info("tfl_stations already built (%d rows)", len(gdf))
        return gdf

    records: dict[str, dict] = {}
    raw_counts: dict[str, dict] = {}
    for mode in TFL_MODES:
        t = time.perf_counter()
        stop_points: list[dict] = []
        page = 1
        while True:  # rail modes fit in one page; loop kept for safety (bus needs paging)
            params = {"page": page} if page > 1 else None
            cache = RAW_TRANSIT / (
                f"tfl_stoppoints_{mode}.json" if page == 1 else f"tfl_stoppoints_{mode}_p{page}.json"
            )
            data = _tfl_get(f"/StopPoint/Mode/{mode}", params, cache_path=cache, force=force)
            sps = data.get("stopPoints", data if isinstance(data, list) else [])
            stop_points.extend(sps)
            total, page_size = data.get("total", len(sps)), data.get("pageSize", len(sps)) or len(sps)
            if len(stop_points) >= total or not sps:
                break
            page += 1
            time.sleep(1.5)
        types = pd.Series([s.get("stopType") for s in stop_points]).value_counts().to_dict()
        raw_counts[mode] = {"stop_points": len(stop_points), "by_stop_type": types}
        n_new = 0
        for s in stop_points:
            if s.get("stopType") not in STATION_STOP_TYPES:
                continue
            sid = s["id"]
            if sid in records:
                records[sid]["query_modes"].append(mode)
                continue
            n_new += 1
            records[sid] = {
                "id": sid,
                "naptan_id": s.get("naptanId"),
                "name": s.get("commonName"),
                "modes": sorted(set(s.get("modes") or [])),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "stop_type": s.get("stopType"),
                "hub_naptan_code": s.get("hubNaptanCode"),
                "station_naptan": s.get("stationNaptan"),
                "lines": sorted({ln.get("id") for ln in (s.get("lines") or []) if ln.get("id")}),
                "query_modes": [mode],
            }
        log.info(
            "TfL %-14s %5d stop points, %4d station-level, %4d new, %.1fs",
            mode,
            len(stop_points),
            sum(1 for s in stop_points if s.get("stopType") in STATION_STOP_TYPES),
            n_new,
            time.perf_counter() - t,
        )
        time.sleep(1.5)

    df = pd.DataFrame(list(records.values()))
    df = df.dropna(subset=["lat", "lon"])
    df["modes_str"] = df["modes"].map("|".join)
    df["n_lines"] = df["lines"].map(len)
    for m in TFL_MODES:
        df[f"mode_{m.replace('-', '_')}"] = df["modes"].map(lambda ms, m=m: m in ms)
    df["rail_modes_str"] = df["modes"].map(lambda ms: "|".join(m for m in ms if m in TFL_MODES))
    poly, poly_src = _london_polygon()
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=CRS_WGS84)
    gdf["in_greater_london"] = gdf.geometry.within(poly)
    gdf["boundary_source"] = poly_src
    gdf["retrieved_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    gdf = gdf.sort_values("id").reset_index(drop=True)
    gdf.to_parquet(STATIONS_PATH, index=False)
    (RAW_TRANSIT / "tfl_stoppoints_raw_counts.json").write_text(json.dumps(raw_counts, indent=2))
    log.info(
        "tfl_stations: %d stations (%d inside Greater London); by rail mode: %s",
        len(gdf),
        int(gdf.in_greater_london.sum()),
        {m: int(gdf[f"mode_{m.replace('-', '_')}"].sum()) for m in TFL_MODES},
    )
    return gdf


# --------------------------------------------------------------------------------------
# C2. NaPTAN bus stops
# --------------------------------------------------------------------------------------
def fetch_naptan_bus_stops(force: bool = False) -> gpd.GeoDataFrame:
    """NaPTAN access nodes for ATCO area 490 (London) filtered to active bus stops."""
    INTERIM_TRANSIT.mkdir(parents=True, exist_ok=True)
    if BUS_STOPS_PATH.exists() and not force:
        gdf = gpd.read_parquet(BUS_STOPS_PATH)
        log.info("naptan bus stops already built (%d rows)", len(gdf))
        return gdf
    if force:
        NAPTAN_CSV_PATH.unlink(missing_ok=True)
    t = time.perf_counter()
    download(NAPTAN_URL, NAPTAN_CSV_PATH, timeout=300, retries=3)
    raw = pd.read_csv(NAPTAN_CSV_PATH, dtype=str, keep_default_na=False, low_memory=False)
    log.info(
        "NaPTAN CSV: %d rows, %.1f MB, %.1fs; StopType counts: %s",
        len(raw),
        NAPTAN_CSV_PATH.stat().st_size / 1e6,
        time.perf_counter() - t,
        raw.StopType.value_counts().to_dict(),
    )
    keep_cols = {
        "ATCOCode": "atco_code",
        "NaptanCode": "naptan_code",
        "CommonName": "common_name",
        "Indicator": "indicator",
        "Bearing": "bearing",
        "Street": "street",
        "Landmark": "landmark",
        "LocalityName": "locality_name",
        "ParentLocalityName": "parent_locality_name",
        "StopType": "stop_type",
        "BusStopType": "bus_stop_type",
        "TimingStatus": "timing_status",
        "Easting": "easting",
        "Northing": "northing",
        "Longitude": "lon",
        "Latitude": "lat",
        "Status": "status",
        "ModificationDateTime": "modification_datetime",
    }
    df = raw[list(keep_cols)].rename(columns=keep_cols)
    is_bus = df.stop_type.isin(BUS_STOP_TYPES)
    is_active = df.status.str.lower().eq("active")
    n_bus_all = int(is_bus.sum())
    df = df[is_bus & is_active].copy()
    df["lon"] = pd.to_numeric(df.lon, errors="coerce")
    df["lat"] = pd.to_numeric(df.lat, errors="coerce")
    df = df.dropna(subset=["lon", "lat"])
    df["easting"] = pd.to_numeric(df.easting, errors="coerce")
    df["northing"] = pd.to_numeric(df.northing, errors="coerce")
    poly, poly_src = _london_polygon()
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=CRS_WGS84)
    gdf["in_greater_london"] = gdf.geometry.within(poly)
    gdf["boundary_source"] = poly_src
    gdf["retrieved_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    gdf = gdf.sort_values("atco_code").reset_index(drop=True)
    gdf.to_parquet(BUS_STOPS_PATH, index=False)
    log.info(
        "naptan bus stops: %d active (of %d bus-type rows); inside Greater London: %d; by StopType %s; by BusStopType %s",
        len(gdf),
        n_bus_all,
        int(gdf.in_greater_london.sum()),
        gdf.stop_type.value_counts().to_dict(),
        gdf.bus_stop_type.value_counts().to_dict(),
    )
    return gdf


# --------------------------------------------------------------------------------------
# C3. TfL cycle hire docking stations
# --------------------------------------------------------------------------------------
def fetch_tfl_bikepoints(force: bool = False) -> gpd.GeoDataFrame:
    """Santander Cycles docking stations (BikePoint). Static attributes only (dock count, install date)."""
    INTERIM_TRANSIT.mkdir(parents=True, exist_ok=True)
    if BIKEPOINTS_PATH.exists() and not force:
        gdf = gpd.read_parquet(BIKEPOINTS_PATH)
        log.info("bikepoints already built (%d rows)", len(gdf))
        return gdf
    data = _tfl_get("/BikePoint", cache_path=RAW_TRANSIT / "tfl_bikepoints.json", force=force)
    rows = []
    for b in data:
        props = {p.get("key"): p.get("value") for p in b.get("additionalProperties", [])}
        inst = props.get("InstallDate")
        rows.append(
            {
                "id": b.get("id"),
                "name": b.get("commonName"),
                "lat": b.get("lat"),
                "lon": b.get("lon"),
                "terminal_name": props.get("TerminalName"),
                "nb_docks": pd.to_numeric(props.get("NbDocks"), errors="coerce"),
                "installed": str(props.get("Installed")).lower() == "true",
                "locked": str(props.get("Locked")).lower() == "true",
                "temporary": str(props.get("Temporary")).lower() == "true",
                "install_date": pd.to_datetime(int(inst), unit="ms", utc=True).date().isoformat()
                if inst and inst.isdigit()
                else None,
            }
        )
    df = pd.DataFrame(rows).dropna(subset=["lat", "lon"])
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=CRS_WGS84)
    gdf["retrieved_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    gdf = gdf.sort_values("id").reset_index(drop=True)
    gdf.to_parquet(BIKEPOINTS_PATH, index=False)
    log.info("bikepoints: %d docking stations, %d docks total", len(gdf), int(gdf.nb_docks.fillna(0).sum()))
    return gdf


# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="+", choices=["stations", "bus", "bikepoints"], default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    steps = args.only or ["stations", "bus", "bikepoints"]
    report: dict[str, Any] = {"started_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    t0 = time.perf_counter()
    for step, fn in (
        ("stations", fetch_tfl_stations),
        ("bus", fetch_naptan_bus_stops),
        ("bikepoints", fetch_tfl_bikepoints),
    ):
        if step not in steps:
            continue
        t = time.perf_counter()
        try:
            gdf = fn(force=args.force)
            entry: dict[str, Any] = {"n_rows": int(len(gdf)), "seconds": round(time.perf_counter() - t, 1)}
            if "in_greater_london" in gdf:
                entry["n_in_greater_london"] = int(gdf.in_greater_london.sum())
            if step == "stations":
                entry["by_rail_mode"] = {m: int(gdf[f"mode_{m.replace('-', '_')}"].sum()) for m in TFL_MODES}
                entry["by_stop_type"] = gdf.stop_type.value_counts().to_dict()
            elif step == "bus":
                entry["by_stop_type"] = gdf.stop_type.value_counts().to_dict()
                entry["by_bus_stop_type"] = gdf.bus_stop_type.value_counts().to_dict()
            elif step == "bikepoints":
                entry["total_docks"] = int(gdf.nb_docks.fillna(0).sum())
            report[step] = entry
        except Exception as e:  # noqa: BLE001
            log.exception("step %s failed", step)
            report[step] = {"error": f"{type(e).__name__}: {e}"}
    report["seconds_total"] = round(time.perf_counter() - t0, 1)
    report["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    log.info("report -> %s", REPORT_PATH)
    return report


if __name__ == "__main__":
    main()
