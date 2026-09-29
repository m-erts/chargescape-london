"""Static map panels in the design-system palette (DESIGN.md).

Writes four single panels for the PPTX deck (reports/figures/panel_*.png) and the three-panel figure
for the README and link previews (reports/figures/00_hero.png, docs/img/hero.png). Grey ramps carry
the quantity, the one accent marks what the reader should look at.
"""

from __future__ import annotations

import json
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, ListedColormap

from chargescape.utils.paths import DOCS, FIGURES, PROCESSED, TABLES
from chargescape.utils.reference import boroughs
from chargescape.viz.design import LIGHT
from chargescape.viz.export_maplibre import _hex_layer, _rapid_layer, _sites_layer

RAMP = ListedColormap([LIGHT[f"r{i}"] for i in range(1, 7)])
LOAD = LinearSegmentedColormap.from_list("load", [LIGHT["r3"], LIGHT["accent"]])
FONTS = ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"]


def _hexes(ax, h, column: str) -> None:
    h.plot(column=column, cmap=RAMP, scheme="quantiles", k=6, ax=ax, linewidth=0)


def panel_supply(ax, h, sites, b) -> None:
    _hexes(ax, h, "piv_private_per_1000_hh")
    b.boundary.plot(ax=ax, color=LIGHT["bg"], linewidth=0.35)
    rapid = sites[sites.pclass >= 2]
    rapid.plot(ax=ax, color=LIGHT["accent"], markersize=7, edgecolor=LIGHT["bg"], linewidth=0.3)


def panel_demand(ax, h, b) -> None:
    _hexes(ax, h, "demand_p50")
    b.boundary.plot(ax=ax, color=LIGHT["bg"], linewidth=0.35)


def panel_queues(ax, rapid, b) -> None:
    b.boundary.plot(ax=ax, color=LIGHT["r2"], linewidth=0.5)
    s = rapid.sort_values("p_wait")
    s.plot(
        ax=ax,
        column="p_wait",
        cmap=LOAD,
        vmin=0,
        vmax=1,
        markersize=np.clip(np.sqrt(s.sessions_day) * 3, 4, 60),
        alpha=0.9,
        linewidth=0,
    )


def panel_hubs(ax, h, hubs, b) -> None:
    _hexes(ax, h, "unmet")
    b.boundary.plot(ax=ax, color=LIGHT["bg"], linewidth=0.35)
    hubs[~hubs.core].plot(ax=ax, color=LIGHT["bg"], markersize=30, edgecolor=LIGHT["fg"], linewidth=1.2)
    hubs[hubs.core].plot(ax=ax, color=LIGHT["accent"], markersize=34, edgecolor=LIGHT["bg"], linewidth=0.9)


def main() -> None:
    k = json.loads((TABLES / "key_numbers.json").read_text())
    h = _hex_layer().to_crs(27700)
    sites = _sites_layer().to_crs(27700)
    rapid = _rapid_layer().to_crs(27700)
    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    rec = sel[(sel.budget_m == 20) & (sel.recommended)]
    hubs = h[["h3", "geometry"]].merge(rec[["h3", "core"]], on="h3")
    hubs["geometry"] = hubs.geometry.centroid
    hubs["core"] = hubs["core"].astype(bool)
    b = boroughs()

    plt.rcParams.update({"font.size": 10, "font.family": FONTS})
    FIGURES.mkdir(parents=True, exist_ok=True)
    panels = {
        "supply": lambda ax: panel_supply(ax, h, sites, b),
        "demand": lambda ax: panel_demand(ax, h, b),
        "queues": lambda ax: panel_queues(ax, rapid, b),
        "hubs": lambda ax: panel_hubs(ax, h, hubs, b),
    }
    for name, draw in panels.items():
        fig, ax = plt.subplots(figsize=(7, 5.6), facecolor=LIGHT["bg"])
        draw(ax)
        ax.set_axis_off()
        fig.savefig(FIGURES / f"panel_{name}.png", dpi=160, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)

    d = k["demand_gwh"]["2026"]
    r20 = next(r for r in k["siting"] if int(r["budget_m"]) == 20)
    titles = [
        f"Demand 2026: {d['total_p50']:.0f} GWh per year (P10 to P90: {d['total_p10']:.0f} to {d['total_p90']:.0f})",
        f"Peak-hour queues: {k['sites_pwait_gt_50']} of {k['rapid_sites']} rapid sites with P(wait) above 0.5",
        f"£20M: {r20['rec_n_hubs']} hubs serve {round(100 * r20['rec_share_p50'])}% of unmet rapid demand",
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6), facecolor=LIGHT["bg"])
    for ax, key, t in zip(axes, ("demand", "queues", "hubs"), titles, strict=True):
        panels[key](ax)
        ax.set_axis_off()
        ax.set_title(t, loc="left", fontsize=11, color=LIGHT["fg"], fontweight="bold")
    fig.text(
        0.01,
        0.015,
        "ChargeScape London, H3 resolution 8. Data: DfT, ONS, Open Charge Map, OpenStreetMap, UKPN, TfL and GLA. github.com/m-erts/chargescape-london",
        fontsize=8,
        color=LIGHT["muted"],
    )
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    out = FIGURES / "00_hero.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    shutil.copy(out, DOCS / "img" / "hero.png")
    print("wrote", out, "and", len(panels), "panels")


if __name__ == "__main__":
    main()
