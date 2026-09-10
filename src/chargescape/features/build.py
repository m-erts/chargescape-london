"""Build the hexagon feature table: demand-side (Census, EV licensing), supply-side (chargers),
activity (POI, transit, traffic) and network accessibility. Layers that are not yet downloaded are
skipped with a message, so the build degrades gracefully.

Run: PYTHONPATH=src python -m chargescape.features.build --res 8
"""

from __future__ import annotations

import argparse
import time

import geopandas as gpd
import numpy as np
import pandas as pd

from chargescape.features.context import dfes_2030_by_hex, headroom_by_hex, laei_vkm_by_hex
from chargescape.features.grid import WGS84, areal_interpolate, count_points_by_cell, make_h3_grid
from chargescape.features.supply import dedupe_within, harmonise_chargers, supply_features
from chargescape.utils.io import read_gdf, write_gdf
from chargescape.utils.paths import INTERIM, PROCESSED

EXTENSIVE = [
    "population",
    "households",
    "cars_est",
    "hh_no_car",
    "workers_16plus",
    "piv_total_est",
    "piv_private_est",
    "piv_company_est",
    "bev_est",
    "bev_private_est",
    "phev_petrol_est",
    "phev_diesel_est",
    "reev_est",
    "cars_licensed_est",
    "cars_licensed_private_est",
]
INTENSIVE = [
    "share_no_car",
    "cars_per_household",
    "share_flat",
    "share_house",
    "share_owner_occupied",
    "share_private_rented",
    "share_social_rented",
    "share_drive_to_work",
    "share_wfh",
    "share_nssec_higher_managerial",
    "share_age_65plus",
    "imd_score",
    "income_score",
    "pop_density_km2",
]

POI_GROUPS = {
    "poi_retail": ["supermarket", "retail"],
    "poi_food": ["food"],
    "poi_hotel": ["hotel"],
    "poi_leisure": ["leisure"],
    "poi_parking": ["parking"],
    "poi_fuel": ["fuel"],
    "poi_car": ["car"],
    "poi_office": ["office"],
    "poi_health_edu": ["health", "education"],
}


def _log(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}")


def demand_side(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    lsoa = read_gdf(INTERIM / "census" / "lsoa21_london.parquet")
    feats = pd.read_parquet(INTERIM / "census" / "lsoa21_london_features.parquet")
    ev = pd.read_parquet(INTERIM / "vehicles" / "ev_by_lsoa_london_latest.parquet")
    ev_cols = [c for c in EXTENSIVE if c in ev.columns and c not in feats.columns]
    src = (
        lsoa[["lsoa21cd", "geometry"]]
        .merge(feats, on="lsoa21cd", how="left")
        .merge(ev[["lsoa21cd", *ev_cols]], on="lsoa21cd", how="left")
    )
    src = gpd.GeoDataFrame(src, geometry="geometry", crs=lsoa.crs)
    ext = [c for c in EXTENSIVE if c in src.columns]
    inten = [c for c in INTENSIVE if c in src.columns]
    out = areal_interpolate(src, grid, extensive=ext, intensive=inten)
    # derived quantities
    out["phev_est"] = out[[c for c in ("phev_petrol_est", "phev_diesel_est", "reev_est") if c in out]].sum(
        axis=1
    )
    out["piv_private_per_1000_hh"] = 1000 * out["piv_private_est"] / out["households"].replace(0, np.nan)
    out["share_no_offstreet"] = out["share_flat"].clip(
        0, 1
    )  # proxy: flats ≈ no private driveway (documented caveat)
    return out


def supply_side(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    osm = read_gdf(INTERIM / "chargepoints" / "osm_charging_stations.parquet")
    ncr = read_gdf(INTERIM / "chargepoints" / "ncr_archive_london_2021.parquet")
    sites = dedupe_within(harmonise_chargers(osm, ncr))
    write_gdf(sites, PROCESSED / "charging_sites.parquet")
    return supply_features(grid, sites)


def activity_side(grid: gpd.GeoDataFrame) -> pd.DataFrame | None:
    p = INTERIM / "osm" / "pois.parquet"
    if not p.exists():
        print("  pois.parquet not found — skipping POI features")
        return None
    pois = read_gdf(p, WGS84)
    pois = pois[pois.geometry.geom_type == "Point"] if (pois.geometry.geom_type != "Point").any() else pois
    out = pd.DataFrame({"h3": grid["h3"].values})
    for name, cats in POI_GROUPS.items():
        sub = pois[pois["category"].isin(cats)]
        out[name] = count_points_by_cell(sub, grid, name).values if len(sub) else 0.0
    if "capacity" in pois.columns:
        park = pois[pois["category"] == "parking"].copy()
        park["cap"] = pd.to_numeric(park["capacity"], errors="coerce")
        out["parking_capacity_known"] = (
            count_points_by_cell(park.dropna(subset=["cap"]), grid, "cap", weight="cap").values
            if len(park)
            else 0.0
        )
    out["poi_total"] = out[[c for c in out.columns if c.startswith("poi_")]].sum(axis=1)
    return out


def transit_side(grid: gpd.GeoDataFrame) -> pd.DataFrame | None:
    out = pd.DataFrame({"h3": grid["h3"].values})
    found = False
    p = INTERIM / "transit" / "tfl_stations.parquet"
    if p.exists():
        st = pd.read_parquet(p)
        g = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st["lon"], st["lat"]), crs=WGS84)
        out["n_rail_stations"] = count_points_by_cell(g, grid, "n_rail_stations").values
        found = True
    p = INTERIM / "transit" / "naptan_bus_stops_london.parquet"
    if p.exists():
        bs = pd.read_parquet(p)
        loncol = "lon" if "lon" in bs.columns else "Longitude"
        latcol = "lat" if "lat" in bs.columns else "Latitude"
        g = gpd.GeoDataFrame(bs, geometry=gpd.points_from_xy(bs[loncol], bs[latcol]), crs=WGS84)
        out["n_bus_stops"] = count_points_by_cell(g, grid, "n_bus_stops").values
        found = True
    return out if found else None


