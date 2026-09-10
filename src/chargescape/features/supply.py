"""Supply-side features: existing chargers per hex and distance to the nearest rapid hub.

Two observed sources are combined deliberately:
* OpenStreetMap 2026 — current but hub-biased (1.3k features vs ~31k official chargers);
  strong for rapid/ultra-rapid hubs, weak for lamp-post chargers.
* National Chargepoint Registry snapshot (May 2021) — complete for its date (6.7k London devices),
  with rated kW on every device; stale for hubs opened since.
The features therefore separate `rapid` (>= 50 kW, OSM 2026 ∪ NCR 2021 de-duplicated within 50 m)
from `slow` (< 50 kW, NCR 2021 only, scaled to DfT borough totals in the model layer).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from chargescape.features.grid import BNG, WGS84, count_points_by_cell

RAPID_KW = 50.0


def harmonise_chargers(osm: gpd.GeoDataFrame, ncr: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One table of charging sites with columns: site_id, source, year, max_kw, n_ports, is_rapid, geometry (WGS84)."""
    o = osm.to_crs(WGS84)[
        ["osm_id", "max_power_kw", "n_sockets", "capacity_int", "operator", "geometry"]
    ].copy()
    o["site_id"] = "osm_" + o["osm_id"].astype(str)
    o["source"], o["year"] = "osm", 2026
    o["max_kw"] = pd.to_numeric(o["max_power_kw"], errors="coerce")
    o["n_ports"] = (
        pd.to_numeric(o["capacity_int"], errors="coerce")
        .fillna(pd.to_numeric(o["n_sockets"], errors="coerce"))
        .fillna(1)
        .clip(lower=1)
    )
    n = ncr.to_crs(WGS84)[
        ["chargeDeviceID", "max_rated_kw", "n_connectors", "deviceControllerName", "geometry"]
    ].copy()
    n["site_id"] = "ncr_" + n["chargeDeviceID"].astype(str)
    n["source"], n["year"] = "ncr", 2021
    n["max_kw"] = pd.to_numeric(n["max_rated_kw"], errors="coerce")
    n["n_ports"] = pd.to_numeric(n["n_connectors"], errors="coerce").fillna(1).clip(lower=1)
    n = n.rename(columns={"deviceControllerName": "operator"})
    cols = ["site_id", "source", "year", "max_kw", "n_ports", "operator", "geometry"]
    out = pd.concat([o[cols], n[cols]], ignore_index=True)
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=WGS84)
    out["is_rapid"] = out["max_kw"].fillna(0) >= RAPID_KW
    return out


def dedupe_within(sites: gpd.GeoDataFrame, radius_m: float = 50.0, prefer: str = "osm") -> gpd.GeoDataFrame:
    """Drop NCR devices that have an OSM feature within radius_m (same physical site)."""
    s = sites.to_crs(BNG)
    a = s[s.source == prefer]
    b = s[s.source != prefer]
    if a.empty or b.empty:
        return sites
    tree = cKDTree(np.c_[a.geometry.x, a.geometry.y])
    d, _ = tree.query(np.c_[b.geometry.x, b.geometry.y], k=1)
    keep = b.index[d > radius_m]
    return sites.loc[a.index.union(keep)].copy()


def supply_features(grid: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> pd.DataFrame:
    """Per-hex counts, ports, kW and distance (m, straight line) to nearest rapid site."""
    rapid = sites[sites.is_rapid]
    slow = sites[~sites.is_rapid]
    out = pd.DataFrame({"h3": grid["h3"].values})
    out["n_sites_rapid"] = count_points_by_cell(rapid, grid, "n_sites_rapid").values
    out["n_sites_slow"] = count_points_by_cell(slow, grid, "n_sites_slow").values
    out["ports_rapid"] = count_points_by_cell(rapid, grid, "ports_rapid", weight="n_ports").values
    out["ports_slow"] = count_points_by_cell(slow, grid, "ports_slow", weight="n_ports").values
    kw = sites.assign(kw_total=sites["max_kw"].fillna(7.0) * sites["n_ports"])
    out["kw_installed"] = count_points_by_cell(kw, grid, "kw_installed", weight="kw_total").values
    g = grid.to_crs(BNG)
    cent = np.c_[g.geometry.centroid.x, g.geometry.centroid.y]
    if len(rapid):
        r = rapid.to_crs(BNG)
        d, _ = cKDTree(np.c_[r.geometry.x, r.geometry.y]).query(cent, k=1)
        out["dist_rapid_m"] = d
    else:
        out["dist_rapid_m"] = np.nan
    return out
