"""Interactive MapLibre GL JS maps for GitHub Pages (docs/maps/), styled per DESIGN.md.

* Monochrome data ramps (six greys per theme) with one accent colour for the thing to notice.
* Light and dark themes: explicit `?theme=`, then the stored choice, then the system setting.
  The basemap follows the theme (CARTO Positron or Dark Matter, no API key).
* MapLibre GL JS 4.7.1 and the Geist fonts are vendored in docs/vendor, so nothing depends on a CDN.
* Data layers ship as GeoJSON (for reuse) and as a JS wrapper loaded with <script>, so the pages
  also work when opened from disk, where fetch() is blocked.
* If the basemap cannot be reached the page draws every data layer on a plain background.
* `?embed` (or being inside an iframe) hides the page text and forwards slide-navigation keys to
  the parent page. This is how the slide deck embeds the maps.

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
from chargescape.viz.design import THEME_BOOT_JS, tokens_css

OUT = DOCS / "maps"
DATA = OUT / "data"
VENDOR = "../vendor"
STYLE_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
STYLE_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
BOUNDS = [[-0.52, 51.28], [0.34, 51.70]]
REPO = "https://github.com/m-erts/chargescape-london"
N_CLASSES = 6


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


def _breaks(values: pd.Series, k: int = N_CLASSES) -> list[float]:
    v = values.dropna().astype(float)
    v = v[v > 0] if (v > 0).sum() > 50 else v
    qs = np.quantile(v, np.linspace(0, 1, k + 1))[1:-1]
    return [float(round(x, 2)) for x in np.unique(qs)]


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.1f}"


def _class_labels(breaks: list[float], unit: str = "") -> list[str]:
    labels, lo = [], None
    for i in range(len(breaks) + 1):
        hi = breaks[i] if i < len(breaks) else None
        if lo is None:
            labels.append(f"under {_fmt(hi)}{unit}")
        elif hi is None:
            labels.append(f"{_fmt(lo)}{unit} and over")
        else:
            labels.append(f"{_fmt(lo)} to {_fmt(hi)}{unit}")
        lo = hi
    return labels


def _legend_ramp(title: str, breaks: list[float], unit: str = "", key: str = "", hidden: bool = False) -> str:
    """Legend group for a grey ramp. Swatch colours come from the --r1..--r6 tokens of the active theme."""
    rows = "".join(
        f'<li><i class="sw r{i + 1}"></i><span class="mono">{label}</span></li>'
        for i, label in enumerate(_class_labels(breaks, unit))
    )
    attrs = (f' data-legend="{key}"' if key else "") + (" hidden" if hidden else "")
    return f'<div class="lgroup"{attrs}><h2>{title}</h2><ul>{rows}</ul></div>'


def _legend_marks(title: str, items: list[tuple[str, str]], note: str = "") -> str:
    rows = "".join(f'<li><i class="mk {cls}"></i><span>{label}</span></li>' for label, cls in items)
    extra = f'<p class="lnote">{note}</p>' if note else ""
    return f'<div class="lgroup"><h2>{title}</h2><ul>{rows}</ul>{extra}</div>'


def _segmented(group: str, label: str, options: list[tuple[str, str]], active: str) -> str:
    btns = "".join(
        f'<button type="button" data-v="{v}" aria-pressed="{"true" if v == active else "false"}">{text}</button>'
        for v, text in options
    )
    return f'<div class="seg" role="group" aria-label="{label}" data-group="{group}">{btns}</div>'


CSS = """
html,body{height:100%}
body{font-size:13px;line-height:1.45;overflow:hidden}
#map{position:absolute;inset:0;background:var(--surface)}
.panel{position:absolute;top:0;left:0;z-index:var(--z-map-ui);background:var(--bg);border-right:1px solid var(--border);border-bottom:1px solid var(--border);padding:16px;max-width:380px}
.panel h1{font-size:17px;line-height:1.2;font-weight:600;letter-spacing:-0.02em;margin:0 0 6px;text-wrap:balance}
.panel p{margin:0 0 12px;color:var(--muted);text-wrap:pretty}
.status{display:inline-block;font-size:11px;color:var(--muted);border:1px solid var(--border);padding:2px 6px;margin:0 0 10px}
.controls{display:flex;flex-direction:column;align-items:flex-start;gap:8px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;background:var(--bg)}
.seg button{appearance:none;border:0;border-right:1px solid var(--border);background:transparent;color:var(--muted);font-size:12px;line-height:1;padding:8px 10px;cursor:pointer;transition:background-color 150ms ease,color 150ms ease,transform 150ms var(--ease-out)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.seg button:active{transform:scale(0.97)}
.seg button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
@media (hover:hover) and (pointer:fine){.seg button[aria-pressed="false"]:hover{color:var(--fg);background:var(--surface)}}
.links{display:flex;gap:14px;margin-top:12px;font-size:12px;color:var(--muted)}
.legend{position:absolute;left:0;bottom:0;z-index:var(--z-map-ui);display:flex;background:var(--bg);border-top:1px solid var(--border);border-right:1px solid var(--border);font-size:12px}
.lgroup{padding:12px 16px}
.lgroup[hidden]{display:none}
.lgroup + .lgroup{border-left:1px solid var(--border)}
.lgroup h2{font-size:12px;font-weight:500;margin:0 0 8px;color:var(--fg)}
.lgroup ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.lgroup li{display:flex;align-items:center;gap:8px;color:var(--muted);white-space:nowrap}
.lnote{margin:8px 0 0;color:var(--muted)}
.sw{width:18px;height:10px;border:1px solid var(--border);flex:none}
.sw.r1{background:var(--r1)}.sw.r2{background:var(--r2)}.sw.r3{background:var(--r3)}.sw.r4{background:var(--r4)}.sw.r5{background:var(--r5)}.sw.r6{background:var(--r6)}
.mk{width:10px;height:10px;border-radius:50%;flex:none;margin:0 4px}
.mk.slow{background:var(--neutral);width:5px;height:5px;margin:0 6.5px}
.mk.fast{background:var(--fg);width:7px;height:7px;margin:0 5.5px}
.mk.rapid{background:var(--accent)}
.mk.ultra{background:var(--accent);box-shadow:0 0 0 1.5px var(--bg),0 0 0 3px var(--fg)}
.mk.free{background:var(--r3)}
.mk.busy{background:var(--accent)}
.mk.core{background:var(--accent)}
.mk.rest{background:var(--bg);box-shadow:inset 0 0 0 2px var(--fg)}
.notice{position:absolute;top:0;right:56px;z-index:var(--z-map-ui);background:var(--bg);border:1px solid var(--border);border-top:0;padding:6px 10px;font-size:12px;color:var(--muted);display:none}
.nobasemap .notice{display:block}
.maplibregl-map{font-family:inherit}
.maplibregl-ctrl-group{border-radius:var(--radius) !important;box-shadow:none !important;border:1px solid var(--border);background:var(--bg) !important;overflow:hidden}
.maplibregl-ctrl-group button{background-color:var(--bg)}
.maplibregl-ctrl-group button + button{border-top:1px solid var(--border)}
.dark .maplibregl-ctrl-group .maplibregl-ctrl-icon,.dark .maplibregl-ctrl-attrib-button{filter:invert(1)}
.maplibregl-ctrl-attrib,.maplibregl-ctrl-attrib.maplibregl-compact{background:var(--bg) !important;color:var(--muted);font-size:11px;border-radius:0;border:1px solid var(--border);margin:0 8px 8px 0}
.maplibregl-ctrl-attrib.maplibregl-compact-show{padding-right:28px}
.maplibregl-ctrl-attrib a{color:var(--muted)}
.maplibregl-ctrl-scale{background:var(--bg);border-color:var(--fg);color:var(--fg);font-size:11px}
.maplibregl-popup-content{background:var(--bg);color:var(--fg);border:1px solid var(--fg);border-radius:0;box-shadow:none;padding:10px 12px;font-size:12px;line-height:1.5}
.maplibregl-popup-tip{display:none}
.maplibregl-popup-content b{font-weight:600}
.maplibregl-popup-content dl{display:grid;grid-template-columns:auto auto;gap:2px 14px;margin:6px 0 0}
.maplibregl-popup-content dt{color:var(--muted)}
.maplibregl-popup-content dd{margin:0;text-align:right}
body.embed{font-size:clamp(10px,1.35vw,14px)}
body.embed .panel{padding:10px;border-color:var(--border)}
body.embed .panel h1,body.embed .panel p,body.embed .status,body.embed .links{display:none}
body.embed .panel:not(:has(button)){display:none}
body.embed .seg button{font-size:0.85em;padding:0.6em 0.8em}
body.embed .legend{font-size:0.85em}
body.embed .lgroup{padding:0.7em 1em}
body.embed .lgroup h2{font-size:1em}
body.embed .lnote{display:none}
@media (max-width:640px){.panel{max-width:none;right:0;border-right:0}.legend{flex-direction:column;right:0;border-right:0}.lgroup + .lgroup{border-left:0;border-top:1px solid var(--border)}}
"""

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ | ChargeScape London</title>
<meta name="description" content="__DESCRIPTION__">
<script>__BOOT__</script>
<link href="__VENDOR__/maplibre-gl-4.7.1/maplibre-gl.css" rel="stylesheet"><script src="__VENDOR__/maplibre-gl-4.7.1/maplibre-gl.js"></script>__SCRIPTS__
<style>__TOKENS____CSS__</style></head><body>
<div id="map"></div>
<div class="panel"><span class="status mono">__STATUS__</span><h1>__TITLE__</h1><p>__SUBTITLE__</p><div class="controls">__CONTROLS__</div><nav class="links" aria-label="Project"><a href="index.html">All maps</a><a href="../slides/">Slides</a><a href="../index.html">Project</a><a href="__REPO__">GitHub</a></nav></div>
<div class="legend">__LEGEND__</div>
<div class="notice">Basemap unavailable. Data layers are shown on a plain background.</div>
<script>
const EMBED = new URLSearchParams(location.search).has('embed') || window.self !== window.top;
const DARK = csIsDark();
document.body.classList.toggle('embed', EMBED);
document.body.classList.toggle('dark', DARK);
const T = {bg: csToken('bg'), fg: csToken('fg'), neutral: csToken('neutral'), accent: csToken('accent'), surface: csToken('surface')};
const RAMP = [1, 2, 3, 4, 5, 6].map(i => csToken('r' + i));
const FALLBACK = {version: 8, sources: {}, layers: [{id: 'bg', type: 'background', paint: {'background-color': T.surface}}]};
const map = new maplibregl.Map({container: 'map', style: DARK ? '__STYLE_DARK__' : '__STYLE_LIGHT__', bounds: __BOUNDS__, fitBoundsOptions: {padding: EMBED ? 8 : 30}, attributionControl: {compact: true}});
map.addControl(new maplibregl.NavigationControl({showCompass: !EMBED, visualizePitch: true}), 'top-right');
if (!EMBED) map.addControl(new maplibregl.ScaleControl({unit: 'metric'}), 'bottom-right');
function layer(name) {
  const d = (window.CS_DATA || {})[name];
  if (!d) { const n = document.querySelector('.notice'); n.textContent = 'Data layer "' + name + '" did not load. Open the published page or serve the folder over http.'; n.style.display = 'block'; }
  return d || {type: 'FeatureCollection', features: []};
}
function steps(prop, breaks) { const e = ['step', ['coalesce', ['get', prop], 0], RAMP[0]]; breaks.forEach((b, i) => e.push(b, RAMP[i + 1])); return e; }
function under() { const l = (map.getStyle().layers || []).find(x => x.type === 'symbol'); return l ? l.id : undefined; }
function rows(pairs) { return '<dl>' + pairs.map(p => '<dt>' + p[0] + '</dt><dd class="mono">' + p[1] + '</dd>').join('') + '</dl>'; }
function popup(title, pairs, lngLat) { new maplibregl.Popup({closeButton: false, maxWidth: '340px', offset: 8}).setLngLat(lngLat).setHTML('<b>' + title + '</b>' + rows(pairs)).addTo(map); }
function pointer(id) { map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer'); map.on('mouseleave', id, () => map.getCanvas().style.cursor = ''); }
function buttons(group, onPick) { const all = document.querySelectorAll('.seg[data-group="' + group + '"] button');
  all.forEach(btn => btn.addEventListener('click', () => { all.forEach(x => x.setAttribute('aria-pressed', x === btn ? 'true' : 'false')); onPick(btn.dataset.v); })); }
function showLegend(key) { document.querySelectorAll('[data-legend]').forEach(el => el.hidden = el.dataset.legend !== key); }
function pct(x) { return Math.round(100 * (x || 0)) + '%'; }
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
  addEventListener('keydown', e => { if (['ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown', 'Home', 'End', ' ', 'f', 'F', 't', 'T'].includes(e.key)) { parent.postMessage({cs_key: e.key}, '*'); e.preventDefault(); } });
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
        .replace("__BOOT__", THEME_BOOT_JS)
        .replace("__TOKENS__", tokens_css(VENDOR))
        .replace("__CSS__", CSS)
        .replace("__VENDOR__", VENDOR)
        .replace("__STATUS__", status)
        .replace("__TITLE__", title)
        .replace("__DESCRIPTION__", subtitle.replace('"', "'"))
        .replace("__SUBTITLE__", subtitle)
        .replace("__CONTROLS__", controls)
        .replace("__LEGEND__", legend)
        .replace("__STYLE_LIGHT__", STYLE_LIGHT)
        .replace("__STYLE_DARK__", STYLE_DARK)
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
    h["borough"] = h["borough"].fillna("Greater London")
    return h


def _sites_layer() -> gpd.GeoDataFrame:
    s = charging_sites()
    s = s[["site_id", "source", "operator", "max_kw", "n_ports", "geometry"]].copy()
    s["max_kw"] = pd.to_numeric(s["max_kw"], errors="coerce").round(1)
    s["n_ports"] = pd.to_numeric(s["n_ports"], errors="coerce").fillna(1).astype(int)
    s["operator"] = s["operator"].fillna("Operator not recorded").astype(str).str.slice(0, 40)
    s["source"] = (
        s["source"]
        .map({"ocm": "Open Charge Map", "osm": "OpenStreetMap", "ncr": "National Chargepoint Registry 2021"})
        .fillna(s["source"])
    )
    s["pclass"] = pd.cut(s["max_kw"].fillna(7), [-1, 7.99, 49.99, 149.99, 1e6], labels=[0, 1, 2, 3]).astype(
        int
    )
    return s.sort_values("pclass")


def _rapid_layer() -> gpd.GeoDataFrame:
    sites = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
    s = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(sites.lon, sites.lat), crs=4326)
    keep = [
        "site_id",
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
    s["operator"] = s["operator"].fillna("Operator not recorded").astype(str).str.slice(0, 40)
    s["borough"] = s["borough"].fillna("Greater London")
    return s.sort_values("p_wait")


def _hubs_layer(hexes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    cent = hexes[["h3", "geometry"]].copy()
    cent["geometry"] = cent.to_crs(27700).geometry.centroid.to_crs(4326)
    hubs = gpd.GeoDataFrame(sel.merge(cent, on="h3", how="left"), geometry="geometry", crs=4326)
    hubs["sessions_day_assigned"] = hubs["sessions_day_assigned"].round(1)
    hubs["budget"] = hubs["budget_m"].astype(int)
    hubs["borough"] = hubs["borough"].fillna("Greater London")
    for c in ("core", "recommended"):
        hubs[c] = hubs[c].fillna(False).astype(int) if c in hubs else 0
    return hubs[
        [
            "h3",
            "model",
            "borough",
            "budget",
            "core",
            "recommended",
            "sessions_day_assigned",
            "cost_gbp",
            "geometry",
        ]
    ].sort_values("core")


# ----------------------------------------------------------------------------- pages
def page_demand(h: gpd.GeoDataFrame) -> None:
    br26, br30 = _breaks(h["demand_p50"]), _breaks(h["demand_2030"])
    body = f"""
const BR = {{demand_p10: {json.dumps(br26)}, demand_p50: {json.dumps(br26)}, demand_p90: {json.dumps(br26)}, demand_2030: {json.dumps(br30)}}};
let PROP = 'demand_p50';
function height(prop) {{ return ['*', ['min', ['coalesce', ['get', prop], 0], 900], 2.2]; }}
function paint() {{ map.setPaintProperty('hex', 'fill-extrusion-color', steps(PROP, BR[PROP])); map.setPaintProperty('hex', 'fill-extrusion-height', height(PROP)); }}
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addLayer({{id: 'hex', type: 'fill-extrusion', source: 'hex', paint: {{'fill-extrusion-color': steps(PROP, BR[PROP]), 'fill-extrusion-height': height(PROP), 'fill-extrusion-opacity': 0.92}}}});
  map.jumpTo({{pitch: 45, bearing: -12}});
  map.on('click', 'hex', e => {{ const p = e.features[0].properties;
    popup(p.borough, [['Demand 2026, P50', p.demand_p50 + ' MWh/yr'], ['P10 to P90', p.demand_p10 + ' to ' + p.demand_p90], ['Demand 2030, mid pathway', p.demand_2030 + ' MWh/yr'], ['Taxi and private hire', pct(p.phv_share)], ['Private EVs per 1,000 households', p.piv_private_per_1000_hh], ['Households in flats', pct(p.share_flat)]], e.lngLat); }});
  pointer('hex');
}}
buttons('demand', v => {{ PROP = v; if (map.getLayer('hex')) paint(); showLegend(v === 'demand_2030' ? '2030' : '2026'); }});
"""
    controls = _segmented(
        "demand",
        "Demand scenario",
        [("demand_p10", "P10"), ("demand_p50", "P50 2026"), ("demand_p90", "P90"), ("demand_2030", "2030")],
        "demand_p50",
    )
    legend = _legend_ramp("MWh per year, 2026 classes", br26, key="2026") + _legend_ramp(
        "MWh per year, 2030 classes", br30, key="2030", hidden=True
    )
    _page(
        "demand_2026",
        "Public charging demand",
        "Bottom-up Monte Carlo model: EV stock, annual distance, energy per km and the share charged in public, which depends on off-street parking. Height and shade show MWh per year per hex. P10 and P90 keep the 2026 classes, so the change in shade is the uncertainty.",
        "model on observed inputs",
        body,
        legend,
        controls,
        ("hex_r8",),
    )


def page_supply(h: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> None:
    br_ev, br_flat = _breaks(h["piv_private_per_1000_hh"]), [0.14, 0.24, 0.33, 0.46, 0.64]
    body = f"""
