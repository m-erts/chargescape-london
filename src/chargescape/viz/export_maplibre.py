"""Interactive MapLibre GL JS maps for GitHub Pages (docs/maps/).

Design choices
* MapLibre GL JS 4.7.1 is vendored in docs/vendor/ (BSD-3), so the pages do not depend on a CDN.
* Data layers are shipped twice: as GeoJSON (for reuse) and as a JS wrapper loaded with <script>,
  so the pages also work when opened straight from disk (file://), where fetch() is blocked.
* Basemap: CARTO Positron (no key). If it cannot be reached (offline talk, blocked network) the page
  switches to a plain background after a few seconds and still draws every analytical layer.
* `?embed` (or being inside an iframe) hides the page chrome and forwards slide-navigation keys to
  the parent page, which is how the HTML slide deck embeds the maps.

Run: PYTHONPATH=src python -m chargescape.viz.export_maplibre
"""

from __future__ import annotations

import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import DOCS, MAPS, PROCESSED
from chargescape.utils.reference import charging_sites

OUT = DOCS / "maps"
DATA = OUT / "data"
VENDOR = "../vendor/maplibre-gl-4.7.1"
STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
BOUNDS = [[-0.52, 51.28], [0.34, 51.70]]
REPO = "https://github.com/m-erts/chargescape-london"

