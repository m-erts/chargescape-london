"""Export interactive MapLibre GL JS maps (no API keys; CARTO Positron vector basemap) to docs/maps/.

Each page is a static HTML file that loads maplibre-gl from a CDN and a shared GeoJSON layer set in
docs/maps/data/. Works on GitHub Pages and locally (open the HTML file).
Run: PYTHONPATH=src python -m chargescape.viz.export_maplibre
"""

from __future__ import annotations

import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import DOCS, MAPS, PROCESSED, TABLES

OUT = DOCS / "maps"
DATA = OUT / "data"
MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"
STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
CENTER = [-0.12, 51.505]
ZOOM = 9.3

VIRIDIS = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"]
YLORRD = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"]
GREYS = ["#f7f7f7", "#d9d9d9", "#bdbdbd", "#969696", "#636363", "#252525"]


def _breaks(values: pd.Series, k: int = 6) -> list[float]:
    v = values.dropna().astype(float)
    v = v[v > 0] if (v > 0).sum() > 50 else v
    qs = np.quantile(v, np.linspace(0, 1, k + 1))[1:-1]
    return [float(round(x, 2)) for x in np.unique(qs)]


def _step_expr(prop: str, breaks: list[float], colors: list[str]) -> list:
    expr: list = ["step", ["coalesce", ["get", prop], 0], colors[0]]
    for b, c in zip(breaks, colors[1 : len(breaks) + 1], strict=False):
        expr += [b, c]
    return expr


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.1f}"


def _legend_html(title: str, breaks: list[float], colors: list[str], unit: str = "") -> str:
    rows = []
    lo = None
    for i, c in enumerate(colors[: len(breaks) + 1]):
        hi = breaks[i] if i < len(breaks) else None
        label = (
            f"< {_fmt(hi)}"
            if lo is None and hi is not None
            else (f"≥ {_fmt(lo)}" if hi is None else f"{_fmt(lo)} – {_fmt(hi)}")
        )
        rows.append(f'<div class="lg"><i style="background:{c}"></i>{label}{unit}</div>')
        lo = hi
    return f'<div class="legend"><b>{title}</b>{"".join(rows)}</div>'


