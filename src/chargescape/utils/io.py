"""I/O helpers: GeoParquet round-trips and light GeoJSON export."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


def read_gdf(path: Path | str, crs: str | int | None = None) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path)
    if crs is not None and (gdf.crs is None or gdf.crs.to_string() != str(crs)):
        gdf = gdf.to_crs(crs)
    return gdf


def write_gdf(gdf: gpd.GeoDataFrame, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path, index=False)
    return path


def write_df(df: pd.DataFrame, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
