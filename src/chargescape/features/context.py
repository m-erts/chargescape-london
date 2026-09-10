"""Context layers that need more than a point count: LAEI vehicle-km on road links, DFES EV
forecasts (2030 scenarios) and primary-substation headroom (grid constraint proxy)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from chargescape.features.grid import BNG, areal_interpolate
from chargescape.utils.io import read_gdf
from chargescape.utils.paths import INTERIM


def laei_vkm_by_hex(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Daily vehicle-km per hex from LAEI 2022 major-road links (length-apportioned) plus minor-road
    1 km grid (area-apportioned). Separate columns for cars, taxis and PHVs."""
    links = read_gdf(INTERIM / "traffic" / "laei2022_major_roads_flows.parquet").to_crs(BNG)
    links = links[links.geometry.notna()].copy()
    g = grid.to_crs(BNG)[["h3", "geometry"]]
    inter = gpd.overlay(
        links[["toid", "aadf_cars", "aadf_taxis", "aadf_phvs", "aadf_total", "geometry"]],
        g,
        how="intersection",
        keep_geom_type=False,
    )
    inter["len_km"] = inter.geometry.length / 1000.0
    out = pd.DataFrame({"h3": grid["h3"].values})
    for col, name in (
        ("aadf_total", "vkm_major_total"),
        ("aadf_cars", "vkm_major_cars"),
        ("aadf_taxis", "vkm_major_taxi"),
        ("aadf_phvs", "vkm_major_phv"),
    ):
        s = (inter[col].fillna(0) * inter["len_km"]).groupby(inter["h3"]).sum()
        out[name] = out["h3"].map(s).fillna(0.0).values
    minor = read_gdf(INTERIM / "traffic" / "laei2022_minor_roads_vkm_1km.parquet").to_crs(BNG)
    mcols = {"vkm_cars": "vkm_minor_cars", "vkm_taxis": "vkm_minor_taxi", "vkm_phvs": "vkm_minor_phv"}
    vcols = [c for c in minor.columns if c.startswith("vkm_")]
    minor[vcols] = minor[vcols] / 365.0  # LAEI minor-road grid is annual vehicle-km; convert to per day
    minor["vkm_minor_total"] = minor[vcols].sum(axis=1)
    m = areal_interpolate(minor.rename(columns=mcols), grid, extensive=[*mcols.values(), "vkm_minor_total"])
    out = out.merge(m, on="h3", how="left")
    out["vkm_total"] = out["vkm_major_total"] + out["vkm_minor_total"].fillna(0)
    out["vkm_taxi_phv"] = (
        out[["vkm_major_taxi", "vkm_major_phv", "vkm_minor_taxi", "vkm_minor_phv"]].fillna(0).sum(axis=1)
    )
    return out


def dfes_2030_by_hex(grid: gpd.GeoDataFrame, year: int = 2030) -> pd.DataFrame:
    """BEV + PHEV cars per hex in `year` for three DFES 2026 pathways (high/mid/low uptake)."""
    d = pd.read_parquet(INTERIM / "ukpn" / "dfes2026_lsoa_london_ev.parquet")
    d = d[d["technology"] == "cars"]
    ycol = f"y{year}"
    piv = d.pivot_table(index="lsoa21cd", columns=["pathway", "parameter"], values=ycol, aggfunc="sum")
    piv.columns = [f"{p}|{q}" for p, q in piv.columns]
    piv = piv.reset_index()
    lsoa = read_gdf(INTERIM / "census" / "lsoa21_london.parquet")[["lsoa21cd", "geometry"]]
    src = gpd.GeoDataFrame(lsoa.merge(piv, on="lsoa21cd", how="left"), geometry="geometry", crs=lsoa.crs)
    cols = [c for c in piv.columns if c != "lsoa21cd"]
    out = areal_interpolate(src.fillna({c: 0 for c in cols}), grid, extensive=cols)
    mapping = {"ElectricEngagement": "high", "HolisticTransition": "mid", "FallingBehind": "low"}
    res = pd.DataFrame({"h3": out["h3"]})
    for pw, tag in mapping.items():
        bev = [c for c in cols if c.startswith(pw + "|") and "BEV" in c]
        phev = [c for c in cols if c.startswith(pw + "|") and "PHEV" in c]
        res[f"bev_{year}_{tag}"] = out[bev].sum(axis=1) if bev else np.nan
        res[f"phev_{year}_{tag}"] = out[phev].sum(axis=1) if phev else np.nan
    return res


def headroom_by_hex(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Primary substation supply-area attributes at each hex centroid (summer 2026 baseline)."""
    hr = read_gdf(INTERIM / "ukpn" / "headroom_primary_areas_summer2026.parquet").to_crs(BNG)
    cent = grid.to_crs(BNG)[["h3", "geometry"]].copy()
    cent["geometry"] = cent.geometry.centroid
    j = gpd.sjoin(
        cent,
        hr[["primary", "firmcapacitysummer", "firmcapacitywinter", "demand", "demandrag", "geometry"]],
        how="left",
        predicate="within",
    )
    j = j[~j.index.duplicated()]
    out = pd.DataFrame({"h3": grid["h3"].values})
    out["primary_substation"] = j["primary"].values
    out["firm_capacity_mva"] = pd.to_numeric(j["firmcapacitysummer"], errors="coerce").values
    out["demand_pct_of_firm"] = pd.to_numeric(j["demand"], errors="coerce").values
    out["headroom_rag"] = j["demandrag"].astype(str).str.upper().str.strip().values
    return out