const BR = {{piv_private_per_1000_hh: {json.dumps(br_ev)}, share_flat: {json.dumps(br_flat)}}};
let PROP = 'piv_private_per_1000_hh';
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('sites', {{type: 'geojson', data: layer('charging_sites')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', layout: {{visibility: PROP === 'none' ? 'none' : 'visible'}}, paint: {{'fill-color': steps(PROP === 'none' ? 'share_flat' : PROP, BR[PROP === 'none' ? 'share_flat' : PROP]), 'fill-opacity': 0.6, 'fill-outline-color': T.bg}}}}, under());
  map.addLayer({{id: 'sites', type: 'circle', source: 'sites', paint: {{
    'circle-color': ['match', ['get', 'pclass'], 0, T.neutral, 1, T.fg, T.accent],
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['match', ['get', 'pclass'], 0, 1.2, 1, 1.8, 2, 3, 4.2], 14, ['match', ['get', 'pclass'], 0, 3.5, 1, 5, 2, 7, 9]],
    'circle-opacity': ['match', ['get', 'pclass'], 0, 0.75, 1],
    'circle-stroke-color': ['match', ['get', 'pclass'], 3, T.fg, T.bg],
    'circle-stroke-width': ['match', ['get', 'pclass'], 0, 0, 1, 0.5, 2, 1, 1.5]}}}});
  map.on('click', 'sites', e => {{ const p = e.features[0].properties;
    popup(p.operator, [['Power', (p.max_kw == null ? 'not recorded' : p.max_kw + ' kW')], ['Charge points', p.n_ports], ['Source', p.source]], e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['sites']}}).length) return; const p = e.features[0].properties;
    popup(p.borough, [['Private plug-in cars per 1,000 households', p.piv_private_per_1000_hh], ['Households in flats', pct(p.share_flat)], ['Slow and fast ports', p.ports_slow], ['Rapid ports', p.ports_rapid]], e.lngLat); }});
  pointer('sites');
}}
buttons('hex', v => {{ PROP = v; showLegend(v); if (!map.getLayer('hex')) return;
  if (v === 'none') {{ map.setLayoutProperty('hex', 'visibility', 'none'); return; }}
  map.setLayoutProperty('hex', 'visibility', 'visible'); map.setPaintProperty('hex', 'fill-color', steps(v, BR[v])); }});
