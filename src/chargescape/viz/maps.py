"""Interactive map export with pydeck (deck.gl) — no API token needed (Carto basemap)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk

LONDON_VIEW = pdk.ViewState(latitude=51.505, longitude=-0.12, zoom=9.3, pitch=0)


def _color_scale(
    values: pd.Series,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    alpha: int = 180,
) -> list[list[int]]:
    import matplotlib

    v = values.astype(float).to_numpy()
    lo = np.nanpercentile(v, 2) if vmin is None else vmin
    hi = np.nanpercentile(v, 98) if vmax is None else vmax
    norm = np.clip((v - lo) / (hi - lo + 1e-12), 0, 1)
    cm = matplotlib.colormaps[cmap]
    rgba = (cm(norm) * 255).astype(int)
    return [[int(r), int(g), int(b), alpha] for r, g, b, _ in rgba]


def h3_layer(
    df: pd.DataFrame,
    value_col: str,
    h3_col: str = "h3",
    cmap: str = "viridis",
    elevation: bool = False,
    elevation_scale: float = 1.0,
    tooltip_cols: list[str] | None = None,
    **kw,
) -> pdk.Layer:
    d = df[[h3_col, value_col] + [c for c in (tooltip_cols or []) if c not in (h3_col, value_col)]].copy()
    d["fill"] = _color_scale(d[value_col], cmap)
    return pdk.Layer(
        "H3HexagonLayer",
        d,
        get_hexagon=h3_col,
        get_fill_color="fill",
        get_elevation=value_col if elevation else 0,
        elevation_scale=elevation_scale if elevation else 0,
        extruded=elevation,
        pickable=True,
        stroked=False,
        opacity=0.9,
        **kw,
    )


def point_layer(
    df: pd.DataFrame,
    lon: str = "lon",
    lat: str = "lat",
    color: tuple[int, int, int, int] = (230, 80, 30, 200),
    radius: int = 40,
    radius_col: str | None = None,
    **kw,
) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position=[lon, lat],
        get_fill_color=list(color),
        get_radius=radius_col or radius,
        radius_min_pixels=2,
        radius_max_pixels=30,
        pickable=True,
        **kw,
    )


def to_html(
    layers: list[pdk.Layer],
    path: Path | str,
    tooltip: dict | str | None = None,
    view: pdk.ViewState = LONDON_VIEW,
    map_style: str = "light",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_provider="carto",
        map_style=map_style,
        tooltip=tooltip or True,
    )
    deck.to_html(str(path), open_browser=False)
    return path
