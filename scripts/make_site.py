"""Project landing page for GitHub Pages (docs/index.html), styled per DESIGN.md.

Numbers come from reports/tables/key_numbers.json. The figure is the same inline SVG as on the
title slide, so the page has no raster images and follows the light or dark theme.
"""

from __future__ import annotations

import json
from pathlib import Path

from make_slides import london_figure

from chargescape.viz.design import THEME_BOOT_JS, tokens_css

ROOT = Path(__file__).resolve().parents[1]
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
REPO = "https://github.com/m-erts/chargescape-london"
NBV = "https://nbviewer.org/github/m-erts/chargescape-london/blob/main/notebooks"
MINUS = "−"

CSS = """
body{font-size:15px;line-height:1.6}
h1,h2,h3,p,ul,dl,dd,figure{margin:0}
ul{padding:0;list-style:none}
.page{max-width:1200px;margin:0 auto;border-left:1px solid var(--border);border-right:1px solid var(--border);min-height:100dvh}
.bar{display:flex;justify-content:space-between;border-bottom:1px solid var(--border);height:56px;position:sticky;top:0;z-index:var(--z-bar);background:var(--bg)}
.brand{display:flex;align-items:center;padding:0 32px;font-weight:600;letter-spacing:-0.01em;text-decoration:none}
.bar nav{display:flex}
.bar nav > *{display:flex;align-items:center;padding:0 20px;border-left:1px solid var(--border);font-size:14px;text-decoration:none;color:var(--muted);transition:color 150ms ease,background-color 150ms ease}
.bar button{appearance:none;border-top:0;border-right:0;border-bottom:0;background:var(--bg);font-size:14px;cursor:pointer}
.bar button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.bar nav > *:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
@media (hover:hover) and (pointer:fine){.bar nav > a:hover,.bar button[aria-pressed="false"]:hover{color:var(--fg);background:var(--surface)}}
.grid{display:grid;gap:1px;background:var(--border);border-bottom:1px solid var(--border)}
.cell{background:var(--bg);padding:32px;min-width:0}
.hero{grid-template-columns:55fr 45fr}
.intro{display:flex;flex-direction:column;padding-top:64px}
h1{font-size:clamp(40px,5.4vw,68px);line-height:1;letter-spacing:-0.045em;font-weight:600}
.sub{font-size:clamp(18px,2vw,22px);line-height:1.3;letter-spacing:-0.02em;margin-top:20px;max-width:30ch;text-wrap:balance}
.q{color:var(--muted);margin-top:20px;max-width:56ch;text-wrap:pretty}
.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:40px}
.actions a{display:inline-flex;align-items:center;height:40px;padding:0 16px;border:1px solid var(--border);text-decoration:none;font-size:14px;font-weight:500;transition:background-color 150ms ease,border-color 150ms ease,transform 150ms ease}
.actions a.primary{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.actions a:active{transform:scale(0.97)}
@media (hover:hover) and (pointer:fine){.actions a:not(.primary):hover{background:var(--surface);border-color:var(--fg)}}
.fig{padding:0;display:grid;grid-template-rows:minmax(0,1fr) auto}
.london{width:100%;height:auto;padding:24px;display:block}
.london .hx{stroke:var(--bg);stroke-width:0.6;vector-effect:non-scaling-stroke}
.london .r1{fill:var(--r1)}.london .r2{fill:var(--r2)}.london .r3{fill:var(--r3)}.london .r4{fill:var(--r4)}.london .r5{fill:var(--r5)}.london .r6{fill:var(--r6)}
.london .core{fill:var(--accent);stroke:var(--bg);stroke-width:2.5}
.london .rest{fill:var(--bg);stroke:var(--fg);stroke-width:2.5}
figcaption{padding:12px 24px;border-top:1px solid var(--border);color:var(--muted);font-size:13px}
.metrics{grid-template-columns:repeat(4,1fr)}
.metric .k{color:var(--muted);font-size:13px}
.metric .v{font-size:32px;line-height:1.05;letter-spacing:-0.04em;font-weight:500;margin:10px 0 8px;white-space:nowrap}
.metric .d{color:var(--muted);font-size:13px;text-wrap:pretty}
.section{grid-template-columns:240px minmax(0,1fr)}
.section > .cell:first-child{padding-top:16px;padding-bottom:16px}
.section h2{font-size:15px;font-weight:600;letter-spacing:-0.01em}
.section .cell.list{padding:0}
.list li{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:24px;padding:16px 32px;border-bottom:1px solid var(--border)}
.list li:last-child{border-bottom:0}
.list a{font-weight:500}
.list span{color:var(--muted)}
footer{padding:24px 32px 48px;color:var(--muted);font-size:13px;max-width:90ch}
@media (max-width:860px){
  .hero,.section{grid-template-columns:1fr}
  .metrics{grid-template-columns:1fr 1fr}
  .cell,.list li{padding-left:20px;padding-right:20px}
  .brand{padding:0 20px}
  .bar nav > a{display:none}
  .list li{grid-template-columns:1fr;gap:4px}
  .intro{padding-top:40px}
  .page{border:0}
  footer{padding-left:20px;padding-right:20px}
}
"""

JS = """
const b = document.getElementById('theme');
b.setAttribute('aria-pressed', String(csIsDark()));
b.addEventListener('click', () => {
  const dark = !csIsDark();
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  try { localStorage.setItem('cs-theme', dark ? 'dark' : 'light'); } catch (e) {}
  b.setAttribute('aria-pressed', String(dark));
});
"""