"""
    controls = _segmented(
        "hex",
        "Hex layer",
        [
            ("piv_private_per_1000_hh", "EVs per 1,000 households"),
            ("share_flat", "Share of flats"),
            ("none", "Chargers only"),
        ],
        "piv_private_per_1000_hh",
    )
    legend = (
        _legend_ramp("Private plug-in cars per 1,000 households", br_ev, key="piv_private_per_1000_hh")
        + _legend_ramp("Share of households in flats", br_flat, key="share_flat", hidden=True)
        + _legend_marks(
            f"{len(sites):,} charging sites",
            [
                ("under 8 kW", "slow"),
                ("8 to 49 kW", "fast"),
                ("50 to 149 kW", "rapid"),
                ("150 kW and over", "ultra"),
            ],
        )
    )
    _page(
        "supply_2026",
        "Who has chargers, who has EVs",
        "Public charging sites from Open Charge Map, OpenStreetMap and the 2021 national registry, de-duplicated within 50 m, over private plug-in cars per household or the share of households in flats. Drivers in flats depend on public charging.",
        "observed",
        body,
        legend,
        controls,
        ("hex_r8", "charging_sites"),
    )


def page_network(h: gpd.GeoDataFrame, rapid: gpd.GeoDataFrame) -> None:
    br = [2, 4, 6, 8, 10]
    body = f"""
