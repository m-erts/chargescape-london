"""Static figure helpers (matplotlib) with a consistent look for the notebooks and README."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import FIGURES, INTERIM

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def boroughs() -> gpd.GeoDataFrame:
    return read_gdf(INTERIM / "census" / "lad24_london.parquet").to_crs(27700)


def hex_map(
    gdf: gpd.GeoDataFrame,
    col: str,
    title: str,
    cmap: str = "viridis",
    vmin=None,
    vmax=None,
    ax=None,
    legend_label: str | None = None,
    log: bool = False,
    scheme: str | None = None,
    k: int = 6,
    points: gpd.GeoDataFrame | None = None,
    point_kw: dict | None = None,
):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 6.5))
    g = gdf.to_crs(27700)
    vals = g[col].astype(float)
    if log:
        vals = np.log10(vals.clip(lower=1e-9))
        g = g.assign(**{col: vals})
    if scheme:
        g.plot(
            column=col,
            cmap=cmap,
            scheme=scheme,
            k=k,
            ax=ax,
            linewidth=0,
            legend=True,
            legend_kwds={
                "loc": "lower right",
                "fontsize": 7,
                "title": legend_label or col,
                "title_fontsize": 7,
                "frameon": False,
            },
            missing_kwds={"color": "#eeeeee"},
        )
    else:
        g.plot(
            column=col,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            ax=ax,
            linewidth=0,
            legend=True,
            legend_kwds={"label": legend_label or col, "shrink": 0.6},
            missing_kwds={"color": "#eeeeee"},
        )
    boroughs().boundary.plot(ax=ax, color="white", linewidth=0.4)
    if points is not None and len(points):
        points.to_crs(27700).plot(
            ax=ax, **({"color": "#e4572e", "markersize": 6, "alpha": 0.8} | (point_kw or {}))
        )
    ax.set_axis_off()
    ax.set_title(title, loc="left")
    return ax


def save(fig, name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    p = FIGURES / name
    fig.savefig(p, bbox_inches="tight")
    return p


def barh(
    series: pd.Series, title: str, xlabel: str = "", ax=None, top: int | None = None, color: str = "#2a6f97"
):
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7, 0.28 * (top or len(series)) + 1))
    s = series.sort_values(ascending=True)
    if top:
        s = s.tail(top)
    ax.barh(s.index.astype(str), s.values, color=color)
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", alpha=0.3)
    return ax