def metric(label: str, value: str, detail: str) -> str:
    return f'<div class="cell metric"><p class="k">{label}</p><p class="v mono">{value}</p><p class="d">{detail}</p></div>'


def section(title: str, items: list[tuple[str, str, str]]) -> str:
    lis = "".join(f'<li><a href="{href}">{name}</a><span>{text}</span></li>' for href, name, text in items)
    return f'<section class="grid section"><div class="cell"><h2>{title}</h2></div><div class="cell list"><ul>{lis}</ul></div></section>'


def main() -> None:
    d = K["demand_gwh"]["2026"]
    r20 = next(r for r in K["siting"] if int(r["budget_m"]) == 20)
    tr = K["transfer"]
    r2 = f"{abs(tr['r2_leave_city_out']):.2f}"
    metrics = (
        metric(
            "Public charging demand, 2026",
            f"{d['total_p50']:.0f} GWh",
            f"P10 to P90: {d['total_p10']:.0f} to {d['total_p90']:.0f}",
        )
        + metric(
            "Rapid sites that queue at the peak",
            f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
            "P(wait) above 0.5 in the peak hour",
        )
        + metric(
            "Recommended plan at £20M",
            f"{r20['rec_n_hubs']} hubs",
            f"serve {round(100 * r20['rec_share_p50'])}% of unmet rapid demand",
        )
        + metric(
            "Usage model in an unseen city",
            f"R² {MINUS if tr['r2_leave_city_out'] < 0 else ''}{r2}",
            f"against {tr['r2_random']:.2f} with random cross-validation",
        )
    )
    maps = [
        (
            "maps/supply_2026.html",
            "Who has chargers, who has EVs",
            f"{K['sites_total']:,} charging sites by power over EV ownership and housing",
        ),
        ("maps/demand_2026.html", "Public charging demand", "P10, P50, P90 and 2030 as 3D hexes"),
        (
            "maps/rapid_network_load_2026.html",
            "Rapid network load",
            "Drive time, modelled load and peak-hour queues per site",
        ),
        (
            "maps/siting_hubs.html",
            "Where the next hubs go",
            "Budgets from £5M to £40M, one plan per demand scenario, robust core",
        ),
    ]
    nbs = [
        (
            "01_supply_audit",
            "Supply audit",
            "Chargers against EVs, Moran's I and Gi* hot spots, drive-time gaps",
        ),
        ("02_demand_surface", "Demand surface", "Monte Carlo demand with P10, P50, P90, calibration, 2030"),
        (
            "03_choice_and_queues",
            "Choice and queues",
            "Logit station choice, Erlang C queues, new against captured demand",
        ),
        ("04_siting", "Siting", "Capacitated MILP per scenario, regret, budget sweep, sensitivity"),
        ("05_utilisation_transfer", "Transfer test", "Does a context model explain usage in an unseen city?"),
    ]
    docs = [
        ("docs/methodology.md", "Methodology", "Every model step, with formulas and assumptions"),
        ("docs/architecture.md", "Architecture and stack", "What each tool does and why it was chosen"),
        ("docs/model_card.md", "Model card", "Intended use, limits and how the result could be proven wrong"),
        (
            "docs/data_catalog/README.md",
            "Data catalog",
            f"{K['n_sources']} datasets with source, licence and status",
        ),
        ("docs/roadmap.md", "Roadmap", "What changes with operator data"),
    ]
    desc = "A spatial decision system for EV charging networks under uncertain demand. London case study built from open data."
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChargeScape London</title><meta name="description" content="{desc}">
<meta property="og:title" content="ChargeScape London"><meta property="og:description" content="{desc}"><meta property="og:image" content="img/hero.png">
<script>{THEME_BOOT_JS}</script>
<style>{tokens_css("vendor")}{CSS}</style></head><body>
<div class="page">
<header class="bar"><a class="brand" href="./">ChargeScape London</a>
<nav aria-label="Project"><a href="slides/">Slides</a><a href="maps/">Maps</a><a href="{REPO}">GitHub</a><button type="button" id="theme" aria-pressed="false">Dark</button></nav></header>
<main>
<section class="grid hero"><div class="cell intro"><h1>ChargeScape London</h1>
<p class="sub">A spatial decision system for EV charging networks under uncertain demand.</p>
<p class="q">Where should London's next rapid-charging hubs go, how large should they be, and how sure can we be? Built end to end from open data, with every assumption visible.</p>
<div class="actions"><a class="primary" href="slides/">Open the slides</a><a href="maps/">Interactive maps</a><a href="{REPO}">Repository</a></div></div>
<figure class="cell fig">{london_figure()}<figcaption>Unmet rapid-charging demand and the recommended £20M plan. Filled hubs are chosen under every demand scenario.</figcaption></figure></section>
<section class="grid metrics" aria-label="Key results">{metrics}</section>
{section("Interactive maps", maps)}
{section("Notebooks", [(f"{NBV}/{f}.ipynb", t, x) for f, t, x in nbs])}
{section("Documentation", [(f"{REPO}/blob/main/{p}", t, x) for p, t, x in docs])}
</main>
<footer>Marija Ercegovac, <a href="https://github.com/m-erts">github.com/m-erts</a>. Code under MIT. Data under ODbL, OGL and CC BY, see the <a href="{REPO}/blob/main/data/LICENSE-DATA.md">data licences</a>. Basemap by CARTO and OpenStreetMap contributors.</footer>
</div>
<script>{JS}</script></body></html>"""
    (ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "docs" / ".nojekyll").write_text("")
    print(f"wrote docs/index.html | {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