const LOW = DARK ? '#555555' : '#B3B3B3';
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('sites', {{type: 'geojson', data: layer('rapid_sites_2026')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', paint: {{'fill-color': steps('tt_rapid', {json.dumps(br)}), 'fill-opacity': 0.6, 'fill-outline-color': T.bg}}}}, under());
  map.addLayer({{id: 'sites', type: 'circle', source: 'sites', paint: {{
    'circle-radius': ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'sessions_day'], 1]], 1, 3, 23, 18],
    'circle-color': ['interpolate', ['linear'], ['coalesce', ['get', 'p_wait'], 0], 0, LOW, 1, T.accent],
    'circle-opacity': 0.9, 'circle-stroke-color': T.bg, 'circle-stroke-width': 1}}}});
  map.on('click', 'sites', e => {{ const p = e.features[0].properties;
    popup(p.operator + ', ' + p.borough, [['Power and ports', p.power_kw + ' kW x ' + p.ports], ['Ports mapped, borough scale', p.ports_known + ', x' + p.port_scale], ['Expected sessions per day', p.sessions_day], ['24 h utilisation', pct(p.utilisation_24h)], ['P(wait) at the peak hour', p.p_wait], ['Mean wait', p.mean_wait_min + ' min']], e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['sites']}}).length) return; const p = e.features[0].properties;
    popup(p.borough, [['Drive time to the nearest rapid site', p.tt_rapid + ' min'], ['Rapid sites within 10 min', p.n_rapid_10], ['Expected wait for drivers here', p.wait + ' min']], e.lngLat); }});
  pointer('sites');
}}
"""
    legend = _legend_ramp("Drive time to the nearest rapid site", br, unit=" min") + _legend_marks(
        f"{len(rapid)} rapid sites",
        [("P(wait) near 0", "free"), ("P(wait) near 1", "busy")],
        note="Circle area follows sessions per day.",
    )
    _page(
        "rapid_network_load_2026",
        "Rapid network: access, load and queues",
        "Hexes show drive time on the OpenStreetMap road network to the nearest site of 50 kW or more. Circles show expected load from logit station choice and Erlang C queues at the peak hour. Ports are calibrated to DfT borough totals.",
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
    body = f"""
