"""Build the HTML presentation docs/slides/index.html: full-screen slides with live MapLibre maps
(embedded from docs/maps/) and the figures from the notebooks. Keyboard ←/→, space, or click the dots.
Numbers come from reports/tables/key_numbers.json so the deck never drifts from the results."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "slides"
IMG = OUT / "img"
FIG = ROOT / "reports" / "figures"
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
d26 = K["demand_gwh"]["2026"]
d30 = K["demand_gwh"]["2030_mid"]
sit = {r["budget_m"]: r for r in K.get("siting", [])}
r20 = sit.get(20.0) or (list(sit.values())[-1] if sit else None)
r40 = sit.get(40.0)

IMG.mkdir(parents=True, exist_ok=True)
for name in [
    "01_hex_supply_demand.png",
    "01_need_hotspots.png",
    "02_demand_p50_uncertainty.png",
    "03_site_load_queues.png",
    "04_budget_curve.png",
    "04_selected_hubs.png",
    "05_importance.png",
    "05_transfer_vs_structural.png",
]:
    if (FIG / name).exists():
        shutil.copy(FIG / name, IMG / name)


def slide(html: str, cls: str = "") -> str:
    return f'<section class="slide {cls}">{html}</section>'


def stat(big: str, label: str, tone: str = "orange") -> str:
    return f'<div class="stat {tone}"><div class="big">{big}</div><div class="lbl">{label}</div></div>'


slides = []
slides.append(
    slide(
        """
<div class="title-wrap">
  <div class="kicker">Portfolio project · September 2026</div>
  <h1>ChargeScape London</h1>
  <p class="sub">A spatial decision system for EV charging networks under uncertain demand</p>
  <p class="lede">Where should the next rapid-charging hubs in Greater London go, how many ports and what power — and how sure can we be? Built end-to-end from open data, with every assumption visible.</p>
  <p class="byline">Marija Ercegovac · urban planner turned geospatial data scientist · <a href="https://github.com/m-erts/chargescape-london">github.com/m-erts/chargescape-london</a></p>
</div>""",
        "dark",
    )
)

slides.append(
    slide(f"""
<h2>Charging is an infrastructure business that lives or dies on utilisation</h2>
<div class="stats">
  {stat(f"{K['chargers_total']:,}", f"public chargers in London (DfT, {K['dft_date']})")}
  {stat(f"{K['rapid_share']:.0%}", "of them are 50 kW+, vs 24 % across the UK", "teal")}
  {stat(f"{(K['piv_private'] + K['piv_company']) / 1000:.0f}k", "plug-in cars kept in London; 41 % company-kept", "navy")}
  {stat("34 %", "occupancy of rapid units (TfL, observed 2025)")}
</div>
<div class="cols">
  <div class="card"><h3>The economics</h3><p>A hub in the wrong hex idles at 5 % and never pays back; the right one runs above 20–30 % with queues. McKinsey and ICCT put break-even between 15 % and 20 % utilisation — payback halves between 10 % and 20 %.</p></div>
  <div class="card"><h3>The analytics gap</h3><p>Operators describe site selection as a demand model on dozens to hundreds of factors. Public projects almost never predict <em>usage</em> (they predict where chargers already are), carry uncertainty into the decision, model queues and cannibalisation, or say how they would be proven wrong.</p></div>
</div>""")
)

slides.append(
    slide("""
<h2>Four things this system does that gap maps do not</h2>
<ol class="four">
  <li><b>Labels on every dataset.</b> observed / proxy / synthetic — 23 sources in the catalog; the label follows the number into every table.</li>
  <li><b>Usage, checked against reality.</b> Demand is modelled bottom-up, then checked against DfT charger counts × TfL occupancy and open session logs.</li>
  <li><b>Uncertainty reaches the decision.</b> P10/P50/P90 per hex; a robust MILP picks hubs that hold across scenarios; the overlap with the P50 answer says which sites are safe.</li>
  <li><b>Queues, cannibalisation, grid.</b> Erlang-C capacity per hub, new vs stolen demand for any candidate, primary-substation headroom as a filter.</li>
</ol>
<div class="flow"><span>Open data</span><span>H3 features</span><span>Structural demand</span><span>Choice &amp; queues</span><span>Siting MILP</span><span>Maps &amp; test plan</span></div>""")
)

slides.append(
    slide("""
<h2>Supply follows devices; need follows cars without driveways</h2>
<div class="two"><img src="img/01_hex_supply_demand.png" alt="supply and demand hex maps">
<ul>
 <li>Inner boroughs: ~1,400 chargers per 100k residents, mostly 5–7 kW lamp-post units. Rapid share: 40 % in Havering and Hillingdon, under 4 % in Westminster and Hackney.</li>
 <li>Private plug-in cars cluster in outer, house-rich boroughs; Moran's I = 0.73.</li>
 <li>EV owners in flats — the group that depends on public charging — form Gi* hot spots in inner-west and inner-south London.</li>
 <li>Median drive time to a rapid site is a few minutes: in London the binding constraint is capacity and queues, not distance.</li>
