"""Export interactive deck.gl maps (pydeck, Carto basemap, no token) to docs/maps/ for GitHub Pages
and reports/maps/. Each map is a standalone HTML file with the data inlined.

Run: PYTHONPATH=src python -m chargescape.viz.export_maps
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pydeck as pdk

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import DOCS, MAPS, PROCESSED, TABLES
from chargescape.viz.maps import h3_layer, to_html

OUT = DOCS / "maps"


def _save(layers, name, tooltip, title_note: str = ""):
    OUT.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    p = to_html(layers, OUT / f"{name}.html", tooltip=tooltip)
    (MAPS / f"{name}.html").write_bytes(p.read_bytes())
    _inject_title(p, name.replace("_", " ").title() + (f" — {title_note}" if title_note else ""))
    print("wrote", p)


def _inject_title(path, title):
    html = path.read_text(encoding="utf-8")
    banner = (
        '<div style="position:absolute;top:10px;left:10px;z-index:10;background:rgba(255,255,255,.92);'
        "padding:8px 12px;border-radius:6px;font:13px/1.35 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;"
        f'max-width:420px;box-shadow:0 1px 4px rgba(0,0,0,.15)"><b>ChargeScape London</b> · {title}<br>'
        '<span style="color:#555">Hover for values. Basemap © CARTO © OpenStreetMap contributors.</span></div>'
    )
    html = html.replace("<body>", "<body>" + banner, 1).replace(
        "<title>pydeck</title>", f"<title>ChargeScape · {title}</title>"
    )
    path.write_text(html, encoding="utf-8")


def main() -> None:
    feats = read_gdf(PROCESSED / "hex_features_r8.small.parquet")
    f = pd.DataFrame(feats.drop(columns="geometry"))
    dem = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
    d26 = dem[dem.scenario == "2026"].set_index("h3")
    f["demand_mwh_p50"] = f["h3"].map(d26["total_kwh_p50"]).fillna(0) / 1e3
    f["demand_mwh_p10"] = f["h3"].map(d26["total_kwh_p10"]).fillna(0) / 1e3
    f["demand_mwh_p90"] = f["h3"].map(d26["total_kwh_p90"]).fillna(0) / 1e3
    f["phv_share"] = (
        f["h3"].map(d26["phv_kwh_p50"]) / f["h3"].map(d26["total_kwh_p50"]).replace(0, np.nan)
    ).round(2)
    for c in (
        "demand_mwh_p50",
        "demand_mwh_p10",
        "demand_mwh_p90",
        "piv_private_per_1000_hh",
        "share_flat",
        "vkm_total",
    ):
        f[c] = f[c].astype(float).round(1)

    # 1. demand surface
    layers = [
        h3_layer(
            f,
            "demand_mwh_p50",
            cmap="viridis",
            elevation=True,
            elevation_scale=1.2,
            tooltip_cols=[
                "borough",
                "demand_mwh_p10",
                "demand_mwh_p90",
                "phv_share",
                "piv_private_per_1000_hh",
                "share_flat",
            ],
        )
    ]
    _save(
        layers,
        "demand_2026",
        {
            "html": "<b>{borough}</b><br>Demand P50: {demand_mwh_p50} MWh/yr<br>P10–P90: {demand_mwh_p10}–{demand_mwh_p90}<br>Taxi/PHV share: {phv_share}<br>Private EVs / 1000 hh: {piv_private_per_1000_hh}<br>Share flats: {share_flat}"
        },
        "public charging demand 2026 (P50, extruded)",
    )

    # 2. supply + service
    svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet").set_index("h3")
    f["tt_nearest_rapid_min"] = f["h3"].map(svc["tt_nearest_rapid_min"]).round(1)
    f["expected_wait_min"] = f["h3"].map(svc["expected_wait_min"]).round(1)
    sites = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
    sites["sessions_day"] = sites["sessions_day"].round(1)
    sites["p_wait"] = sites["p_wait"].round(2)
    sites["utilisation_24h"] = sites["utilisation_24h"].round(2)
    sites["radius"] = (np.sqrt(sites["sessions_day"].clip(lower=1)) * 25).round(0)
    sites["color"] = [
        [int(255 * min(1, p)), int(90 * (1 - min(1, p))), 40, 210] for p in sites["p_wait"].fillna(0)
    ]
    layers = [
        h3_layer(f, "tt_nearest_rapid_min", cmap="YlOrRd", tooltip_cols=["borough", "expected_wait_min"]),
        pdk.Layer(
            "ScatterplotLayer",
            sites,
            get_position=["lon", "lat"],
            get_radius="radius",
            get_fill_color="color",
            radius_min_pixels=3,
            radius_max_pixels=40,
            pickable=True,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
        ),
    ]
    _save(
        layers,
        "rapid_network_load_2026",
        {
            "html": "<b>{borough}{operator}</b><br>Drive time to nearest rapid: {tt_nearest_rapid_min} min<br>Expected wait: {expected_wait_min} min<br>Site: {power_kw} kW × {ports} ports · {sessions_day} sessions/day · P(wait) {p_wait} · util {utilisation_24h}"
        },
        "drive time to rapid sites and modelled site load",
    )

    # 3. siting result (if available)
    sel_path = PROCESSED / "siting_selected_2026.small.parquet"
    if sel_path.exists():
        sel = pd.read_parquet(sel_path)
        b = 20.0 if (sel.budget_m == 20.0).any() else sel.budget_m.max()
        s = sel[sel.budget_m == b].merge(f[["h3", "lat", "lon"]], on="h3", how="left")
        s["sessions_day_assigned"] = s["sessions_day_assigned"].round(1)
        s["color"] = [[228, 87, 46, 230] if m == "p50" else [27, 73, 101, 230] for m in s["model"]]
        f["unmet_sessions_day"] = (
            f["h3"].map(svc["unserved_sessions_day"]).fillna(0)
            + f["h3"].map(svc["rapid_sessions_day"]).fillna(0)
            * f["h3"].map(svc["served_share"]).fillna(0)
            * np.clip(f["expected_wait_min"].fillna(0) / 30, 0, 1)
        ).round(1)
        layers = [
            h3_layer(f, "unmet_sessions_day", cmap="Greys", tooltip_cols=["borough"]),
            pdk.Layer(
                "ScatterplotLayer",
                s,
                get_position=["lon", "lat"],
                get_radius=350,
                get_fill_color="color",
                pickable=True,
                stroked=True,
                get_line_color=[255, 255, 255],
                line_width_min_pixels=1,
            ),
        ]
        _save(
            layers,
            f"siting_hubs_budget_{int(b)}m",
            {
                "html": "<b>{borough}</b><br>Unmet rapid demand: {unmet_sessions_day} sessions/day<br>Hub ({model}): {sessions_day_assigned} sessions/day assigned"
            },
            f"selected 4×150 kW hubs, £{int(b)}M budget (orange = P50, blue = robust)",
        )

    # index page
    files = sorted(p.name for p in OUT.glob("*.html"))
    links = "\n".join(f'<li><a href="{n}">{n.replace("_", " ").replace(".html", "")}</a></li>' for n in files)
    (OUT / "index.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>ChargeScape London — maps</title><body style='font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:720px;margin:40px auto;padding:0 20px'><h1>ChargeScape London — interactive maps</h1><p>deck.gl maps exported by <code>chargescape.viz.export_maps</code>. Data status and methods: see the repository README.</p><ul>{links}</ul></body>",
        encoding="utf-8",
    )
    meta = TABLES / "siting_meta_2026.json"
    if meta.exists():
        print(json.loads(meta.read_text()))


if __name__ == "__main__":
    main()