def _page(
    title: str, subtitle: str, body_js: str, legend: str, controls: str = "", extra_css: str = ""
) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChargeScape London · {title}</title>
<link href="{MAPLIBRE_CSS}" rel="stylesheet"><script src="{MAPLIBRE_JS}"></script>
<style>
html,body{{margin:0;height:100%;font:14px/1.4 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a2027}}
#map{{position:absolute;inset:0}}
.panel{{position:absolute;top:12px;left:12px;z-index:5;background:rgba(255,255,255,.94);padding:12px 14px;border-radius:8px;max-width:360px;box-shadow:0 1px 6px rgba(0,0,0,.18)}}
.panel h1{{font:600 16px/1.25 Georgia,'Times New Roman',serif;margin:0 0 6px}}
.panel p{{margin:0 0 8px;color:#4b5763;font-size:12.5px}}
.panel .nav a{{font-size:12px;color:#0c7c70;margin-right:10px}}
.legend{{position:absolute;bottom:28px;left:12px;z-index:5;background:rgba(255,255,255,.94);padding:10px 12px;border-radius:8px;font-size:12px;box-shadow:0 1px 6px rgba(0,0,0,.18)}}
.legend b{{display:block;margin-bottom:6px}}
.lg{{display:flex;align-items:center;gap:8px;margin:2px 0}}
.lg i{{display:inline-block;width:16px;height:12px;border-radius:2px;border:1px solid rgba(0,0,0,.15)}}
.btns{{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}}
.btns button{{font:12px inherit;padding:4px 9px;border:1px solid #cfd6dc;border-radius:14px;background:#fff;cursor:pointer}}
.btns button.on{{background:#0c7c70;color:#fff;border-color:#0c7c70}}
.maplibregl-popup-content{{font-size:12.5px;line-height:1.45;padding:10px 12px}}
{extra_css}
</style></head><body>
<div id="map"></div>
<div class="panel"><h1>{title}</h1><p>{subtitle}</p>{controls}<div class="nav"><a href="index.html">all maps</a><a href="../index.html">project</a><a href="https://github.com/m-erts/chargescape-london">github</a></div></div>
{legend}
<script>
const map = new maplibregl.Map({{container:'map', style:'{STYLE}', center:{json.dumps(CENTER)}, zoom:{ZOOM}, pitch:0, attributionControl:true}});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.ScaleControl({{unit:'metric'}}));
function popup(html, lngLat){{ new maplibregl.Popup({{closeButton:false}}).setLngLat(lngLat).setHTML(html).addTo(map); }}
map.on('load', () => {{
{body_js}
}});
</script></body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    feats = read_gdf(PROCESSED / "hex_features_r8.small.parquet").to_crs(4326)
    dem = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
    d26 = dem[dem.scenario == "2026"].set_index("h3")
    d30 = dem[dem.scenario == "2030_mid"].set_index("h3")
    svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet").set_index("h3")
    h = feats[
        [
            "h3",
            "borough",
            "geometry",
            "piv_private_per_1000_hh",
            "share_flat",
            "ports_rapid",
            "ports_slow",
            "vkm_total",
        ]
    ].copy()
    h["demand_p10"] = h.h3.map(d26.total_kwh_p10) / 1e3
    h["demand_p50"] = h.h3.map(d26.total_kwh_p50) / 1e3
    h["demand_p90"] = h.h3.map(d26.total_kwh_p90) / 1e3
    h["demand_2030"] = h.h3.map(d30.total_kwh_p50) / 1e3
    h["phv_share"] = (h.h3.map(d26.phv_kwh_p50) / h.h3.map(d26.total_kwh_p50).replace(0, np.nan)).round(2)
    h["tt_rapid"] = h.h3.map(svc.tt_nearest_rapid_min)
    h["wait"] = h.h3.map(svc.expected_wait_min)
    h["n_rapid_10"] = h.h3.map(svc.n_rapid_within_10min)
    h["unmet"] = h.h3.map(svc.unserved_sessions_day).fillna(0) + h.h3.map(svc.rapid_sessions_day).fillna(
        0
    ) * h.h3.map(svc.served_share).fillna(0) * np.clip(h["wait"].fillna(0) / 30, 0, 1)
    for c in (
        "demand_p10",
        "demand_p50",
        "demand_p90",
        "demand_2030",
        "piv_private_per_1000_hh",
        "share_flat",
        "vkm_total",
        "tt_rapid",
        "wait",
        "unmet",
    ):
        h[c] = h[c].astype(float).round(2)
    h["geometry"] = h.geometry.simplify(0.00005)
    h.to_file(DATA / "hex_r8.geojson", driver="GeoJSON")

    sites = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
    s = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(sites.lon, sites.lat), crs=4326)
    keep = [
        "site_id",
        "source",
        "operator",
        "borough",
        "power_kw",
        "ports",
        "ports_known",
        "port_scale",
        "sessions_day",
        "utilisation_24h",
        "p_wait",
        "mean_wait_min",
        "geometry",
    ]
    s = s[[c for c in keep if c in s.columns]].copy()
    for c in ("sessions_day", "utilisation_24h", "p_wait", "mean_wait_min", "port_scale"):
        if c in s:
            s[c] = pd.to_numeric(s[c], errors="coerce").replace([np.inf, -np.inf], 120).round(2)
    s["operator"] = s["operator"].fillna("unknown").astype(str)
    s.to_file(DATA / "rapid_sites_2026.geojson", driver="GeoJSON")

    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    b = 20.0 if (sel.budget_m == 20.0).any() else sel.budget_m.max()
    hubs = sel[sel.budget_m == b].merge(feats[["h3", "geometry"]], on="h3", how="left")
    hubs = gpd.GeoDataFrame(hubs, geometry="geometry", crs=4326)
    hubs["geometry"] = hubs.geometry.centroid
    hubs["sessions_day_assigned"] = hubs["sessions_day_assigned"].round(1)
    hubs[["h3", "model", "borough", "sessions_day_assigned", "cost_gbp", "geometry"]].to_file(
        DATA / f"hubs_budget_{int(b)}m.geojson", driver="GeoJSON"
    )

    # ------------------------------------------------------------------ 1. demand
    br = _breaks(h["demand_p50"])
    js = f"""
  map.addSource('hex', {{type:'geojson', data:'data/hex_r8.geojson'}});
  const BR = {json.dumps(br)}, COL = {json.dumps(VIRIDIS)};
  function stepExpr(prop){{ const e=['step',['coalesce',['get',prop],0],COL[0]]; BR.forEach((b,i)=>e.push(b,COL[i+1])); return e; }}
  map.addLayer({{id:'hex-fill', type:'fill-extrusion', source:'hex', paint:{{
     'fill-extrusion-color': stepExpr('demand_p50'),
     'fill-extrusion-height': ['*', ['coalesce',['get','demand_p50'],0], 2.5],
     'fill-extrusion-opacity': 0.85}} }});
  let cur='demand_p50';
  document.querySelectorAll('.btns button').forEach(btn => btn.onclick = () => {{
     cur = btn.dataset.prop; document.querySelectorAll('.btns button').forEach(x=>x.classList.toggle('on', x===btn));
     map.setPaintProperty('hex-fill','fill-extrusion-color', stepExpr(cur));
     map.setPaintProperty('hex-fill','fill-extrusion-height', ['*',['coalesce',['get',cur],0],2.5]); }});
  map.easeTo({{pitch:45, bearing:-10, duration:1500}});
  map.on('click','hex-fill', e => {{ const p=e.features[0].properties;
     popup(`<b>${{p.borough||''}}</b><br>Demand 2026 P50: <b>${{p.demand_p50}}</b> MWh/yr<br>P10–P90: ${{p.demand_p10}} – ${{p.demand_p90}}<br>2030 (DFES mid): ${{p.demand_2030}} MWh/yr<br>Taxi/PHV share: ${{p.phv_share}}<br>Private EVs / 1000 hh: ${{p.piv_private_per_1000_hh}} · flats: ${{p.share_flat}}`, e.lngLat); }});
  map.on('mouseenter','hex-fill',()=>map.getCanvas().style.cursor='pointer'); map.on('mouseleave','hex-fill',()=>map.getCanvas().style.cursor='');
"""
    controls = '<div class="btns"><button data-prop="demand_p10">P10</button><button data-prop="demand_p50" class="on">P50 · 2026</button><button data-prop="demand_p90">P90</button><button data-prop="demand_2030">2030 mid</button></div>'
    (OUT / "demand_2026.html").write_text(
        _page(
            "Public charging demand, 2026",
            "Structural Monte Carlo model on observed inputs (EV stock, housing, traffic, POIs); height and colour = MWh per year per H3 hex. Click a hex for its interval and components.",
            js,
            _legend_html("MWh / year (P50 classes)", br, VIRIDIS),
            controls,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------ 2. rapid network load
    br2 = [2, 4, 6, 8, 10]
    js = f"""
  map.addSource('hex', {{type:'geojson', data:'data/hex_r8.geojson'}});
  map.addSource('sites', {{type:'geojson', data:'data/rapid_sites_2026.geojson'}});
  map.addLayer({{id:'hex-tt', type:'fill', source:'hex', paint:{{'fill-color': {json.dumps(_step_expr("tt_rapid", br2, YLORRD))}, 'fill-opacity':0.55, 'fill-outline-color':'rgba(255,255,255,0.4)'}} }});
  map.addLayer({{id:'sites', type:'circle', source:'sites', paint:{{
     'circle-radius': ['interpolate',['linear'],['sqrt',['coalesce',['get','sessions_day'],1]], 1,3, 23,22],
     'circle-color': ['interpolate',['linear'],['coalesce',['get','p_wait'],0], 0,'#1b9e77', 0.5,'#fdae61', 1,'#d7191c'],
     'circle-opacity':0.85, 'circle-stroke-color':'#fff', 'circle-stroke-width':1}} }});
  map.on('click','sites', e => {{ const p=e.features[0].properties;
     popup(`<b>${{p.operator}}</b> · ${{p.borough||''}}<br>${{p.power_kw}} kW × ${{p.ports}} ports (known ${{p.ports_known}}, scale ×${{p.port_scale}})<br>Expected sessions/day: <b>${{p.sessions_day}}</b><br>24 h utilisation: ${{p.utilisation_24h}} · P(wait) at peak: <b>${{p.p_wait}}</b> · mean wait ${{p.mean_wait_min}} min`, e.lngLat); }});
  map.on('click','hex-tt', e => {{ if (map.queryRenderedFeatures(e.point, {{layers:['sites']}}).length) return; const p=e.features[0].properties;
     popup(`<b>${{p.borough||''}}</b><br>Drive time to nearest rapid site: <b>${{p.tt_rapid}}</b> min<br>Rapid sites within 10 min: ${{p.n_rapid_10}}<br>Expected wait for this hex's drivers: ${{p.wait}} min`, e.lngLat); }});
  map.on('mouseenter','sites',()=>map.getCanvas().style.cursor='pointer'); map.on('mouseleave','sites',()=>map.getCanvas().style.cursor='');
"""
    legend = (
        _legend_html("Drive time to nearest rapid site (min)", br2, YLORRD)
        + '<div class="legend" style="left:auto;right:12px"><b>Rapid sites</b><div class="lg"><i style="background:#1b9e77;border-radius:50%"></i>P(wait) ≈ 0</div><div class="lg"><i style="background:#fdae61;border-radius:50%"></i>P(wait) ≈ 0.5</div><div class="lg"><i style="background:#d7191c;border-radius:50%"></i>P(wait) ≈ 1</div><div class="lg">size = expected sessions/day</div></div>'
    )
    (OUT / "rapid_network_load_2026.html").write_text(
        _page(
            "Rapid network: access, load and queues",
            "Hexes: drive time on the OSM road network to the nearest rapid (≥50 kW) site. Circles: modelled site load from MNL allocation and Erlang-C queues; ports calibrated to DfT borough totals.",
            js,
            legend,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------ 3. siting
    br3 = _breaks(h["unmet"])
    js = f"""
  map.addSource('hex', {{type:'geojson', data:'data/hex_r8.geojson'}});
  map.addSource('hubs', {{type:'geojson', data:'data/hubs_budget_{int(b)}m.geojson'}});
  map.addLayer({{id:'hex-unmet', type:'fill', source:'hex', paint:{{'fill-color': {json.dumps(_step_expr("unmet", br3, GREYS))}, 'fill-opacity':0.6, 'fill-outline-color':'rgba(255,255,255,0.35)'}} }});
  map.addLayer({{id:'hubs', type:'circle', source:'hubs', paint:{{
     'circle-radius': 8, 'circle-color': ['match',['get','model'],'p50','#e4572e','robust','#1b4965','#888'],
     'circle-opacity':0.92, 'circle-stroke-color':'#fff', 'circle-stroke-width':1.5}} }});
  document.querySelectorAll('.btns button').forEach(btn => btn.onclick = () => {{
     const m = btn.dataset.model; document.querySelectorAll('.btns button').forEach(x=>x.classList.toggle('on', x===btn));
     map.setFilter('hubs', m==='all' ? null : ['==',['get','model'],m]); }});
  map.on('click','hubs', e => {{ const p=e.features[0].properties;
     popup(`<b>Hub (${{p.model}})</b> · ${{p.borough||''}}<br>4 × 150 kW, cost £${{(p.cost_gbp/1e6).toFixed(2)}}M<br>Unmet demand assigned: <b>${{p.sessions_day_assigned}}</b> sessions/day`, e.lngLat); }});
  map.on('click','hex-unmet', e => {{ if (map.queryRenderedFeatures(e.point, {{layers:['hubs']}}).length) return; const p=e.features[0].properties;
     popup(`<b>${{p.borough||''}}</b><br>Unmet / queue-constrained rapid demand: <b>${{p.unmet}}</b> sessions/day<br>Expected wait today: ${{p.wait}} min`, e.lngLat); }});
  map.on('mouseenter','hubs',()=>map.getCanvas().style.cursor='pointer'); map.on('mouseleave','hubs',()=>map.getCanvas().style.cursor='');
"""
    controls = '<div class="btns"><button data-model="all" class="on">both</button><button data-model="p50">P50 solution</button><button data-model="robust">robust solution</button></div>'
    legend = (
        _legend_html("Unmet rapid demand (sessions/day)", br3, GREYS)
        + '<div class="legend" style="left:auto;right:12px"><b>Selected hubs, £%dM</b><div class="lg"><i style="background:#e4572e;border-radius:50%%"></i>P50 solution</div><div class="lg"><i style="background:#1b4965;border-radius:50%%"></i>robust (P10/P50/P90)</div></div>'
        % int(b)
    )
    (OUT / f"siting_hubs_budget_{int(b)}m.html").write_text(
        _page(
            f"Where the next hubs go — £{int(b)}M budget",
            "Capacitated maximal-covering MILP (HiGHS): 4 × 150 kW hubs, 8-minute drive-time coverage, Erlang-C capacity, primary-substation headroom filter. Grey = demand today's network does not serve at an acceptable wait.",
            js,
            legend,
            controls,
        ),
        encoding="utf-8",
    )

    # index
    files = sorted(p.name for p in OUT.glob("*.html") if p.name != "index.html")
    links = "\n".join(f'<li><a href="{n}">{n.replace("_", " ").replace(".html", "")}</a></li>' for n in files)
    (OUT / "index.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>ChargeScape London — maps</title><body style='font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:720px;margin:40px auto;padding:0 20px'><h1>ChargeScape London — interactive maps</h1><p>MapLibre GL JS maps exported by <code>chargescape.viz.export_maplibre</code>; basemap © CARTO © OpenStreetMap contributors. Data status and methods: see the <a href='../index.html'>project page</a>.</p><ul>{links}</ul></body>",
        encoding="utf-8",
    )
    for p in OUT.glob("*.html"):
        shutil.copy(p, MAPS / p.name)
    meta = TABLES / "siting_meta_2026.json"
    print(
        "maps written:",
        files,
        "| data:",
        [p.name for p in DATA.glob("*.geojson")],
        "| siting meta present:",
        meta.exists(),
    )


if __name__ == "__main__":
    main()
