"""H3 hexagonal grid utilities and area-weighted interpolation.

Design notes
------------
* Resolution 8 (~0.74 km², edge ~460 m) is the working scale for city-wide siting;
  resolution 9 (~0.11 km², edge ~174 m) is used for sensitivity to the MAUP.
* All heavy geometry work happens in British National Grid (EPSG:27700); H3 indexing
  is done in WGS84 (EPSG:4326) as required by H3.
"""

from __future__ import annotations

from collections.abc import Iterable

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon, mapping

BNG = "EPSG:27700"
WGS84 = "EPSG:4326"


def polygon_to_cells(geom: Polygon | MultiPolygon, resolution: int) -> set[str]:
    """H3 cells whose centroid falls inside geom (WGS84)."""
    geoms = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    cells: set[str] = set()
    for g in geoms:
        cells |= set(h3.geo_to_cells(mapping(g), resolution))
    return cells


def cells_to_gdf(cells: Iterable[str]) -> gpd.GeoDataFrame:
    """GeoDataFrame of hexagon polygons (WGS84) with centroid lat/lon and area."""
    cells = list(cells)
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in cells]
    lat = [h3.cell_to_latlng(c)[0] for c in cells]
    lng = [h3.cell_to_latlng(c)[1] for c in cells]
    area = [h3.cell_area(c, unit="km^2") for c in cells]
    return gpd.GeoDataFrame(
        {"h3": cells, "lat": lat, "lon": lng, "area_km2": area}, geometry=polys, crs=WGS84
    )


def make_h3_grid(boundary: gpd.GeoDataFrame | gpd.GeoSeries, resolution: int = 8) -> gpd.GeoDataFrame:
    """Hex grid covering a boundary. Cells are kept if their centroid is inside the boundary
    (H3 default), which keeps the grid free of half-cells at the edge."""
    geom = (
        boundary.to_crs(WGS84).union_all()
        if hasattr(boundary, "union_all")
        else boundary.to_crs(WGS84).unary_union
    )
    cells = polygon_to_cells(geom, resolution)
    gdf = cells_to_gdf(sorted(cells))
    gdf["resolution"] = resolution
    return gdf


def points_to_cells(gdf: gpd.GeoDataFrame, resolution: int = 8, col: str = "h3") -> gpd.GeoDataFrame:
    """Assign an H3 cell to each point geometry."""
    pts = gdf.to_crs(WGS84)
    out = gdf.copy()
    out[col] = [h3.latlng_to_cell(p.y, p.x, resolution) for p in pts.geometry]
    return out


def count_points_by_cell(
    points: gpd.GeoDataFrame, grid: gpd.GeoDataFrame, name: str, weight: str | None = None
) -> pd.Series:
    """Count (or sum a weight of) points per grid cell, aligned to grid order (missing -> 0)."""
    res = int(grid["resolution"].iloc[0]) if "resolution" in grid else h3.get_resolution(grid["h3"].iloc[0])
    p = points_to_cells(points, res)
    agg = p.groupby("h3")[weight].sum() if weight else p.groupby("h3").size()
    return grid["h3"].map(agg).fillna(0).rename(name)


def areal_interpolate(
    source: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    extensive: list[str] | None = None,
    intensive: list[str] | None = None,
    target_id: str = "h3",
) -> pd.DataFrame:
    """Area-weighted interpolation from source polygons (e.g. LSOA) to target polygons (hexes).

    * extensive variables (counts: population, households, EVs) are split proportionally to the
      intersected area share of the *source* polygon;
    * intensive variables (rates, shares) are averaged weighted by intersected area of the *target*.
    Caveat: uniform density inside a source polygon is assumed. For London LSOAs (~1,500 residents)
    this is acceptable at H3 res 8; a dasymetric refinement with building footprints is a natural upgrade.
    """
    extensive = extensive or []
    intensive = intensive or []
    s = source.to_crs(BNG).copy()
    t = target.to_crs(BNG)[[target_id, "geometry"]].copy()
    s["_src_area"] = s.geometry.area
    s["_sid"] = np.arange(len(s))
    inter = gpd.overlay(s, t, how="intersection", keep_geom_type=False)
    inter["_int_area"] = inter.geometry.area
    inter["_w_ext"] = inter["_int_area"] / inter["_src_area"]
    out = pd.DataFrame({target_id: target[target_id].values})
    for col in extensive:
        vals = (inter[col].astype(float) * inter["_w_ext"]).groupby(inter[target_id]).sum()
        out[col] = out[target_id].map(vals).fillna(0.0).values
    if intensive:
        tarea = inter.groupby(target_id)["_int_area"].sum()
        for col in intensive:
            num = (inter[col].astype(float) * inter["_int_area"]).groupby(inter[target_id]).sum()
            out[col] = out[target_id].map(num / tarea).values
    return out


def neighbours(cells: Iterable[str], k: int = 1) -> dict[str, list[str]]:
    """k-ring neighbours restricted to the provided cell set (for spatial lags / graph edges)."""
    cell_set = set(cells)
    return {c: [n for n in h3.grid_disk(c, k) if n != c and n in cell_set] for c in cell_set}