let BUDGET = {default}, MODEL = 'rec';
function applyFilter() {{ const which = MODEL === 'rec' ? ['==', ['get', 'recommended'], 1] : ['==', ['get', 'model'], MODEL];
  map.setFilter('hubs', ['all', ['==', ['get', 'budget'], BUDGET], which]); }}
function addLayers() {{
  map.addSource('hex', {{type: 'geojson', data: layer('hex_r8')}});
  map.addSource('hubs', {{type: 'geojson', data: layer('hubs_all_budgets')}});
  map.addLayer({{id: 'hex', type: 'fill', source: 'hex', paint: {{'fill-color': steps('unmet', {json.dumps(br)}), 'fill-opacity': 0.62, 'fill-outline-color': T.bg}}}}, under());
  map.addLayer({{id: 'hubs', type: 'circle', source: 'hubs', paint: {{'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 5.5, 13, 10],
    'circle-color': ['case', ['==', ['get', 'core'], 1], T.accent, T.bg],
    'circle-stroke-color': ['case', ['==', ['get', 'core'], 1], T.bg, T.fg], 'circle-stroke-width': 2}}}});
  applyFilter();
  map.on('click', 'hubs', e => {{ const p = e.features[0].properties;
    popup('Hub in ' + p.borough, [['Plan optimised for', p.model.toUpperCase() + ' demand' + (p.recommended === 1 ? ' (recommended)' : '')], ['Robust core', p.core === 1 ? 'yes' : 'no'], ['Configuration', '4 x 150 kW'], ['Capex', '£' + (p.cost_gbp / 1e6).toFixed(2) + 'M'], ['Unmet demand assigned', p.sessions_day_assigned + ' per day']], e.lngLat); }});
  map.on('click', 'hex', e => {{ if (map.queryRenderedFeatures(e.point, {{layers: ['hubs']}}).length) return; const p = e.features[0].properties;
    popup(p.borough, [['Unmet rapid demand', p.unmet + ' sessions per day'], ['Expected wait today', p.wait + ' min']], e.lngLat); }});
  pointer('hubs');
}}
buttons('budget', v => {{ BUDGET = +v; if (map.getLayer('hubs')) applyFilter(); }});
buttons('model', v => {{ MODEL = v; if (map.getLayer('hubs')) applyFilter(); }});
"""
    controls = _segmented(
        "budget", "Budget", [(str(b), f"£{b}M") for b in budgets], str(default)
    ) + _segmented(
        "model",
        "Plan",
        [("rec", "Recommended"), ("p10", "P10 plan"), ("p50", "P50 plan"), ("p90", "P90 plan")],
        "rec",
    )
    legend = _legend_ramp("Unmet rapid demand, sessions per day", br) + _legend_marks(
        "4 x 150 kW hubs", [("robust core: all three plans agree", "core"), ("outside the core", "rest")]
    )
    _page(
        "siting_hubs",
        "Where the next hubs go",
        "Capacitated maximal covering MILP: 4 x 150 kW hubs, 8-minute drive-time coverage, Erlang C capacity and a substation headroom filter. One plan is solved for each of P10, P50 and P90 demand and tested under the others. The recommended plan has the smallest worst-case regret.",
        "model and optimisation",
        body,
        legend,
        controls,
        ("hex_r8", "hubs_all_budgets"),
    )


INDEX_CSS = """
body{font-size:15px;line-height:1.55}
main{max-width:880px;margin:0 auto;padding:64px 24px}
h1{font-size:32px;line-height:1.1;font-weight:600;letter-spacing:-0.03em;margin:0 0 12px}
p{color:var(--muted);margin:0 0 32px;max-width:65ch}
table{width:100%;border-collapse:collapse;border:1px solid var(--border)}
th,td{text-align:left;vertical-align:top;padding:14px 16px;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:0}
th{font-weight:500;color:var(--muted);font-size:13px;background:var(--surface)}
td.status{color:var(--muted);font-size:13px;white-space:nowrap}
nav{display:flex;gap:16px;margin-top:24px;font-size:14px;color:var(--muted)}
"""


def page_index() -> None:
    items = [
        (
            "supply_2026.html",
            "Who has chargers, who has EVs",
            "13,174 charging sites by power over private EVs per household or the share of flats.",
            "observed",
        ),
        (
            "demand_2026.html",
            "Public charging demand",
            "Monte Carlo demand surface with P10, P50, P90 and 2030.",
            "model",
        ),
        (
            "rapid_network_load_2026.html",
            "Rapid network: access, load and queues",
            "Drive time to rapid sites, expected load and peak-hour waiting per site.",
            "model",
        ),
        (
            "siting_hubs.html",
            "Where the next hubs go",
            "Hub locations for budgets of £5M to £40M, with the robust core.",
            "optimisation",
        ),
    ]
    rows = "".join(
        f'<tr><td><a href="{f}">{t}</a></td><td>{d}</td><td class="status mono">{s}</td></tr>'
        for f, t, d, s in items
    )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Maps | ChargeScape London</title><meta name="description" content="Interactive maps of the ChargeScape London project.">
<script>{THEME_BOOT_JS}</script><style>{tokens_css(VENDOR)}{INDEX_CSS}</style></head><body><main>
<h1>Interactive maps</h1>
<p>MapLibre GL JS with CARTO basemaps. Each map follows the light or dark system theme and still draws its data on a plain background when the basemap cannot load.</p>
<table><thead><tr><th scope="col">Map</th><th scope="col">Shows</th><th scope="col">Status</th></tr></thead><tbody>{rows}</tbody></table>
<nav aria-label="Project"><a href="../slides/">Slides</a><a href="../index.html">Project</a><a href="{REPO}">GitHub</a></nav>
</main></body></html>"""
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