def traffic_side(grid: gpd.GeoDataFrame) -> pd.DataFrame | None:
    p = INTERIM / "traffic" / "dft_aadf_london.parquet"
    if not p.exists():
        print("  dft_aadf_london.parquet not found — skipping traffic features")
        return None
    df = pd.read_parquet(p)
    if "year" in df.columns:
        df = df[df["year"] == df["year"].max()]
    loncol = "lon" if "lon" in df.columns else "longitude"
    latcol = "lat" if "lat" in df.columns else "latitude"
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[loncol], df[latcol]), crs=WGS84)
    valcol = (
        "all_motor_vehicles"
        if "all_motor_vehicles" in g.columns
        else [c for c in g.columns if "motor" in c.lower()][0]
    )
    out = pd.DataFrame({"h3": grid["h3"].values})
    out["n_count_points"] = count_points_by_cell(g, grid, "n_count_points").values
    out["aadf_sum"] = count_points_by_cell(g, grid, "aadf_sum", weight=valcol).values
    # smooth with neighbours later in the model layer; keep raw here
    return out


def build(res: int = 8) -> gpd.GeoDataFrame:
    t0 = time.time()
    boundary = read_gdf(INTERIM / "census" / "greater_london.parquet")
    grid = make_h3_grid(boundary, res)
    _log(f"grid res {res}: {len(grid)} hexes", t0)
    parts = [demand_side(grid)]
    _log("demand side interpolated", t0)
    parts.append(supply_side(grid))
    _log("supply side done", t0)
    for fn in (activity_side, transit_side, traffic_side, laei_vkm_by_hex, dfes_2030_by_hex, headroom_by_hex):
        r = fn(grid)
        if r is not None:
            parts.append(r)
            _log(f"{fn.__name__} done", t0)
    feats = grid.copy()
    for p in parts:
        feats = feats.merge(p, on="h3", how="left")
    # borough label for spatial CV and reporting (majority by area via LSOA lookup)
    lsoa = read_gdf(INTERIM / "census" / "lsoa21_london.parquet")
    if "lad22nm" not in lsoa.columns or "inner_london" not in lsoa.columns:
        lk = pd.read_parquet(INTERIM / "census" / "lsoa21_london_features.parquet")[
            ["lsoa21cd", "lad22nm", "inner_london"]
        ]
        lsoa = lsoa.drop(columns=[c for c in ("lad22nm", "inner_london") if c in lsoa.columns]).merge(
            lk, on="lsoa21cd"
        )
    cent = feats[["h3", "geometry"]].copy()
    cent["geometry"] = cent.to_crs(27700).geometry.centroid
    j = gpd.sjoin(
        cent.set_crs(27700, allow_override=True),
        lsoa.to_crs(27700)[["lad22nm", "inner_london", "geometry"]],
        how="left",
        predicate="within",
    )
    j = j[~j.index.duplicated()]
    feats["borough"] = j["lad22nm"].values
    feats["inner_london"] = j["inner_london"].values
    out = PROCESSED / f"hex_features_r{res}.small.parquet"
    write_gdf(feats, out)
    _log(f"wrote {out} ({feats.shape})", t0)
    return feats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=8)
    a = ap.parse_args()
    build(a.res)
