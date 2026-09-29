"""Hex-centroid → point travel-time matrices (minutes), cached on disk.

Uses the OSM drive graph through igraph when `data/interim/osm/london_drive.graphml` exists;
otherwise falls back to a documented approximation (great-circle distance × 1.3 circuity at
22 km/h, the typical inner-London average speed) and records `method="approx"` so notebooks can
state which one was used.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox

from chargescape.utils.paths import INTERIM, PROCESSED

GRAPH_PATH = INTERIM / "osm" / "london_drive.graphml"
_GRAPH_CACHE: dict[str, object] = {}


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2[:, None] - p1[None, :]
    dl = np.radians(lon2)[:, None] - np.radians(lon1)[None, :]
    a = np.sin(dphi / 2) ** 2 + np.cos(p1)[None, :] * np.cos(p2)[:, None] * np.sin(dl / 2) ** 2
    return (2 * r * np.arcsin(np.sqrt(a))).T  # (len1, len2)


def load_road_graph():
    from chargescape.features.accessibility import RoadGraph

    if "rg" not in _GRAPH_CACHE:
        G = ox.load_graphml(GRAPH_PATH)
        _GRAPH_CACHE["rg"] = RoadGraph.from_networkx(G, weight="travel_time")
    return _GRAPH_CACHE["rg"]


def _signature(o_lat, o_lon, t_lat, t_lon, method: str) -> str:
    """Hash of origin/target coordinates (5 dp) and method, so a cache is reused only for the same inputs."""
    h = hashlib.sha1(method.encode())
    for a in (o_lat, o_lon, t_lat, t_lon):
        h.update(np.round(np.asarray(a, float), 5).tobytes())
    return h.hexdigest()[:16]


def travel_time_minutes(
    origins: gpd.GeoDataFrame,
    targets: gpd.GeoDataFrame,
    name: str,
    force_approx: bool = False,
    cache: bool = True,
) -> tuple[np.ndarray, str]:
    """Return (matrix in minutes of shape (origins, targets), method). Origins/targets need lat/lon columns
    or point geometries in WGS84. Results are cached in data/processed/tt_{name}.npz together with a
    signature of the inputs; a cache is reused only when the signature matches (so committed caches
    let the models run from a fresh clone without the road graph)."""
    o_lat, o_lon = _latlon(origins)
    t_lat, t_lon = _latlon(targets)
    cache_path = PROCESSED / f"tt_{name}.npz"
    meta_path = Path(str(cache_path) + ".json")
    use_graph = GRAPH_PATH.exists() and not force_approx
    if cache and cache_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        sigs = {_signature(o_lat, o_lon, t_lat, t_lon, m) for m in ("osm_igraph", "approx_haversine_22kmh")}
        if meta.get("sig") in sigs and (meta.get("method") == "osm_igraph" or not use_graph):
            return np.load(cache_path, allow_pickle=False)["tt"], meta["method"]
    if use_graph:
        rg = load_road_graph()
        src = rg.nearest_vertices(o_lon, o_lat)
        dst = rg.nearest_vertices(t_lon, t_lat)
        tt = rg.travel_time_matrix(src, dst) / 60.0
        tt = np.where(np.isfinite(tt), tt, np.nan).astype(np.float32)
        method = "osm_igraph"
    else:
        km = _haversine_km(o_lat, o_lon, t_lat, t_lon) * 1.3
        tt = (km / 22.0 * 60.0).astype(np.float32)
        method = "approx_haversine_22kmh"
    if cache:
        np.savez_compressed(cache_path, tt=tt)
        meta_path.write_text(
            json.dumps(
                {
                    "method": method,
                    "shape": list(tt.shape),
                    "sig": _signature(o_lat, o_lon, t_lat, t_lon, method),
                }
            )
        )
    return tt, method


def _latlon(gdf: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    if "lat" in gdf.columns and "lon" in gdf.columns:
        return gdf["lat"].to_numpy(float), gdf["lon"].to_numpy(float)
    g = gdf.to_crs(4326).geometry
    if (g.geom_type != "Point").any():
        g = gdf.to_crs(27700).geometry.centroid.to_crs(4326)
    return g.y.to_numpy(), g.x.to_numpy()