VIRIDIS = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"]
YLORRD = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026"]
GREYS = ["#f7f7f7", "#d9d9d9", "#bdbdbd", "#969696", "#636363", "#252525"]
BLUES = ["#eff3ff", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"]
MAGMA = ["#fcfdbf", "#feb078", "#f1605d", "#b5367a", "#721f81", "#2c115f"]
POWER = [
    ("< 8 kW (lamp-post, slow AC)", "#9aa5b1"),
    ("8–49 kW (fast)", "#2a788e"),
    ("50–149 kW (rapid)", "#f28e2b"),
    ("≥ 150 kW (ultra-rapid)", "#c0392b"),
]


# ----------------------------------------------------------------------------- helpers
def _write_layer(gdf: gpd.GeoDataFrame, name: str, precision: int = 5) -> None:
    """GeoJSON for reuse plus a JS wrapper that registers it in window.CS_DATA."""
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"{name}.geojson"
    gdf.to_crs(4326).to_file(path, driver="GeoJSON", COORDINATE_PRECISION=precision)
    js = (
        "window.CS_DATA=window.CS_DATA||{};window.CS_DATA["
        + json.dumps(name)
        + "]="
        + path.read_text(encoding="utf-8")
        + ";"
    )
    (DATA / f"{name}.js").write_text(js, encoding="utf-8")


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


def _legend_html(title: str, breaks: list[float], colors: list[str], unit: str = "", attrs: str = "") -> str:
    rows, lo = [], None
    for i, c in enumerate(colors[: len(breaks) + 1]):
        hi = breaks[i] if i < len(breaks) else None
        if lo is None and hi is not None:
            label = f"< {_fmt(hi)}"
        elif hi is None:
            label = f"≥ {_fmt(lo)}"
        else:
            label = f"{_fmt(lo)} – {_fmt(hi)}"
        rows.append(f'<div class="lg"><i style="background:{c}"></i>{label}{unit}</div>')
        lo = hi
    return f'<div class="legend" {attrs}><b>{title}</b>{"".join(rows)}</div>'


def _swatches(title: str, items: list[tuple[str, str]], round_: bool = True, attrs: str = "") -> str:
    r = "border-radius:50%;" if round_ else ""
    rows = "".join(f'<div class="lg"><i style="background:{c};{r}"></i>{t}</div>' for t, c in items)
    return f'<div class="legend right" {attrs}><b>{title}</b>{rows}</div>'


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChargeScape London · __TITLE__</title>
<link href="__VENDOR__/maplibre-gl.css" rel="stylesheet"><script src="__VENDOR__/maplibre-gl.js"></script>__SCRIPTS__
<style>
html,body{margin:0;height:100%;font:14px/1.4 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1a2027;background:#eef0ec}
#map{position:absolute;inset:0}
.panel{position:absolute;top:12px;left:12px;z-index:5;background:rgba(255,255,255,.95);padding:12px 14px;border-radius:8px;max-width:370px;box-shadow:0 1px 6px rgba(0,0,0,.18)}
.panel h1{font:600 16px/1.25 Georgia,"Times New Roman",serif;margin:0 0 6px}
.panel p{margin:0 0 8px;color:#4b5763;font-size:12.5px}
.status{display:inline-block;font:11px/1 ui-monospace,Menlo,monospace;letter-spacing:.04em;text-transform:uppercase;padding:3px 7px;border-radius:10px;background:#e6f2f0;color:#0a665c;margin-bottom:8px}
.status.model{background:#fdeee8;color:#a8401f}
.nav a{font-size:12px;color:#0c7c70;margin-right:10px}
.legend{position:absolute;bottom:30px;left:12px;z-index:5;background:rgba(255,255,255,.95);padding:10px 12px;border-radius:8px;font-size:12px;box-shadow:0 1px 6px rgba(0,0,0,.18)}
.legend.right{left:auto;right:12px;bottom:40px}
.legend b{display:block;margin-bottom:6px}
.lg{display:flex;align-items:center;gap:8px;margin:2px 0}
.lg i{display:inline-block;width:16px;height:12px;border-radius:2px;border:1px solid rgba(0,0,0,.15)}
.btns{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 8px}
.btns button{font:12px/1 inherit;padding:5px 9px;border:1px solid #cfd6dc;border-radius:14px;background:#fff;cursor:pointer;color:#1a2027}
.btns button.on{background:#0c7c70;color:#fff;border-color:#0c7c70}
.btns button:focus-visible{outline:2px solid #0c7c70;outline-offset:1px}
.maplibregl-popup-content{font-size:12.5px;line-height:1.45;padding:10px 12px}
.note{position:absolute;right:12px;top:12px;z-index:6;background:#fff8e6;border:1px solid #f0d9a6;border-radius:6px;padding:6px 9px;font-size:12px;display:none}
.nobasemap .note{display:block}
body.embed .panel p,body.embed .panel h1,body.embed .nav,body.embed .status{display:none}
body.embed .panel{padding:6px 8px;max-width:none}
body.embed .panel:not(:has(button)){display:none}
body.embed .legend{font-size:11px;padding:7px 9px;bottom:22px}
</style></head><body>
<div id="map"></div>
<div class="panel"><span class="status __STATUS_CLASS__">__STATUS__</span><h1>__TITLE__</h1><p>__SUBTITLE__</p>__CONTROLS__<div class="nav"><a href="index.html">all maps</a><a href="../index.html">project</a><a href="../slides/">slides</a><a href="__REPO__">github</a></div></div>
__LEGEND__
<div class="note">Basemap unavailable — showing data layers on a plain background.</div>
<script>
const EMBED = new URLSearchParams(location.search).has('embed') || window.self !== window.top;
if (EMBED) document.body.classList.add('embed');
const FALLBACK = {version: 8, sources: {}, layers: [{id: 'bg', type: 'background', paint: {'background-color': '#eef0ec'}}]};
const map = new maplibregl.Map({container: 'map', style: '__STYLE__', bounds: __BOUNDS__, fitBoundsOptions: {padding: EMBED ? 8 : 30}, attributionControl: {compact: true}});
map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), 'top-right');
map.addControl(new maplibregl.ScaleControl({unit: 'metric'}), 'bottom-right');
function layer(name) {
  const d = (window.CS_DATA || {})[name];
  if (!d) { const b = document.createElement('div'); b.className = 'legend right'; b.style.top = '60px'; b.style.bottom = 'auto';
    b.innerHTML = '<b>Data layer “' + name + '” did not load.</b>Open the GitHub Pages version or serve the folder: python -m http.server'; document.body.appendChild(b); }
  return d || {type: 'FeatureCollection', features: []};
}
function popup(html, lngLat) { new maplibregl.Popup({closeButton: false, maxWidth: '320px'}).setLngLat(lngLat).setHTML(html).addTo(map); }
function pointer(id) { map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer'); map.on('mouseleave', id, () => map.getCanvas().style.cursor = ''); }
function buttons(group, onPick) { document.querySelectorAll('.btns[data-group="' + group + '"] button').forEach(btn => btn.onclick = () => {
  document.querySelectorAll('.btns[data-group="' + group + '"] button').forEach(x => x.classList.toggle('on', x === btn)); onPick(btn.dataset.v); }); }
function showLegend(key) { document.querySelectorAll('[data-legend]').forEach(el => el.style.display = el.dataset.legend === key ? '' : 'none'); }
let added = false, styleReady = false, fitted = false;
function ensureFit() { const c = map.getContainer(); if (fitted || c.clientWidth < 80 || c.clientHeight < 80) return;
  fitted = true; map.resize(); map.fitBounds(__BOUNDS__, {padding: EMBED ? 8 : 30, duration: 0}); }
map.on('resize', ensureFit);
function useFallback(reason) { if (styleReady) return; styleReady = true; console.warn('basemap unavailable (' + reason + ')'); document.body.classList.add('nobasemap'); map.setStyle(FALLBACK); }
map.on('style.load', () => { styleReady = true; ensureFit(); if (!added) { added = true; addLayers(); } });
map.on('error', e => { const m = e && e.error ? String(e.error.message || e.error) : String(e); console.error('maplibre:', m); if (!added) useFallback(m); });
setTimeout(() => { if (!added) useFallback('timeout'); }, 7000);
if (EMBED) {
  map.keyboard.disable();
  addEventListener('keydown', e => { if (['ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown', ' ', 'f', 'F'].includes(e.key)) { parent.postMessage({cs_key: e.key}, '*'); e.preventDefault(); } });
}
__BODY__
</script></body></html>"""


def _page(
    name: str,
    title: str,
    subtitle: str,
    status: str,
    body_js: str,
    legend: str,
    controls: str = "",
    layers: tuple[str, ...] = (),
) -> None:
    scripts = "".join(f'<script src="data/{n}.js"></script>' for n in layers)
    html = (
        TEMPLATE.replace("__SCRIPTS__", scripts)
        .replace("__VENDOR__", VENDOR)
        .replace("__STATUS_CLASS__", "model" if status.lower().startswith("model") else "")
        .replace("__STATUS__", status)
        .replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__CONTROLS__", controls)
        .replace("__LEGEND__", legend)
        .replace("__STYLE__", STYLE)
        .replace("__BOUNDS__", json.dumps(BOUNDS))
        .replace("__REPO__", REPO)
        .replace("__BODY__", body_js)
    )
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")


# ----------------------------------------------------------------------------- data
def _hex_layer() -> gpd.GeoDataFrame:
    feats = read_gdf(PROCESSED / "hex_features_r8.small.parquet").to_crs(4326)
    dem = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
    d26 = dem[dem.scenario == "2026"].set_index("h3")
    d30 = dem[dem.scenario == "2030_mid"].set_index("h3")
    svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet").set_index("h3")
    h = feats[
        ["h3", "borough", "geometry", "piv_private_per_1000_hh", "share_flat", "ports_rapid", "ports_slow"]
    ].copy()
    h["demand_p10"] = h.h3.map(d26.total_kwh_p10) / 1e3
    h["demand_p50"] = h.h3.map(d26.total_kwh_p50) / 1e3
    h["demand_p90"] = h.h3.map(d26.total_kwh_p90) / 1e3
    h["demand_2030"] = h.h3.map(d30.total_kwh_p50) / 1e3
    h["phv_share"] = h.h3.map(d26.phv_kwh_p50) / h.h3.map(d26.total_kwh_p50).replace(0, np.nan)
    h["tt_rapid"] = h.h3.map(svc.tt_nearest_rapid_min)
    h["wait"] = h.h3.map(svc.expected_wait_min)
    h["n_rapid_10"] = h.h3.map(svc.n_rapid_within_10min)
    served = h.h3.map(svc.served_share).fillna(0)
    h["unmet"] = h.h3.map(svc.unserved_sessions_day).fillna(0) + h.h3.map(svc.rapid_sessions_day).fillna(
        0
    ) * served * np.clip(h["wait"].fillna(0) / 30, 0, 1)
    num = [c for c in h.columns if c not in ("h3", "borough", "geometry")]
    h[num] = h[num].astype(float).round(2)
    h["borough"] = h["borough"].fillna("")
    return h


def _sites_layer() -> gpd.GeoDataFrame:
    s = charging_sites()
    s = s[["site_id", "source", "operator", "max_kw", "n_ports", "geometry"]].copy()
    s["max_kw"] = pd.to_numeric(s["max_kw"], errors="coerce").round(1)
    s["n_ports"] = pd.to_numeric(s["n_ports"], errors="coerce").fillna(1).astype(int)
    s["operator"] = s["operator"].fillna("unknown").astype(str).str.slice(0, 40)
    s["pclass"] = pd.cut(s["max_kw"].fillna(7), [-1, 7.99, 49.99, 149.99, 1e6], labels=[0, 1, 2, 3]).astype(
        int
    )
    return s.sort_values("pclass")


def _rapid_layer() -> gpd.GeoDataFrame:
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
        s[c] = pd.to_numeric(s[c], errors="coerce").replace([np.inf, -np.inf], 120).round(2)
    s["operator"] = s["operator"].fillna("unknown").astype(str).str.slice(0, 40)
    s["borough"] = s["borough"].fillna("")
    return s


def _hubs_layer(hexes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    cent = hexes[["h3", "geometry"]].copy()
    cent["geometry"] = cent.to_crs(27700).geometry.centroid.to_crs(4326)
    hubs = gpd.GeoDataFrame(sel.merge(cent, on="h3", how="left"), geometry="geometry", crs=4326)
    hubs["sessions_day_assigned"] = hubs["sessions_day_assigned"].round(1)
    hubs["budget"] = hubs["budget_m"].astype(int)
    return hubs[["h3", "model", "borough", "budget", "sessions_day_assigned", "cost_gbp", "geometry"]]


# ----------------------------------------------------------------------------- pages
def page_demand(h: gpd.GeoDataFrame) -> None:
    br26, br30 = _breaks(h["demand_p50"]), _breaks(h["demand_2030"])
    body = f"""
const BR = {{demand_p10: {json.dumps(br26)}, demand_p50: {json.dumps(br26)}, demand_p90: {json.dumps(br26)}, demand_2030: {json.dumps(br30)}}};
const COL = {json.dumps(VIRIDIS)};
function stepExpr(prop) {{ const e = ['step', ['coalesce', ['get', prop], 0], COL[0]]; BR[prop].forEach((b, i) => e.push(b, COL[i + 1])); return e; }}
function heightExpr(prop) {{ return ['*', ['min', ['coalesce', ['get', prop], 0], 900], 2.2]; }}
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addLayer({{id: 'hex', type: 'fill-extrusion', source: 'hex', paint: {{'fill-extrusion-color': stepExpr('demand_p50'), 'fill-extrusion-height': heightExpr('demand_p50'), 'fill-extrusion-opacity': 0.88}}}});
  map.easeTo({{pitch: 45, bearing: -12, duration: 1400}});
  map.on('click', 'hex', e => {{ const p = e.features[0].properties;
    popup(`<b>${{p.borough}}</b><br>Public charging demand 2026, P50: <b>${{p.demand_p50}}</b> MWh/yr<br>P10–P90: ${{p.demand_p10}} – ${{p.demand_p90}}<br>2030, DFES mid pathway: ${{p.demand_2030}} MWh/yr<br>Taxi &amp; private-hire share: ${{Math.round(100 * (p.phv_share || 0))}} %<br>Private EVs per 1,000 households: ${{p.piv_private_per_1000_hh}} · flats: ${{Math.round(100 * p.share_flat)}} %`, e.lngLat); }});
  pointer('hex');
}}
buttons('demand', v => {{ map.setPaintProperty('hex', 'fill-extrusion-color', stepExpr(v)); map.setPaintProperty('hex', 'fill-extrusion-height', heightExpr(v)); showLegend(v === 'demand_2030' ? '2030' : '2026'); }});
"""
    controls = '<div class="btns" data-group="demand"><button data-v="demand_p10">P10</button><button data-v="demand_p50" class="on">P50 · 2026</button><button data-v="demand_p90">P90</button><button data-v="demand_2030">2030</button></div>'
    legend = _legend_html(
        "MWh per year (2026 classes)", br26, VIRIDIS, attrs='data-legend="2026"'
    ) + _legend_html(
        "MWh per year (2030 classes)", br30, VIRIDIS, attrs='data-legend="2030" style="display:none"'
    )
    _page(
        "demand_2026",
        "Public charging demand",
        "Bottom-up Monte Carlo model: EV stock × km × kWh/km × share charged publicly (depends on off-street parking), plus destination and taxi/private-hire demand. Height and colour: MWh per year per H3 hex. P10 and P90 use the 2026 classes, so the colour shift is the uncertainty.",
        "model on observed inputs",
        body,
        legend,
        controls,
        ("hex_r8",),
    )


def page_supply(h: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> None:
    br_ev, br_flat = _breaks(h["piv_private_per_1000_hh"]), [0.14, 0.24, 0.33, 0.46, 0.64]
    colors = [c for _, c in POWER]
    body = f"""
const HEX = {{piv_private_per_1000_hh: {{br: {json.dumps(br_ev)}, col: {json.dumps(BLUES)}}}, share_flat: {{br: {json.dumps(br_flat)}, col: {json.dumps(MAGMA)}}}}};
function stepExpr(prop) {{ const s = HEX[prop]; const e = ['step', ['coalesce', ['get', prop], 0], s.col[0]]; s.br.forEach((b, i) => e.push(b, s.col[i + 1])); return e; }}
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('sites', {{type: 'geojson', data: layer('charging_sites')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', paint: {{'fill-color': stepExpr('piv_private_per_1000_hh'), 'fill-opacity': 0.55, 'fill-outline-color': 'rgba(255,255,255,0.3)'}}}});
  map.addLayer({{id: 'sites', type: 'circle', source: 'sites', paint: {{
    'circle-color': ['match', ['get', 'pclass'], 0, '{colors[0]}', 1, '{colors[1]}', 2, '{colors[2]}', '{colors[3]}'],
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['match', ['get', 'pclass'], 0, 1.3, 1, 2, 2, 3.2, 4.2], 14, ['match', ['get', 'pclass'], 0, 4, 1, 5, 2, 7, 9]],
    'circle-opacity': 0.9, 'circle-stroke-color': '#fff', 'circle-stroke-width': ['match', ['get', 'pclass'], 0, 0, 0.6]}}}});
  map.on('click', 'sites', e => {{ const p = e.features[0].properties;
    popup(`<b>${{p.operator}}</b><br>${{p.max_kw ?? '?'}} kW · ${{p.n_ports}} point(s)<br>source: ${{p.source}}`, e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['sites']}}).length) return; const p = e.features[0].properties;
    popup(`<b>${{p.borough}}</b><br>Private plug-in cars per 1,000 households: <b>${{p.piv_private_per_1000_hh}}</b><br>Households in flats: ${{Math.round(100 * p.share_flat)}} %<br>Ports: ${{p.ports_slow}} slow · ${{p.ports_rapid}} rapid`, e.lngLat); }});
  pointer('sites');
}}
buttons('hex', v => {{ if (v === 'none') {{ map.setLayoutProperty('hex', 'visibility', 'none'); showLegend('none'); return; }}
  map.setLayoutProperty('hex', 'visibility', 'visible'); map.setPaintProperty('hex', 'fill-color', stepExpr(v)); showLegend(v); }});
"""
    controls = '<div class="btns" data-group="hex"><button data-v="piv_private_per_1000_hh" class="on">EVs per 1,000 hh</button><button data-v="share_flat">Share of flats</button><button data-v="none">Chargers only</button></div>'
    legend = (
        _legend_html(
            "Private plug-in cars / 1,000 households (DfT 2026 Q1)",
            br_ev,
            BLUES,
            attrs='data-legend="piv_private_per_1000_hh"',
        )
        + _legend_html(
            "Households in flats (Census 2021)",
            br_flat,
            MAGMA,
            attrs='data-legend="share_flat" style="display:none"',
        )
        + _swatches(f"Charging sites ({len(sites):,})", POWER)
    )
    _page(
        "supply_2026",
        "Who has chargers, who has EVs",
        "Public charging sites (Open Charge Map ∪ OpenStreetMap ∪ 2021 registry, de-duplicated within 50 m) over private plug-in cars per household or the share of households in flats — the group that depends on public charging.",
        "observed",
        body,
        legend,
        controls,
        ("hex_r8", "charging_sites"),
    )


def page_network(h: gpd.GeoDataFrame, rapid: gpd.GeoDataFrame) -> None:
    br = [2, 4, 6, 8, 10]
    body = f"""
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('sites', {{type: 'geojson', data: layer('rapid_sites_2026')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', paint: {{'fill-color': {json.dumps(_step_expr("tt_rapid", br, YLORRD))}, 'fill-opacity': 0.55, 'fill-outline-color': 'rgba(255,255,255,0.35)'}}}});
  map.addLayer({{id: 'sites', type: 'circle', source: 'sites', paint: {{
    'circle-radius': ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'sessions_day'], 1]], 1, 3, 23, 20],
    'circle-color': ['interpolate', ['linear'], ['coalesce', ['get', 'p_wait'], 0], 0, '#1b9e77', 0.5, '#fdae61', 1, '#d7191c'],
    'circle-opacity': 0.85, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1}}}});
  map.on('click', 'sites', e => {{ const p = e.features[0].properties;
    popup(`<b>${{p.operator}}</b> · ${{p.borough}}<br>${{p.power_kw}} kW × ${{p.ports}} ports (mapped ${{p.ports_known}}, borough scale ×${{p.port_scale}})<br>Expected sessions/day: <b>${{p.sessions_day}}</b><br>24 h utilisation: ${{Math.round(100 * p.utilisation_24h)}} % · P(wait) at the peak hour: <b>${{p.p_wait}}</b> · mean wait ${{p.mean_wait_min}} min`, e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['sites']}}).length) return; const p = e.features[0].properties;
    popup(`<b>${{p.borough}}</b><br>Drive time to the nearest rapid site: <b>${{p.tt_rapid}}</b> min<br>Rapid sites within 10 min: ${{p.n_rapid_10}}<br>Expected wait for this hex's drivers: ${{p.wait}} min`, e.lngLat); }});
  pointer('sites');
}}
"""
    legend = _legend_html("Drive time to the nearest rapid site (min)", br, YLORRD) + _swatches(
        f"Rapid sites ({len(rapid)}), size = sessions/day",
        [("P(wait) ≈ 0", "#1b9e77"), ("P(wait) ≈ 0.5", "#fdae61"), ("P(wait) ≈ 1", "#d7191c")],
    )
    _page(
        "rapid_network_load_2026",
        "Rapid network: access, load and queues",
        "Hexes: drive time on the OpenStreetMap road network to the nearest ≥50 kW site. Circles: expected load from multinomial-logit station choice and Erlang-C queues at the peak hour; ports calibrated to DfT borough totals.",
        "model on observed inputs",
        body,
        legend,
        "",
        ("hex_r8", "rapid_sites_2026"),
    )


def page_siting(h: gpd.GeoDataFrame, hubs: gpd.GeoDataFrame) -> None:
    br = _breaks(h["unmet"])
    budgets = sorted(hubs["budget"].unique())
    default = 20 if 20 in budgets else budgets[-1]
    counts = hubs.groupby(["budget", "model"]).size().to_dict()
    body = f"""
