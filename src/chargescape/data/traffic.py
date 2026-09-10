"""Traffic: DfT road traffic statistics (AADF + raw hourly counts) for London, and LAEI road flows.

Sources
-------
* DfT Road Traffic Statistics (OGL v3) - per-region CSV extracts hosted on GCS:
    aadf:      .../downloads/aadf/region_id/dft_aadf_region_id_6.csv        (London, 2000-2025)
    rawcount:  .../downloads/rawcount/region_id/dft_rawcount_region_id_6.csv (hourly manual counts)
  Region id 6 == London (ONS E12000007); 33 local authorities incl. City of London.
* London Atmospheric Emissions Inventory (LAEI), London Datastore (GLA / TfL):
    LAEI 2022 traffic flows & speeds, major roads (gpkg, 79,437 TOID links, EPSG:27700) and
    minor roads (1 km grid vkm); LAEI 2019 major-road flows shapefile.  No login required.

Outputs (data/interim/traffic/)
-------
  dft_aadf_london.parquet          count-point x year AADF (all years 2000-2025, London only)
  dft_rawcount_london.parquet      hourly manual counts (count point x date x hour x direction)
  laei2022_major_roads_flows.parquet   GeoParquet (EPSG:27700) TOID links with AADF by vehicle type
  laei2022_minor_roads_vkm_1km.parquet GeoParquet (EPSG:4326) 1 km grid vehicle-km by type
  laei2019_major_roads_flows.parquet   GeoParquet (EPSG:27700) 2019 base-year links

Run:  PYTHONPATH=src python -m chargescape.data.traffic
Idempotent: downloads are skipped if present; parquet files are rebuilt from raw (fast).
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

from chargescape.utils.http import download
from chargescape.utils.paths import INTERIM, RAW

DFT_BASE = "https://storage.googleapis.com/dft-statistics/road-traffic/downloads"
LONDON_REGION_ID = 6
DFT_URLS = {
    "aadf": f"{DFT_BASE}/aadf/region_id/dft_aadf_region_id_{LONDON_REGION_ID}.csv",
    "rawcount": f"{DFT_BASE}/rawcount/region_id/dft_rawcount_region_id_{LONDON_REGION_ID}.csv",
    "metadata_pdf": "https://storage.googleapis.com/dft-statistics/road-traffic/all-traffic-data-metadata.pdf",
}
LAEI_URLS = {
    # LAEI 2022 (GLA/TfL, London Datastore dataset 2lg5g) - traffic flows & speeds, major + minor roads
    "laei2022_flows_gis": "https://data.london.gov.uk/download/2lg5g/95w/LAEI2022-Traffic-Flows-and-Speeds-Major-and-Minor-Roads-GIS.zip",
    # LAEI 2019 (dataset e758q) - major roads, unique TOIDs, flows & speeds (shapefile, OSGB)
    "laei2019_major_roads": "https://data.london.gov.uk/download/e758q/64fa10ab-7b0a-4de7-b4d9-5f7a3b471ed1/laei-2019-major-roads-final-unique-toids-flows-speeds-osgb.zip",
}

RAW_DFT = RAW / "traffic" / "dft"
RAW_LAEI = RAW / "traffic" / "laei"
OUT = INTERIM / "traffic"

AADF_KEEP = [
    "count_point_id",
    "year",
    "region_id",
    "local_authority_id",
    "local_authority_name",
    "local_authority_ons",
    "road_name",
    "road_type",
    "road_category",
    "start_junction_road_name",
    "end_junction_road_name",
    "easting",
    "northing",
    "latitude",
    "longitude",
    "link_length_km",
    "estimation_method",
    "estimation_method_detailed",
    "pedal_cycles",
    "two_wheeled_motor_vehicles",
    "cars_and_taxis",
    "buses_and_coaches",
    "lgvs",
    "all_hgvs",
    "all_motor_vehicles",
]


def road_category(road_name: str, road_type: str) -> str:
    """Coarse DfT-style category from the road name prefix (M / A / B / C / U)."""
    n = (road_name or "").strip().upper()
    if n.startswith("M") or n.startswith("A") and "(M)" in n:
        return "M"
    if n.startswith("A"):
        return "A"
    if n.startswith("B"):
        return "B"
    if n.startswith("C"):
        return "C"
    if n.startswith("U") or road_type == "Minor":
        return "U"
    return "other"


# --------------------------------------------------------------------------- DfT
def build_dft_aadf() -> pd.DataFrame:
    src = download(DFT_URLS["aadf"], RAW_DFT / "dft_aadf_region_id_6.csv", timeout=600)
    df = pd.read_csv(src, low_memory=False)
    df = df[df.region_id == LONDON_REGION_ID].copy()
    # ONS LA codes from the DfT lookup API snapshot (kept in raw for provenance)
    la = _local_authorities()
    df["local_authority_ons"] = df.local_authority_id.map(la)
    df["road_category"] = [road_category(a, b) for a, b in zip(df.road_name, df.road_type, strict=True)]
    out = df[AADF_KEEP].sort_values(["count_point_id", "year"]).reset_index(drop=True)
    for c in ("count_point_id", "year", "local_authority_id", "easting", "northing"):
        out[c] = out[c].astype("int32")
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / "dft_aadf_london.parquet", index=False)
    return out


def build_dft_rawcount() -> pd.DataFrame:
    src = download(DFT_URLS["rawcount"], RAW_DFT / "dft_rawcount_region_id_6.csv", timeout=900)
    df = pd.read_csv(src, low_memory=False)
    df = df[df.region_id == LONDON_REGION_ID].copy()
    df["count_date"] = pd.to_datetime(df.count_date)
    keep = [
        "count_point_id",
        "direction_of_travel",
        "year",
        "count_date",
        "hour",
        "local_authority_id",
        "local_authority_name",
        "road_name",
        "road_type",
        "easting",
        "northing",
        "latitude",
        "longitude",
        "pedal_cycles",
        "two_wheeled_motor_vehicles",
        "cars_and_taxis",
        "buses_and_coaches",
        "lgvs",
        "all_hgvs",
        "all_motor_vehicles",
    ]
    out = (
        df[keep]
        .sort_values(["count_point_id", "count_date", "hour", "direction_of_travel"])
        .reset_index(drop=True)
    )
    for c in ("count_point_id", "year", "hour", "local_authority_id", "easting", "northing"):
        out[c] = out[c].astype("int32")
    out.to_parquet(OUT / "dft_rawcount_london.parquet", index=False)
    return out


def _local_authorities() -> dict[int, str]:
    """DfT local-authority id -> ONS code, cached from the roadtraffic API."""
    from chargescape.utils.http import get_json

    rows = get_json("https://roadtraffic.dft.gov.uk/api/local-authorities", cache_dir=RAW_DFT / "api")
    return {int(r["id"]): r.get("ons_code") for r in rows}


# --------------------------------------------------------------------------- LAEI
def _unzip(zp: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        for m in z.namelist():
            if m.startswith("__MACOSX/") or m.endswith("/"):
                continue
            target = dest / Path(m).name
            if not target.exists():
                with z.open(m) as f, open(target, "wb") as g:
                    g.write(f.read())
    return dest


def build_laei() -> dict[str, int]:
    counts = {}
    z22 = download(
        LAEI_URLS["laei2022_flows_gis"],
        RAW_LAEI / "LAEI2022-Traffic-Flows-and-Speeds-Major-and-Minor-Roads-GIS.zip",
        timeout=600,
    )
    d22 = _unzip(z22, RAW_LAEI / "extracted")
    major = gpd.read_file(d22 / "LAEI2022-major-roads-flows-and-speeds.gpkg")
    major.columns = [c.replace(".", "_").lower() for c in major.columns]
    major["in_gla"] = major["laei_zone"].ne("Non-GLA")
    aadf_cols = [c for c in major.columns if c.startswith("aadf_")]
    major["aadf_total"] = major[aadf_cols].sum(axis=1)
    major.to_parquet(OUT / "laei2022_major_roads_flows.parquet", index=False)
    counts["laei2022_major_roads_flows"] = len(major)

    minor = gpd.read_file(d22 / "LAEI2022-minor-roads-flows-and-speeds.gpkg")
    minor.columns = [c.replace(".", "_").lower() for c in minor.columns]
    minor["in_gla"] = minor["laei_zone"].ne("Non-GLA")
    minor.to_parquet(OUT / "laei2022_minor_roads_vkm_1km.parquet", index=False)
    counts["laei2022_minor_roads_vkm_1km"] = len(minor)

    z19 = download(
        LAEI_URLS["laei2019_major_roads"],
        RAW_LAEI / "laei-2019-major-roads-final-unique-toids-flows-speeds-osgb.zip",
        timeout=600,
    )
    d19 = _unzip(z19, RAW_LAEI / "extracted" / "laei2019")
    m19 = gpd.read_file(d19 / "laei-2019-major-roads-final-unique-toids-flows-speeds-osgb.shp")
    m19.columns = [c.lower() for c in m19.columns]
    m19["in_gla"] = m19["laeizone"].ne("Non-GLA")
    m19.to_parquet(OUT / "laei2019_major_roads_flows.parquet", index=False)
    counts["laei2019_major_roads_flows"] = len(m19)
    return counts


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    download(DFT_URLS["metadata_pdf"], RAW_DFT / "all-traffic-data-metadata.pdf", timeout=300)
    aadf = build_dft_aadf()
    latest = aadf.year.max()
    print(
        f"[traffic] dft_aadf_london: rows={len(aadf):,} count_points={aadf.count_point_id.nunique():,} years={aadf.year.min()}-{latest}"
    )
    print(aadf[aadf.year == latest].groupby("road_type").size().rename("count_points_latest").to_string())
    raw = build_dft_rawcount()
    print(
        f"[traffic] dft_rawcount_london: rows={len(raw):,} count_points={raw.count_point_id.nunique():,} years={raw.year.min()}-{raw.year.max()}"
    )
    counts = build_laei()
    print(f"[traffic] LAEI: {counts}")
    summary = {
        "dft_aadf_london": {
            "rows": int(len(aadf)),
            "count_points": int(aadf.count_point_id.nunique()),
            "years": [int(aadf.year.min()), int(latest)],
        },
        "dft_rawcount_london": {
            "rows": int(len(raw)),
            "count_points": int(raw.count_point_id.nunique()),
            "years": [int(raw.year.min()), int(raw.year.max())],
        },
        **{k: {"rows": v} for k, v in counts.items()},
    }
    (OUT / "_summary.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