</ul></div>""")
)

slides.append(
    slide(f"""
<h2>A demand surface with the uncertainty attached <span class="tag">live map</span></h2>
<div class="mapwrap"><iframe src="../maps/demand_2026.html" loading="lazy" title="demand map"></iframe>
<aside>
 {stat(f"{d26['total_p50']:.0f} GWh", f"public charging demand 2026, P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f})")}
 {stat(f"{d26['phv_p50']:.0f} GWh", "from taxi & private hire — London's rapid-charging anchor", "teal")}
 {stat(f"{d30['total_p50']:.0f} GWh", "in 2030, DFES mid pathway (1,100–1,410 across pathways)", "navy")}
 <p class="note">Structural Monte Carlo model: EV stock × km × kWh/km × public share (depends on off-street parking). Toggle P10 / P50 / P90 / 2030 on the map.</p>
</aside></div>""")
)

slides.append(
    slide(f"""
<h2>No London usage data is open — so the model is checked against what is observed</h2>
<div class="cols">
 <div class="card"><h3>Supply-implied energy</h3><p>28.8k slow + 2.5k rapid chargers (DfT) × TfL-observed occupancy × charging-time share ⇒ ≈ 760 GWh/yr the network <em>could</em> deliver.</p></div>
 <div class="card"><h3>Modelled demand</h3><p>{d26["total_p50"]:.0f} GWh P50 (P10–P90 {d26["total_p10"]:.0f}–{d26["total_p90"]:.0f}); rapid-type demand ≈ {d26["dest_p50"] + d26["phv_p50"]:.0f} GWh — the same order as the rapid side of the supply estimate.</p></div>
</div>
<div class="stats three">
 {stat(f"{K['rapid_sessions_per_charger_day']}", "implied rapid sessions per charger per day (model)")}
 {stat("≈13", "what TfL's 34 % occupancy implies with 38-min sessions", "teal")}
 {stat("≈3", "observed in Dundee's open session log", "navy")}
</div>
<p class="note">The wide band is the honest statement: the two levers are the public-charging share of drivers without a driveway and the size of the electric PHV fleet.</p>""")
)

slides.append(
    slide(f"""