let BUDGET = {default}, MODEL = 'all';
function applyFilter() {{ const f = ['all', ['==', ['get', 'budget'], BUDGET]]; if (MODEL !== 'all') f.push(['==', ['get', 'model'], MODEL]); map.setFilter('hubs', f); }}
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('hubs', {{type: 'geojson', data: layer('hubs_all_budgets')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', paint: {{'fill-color': {json.dumps(_step_expr("unmet", br, GREYS))}, 'fill-opacity': 0.62, 'fill-outline-color': 'rgba(255,255,255,0.35)'}}}});
  map.addLayer({{id: 'hubs', type: 'circle', source: 'hubs', paint: {{'circle-radius': ['match', ['get', 'model'], 'p50', 8, 5.5], 'circle-color': ['match', ['get', 'model'], 'p50', '#e4572e', '#1b4965'], 'circle-opacity': 0.92, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5}}}});
  applyFilter();
  map.on('click', 'hubs', e => {{ const p = e.features[0].properties;
    popup(`<b>Hub, ${{p.model === 'p50' ? 'P50 solution' : 'robust solution'}}</b> · ${{p.borough}}<br>4 × 150 kW, capex £${{(p.cost_gbp / 1e6).toFixed(2)}}M (budget £${{p.budget}}M)<br>Unmet demand assigned: <b>${{p.sessions_day_assigned}}</b> sessions/day`, e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['hubs']}}).length) return; const p = e.features[0].properties;
    popup(`<b>${{p.borough}}</b><br>Unmet or queue-constrained rapid demand: <b>${{p.unmet}}</b> sessions/day<br>Expected wait today: ${{p.wait}} min`, e.lngLat); }});
  pointer('hubs');
}}
buttons('budget', v => {{ BUDGET = +v; if (map.getLayer('hubs')) applyFilter(); }});
buttons('model', v => {{ MODEL = v; if (map.getLayer('hubs')) applyFilter(); }});
"""
    on = ' class="on"'
    bbtn = "".join(f'<button data-v="{b}"{on if b == default else ""}>£{b}M</button>' for b in budgets)
    controls = f'<div class="btns" data-group="budget">{bbtn}</div><div class="btns" data-group="model"><button data-v="all" class="on">both</button><button data-v="p50">P50 solution</button><button data-v="robust">robust</button></div>'
    lines = [
        f"£{b}M: {counts.get((b, 'p50'), 0)} hubs (P50), {counts.get((b, 'robust'), 0)} (robust)"
        for b in budgets
    ]
    legend = _legend_html("Unmet rapid demand, sessions/day", br, GREYS) + _swatches(
        "Selected 4 × 150 kW hubs", [("P50 solution", "#e4572e"), ("robust over P10/P50/P90", "#1b4965")]
    ).replace("</div></div>", "</div>" + "".join(f'<div class="lg">{t}</div>' for t in lines) + "</div>", 1)
    _page(
        "siting_hubs",
        "Where the next hubs go",
        "Capacitated maximal-covering MILP (HiGHS): 4 × 150 kW hubs, 8-minute drive-time coverage, Erlang-C capacity per hub, primary-substation headroom filter. Grey: demand today's network does not serve at an acceptable wait. Switch budgets and solutions.",
        "model · optimisation",
        body,
        legend,
        controls,
        ("hex_r8", "hubs_all_budgets"),
    )


def page_index() -> None:
    items = [
        (
            "supply_2026.html",
            "Who has chargers, who has EVs",
            "13k charging sites by power over private EVs per household or share of flats (observed).",
        ),
        (
            "demand_2026.html",
            "Public charging demand",
            "Monte Carlo demand surface, P10/P50/P90 and 2030 (model).",
        ),
        (
            "rapid_network_load_2026.html",
            "Rapid network: access, load and queues",
            "Drive time to rapid sites; expected load and peak-hour waiting per site (model).",
        ),
        (
            "siting_hubs.html",
            "Where the next hubs go",
            "Hub locations for £5–40M budgets, P50 vs robust solutions (optimisation).",
        ),
    ]
    li = "".join(f'<li><a href="{f}">{t}</a><br><span>{d}</span></li>' for f, t, d in items)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ChargeScape London · maps</title>
<style>body{{font:16px/1.55 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;max-width:720px;margin:48px auto;padding:0 20px;color:#1a2027;background:#fff}} h1{{font:600 30px/1.2 Georgia,serif;margin:0 0 6px}} p{{color:#4b5763}} ul{{padding-left:1.1em}} li{{margin:14px 0}} a{{color:#0a665c;font-weight:600}} span{{color:#4b5763;font-size:14px}}</style></head>
<body><h1>ChargeScape London — interactive maps</h1><p>MapLibre GL JS; basemap © CARTO © OpenStreetMap contributors. Each map works offline on a plain background if the basemap cannot load. <a href="../index.html">Project page</a> · <a href="../slides/">slides</a> · <a href="{REPO}">repository</a></p><ul>{li}</ul></body></html>"""
    (OUT / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("*.html")) + list(DATA.glob("*")):
        old.unlink()
    h = _hex_layer()
    sites = _sites_layer()
    rapid = _rapid_layer()
    hubs = _hubs_layer(h)
    _write_layer(h, "hex_r8")
    _write_layer(sites, "charging_sites")
    _write_layer(rapid, "rapid_sites_2026")
    _write_layer(hubs, "hubs_all_budgets")
    page_supply(h, sites)
    page_demand(h)
    page_network(h, rapid)
    page_siting(h, hubs)
    page_index()
    MAPS.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob("*.html"):
        shutil.copy(p, MAPS / p.name)
    sizes = {p.name: round(p.stat().st_size / 1024) for p in DATA.glob("*.js")}
    print("maps:", sorted(p.name for p in OUT.glob("*.html")), "| layer sizes KB:", sizes)


if __name__ == "__main__":
    main()
