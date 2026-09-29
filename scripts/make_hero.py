"""Three-panel hero figure for the README and the project page: demand → queues → new hubs."""

from __future__ import annotations

import json
import shutil

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import DOCS, FIGURES, PROCESSED, TABLES
from chargescape.utils.reference import boroughs


def main() -> None:
    k = json.loads((TABLES / "key_numbers.json").read_text())
    feats = read_gdf(PROCESSED / "hex_features_r8.small.parquet").to_crs(27700)
    dem = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
    d26 = dem[dem.scenario == "2026"].set_index("h3")
    svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet").set_index("h3")
    sites = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
    sites = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(sites.lon, sites.lat), crs=4326).to_crs(27700)
    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    hubs = feats.set_index("h3").loc[sel[(sel.budget_m == 20) & (sel.model == "p50")].h3].reset_index()
    hubs["geometry"] = hubs.geometry.centroid
    b = boroughs()

    feats["demand"] = feats.h3.map(d26.total_kwh_p50) / 1e3
    served = feats.h3.map(svc.served_share).fillna(0)
    wait = feats.h3.map(svc.expected_wait_min).fillna(0)
    feats["unmet"] = feats.h3.map(svc.unserved_sessions_day).fillna(0) + feats.h3.map(
        svc.rapid_sessions_day
    ).fillna(0) * served * np.clip(wait / 30, 0, 1)

    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6), facecolor="white")
    d = k["demand_gwh"]["2026"]
    r20 = next((r for r in k.get("siting", []) if abs(r["budget_m"] - 20) < 1e-9), None)
    titles = [
        f"1  Demand 2026: {d['total_p50']:.0f} GWh/yr (P10–P90 {d['total_p10']:.0f}–{d['total_p90']:.0f})",
        f"2  Peak-hour queues: {k['sites_pwait_gt_50']} of {k['rapid_sites']} rapid sites P(wait) > 0.5",
        f"3  £20M: {r20['n_hubs']} hubs serve {100 * r20['coverage_share']:.0f} % of unmet demand"
        if r20
        else "3  New hubs",
    ]
    feats.plot(column="demand", cmap="viridis", scheme="quantiles", k=7, ax=axes[0], linewidth=0)
    b.boundary.plot(ax=axes[1], color="#9aa5b1", linewidth=0.5)
    s = sites.sort_values("p_wait")
    s.plot(
        ax=axes[1],
        column="p_wait",
        cmap="RdYlGn_r",
        vmin=0,
        vmax=1,
        markersize=np.clip(np.sqrt(s.sessions_day) * 3, 4, 60),
        alpha=0.85,
        linewidth=0,
    )
    feats.plot(column="unmet", cmap="Greys", scheme="quantiles", k=6, ax=axes[2], linewidth=0)
    hubs.plot(ax=axes[2], color="#e4572e", markersize=34, edgecolor="white", linewidth=0.7)
    for ax, t in zip(axes, titles, strict=True):
        b.boundary.plot(ax=ax, color="white", linewidth=0.35) if ax is not axes[1] else None
        ax.set_axis_off()
        ax.set_title(t, loc="left", fontsize=11, color="#14213D", fontweight="bold")
    fig.text(
        0.01,
        0.015,
        "ChargeScape London · H3 resolution 8 · data: DfT, ONS, Open Charge Map, OpenStreetMap, UKPN, TfL/GLA · github.com/m-erts/chargescape-london",
        fontsize=8,
        color="#5B6B7A",
    )
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    FIGURES.mkdir(parents=True, exist_ok=True)
    out = FIGURES / "00_hero.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    shutil.copy(out, DOCS / "img" / "hero.png")
    print("wrote", out)


if __name__ == "__main__":
    main()