<h2>Where the demand lands today — and where queues form at the peak hour <span class="tag">live map</span></h2>
<div class="mapwrap"><iframe src="../maps/rapid_network_load_2026.html" loading="lazy" title="network load map"></iframe>
<aside>
 {stat(f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}", "rapid sites with P(wait) > 0.5 at the peak hour")}
 {stat(f"{K['util24_median']:.0%}", "median 24 h utilisation of a rapid site", "teal")}
 <p class="note">MNL station choice on OSM drive times (igraph), Erlang-C queues with 38-min service. Supply: Open Charge Map ∪ OSM ∪ NCR, ports calibrated to DfT borough totals. For any candidate hub the model splits captured demand into new vs cannibalised — typically 70–80 % is taken from existing sites.</p>
</aside></div>""")
)

siting_txt = ""
if r20:
    siting_txt = f"£{r20['budget_m']:.0f}M ⇒ {r20['n_hubs']} hubs serving {r20['coverage_share']:.0%} of unmet rapid demand ({r20['covered_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions/day)."
    if r40:
        siting_txt += f" £40M ⇒ {r40['n_hubs']} hubs, {r40['coverage_share']:.0%}."
slides.append(
    slide(f"""
<h2>Siting new 4 × 150 kW hubs under budget, capacity, grid and demand uncertainty <span class="tag">live map</span></h2>
<div class="mapwrap"><iframe src="../maps/siting_hubs_budget_20m.html" loading="lazy" title="siting map"></iframe>
<aside>
 <img src="img/04_budget_curve.png" alt="budget curve" class="small">
 <p class="note"><b>{siting_txt}</b></p>
 <p class="note">The regime is capacity-bound: a hub absorbs ≈{K.get("siting_meta", {}).get("hub_capacity_sessions_day", 33):.0f} sessions/day at P(wait) ≤ 15 %, so coverage grows almost linearly with budget. Greedy uncapacitated coverage overstates served demand several-fold. Low P50/robust overlap is degeneracy — many equivalent hub sets — not fragility.</p>
</aside></div>""")
)

slides.append(
    slide(f"""
<h2>Do context features explain observed utilisation anywhere? A negative result, on purpose</h2>
<div class="two"><img src="img/05_importance.png" alt="feature importance">
<div>
 <div class="stats two-stats">{stat("0.70", "R² with random 5-fold CV (looks respectable)", "teal")}{stat("−0.25", "R² with leave-city-out CV (the number that matters)")}</div>
 <ul>
  <li>{K["transfer_stations"]} chargers with open session logs (Dundee, Perth &amp; Kinross, Palo Alto, Boulder); LightGBM on OpenStreetMap context, population and charger power.</li>
  <li>Charger power and the city's level dominate; rankings do not transfer reliably (Spearman −0.3 to +0.6 by city).</li>
  <li>Implication: any "geo-embedding site model" must be validated out-of-city against observed usage — this is the test to ask for.</li>
 </ul>
</div></div>""")
)

slides.append(
    slide("""
<h2>Limitations — and how the whole thing would be proven wrong</h2>
<div class="cols">
 <div class="card"><h3>Known limitations</h3><ul>
  <li>No open London charger-level usage; behaviour from other UK cities and fleet trials.</li>
  <li>Open Charge Map covers most sites but not all ports; remaining gaps are closed by borough-level calibration to DfT totals.</li>
  <li>Choice-model coefficients are literature-informed, not estimated.</li>
  <li>Grid constraint stops at primary-substation headroom.</li>
  <li>Area-weighted LSOA→hex interpolation; ≈1.4 % of population in dropped edge hexes.</li></ul></div>
 <div class="card teal"><h3>The post-hoc test</h3><p>DfT/Zapmap publish borough device counts quarterly; TfL publishes utilisation by charger type.</p><p>Hubs opened after July 2026 in hexes flagged here as high unmet demand should reach above-median utilisation within a year.</p><p>If not, the model card names the priors to revisit first: PHV fleet size, public share without home charging, choice radius.</p><p><b>Predict → deploy → measure → retrain</b> is the product; the maps are its interface.</p></div>
</div>""")
)

slides.append(
    slide(
        """
<div class="title-wrap">
  <h1 class="h1s">Explore it</h1>
  <ul class="links">
   <li>Repository: <a href="https://github.com/m-erts/chargescape-london">github.com/m-erts/chargescape-london</a> — code, 16 tests, data catalog with 23 source cards, methodology, model card</li>
   <li>Notebooks 01–05: supply audit · demand surface · choice &amp; queues · siting · utilisation transfer</li>
   <li>Live maps (MapLibre): <a href="../maps/demand_2026.html">demand 2026</a> · <a href="../maps/rapid_network_load_2026.html">network load &amp; queues</a> · <a href="../maps/siting_hubs_budget_20m.html">selected hubs, £20M</a></li>
   <li>Reproduce: <code>pip install -e . → make data → make features → make models → make maps</code></li>
  </ul>
  <p class="byline">Marija Ercegovac · mercegovacm@gmail.com</p>
</div>""",
        "dark",
    )
)

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChargeScape London — slides</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600&family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--navy:#14213D;--orange:#E4572E;--teal:#0C7C70;--ink:#1A2027;--muted:#5B6B7A;--pale:#EEF2F4;--bg:#FFFFFF}}
*{{box-sizing:border-box}} html,body{{margin:0;height:100%;background:var(--bg);color:var(--ink);font-family:"Golos Text","Helvetica Neue",Arial,sans-serif;font-size:clamp(14px,1.25vw,19px);line-height:1.45}}
.deck{{height:100vh;overflow:hidden;position:relative}}
.slide{{position:absolute;inset:0;padding:5vh 5vw;display:none;flex-direction:column;overflow:hidden}}
.slide.active{{display:flex;animation:fade .35s ease}}
@keyframes fade{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
.slide.dark{{background:var(--navy);color:#fff}} .slide.dark a{{color:#9FD8CF}}
h1{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(38px,6vw,84px);line-height:1.05;margin:.1em 0 .2em;text-wrap:balance}}
h1.h1s{{font-size:clamp(34px,5vw,64px)}}
h2{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(22px,2.6vw,40px);line-height:1.15;margin:0 0 .6em;color:var(--navy);text-wrap:balance}}
h3{{margin:0 0 .4em;font-size:1.05em;color:var(--navy)}}
.kicker{{font-family:"JetBrains Mono",monospace;font-size:.8em;letter-spacing:.08em;text-transform:uppercase;color:#C8D3DC}}
.title-wrap{{max-width:60ch;margin:auto 0}} .sub{{font-family:Spectral,Georgia,serif;font-size:clamp(18px,2.2vw,30px);color:#C8D3DC;margin:0 0 .8em}} .lede{{font-size:1.05em;max-width:60ch}} .byline{{color:#C8D3DC;font-size:.9em;margin-top:2em}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:2vw;margin:0 0 3vh}} .stats.three{{grid-template-columns:repeat(3,1fr)}} .two-stats{{grid-template-columns:1fr 1fr;margin-bottom:1.5vh}}
.stat .big{{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(28px,3.6vw,54px);line-height:1;color:var(--orange)}} .stat.teal .big{{color:var(--teal)}} .stat.navy .big{{color:var(--navy)}} .stat .lbl{{color:var(--muted);font-size:.85em;margin-top:.35em}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:2vw}} .card{{background:var(--pale);border-radius:10px;padding:1.2em 1.4em}} .card.teal{{background:#E6F2F0}} .card p{{margin:0 0 .6em}} .card ul{{margin:0;padding-left:1.1em}} .card li{{margin:.3em 0}}
ol.four{{counter-reset:n;list-style:none;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:1.2vh 2vw;margin:0 0 3vh}} ol.four li{{position:relative;padding-left:2.6em;font-size:1em}} ol.four li::before{{counter-increment:n;content:counter(n);position:absolute;left:0;top:0;width:1.9em;height:1.9em;border-radius:50%;background:var(--teal);color:#fff;display:grid;place-items:center;font-weight:600}} ol.four li:nth-child(1)::before,ol.four li:nth-child(4)::before{{background:var(--orange)}} ol.four li:nth-child(3)::before{{background:var(--navy)}}
.flow{{display:flex;gap:.6vw;margin-top:auto}} .flow span{{flex:1;background:var(--navy);color:#fff;padding:.6em .4em;text-align:center;font-size:.85em;clip-path:polygon(0 0,92% 0,100% 50%,92% 100%,0 100%,8% 50%)}} .flow span:first-child{{clip-path:polygon(0 0,92% 0,100% 50%,92% 100%,0 100%)}} .flow span:nth-child(2n){{background:var(--teal)}} .flow span:nth-child(3){{background:var(--orange)}}
.two{{display:grid;grid-template-columns:1.25fr 1fr;gap:2vw;align-items:start;min-height:0}} .two img{{width:100%;height:auto;max-height:72vh;object-fit:contain;border-radius:6px}} .two ul{{margin:0;padding-left:1.1em}} .two li{{margin:.5em 0}}
.mapwrap{{display:grid;grid-template-columns:1.6fr 1fr;gap:2vw;flex:1;min-height:0}} .mapwrap iframe{{width:100%;height:100%;min-height:55vh;border:0;border-radius:10px;box-shadow:0 1px 8px rgba(0,0,0,.15)}} .mapwrap aside .stat{{margin-bottom:2vh}} .mapwrap aside img.small{{width:100%;border-radius:6px;margin-bottom:1vh}}
.note{{color:var(--muted);font-size:.9em}} .tag{{font-family:"JetBrains Mono",monospace;font-size:.45em;vertical-align:middle;background:var(--teal);color:#fff;padding:.2em .6em;border-radius:1em;margin-left:.5em}}
ul.links{{font-size:1.05em;line-height:1.6;padding-left:1.1em}} code{{font-family:"JetBrains Mono",monospace;font-size:.9em;background:rgba(255,255,255,.12);padding:.1em .4em;border-radius:4px}}
.nav{{position:fixed;bottom:14px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:9}} .nav i{{width:9px;height:9px;border-radius:50%;background:#B8C2CC;cursor:pointer;display:block}} .nav i.on{{background:var(--orange)}}
.counter{{position:fixed;bottom:12px;right:18px;font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--muted);z-index:9}}
.hint{{position:fixed;top:12px;right:18px;font-size:12px;color:var(--muted);z-index:9}}
@media (max-width:900px){{.stats,.cols,.two,.mapwrap,ol.four{{grid-template-columns:1fr}} .mapwrap iframe{{min-height:45vh}} .slide{{overflow:auto}}}}
@media (prefers-reduced-motion:reduce){{.slide.active{{animation:none}}}}
</style></head><body>
<div class="deck">{"".join(slides)}</div>
<div class="nav" id="nav"></div><div class="counter" id="counter"></div><div class="hint">← → to navigate · F for fullscreen</div>
<script>
const S=[...document.querySelectorAll('.slide')];let i=Math.max(0,Math.min(S.length-1,parseInt(location.hash.slice(1))||0));
const nav=document.getElementById('nav');S.forEach((_,k)=>{{const d=document.createElement('i');d.onclick=()=>go(k);nav.appendChild(d)}});
function go(k){{i=(k+S.length)%S.length;S.forEach((s,j)=>s.classList.toggle('active',j===i));[...nav.children].forEach((d,j)=>d.classList.toggle('on',j===i));document.getElementById('counter').textContent=(i+1)+' / '+S.length;location.hash=i;}}
addEventListener('keydown',e=>{{if(['ArrowRight',' ','PageDown'].includes(e.key))go(i+1);else if(['ArrowLeft','PageUp'].includes(e.key))go(i-1);else if(e.key==='f'||e.key==='F')document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen();}});
go(i);
</script></body></html>"""
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "index.html").write_text(html, encoding="utf-8")
print("wrote", OUT / "index.html", "slides:", len(slides))
