"""Build the presentation (docs/slides/index.html), styled per DESIGN.md.

* One fixed 16:9 stage. Every size is a multiple of --u (1% of the stage width), so the layout is
  identical on any screen while borders stay exactly 1px and the maps render at native resolution.
* Every number comes from reports/tables/key_numbers.json, so the deck cannot drift from the results.
* Charts are inline HTML and SVG drawn from the same data, and follow the light or dark theme.
* Live MapLibre maps are loaded when their slide is shown and follow the deck theme.
* Slide changes are instant (keyboard-driven actions are never animated).

Keys: left and right arrows, space, Page Up, Page Down, Home, End, F for full screen, T for theme.
Below 768px the deck becomes a scrolling document.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from chargescape.utils.paths import PROCESSED
from chargescape.viz.design import THEME_BOOT_JS, tokens_css
from chargescape.viz.export_maplibre import N_CLASSES, _breaks, _hex_layer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "slides"
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
REPO = "https://github.com/m-erts/chargescape-london"
REPO_TEXT = "github.com/m-erts/chargescape-london"
NBVIEWER = "https://nbviewer.org/github/m-erts/chargescape-london/tree/main/notebooks/"
MINUS = "−"


# ----------------------------------------------------------------------------- numbers
def n(x: float, dec: int = 0) -> str:
    s = f"{abs(x):,.{dec}f}"
    return (MINUS + s) if x < 0 and float(s.replace(",", "")) != 0 else s


def pct(x: float) -> str:
    return f"{round(100 * x)}%"


D26, D30 = K["demand_gwh"]["2026"], K["demand_gwh"]["2030_mid"]
D30_LO, D30_HI = K["demand_gwh"]["2030_low"]["total_p50"], K["demand_gwh"]["2030_high"]["total_p50"]
SIT = {int(r["budget_m"]): r for r in K["siting"]}
R20, R40 = SIT[20], SIT[40]
CAP = K["siting_meta"]["hub_capacity_sessions_day"]
N_RAPID = K["chargers_rapid"]
N_SLOW = K["chargers_total"] - N_RAPID
SUPPLY_SLOW = N_SLOW * 7 * 8760 * 0.47 * 0.45 / 1e6
SUPPLY_RAPID = N_RAPID * 60 * 8760 * 0.34 * 0.85 / 1e6
TR = K["transfer"]
CAN = K["cannibalisation"]
SENS = K["sensitivity"]
BOR = K["boroughs"]


# ----------------------------------------------------------------------------- components
def metric(label: str, value: str, detail: str = "", cls: str = "") -> str:
    d = f'<p class="d">{detail}</p>' if detail else ""
    return f'<div class="cell metric {cls}"><p class="k">{label}</p><p class="v mono">{value}</p>{d}</div>'


def text_cell(title: str, body: str, cls: str = "") -> str:
    return f'<div class="cell prose {cls}"><h3>{title}</h3><p>{body}</p></div>'


def rows(items: list[tuple[str, str]], cls: str = "") -> str:
    body = "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in items)
    return f'<dl class="rows {cls}">{body}</dl>'


def table(
    head: list[str], body: list[list[str]], num: tuple[int, ...] = (), cls: str = "", caption: str = ""
) -> str:
    def c(tag: str, i: int, v: str, extra: str = "") -> str:
        k = ' class="num"' if i in num else ""
        return f"<{tag}{k}{extra}>{v}</{tag}>"

    th = "".join(c("th", i, h, ' scope="col"') for i, h in enumerate(head))
    trs = "".join("<tr>" + "".join(c("td", i, v) for i, v in enumerate(r)) + "</tr>" for r in body)
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f'<table class="t {cls}">{cap}<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def bar(share: float, cls: str = "") -> str:
    return f'<i class="bar {cls}" style="width:{max(0.0, min(1.0, share)) * 100:.1f}%"></i>'


def map_cell(name: str, caption: str, title: str) -> str:
    return (
        f'<figure class="cell map"><iframe data-src="../maps/{name}.html?embed" title="{escape(title)}"></iframe>'
        f'<figcaption><span>{caption}</span><a href="../maps/{name}.html">Open the full map</a></figcaption></figure>'
    )


def slide(title: str, body: str, lead: str = "", layout: str = "", label: str = "") -> str:
    ld = f'<p class="lead">{lead}</p>' if lead else ""
    return f'<section class="slide" aria-label="{escape(label or title)}" hidden><header class="head"><h2>{title}</h2>{ld}</header><div class="body {layout}">{body}</div></section>'


# ----------------------------------------------------------------------------- figures
def london_figure() -> str:
    """Unmet demand hexes and the recommended £20M plan as one theme-aware inline SVG."""
    h = _hex_layer().to_crs(27700)
    br = _breaks(h["unmet"])
    cls = np.searchsorted(np.array(br), h["unmet"].fillna(0).to_numpy(), side="right")
    minx, miny, maxx, maxy = h.total_bounds
    s = 1000.0 / (maxx - minx)
    height = (maxy - miny) * s
    paths = []
    for k in range(N_CLASSES):
        d = []
        for geom in h.geometry[cls == k]:
            pts = " ".join(
                f"{(x - minx) * s:.1f},{(maxy - y) * s:.1f}" for x, y in list(geom.exterior.coords)[:-1]
            )
            d.append(f"M{pts}Z")
        if d:
            paths.append(f'<path class="hx r{k + 1}" d="{"".join(d)}"/>')
    sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
    rec = sel[(sel.budget_m == 20) & (sel.recommended)].merge(h[["h3", "geometry"]], on="h3")
    marks = []
    for core in (False, True):
        for geom in rec.loc[rec.core == core, "geometry"]:
            c = geom.centroid
            marks.append(
                f'<circle class="{"core" if core else "rest"}" cx="{(c.x - minx) * s:.1f}" cy="{(maxy - c.y) * s:.1f}" r="10"/>'
            )
    alt = f"Map of Greater London. Hexes are shaded by unmet rapid-charging demand, darkest in the centre and along main roads. {len(rec)} recommended hubs are marked, {int(rec.core.sum())} of them in the robust core."
    return f'<svg class="london" viewBox="-12 -12 1024 {height + 24:.0f}" role="img" aria-label="{alt}">{"".join(paths)}{"".join(marks)}</svg>'


def budget_chart() -> str:
    rws = [SIT[b] for b in sorted(SIT)]
    total = rws[0]["total_unmet_p50"]
    x0, x1, y0, y1 = 56, 462, 352, 30
    top = 3000.0

    def fx(b: float) -> float:
        return x0 + (x1 - x0) * b / 40.0

    def fy(v: float) -> float:
        return y0 - (y0 - y1) * v / top

    grid = "".join(
        f'<line class="g" x1="{x0}" x2="{x1}" y1="{fy(v):.1f}" y2="{fy(v):.1f}"/><text class="ax" x="{x0 - 8}" y="{fy(v) + 4:.1f}" text-anchor="end">{n(v)}</text>'
        for v in (0, 1000, 2000, 3000)
    )
    ticks = "".join(
        f'<text class="ax" x="{fx(r["budget_m"]):.1f}" y="{y0 + 20}" text-anchor="middle">£{int(r["budget_m"])}M</text>'
        for r in rws
    )
    exact = " ".join(f"{fx(r['budget_m']):.1f},{fy(r['covered_p50']):.1f}" for r in rws)
    greedy = " ".join(f"{fx(r['budget_m']):.1f},{fy(r['greedy_uncapacitated_covered']):.1f}" for r in rws)
    pts = "".join(
        f'<rect class="pt" x="{fx(r["budget_m"]) - 3.5:.1f}" y="{fy(r["covered_p50"]) - 3.5:.1f}" width="7" height="7"/>'
        for r in rws
    )
    last = rws[-1]["budget_m"]
    lab = "".join(
        '<text class="val" x="{:.1f}" y="{:.1f}"{}>{}</text>'.format(
            fx(r["budget_m"]) + (-10 if r["budget_m"] == last else 8),
            fy(r["covered_p50"]) + (26 if r["budget_m"] == last else 17),
            ' text-anchor="end"' if r["budget_m"] == last else "",
            n(r["covered_p50"]),
        )
        for r in rws
    )
    alt = (
        "Line chart. With capacity, served demand rises almost linearly from "
        + n(rws[0]["covered_p50"])
        + " sessions per day at £5M to "
        + n(rws[-1]["covered_p50"])
        + " at £40M. The greedy estimate without capacity claims "
        + n(rws[0]["greedy_uncapacitated_covered"])
        + " already at £5M."
    )
    return (
        f'<svg class="chart" viewBox="0 0 480 392" role="img" aria-label="{alt}">{grid}'
        f'<line class="cap" x1="{x0}" x2="{x1}" y1="{fy(total):.1f}" y2="{fy(total):.1f}"/><text class="ax" x="{x1}" y="{fy(total) - 7:.1f}" text-anchor="end">unmet demand {n(total)}</text>'
        f'<polyline class="greedy" points="{greedy}"/><polyline class="exact" points="{exact}"/>{pts}{lab}{ticks}'
        f'<text class="ax" x="{fx(10) + 10:.1f}" y="{fy(rws[1]["greedy_uncapacitated_covered"]) + 18:.1f}">greedy, capacity ignored</text></svg>'
    )


# ----------------------------------------------------------------------------- slides
def build() -> list[str]:
    out = []
    dens, top, bot = BOR["densest"], BOR["rapid_share_top"], BOR["rapid_share_bottom"]

    # 1 title
    out.append(
        '<section class="slide title" aria-label="ChargeScape London" hidden><div class="body">'
        '<div class="cell intro"><h1>ChargeScape London</h1>'
        '<p class="sub">A spatial decision system for EV charging networks under uncertain demand.</p>'
        '<p class="q">Where should London\'s next rapid-charging hubs go, how large should they be, and how sure can we be? Built end to end from open data, with every assumption visible.</p>'
        f'<p class="by">Marija Ercegovac, geospatial data science<br><a href="{REPO}">{REPO_TEXT}</a></p></div>'
        f'<figure class="cell fig">{london_figure()}<figcaption>Unmet rapid-charging demand and the recommended £20M plan. Filled hubs are chosen under every demand scenario.</figcaption></figure>'
        '<div class="strip">'
        + metric(
            "Public charging demand, 2026",
            f"{n(D26['total_p50'])} GWh",
            f"P10 to P90: {n(D26['total_p10'])} to {n(D26['total_p90'])}",
        )
        + metric(
            "Rapid sites that queue at the peak",
            f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
            "P(wait) above 0.5 in the peak hour",
        )
        + metric(
            "Recommended plan at £20M",
            f"{R20['rec_n_hubs']} hubs",
            f"serve {pct(R20['rec_share_p50'])} of unmet rapid demand",
        )
        + metric(
            "Usage model in an unseen city",
            f"R² {n(TR['r2_leave_city_out'], 2)}",
            f"against {n(TR['r2_random'], 2)} with random cross-validation",
        )
        + "</div></div></section>"
    )

    # 2 problem
    out.append(
        slide(
            "Charging is an infrastructure business that lives or dies on utilisation",
            '<div class="strip">'
            + metric("Public chargers in London", n(K["chargers_total"]), "DfT, 1 July 2026", "big")
            + metric(
                "Share rated 50 kW or more",
                pct(K["rapid_share"]),
                f"{pct(BOR['uk_rapid_share'])} across the UK",
                "big",
            )
            + metric("Plug-in cars kept in London", "300k", "DfT vehicle licensing, Q1 2026", "big")
            + metric("Occupancy of rapid chargers", "34%", "TfL, observed in 2025", "big")
            + "</div>"
            + '<div class="pair">'
            + text_cell(
                "The economics",
                "A hub in the wrong place idles at 5% and never pays back. A hub in the right place runs above 20% and starts to queue. Industry analyses put break-even at 15 to 20% utilisation.",
                "big",
            )
            + text_cell(
                "The analytics gap",
                "Operators describe site selection as a demand model with dozens to hundreds of factors. Public projects usually predict where chargers already are, ignore queues and cannibalisation, and never say how they could be proven wrong.",
                "big",
            )
            + "</div>",
            layout="halves",
        )
    )

    # 3 approach
    steps = [
        ("Open data", f"{K['n_sources']} datasets"),
        ("H3 features", f"{n(K['n_hexes'])} hexes"),
        ("Demand", "Monte Carlo"),
        ("Choice and queues", "logit, Erlang C"),
        ("Siting", "MILP, HiGHS"),
        ("Maps and test plan", "MapLibre"),
    ]
    out.append(
        slide(
            "What this system does differently",
            '<div class="cell flush">'
            + rows(
                [
                    (
                        "A label on every dataset",
                        f"Observed, proxy or synthetic. {K['n_sources']} datasets in the catalog, and the label follows each number into every table.",
                    ),
                    (
                        "Demand checked against reality",
                        "Modelled bottom up, then compared with DfT charger counts, TfL occupancy and open session logs.",
                    ),
                    (
                        "Uncertainty reaches the decision",
                        "P10, P50 and P90 for every hex. One plan per demand scenario, each tested under the others.",
                    ),
                    (
                        "Queues, cannibalisation, grid",
                        "Erlang C capacity per hub, new against captured demand for any candidate, substation headroom as a filter.",
                    ),
                ],
                cls="lg",
            )
            + "</div>"
            + '<ol class="pipe">'
            + "".join(
                f'<li class="cell"><span class="mono idx">{i + 1}</span><b>{a}</b><span class="mono sub">{b}</span></li>'
                for i, (a, b) in enumerate(steps)
            )
            + "</ol>",
            layout="stack",
        )
    )

    # 4 data
    src = K["sites_by_source"]
    out.append(
        slide(
            f"{K['n_sources']} open datasets, each labelled observed, proxy or synthetic",
            '<div class="cell flush">'
            + table(
                ["Layer", "Sources", "Status"],
                [
                    [
                        "Supply",
                        f"Open Charge Map ({n(src.get('ocm', 0))} points), OpenStreetMap, National Chargepoint Registry 2021, DfT statistics for July 2026",
                        "observed",
                    ],
                    [
                        "Where EVs live",
                        "Census 2021 for 4,994 small areas, DfT vehicle licensing for Q1 2026, Indices of Deprivation 2025",
                        "observed",
                    ],
                    [
                        "Activity and traffic",
                        "74,000 OpenStreetMap places, LAEI 2022 road flows with taxi and private hire, TfL stations",
                        "observed, proxy",
                    ],
                    [
                        "Grid and future",
                        "UK Power Networks substation headroom for 2026, DFES 2026 pathways to 2030",
                        "proxy",
                    ],
                    [
                        "Behaviour elsewhere",
                        "Charging session logs from Dundee, Perth and Kinross, Palo Alto and Boulder",
                        "observed",
                    ],
                    [
                        "Model outputs",
                        "Monte Carlo demand draws and literature-informed choice parameters, never presented as observed",
                        "synthetic",
                    ],
                ],
                cls="status",
            )
            + "</div>"
            + '<div class="strip three">'
            + metric(
                "Charging sites", n(K["sites_total"]), "after de-duplication within 50 m across three sources"
            )
            + metric("Hexes", n(K["n_hexes"]), "H3 resolution 8, 0.74 km² each, covering Greater London")
            + metric(
                "Chargers with observed usage", n(TR["n_stations"]), "in four cities, used to test transfer"
            )
            + "</div>",
            layout="stack",
        )
    )

    # 5 supply
    out.append(
        slide(
            "Supply follows devices. Need follows cars without driveways.",
            map_cell(
                "supply_2026",
                "Live map. Switch the hex layer, click a site or a hex.",
                "Map of charging sites and EV ownership",
            )
            + '<div class="cell flush">'
            + rows(
                [
                    (
                        "Inner boroughs",
                        f"About {n(round(dens[0]['per_100k'], -2))} chargers per 100,000 residents in {dens[0]['name']} and {dens[1]['name']}, mostly lamp-post units of 5 to 7 kW.",
                    ),
                    (
                        "Rapid share",
                        f"{pct(top[0]['share'])} in {top[0]['name']} and {pct(top[1]['share'])} in {top[1]['name']}. Under {int(np.ceil(100 * bot[2]['share']))}% in {bot[0]['name']}, {bot[1]['name']} and {bot[2]['name']}.",
                    ),
                    (
                        "Private EVs",
                        f"Clustered in outer boroughs with houses and driveways. Moran's I is {n(K['moran_private_ev'], 2)}.",
                    ),
                    (
                        "Drive time",
                        f"A median of {n(K['median_tt_nearest_rapid_min'], 1)} minutes to a rapid site. The constraint is capacity, not distance.",
                    ),
                ],
                cls="stacked lg",
            )
            + "</div>",
            layout="split",
        )
    )

    # 6 demand
    out.append(
        slide(
            "A demand surface with the uncertainty attached",
            map_cell(
                "demand_2026",
                "Live map. Switch between P10, P50, P90 and 2030.",
                "3D map of public charging demand",
            )
            + '<div class="side">'
            + metric(
                "Public charging demand, 2026",
                f"{n(D26['total_p50'])} GWh",
                f"P10 to P90: {n(D26['total_p10'])} to {n(D26['total_p90'])}",
            )
            + metric(
                "Taxi and private hire", f"{n(D26['phv_p50'])} GWh", "the anchor of rapid charging in London"
            )
            + metric(
                "Demand in 2030",
                f"{n(D30['total_p50'])} GWh",
                f"DFES mid pathway, {n(D30_LO)} to {n(D30_HI)} across pathways",
            )
            + '<div class="cell note"><p>EV stock x annual distance x energy per km x the share charged in public, which depends on off-street parking. 500 Monte Carlo draws per scenario.</p></div>'
            + "</div>",
            layout="split",
        )
    )

    # 7 calibration
    out.append(
        slide(
            "London publishes no charger usage, so the model is checked against what is observed",
            '<div class="pair">'
            + metric(
                "Energy the network could deliver",
                f"{n(SUPPLY_SLOW + SUPPLY_RAPID)} GWh",
                f"{n(N_SLOW)} slow and {n(N_RAPID)} rapid chargers x occupancy observed by TfL x time spent charging. The rapid side is {n(SUPPLY_RAPID)} GWh.",
            )
            + metric(
                "Modelled public demand",
                f"{n(D26['total_p50'])} GWh",
                f"P10 to P90: {n(D26['total_p10'])} to {n(D26['total_p90'])}. Rapid-type demand is {n(D26['dest_p50'] + D26['phv_p50'])} GWh, the same order as the rapid side of supply.",
            )
            + "</div>"
            + '<div class="cell band"><p>Sessions per rapid charger per day</p></div>'
            + '<div class="strip three">'
            + metric("Implied by the model", n(K["rapid_sessions_per_charger_day"], 1))
            + metric("Implied by TfL occupancy", "13", "34% occupancy with 38-minute sessions")
            + metric("Observed in Dundee", "3", "open session log of a small city")
            + "</div>"
            + '<div class="cell note"><p>The interval is the honest statement. The two levers are the public share of drivers without a driveway and the size of the electric private-hire fleet.</p></div>',
            layout="stack",
        )
    )

    # 8 queues
    out.append(
        slide(
            "Where demand lands today, and where queues form at the peak hour",
            map_cell(
                "rapid_network_load_2026",
                "Live map. Click a site for load and waiting.",
                "Map of rapid charging sites with modelled load",
            )
            + '<div class="side">'
            + metric(
                "Rapid sites that queue",
                f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
                "P(wait) above 0.5 in the peak hour",
            )
            + metric(
                "Median utilisation", pct(K["util24_median"]), "over 24 hours. The average hides the peak."
            )
            + f'<div class="cell note"><p>Logit station choice on drive times over the OpenStreetMap network. Erlang C queues with 38-minute sessions. Ports are scaled per borough to DfT totals, median factor {n(K["port_scale_median"], 1)}.</p></div>'
            + "</div>",
            layout="split",
        )
    )

    # 9 cannibalisation
    cr = CAN["rows"]
    mx = max(r["captured"] for r in cr)
    body = [
        [
            f"{r['power_kw']} kW x {r['ports']}",
            f'<span class="bars">{bar(r["new"] / mx, "accent")}{bar(r["cannibalised"] / mx)}</span>',
            n(r["new"]),
            n(r["cannibalised"]),
            pct(r["cannibalisation_share"]),
        ]
        for r in cr
    ]
    lo, hi = min(r["cannibalisation_share"] for r in cr), max(r["cannibalisation_share"] for r in cr)
    out.append(
        slide(
            "A new hub mostly takes customers from its neighbours",
            '<div class="cell flush keyed">'
            + table(
                ["Hub", "Sessions per day", "New", "Captured", "Share captured"],
                body,
                num=(2, 3, 4),
                cls="barcol",
            )
            + '<p class="key"><i class="bar accent"></i>new demand<i class="bar"></i>captured from existing sites</p>'
            + "</div>"
            + '<div class="side">'
            + metric(
                "Share taken from existing sites",
                f"{round(100 * lo)} to {pct(hi)}",
                "of the sessions of a new hub",
            )
            + '<div class="cell note"><p>Larger and faster hubs capture more sessions and take a larger share from their neighbours. An investor needs this number next to expected sessions. A gap map cannot show it.</p></div>'
            + "</div>",
            lead=f"A hub placed in the hex with the largest unmet demand, in {CAN['candidate']['borough']}. The logit has an outside option, so new demand means sessions that would otherwise not use a rapid charger.",
            layout="split wide-left",
        )
    )

    # 10 siting map
    out.append(
        slide(
            "Where the next hubs go",
            map_cell(
                "siting_hubs",
                "Live map. Switch budgets and plans, click a hub.",
                "Map of recommended charging hubs",
            )
            + '<div class="side">'
            + metric(
                "Recommended plan at £20M",
                f"{R20['rec_n_hubs']} hubs",
                f"serve {pct(R20['rec_share_p50'])} of unmet rapid demand, {n(R20['rec_share_p50'] * R20['total_unmet_p50'])} of {n(R20['total_unmet_p50'])} sessions per day",
            )
            + metric(
                "Capacity of one hub",
                f"{n(CAP)} per day",
                "sessions, with P(wait) of 15% or less in the peak hour",
            )
            + metric(
                "Robust core",
                f"{R20['rec_core']} of {R20['rec_n_hubs']}",
                "hubs that every demand scenario puts in the same or an adjacent hex",
            )
            + "</div>",
            lead="4 x 150 kW hubs under a budget, with capacity from the queue model and a filter on substation headroom.",
            layout="split",
        )
    )

    # 11 budgets and uncertainty
    body = []
    for b in sorted(SIT):
        r = SIT[b]
        body.append(
            [
                f"£{b}M",
                r["rec_plan"].upper(),
                n(r["rec_n_hubs"]),
                pct(r["rec_share_p10"]),
                pct(r["rec_share_p50"]),
                pct(r["rec_share_p90"]),
                n(r["rec_max_regret"]),
                f"{r['rec_core']} of {r['rec_n_hubs']}",
            ]
        )
    low = [b for b in sorted(SIT) if SIT[b]["rec_plan"] == "p10"]
    out.append(
        slide(
            "Plan for pessimistic demand while capacity binds",
            '<div class="left">'
            + '<div class="cell flush">'
            + table(
                [
                    "Budget",
                    "Best plan",
                    "Hubs",
                    "Served at P10",
                    "at P50",
                    "at P90",
                    "Worst regret",
                    "Robust core",
                ],
                body,
                num=(2, 3, 4, 5, 6, 7),
                cls="grid",
            )
            + "</div>"
            + '<div class="pair">'
            + metric(
                f"£{low[0]}M to £{low[-1]}M",
                "Plan for P10",
                f"Capacity binds. Hubs placed where even low demand is dense fill up in every scenario. Worst regret: {n(max(SIT[b]['rec_max_regret'] for b in low))} sessions per day.",
            )
            + metric(
                "£40M",
                f"Plan for {R40['rec_plan'].upper()}",
                f"Capacity no longer binds everywhere. {R40['rec_n_hubs']} hubs serve {pct(R40['rec_share_p50'])} and lose at most {n(max(R40['rec_max_regret'], 1))} session per day.",
            )
            + "</div></div>"
            + f'<figure class="cell chartcell"><figcaption>Unmet sessions per day served, by budget</figcaption>{budget_chart()}<p class="d">The exact model with capacity against a greedy estimate that ignores it. The gap is demand a hub cannot absorb at an acceptable wait.</p></figure>',
            lead="One plan is solved for each of P10, P50 and P90 demand, then evaluated exactly under the other two. Regret is what a plan loses against the one that knew the scenario in advance.",
            layout="split wide-left",
        )
    )

    # 12 sensitivity
    names = {
        "base": "Base case",
        "travel-time coefficient": "Travel time weight",
        "power coefficient": "Charger power weight",
        "choice set": "Choice set",
        "service level": "Service level",
        "coverage radius": "Coverage radius",
    }
    detail = [
        "",
        "0.15 per min",
        "0.40 per min",
        "0.3",
        "1.0",
        "15 min",
        "30 min",
        "P(wait) up to 30%",
        "6 min",
        "10 min",
    ]
    body = []
    for i, r in enumerate(SENS["rows"]):
        head = next((v for k, v in names.items() if r["variant"].startswith(k)), r["variant"])
        label = head if i == 0 else f'{head} <span class="dim">{detail[i] if i < len(detail) else ""}</span>'
        body.append(
            [
                label,
                n(r["unmet_sessions_day"]),
                pct(r["coverage_share"]),
                pct(r["same_hex_as_base"]),
                f'<span class="bars">{bar(r["same_or_adjacent_hex"])}</span>',
                pct(r["same_or_adjacent_hex"]),
            ]
        )
    service = next(r for r in SENS["rows"] if r["variant"].startswith("service level"))
    out.append(
        slide(
            "What moves when the assumptions change",
            '<div class="cell flush">'
            + table(
                ["Assumption", "Unmet per day", "Served", "Same hex", "Same or adjacent", ""],
                body,
                num=(1, 2, 3, 5),
                cls="barcol dense",
            )
            + "</div>"
            + '<div class="side">'
            + metric(
                "Hubs that stay in place",
                pct(SENS["same_or_adjacent_median"]),
                f"median across {SENS['variants']} changes, same or adjacent hex",
            )
            + metric(
                "Effect of the service level",
                f"{pct(SENS['rows'][0]['coverage_share'])} to {pct(service['coverage_share'])}",
                "served when a P(wait) of 30% is accepted instead of 15%",
            )
            + '<div class="cell note"><p>The corridors are stable. The exact hex is a decision for a site survey. The service standard is a business choice with a larger effect than any behavioural coefficient.</p></div>'
            + "</div>",
            lead="The £20M plan solved again under nine changed assumptions, on the same 500 candidate hexes. Base case: travel time weight 0.25 per minute, charger power weight 0.6, choice set 20 minutes, P(wait) up to 15%, coverage radius 8 minutes.",
            layout="split wide-left",
        )
    )

    # 13 transfer
    imp = TR["importance"][:6]
    top_share = imp[0]["gain_share"]
    out.append(
        slide(
            "Do context features explain observed usage? A negative result, on purpose",
            '<div class="left top">'
            + '<div class="pair">'
            + metric("Random 5-fold cross-validation", f"R² {n(TR['r2_random'], 2)}", "looks respectable")
            + metric("One city held out", f"R² {n(TR['r2_leave_city_out'], 2)}", "the number that matters")
            + "</div>"
            + '<div class="cell flush">'
            + table(
                ["City held out", "Chargers", "Median sessions per day", "R²", "Rank correlation"],
                [
                    [c["city"], n(c["n"]), n(c["median_sessions_day"], 2), n(c["r2"], 2), n(c["spearman"], 2)]
                    for c in TR["by_city"]
                ],
                num=(1, 2, 3, 4),
                cls="grid",
            )
            + "</div></div>"
            + '<div class="side">'
            + '<div class="cell flush">'
            + table(
                ["Feature", "Share of model gain", ""],
                [
                    [
                        f["label"],
                        f'<span class="bars">{bar(f["gain_share"] / top_share)}</span>',
                        pct(f["gain_share"]),
                    ]
                    for f in imp
                ],
                num=(2,),
                cls="barcol dense",
            )
            + "</div>"
            + '<div class="cell note"><p>Charger power and the level of each city dominate. Rankings do not transfer either. A site-selection model has to be validated in a city it has not seen, against observed usage.</p></div>'
            + "</div>",
            lead=f"{n(TR['n_stations'])} chargers with open session logs in four cities. LightGBM on OpenStreetMap context, population and charger power.",
            layout="split even",
        )
    )

    # 14 engineering
    out.append(
        slide(
            "Reproducible from a clean clone",
            '<div class="cell flush">'
            + table(
                ["Layer", "Tools", "Why"],
                [
                    [
                        "Spatial",
                        "H3, GeoPandas, Shapely",
                        "Equal-area hex grid and areal interpolation from census units",
                    ],
                    [
                        "Network",
                        "OSMnx, igraph",
                        "Drive times on a graph of 131,000 nodes in seconds, no routing server",
                    ],
                    [
                        "Statistics and ML",
                        "esda, LightGBM, scikit-learn",
                        "Moran's I, Gi*, spatial cross-validation by default",
                    ],
                    [
                        "Optimisation",
                        "SciPy milp and linprog (HiGHS)",
                        "Sparse MILP, exact evaluation of plans, every MIP gap recorded",
                    ],
                    ["Choice and queues", "NumPy", "Erlang C and logit, tested against closed forms"],
                    [
                        "Delivery",
                        "MapLibre GL JS, GitHub Pages",
                        "Maps that also work offline, and this deck",
                    ],
                ],
                cls="kit",
            )
            + "</div>"
            + '<div class="strip">'
            + metric("Unit tests", n(K["n_tests"]), "queues, choice, MILP, grid, caches")
            + metric("Python versions in CI", "3.11, 3.12", "lint, tests and a model smoke run")
            + metric("Data cards with licences", n(K["n_sources"]), "one per dataset")
            + metric("Raw data needed to rerun models", "0 GB", "compact tables are committed")
            + "</div>",
            layout="stack",
        )
    )

    # 15 limitations
    out.append(
        slide(
            "Limitations, and how this could be proven wrong",
            '<div class="cell flush headed"><h3 class="colhead">Known limitations</h3>'
            + rows(
                [
                    (
                        "Usage",
                        "London publishes no charger-level usage. Behaviour comes from other UK cities and fleet trials.",
                    ),
                    (
                        "Supply",
                        "Open Charge Map covers most sites but not every port. The rest is closed per borough against DfT totals.",
                    ),
                    (
                        "Choice",
                        "Coefficients come from the literature, not from estimation. The sensitivity table shows what they move.",
                    ),
                    ("Grid", "Constraints stop at the headroom of primary substations."),
                    (
                        "Interpolation",
                        "Area-weighted from census units. About 1.4% of residents fall in dropped edge hexes.",
                    ),
                ],
                cls="narrow lg",
            )
            + "</div>"
            + '<div class="cell flush headed"><h3 class="colhead">The test</h3>'
            + rows(
                [
                    (
                        "Data",
                        "DfT and Zapmap publish device counts by borough every quarter. TfL publishes utilisation by charger type.",
                    ),
                    (
                        "Claim",
                        "Hubs opened after July 2026 in hexes flagged here should reach above-median utilisation within a year.",
                    ),
                    (
                        "If not",
                        "The model card names the priors to revisit first: private-hire fleet size, public share without home charging, choice radius.",
                    ),
                    (
                        "Loop",
                        "Predict, deploy, measure, retrain. That loop is the product. The maps are its interface.",
                    ),
                ],
                cls="narrow lg",
            )
            + "</div>",
            layout="pair",
        )
    )

    # 16 value
    out.append(
        slide(
            "What an operator or investor gets, and what comes next",
            '<div class="cell flush headed"><h3 class="colhead">Today, from open data</h3>'
            + rows(
                [
                    (
                        "Ranked candidates",
                        "Expected sessions per day with P10 to P90, the share taken from neighbours, substation headroom and drive-time catchment for every hex.",
                    ),
                    (
                        "Capacity",
                        "Ports and power sized from the queue model against a service level, not from a template.",
                    ),
                    (
                        "A robust plan",
                        "The hubs every demand scenario agrees on are built first. The rest are phased as utilisation data arrive.",
                    ),
                ],
                cls="narrow lg",
            )
            + "</div>"
            + '<div class="cell flush headed"><h3 class="colhead">Next, with operator data</h3>'
            + rows(
                [
                    ("Choice", "Parameters estimated from real routes and the station each driver chose."),
                    ("Time", "Hour-of-day profiles for arrivals and queues."),
                    ("Uncertainty", "Intervals per hex learned from sessions, not from global priors."),
                    ("Effect", "Staggered difference-in-differences on hub openings."),
                ],
                cls="narrow lg",
            )
            + "</div>",
            layout="pair",
        )
    )

    # 17 explore
    maps = " ".join(
        f'<a href="../maps/{f}.html">{t}</a>'
        for f, t in [
            ("supply_2026", "Supply"),
            ("demand_2026", "Demand"),
            ("rapid_network_load_2026", "Network load"),
            ("siting_hubs", "Hub siting"),
        ]
    )
    out.append(
        slide(
            "Explore it",
            '<div class="cell flush">'
            + rows(
                [
                    (
                        "Repository",
                        f'<a href="{REPO}">{REPO_TEXT}</a><br>Code, {K["n_tests"]} tests, data catalog, methodology, model card',
                    ),
                    ("Live maps", f'<span class="linklist">{maps}</span>'),
                    (
                        "Notebooks",
                        f'<a href="{NBVIEWER}">Notebooks 01 to 05 on nbviewer</a><br>Supply audit, demand, choice and queues, siting, transfer test',
                    ),
                    (
                        "Reproduce",
                        '<code>pip install -e ".[all]"</code><br><code>make models maps slides</code>',
                    ),
                    ("Author", 'Marija Ercegovac, <a href="https://github.com/m-erts">github.com/m-erts</a>'),
                ],
                cls="wide lg",
            )
            + "</div>",
            layout="stack",
        )
    )
    return out


# ----------------------------------------------------------------------------- page
CSS = """
:root{--u:min(1vw,1.7778vh)}
@supports (height:1dvh){:root{--u:min(1dvw,1.7778dvh)}}
html,body{height:100%}
body{overflow:hidden}
h1,h2,h3,p,dl,dd,ol,ul,figure{margin:0}
ol,ul{padding:0;list-style:none}
.deck{position:fixed;inset:0;display:grid;place-items:center;background:var(--bg)}
.stage{width:calc(var(--u)*100);height:calc(var(--u)*56.25);display:grid;grid-template-rows:calc(var(--u)*3.4) minmax(0,1fr);background:var(--bg);border:1px solid var(--border);font-size:calc(var(--u)*1.12);line-height:1.5}

.topbar{display:flex;justify-content:space-between;border-bottom:1px solid var(--border);font-size:calc(var(--u)*0.9)}
.brand{display:flex;align-items:center;padding:0 calc(var(--u)*3);font-weight:600;letter-spacing:-0.01em;text-decoration:none}
.tools{display:flex}
.tools > *{border-left:1px solid var(--border);display:flex;align-items:center;justify-content:center}
.counter{padding:0 calc(var(--u)*1.4);color:var(--muted)}
.tools button{appearance:none;border-top:0;border-right:0;border-bottom:0;background:var(--bg);color:var(--fg);font-size:inherit;line-height:1;min-width:calc(var(--u)*3.4);padding:0 calc(var(--u)*1.2);cursor:pointer;transition:background-color 150ms ease,color 150ms ease}
.tools button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.tools button:disabled{color:var(--border);cursor:default}
.tools button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.tools button:active:not(:disabled){background:var(--surface)}
@media (hover:hover) and (pointer:fine){.tools button:hover:not(:disabled):not([aria-pressed="true"]){background:var(--surface)}}

main{display:grid;grid-template-rows:minmax(0,1fr);min-height:0;min-width:0}
.slide{display:grid;grid-template-rows:auto minmax(0,1fr);min-height:0}
.slide[hidden]{display:none}
.head{padding:calc(var(--u)*2.4) calc(var(--u)*3) calc(var(--u)*2);border-bottom:1px solid var(--border)}
h2{font-size:calc(var(--u)*2.6);line-height:1.1;letter-spacing:-0.035em;font-weight:600;max-width:36ch;text-wrap:balance}
.lead{margin-top:calc(var(--u)*0.9);color:var(--muted);font-size:calc(var(--u)*1.15);max-width:88ch;text-wrap:pretty}
h3{font-size:calc(var(--u)*1.15);font-weight:600;letter-spacing:-0.01em}

.body,.side,.left,.strip,.pair,.pipe{display:grid;gap:1px;background:var(--border);min-height:0;min-width:0}
.cell{background:var(--bg);padding:calc(var(--u)*1.8) calc(var(--u)*3);min-width:0;min-height:0}
.cell.flush{padding:0;display:grid;grid-template-rows:minmax(0,1fr)}
.cell.flush.headed{grid-template-rows:auto minmax(0,1fr)}
.cell.flush.keyed{grid-template-rows:minmax(0,1fr) auto}
.body.stack{grid-auto-rows:auto;grid-template-rows:minmax(0,1fr)}
.body.stack > :first-child{align-self:stretch}
.body.split{grid-template-columns:62fr 38fr}
.body.split.wide-left{grid-template-columns:60fr 40fr}
.body.split.even{grid-template-columns:54fr 46fr}
.body.pair{grid-template-columns:1fr 1fr}
.side,.left{grid-auto-rows:auto;align-content:stretch;background:var(--border)}
.side > .cell:not(.flush){padding-left:calc(var(--u)*2.2);padding-right:calc(var(--u)*2.2)}
.left{grid-template-rows:minmax(0,1fr) auto}
.left.top{grid-template-rows:auto minmax(0,1fr)}
.body.halves{grid-template-rows:minmax(0,1fr) minmax(0,1fr)}
.side > :last-child,.left > :last-child{align-self:stretch}
.side{grid-template-rows:repeat(auto-fit,minmax(0,auto))}
.strip,.pair{grid-template-rows:minmax(0,1fr) auto auto}
.strip > .cell,.pair > .cell{grid-row:span 3}
@supports (grid-template-rows:subgrid){.strip > .metric,.pair > .metric{display:grid;grid-template-rows:subgrid;row-gap:0}}
.strip{grid-template-columns:repeat(4,1fr)}
.strip.three{grid-template-columns:repeat(3,1fr)}
.pair{grid-template-columns:1fr 1fr}

.metric,.prose{display:flex;flex-direction:column}
.metric .k{color:var(--muted);font-size:calc(var(--u)*0.95);margin-bottom:auto;padding-bottom:calc(var(--u)*0.2)}
.metric .v{font-size:calc(var(--u)*2.7);line-height:1.05;letter-spacing:-0.04em;font-weight:500;margin:calc(var(--u)*0.5) 0 calc(var(--u)*0.55);white-space:nowrap}
.metric .d{color:var(--muted);font-size:calc(var(--u)*0.95);max-width:46ch;text-wrap:pretty}
.prose h3{margin-bottom:auto;padding-bottom:calc(var(--u)*0.6);color:var(--muted);font-weight:400;font-size:calc(var(--u)*0.95);letter-spacing:0}
.prose p{max-width:58ch;text-wrap:pretty}
.big .v{font-size:calc(var(--u)*4.2)}
.big .d{font-size:calc(var(--u)*1.1)}
.prose.big p{font-size:calc(var(--u)*1.45);line-height:1.4;letter-spacing:-0.015em}
.note{background:var(--surface)}
.note p{color:var(--muted);font-size:calc(var(--u)*1);max-width:60ch;text-wrap:pretty}
.band{background:var(--surface);padding-top:calc(var(--u)*0.8);padding-bottom:calc(var(--u)*0.8);color:var(--muted);font-size:calc(var(--u)*0.95)}

.rows{display:grid;grid-auto-rows:minmax(min-content,1fr);background:var(--bg);min-height:0}
.rows > div{display:grid;align-content:center;grid-template-columns:calc(var(--u)*22) minmax(0,1fr);gap:calc(var(--u)*2);padding:calc(var(--u)*1.35) calc(var(--u)*3);border-bottom:1px solid var(--border)}
.rows > div:last-child{border-bottom:0}
.rows dt{font-weight:600;letter-spacing:-0.01em}
.rows dd{color:var(--muted);max-width:74ch;text-wrap:pretty}
.rows.narrow > div{grid-template-columns:calc(var(--u)*10.5) minmax(0,1fr);padding:calc(var(--u)*1.2) calc(var(--u)*2.2)}
.rows.stacked > div{grid-template-columns:1fr;gap:calc(var(--u)*0.3);padding:calc(var(--u)*1.5) calc(var(--u)*2.2)}
.rows.wide > div{grid-template-columns:calc(var(--u)*14) minmax(0,1fr)}
.rows.wide dd{color:var(--fg)}
.rows.lg{font-size:calc(var(--u)*1.25)}
.colhead{padding:calc(var(--u)*1.1) calc(var(--u)*2.2);border-bottom:1px solid var(--border);background:var(--surface);font-weight:500;color:var(--muted);font-size:calc(var(--u)*0.95)}
.body.pair > .cell:first-child .rows > div,.body.pair > .cell:first-child .colhead{padding-left:calc(var(--u)*3)}
.linklist{display:flex;flex-wrap:wrap;gap:calc(var(--u)*0.4) calc(var(--u)*1.6)}
code{font-size:0.92em}

.pipe{grid-template-columns:repeat(6,1fr)}
.pipe li{display:grid;gap:calc(var(--u)*0.25);padding:calc(var(--u)*1.4) calc(var(--u)*1.6)}
.pipe b{font-weight:600;letter-spacing:-0.01em}
.pipe .idx,.pipe .sub{color:var(--muted);font-size:calc(var(--u)*0.9)}

.t{width:100%;border-collapse:collapse;font-size:calc(var(--u)*1.05)}
.cell.flush > .t{height:100%}
.t th,.t th.num{font-family:"Geist","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-weight:500;color:var(--muted);font-size:calc(var(--u)*0.9);text-align:left;background:var(--surface)}
.t th,.t td{padding:calc(var(--u)*0.95) calc(var(--u)*1.4);border-bottom:1px solid var(--border);vertical-align:middle}
.t tbody tr:last-child td{border-bottom:0}
.t th:first-child,.t td:first-child{padding-left:calc(var(--u)*3)}
.t th:last-child,.t td:last-child{padding-right:calc(var(--u)*3)}
.side .t th:first-child,.side .t td:first-child{padding-left:calc(var(--u)*2.2)}
.side .t th:last-child,.side .t td:last-child,.left .t th:last-child,.left .t td:last-child{padding-right:calc(var(--u)*2.2)}
.body.split > .cell.flush .t th:last-child,.body.split > .cell.flush .t td:last-child{padding-right:calc(var(--u)*2.2)}
.t .num{text-align:right;white-space:nowrap}
.t td:first-child{font-weight:500}
.t.grid th + th,.t.grid td + td{border-left:1px solid var(--border)}
.t.dense th,.t.dense td{padding-top:calc(var(--u)*0.5);padding-bottom:calc(var(--u)*0.5)}
.t.dense td:first-child{white-space:nowrap}
.t.status td:nth-child(2),.t.kit td:nth-child(3){color:var(--muted)}
.t.status td:nth-child(3){font-family:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:0.9em;color:var(--muted);white-space:nowrap}
.t.kit td:nth-child(2){font-family:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:0.9em;white-space:nowrap}
.t .dim{color:var(--muted);font-weight:400}
.bars{display:flex;align-items:center;gap:1px;height:calc(var(--u)*1.55);min-width:calc(var(--u)*9)}
.bar{display:block;height:calc(var(--u)*0.8);background:var(--fg);flex:none}
.bar.accent{background:var(--accent)}
.key{display:flex;align-items:center;gap:calc(var(--u)*0.6);padding:calc(var(--u)*1) calc(var(--u)*3);border-top:1px solid var(--border);color:var(--muted);font-size:calc(var(--u)*0.9)}
.key .bar{width:calc(var(--u)*1.6)}
.key .bar + .bar,.key .bar:nth-of-type(2){margin-left:calc(var(--u)*1.2)}

.map{padding:0;display:grid;grid-template-rows:minmax(0,1fr) auto;background:var(--surface)}
.map iframe{width:100%;height:100%;border:0;display:block;background:var(--surface)}
.map figcaption,.fig figcaption{display:flex;justify-content:space-between;gap:calc(var(--u)*2);padding:calc(var(--u)*0.75) calc(var(--u)*1.4);border-top:1px solid var(--border);background:var(--bg);color:var(--muted);font-size:calc(var(--u)*0.9)}
.chartcell{display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:calc(var(--u)*0.8);padding:calc(var(--u)*1.6) calc(var(--u)*2.2)}
.chartcell figcaption{font-weight:500;font-size:calc(var(--u)*0.95);color:var(--muted)}
.chartcell .d{color:var(--muted);font-size:calc(var(--u)*0.95);text-wrap:pretty}
.chart{width:100%;height:100%;min-height:0}
.chart .g{stroke:var(--border);stroke-width:1;vector-effect:non-scaling-stroke}
.chart .cap{stroke:var(--neutral);stroke-width:1;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.chart .exact{fill:none;stroke:var(--fg);stroke-width:2;vector-effect:non-scaling-stroke}
.chart .greedy{fill:none;stroke:var(--neutral);stroke-width:1.5;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}
.chart .pt{fill:var(--fg)}
.chart text{font-family:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;fill:var(--muted)}
.chart .val{fill:var(--fg)}

.title .body{grid-template-columns:56fr 44fr;grid-template-rows:minmax(0,1fr) auto}
.title{grid-template-rows:minmax(0,1fr)}
.intro{display:flex;flex-direction:column;padding:calc(var(--u)*4) calc(var(--u)*3) calc(var(--u)*2.4)}
h1{font-size:calc(var(--u)*5.4);line-height:1;letter-spacing:-0.045em;font-weight:600}
.sub{font-size:calc(var(--u)*1.9);line-height:1.2;letter-spacing:-0.02em;margin-top:calc(var(--u)*1.4);max-width:26ch;text-wrap:balance}
.q{color:var(--muted);margin-top:calc(var(--u)*1.6);max-width:54ch;font-size:calc(var(--u)*1.15);text-wrap:pretty}
.by{margin-top:auto;color:var(--muted);font-size:calc(var(--u)*1)}
.fig{padding:0;display:grid;grid-template-rows:minmax(0,1fr) auto;background:var(--bg)}
.london{width:100%;height:100%;min-height:0;padding:calc(var(--u)*1.2)}
.london .hx{stroke:var(--bg);stroke-width:0.6;vector-effect:non-scaling-stroke}
.london .r1{fill:var(--r1)}.london .r2{fill:var(--r2)}.london .r3{fill:var(--r3)}.london .r4{fill:var(--r4)}.london .r5{fill:var(--r5)}.london .r6{fill:var(--r6)}
.london .core{fill:var(--accent);stroke:var(--bg);stroke-width:2.5}
.london .rest{fill:var(--bg);stroke:var(--fg);stroke-width:2.5}
.title .strip{grid-column:1 / -1}

@media (max-width:767px){
  html,body{height:auto}
  body{overflow:auto}
  :root{--u:13.5px}
  .deck{position:static;display:block}
  .stage{width:100%;height:auto;display:block;border:0}
  .topbar{position:sticky;top:0;z-index:var(--z-bar);background:var(--bg);height:48px}
  .tools .nav,.counter,.tools .fs{display:none}
  .tools button{min-width:64px}
  .brand{padding:0 16px}
  main{display:block}
  .slide,.slide[hidden]{display:block;border-bottom:1px solid var(--border)}
  .head,.cell,.rows > div,.key{padding-left:16px;padding-right:16px}
  .t th:first-child,.t td:first-child{padding-left:16px}
  .t th:last-child,.t td:last-child{padding-right:16px}
  .body,.body.split,.body.split.wide-left,.body.split.even,.body.pair,.title .body,.strip,.strip.three,.pair,.pipe{grid-template-columns:1fr}
  .rows > div,.rows.narrow > div,.rows.wide > div,.rows.stacked > div{grid-template-columns:1fr;gap:4px;padding-left:16px;padding-right:16px}
  .body.pair > .cell:first-child .rows > div,.body.pair > .cell:first-child .colhead,.colhead{padding-left:16px}
  .cell.map,.cell.fig,.cell.flush{padding-left:0;padding-right:0}
  .by{margin-top:24px}
  .side > .cell:not(.flush){padding-left:16px;padding-right:16px}
  h1{font-size:40px}
  h2{font-size:26px}
  .cell.flush{overflow-x:auto}
  .map{height:70vh}
  .london{height:auto}
  .metric .v{white-space:normal}
}
@media print{
  @page{size:1600px 900px;margin:0}
  :root{--u:16px}
  html,body{height:auto}
  body{overflow:visible}
  .deck{position:static;display:block}
  .stage{display:block;width:1600px;height:auto;border:0}
  .topbar{display:none}
  main{display:block}
  .slide,.slide[hidden]{display:grid;width:1600px;height:900px;break-after:page;border-bottom:1px solid var(--border)}
}
"""

JS = """
const slides = [...document.querySelectorAll('.slide')];
const counter = document.getElementById('counter');
const prev = document.getElementById('prev'), next = document.getElementById('next');
const themeBtn = document.getElementById('theme'), fsBtn = document.getElementById('fs');
const isDoc = () => matchMedia('(max-width: 767px)').matches;
const pad = v => String(v).padStart(2, '0');
let i = 0;
function loadMaps(scope) {
  const theme = csIsDark() ? 'dark' : 'light';
  scope.querySelectorAll('iframe[data-src]').forEach(f => { const u = f.dataset.src + '&theme=' + theme; if (f.dataset.loaded !== u) { f.src = u; f.dataset.loaded = u; } });
}
function go(k) {
  i = Math.max(0, Math.min(slides.length - 1, k));
  if (!isDoc()) slides.forEach((s, j) => { s.hidden = j !== i; });
  loadMaps(slides[i]);
  counter.textContent = pad(i + 1) + ' / ' + pad(slides.length);
  prev.disabled = i === 0; next.disabled = i === slides.length - 1;
  history.replaceState(null, '', '#' + (i + 1));
}
function setTheme(dark) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  try { localStorage.setItem('cs-theme', dark ? 'dark' : 'light'); } catch (e) {}
  themeBtn.setAttribute('aria-pressed', String(dark));
  document.querySelectorAll('iframe[data-loaded]').forEach(f => loadMaps(f.parentElement));
}
function fullscreen() { if (document.fullscreenElement) document.exitFullscreen(); else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen(); }
function key(k) {
  if (k === 'ArrowRight' || k === 'PageDown' || k === ' ') go(i + 1);
  else if (k === 'ArrowLeft' || k === 'PageUp') go(i - 1);
  else if (k === 'Home') go(0);
  else if (k === 'End') go(slides.length - 1);
  else if (k === 'f' || k === 'F') fullscreen();
  else if (k === 't' || k === 'T') setTheme(!csIsDark());
  else return false;
  return true;
}
prev.addEventListener('click', () => go(i - 1));
next.addEventListener('click', () => go(i + 1));
themeBtn.addEventListener('click', () => setTheme(!csIsDark()));
fsBtn.addEventListener('click', fullscreen);
document.addEventListener('fullscreenchange', () => fsBtn.setAttribute('aria-pressed', String(!!document.fullscreenElement)));
addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey || isDoc()) return;
  if ((e.key === ' ' || e.key === 'Enter') && e.target.closest && e.target.closest('a,button')) return;
  if (key(e.key)) e.preventDefault();
});
addEventListener('message', e => { if (e.data && e.data.cs_key && !isDoc()) key(e.data.cs_key); });
addEventListener('hashchange', () => { const k = parseInt(location.hash.slice(1), 10); if (!isNaN(k) && k - 1 !== i) go(k - 1); });
let x0 = null;
addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, {passive: true});
addEventListener('touchend', e => { if (x0 === null || isDoc()) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 60) go(i + (dx < 0 ? 1 : -1)); x0 = null; }, {passive: true});
addEventListener('beforeprint', () => slides.forEach(loadMaps));
matchMedia('(max-width: 767px)').addEventListener('change', () => { if (isDoc()) slides.forEach(s => { s.hidden = false; }); go(i); });
if (isDoc() && 'IntersectionObserver' in window) {
  slides.forEach(s => { s.hidden = false; });
  const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { loadMaps(en.target); io.unobserve(en.target); } }), {rootMargin: '400px'});
  document.querySelectorAll('.map').forEach(m => io.observe(m));
}
themeBtn.setAttribute('aria-pressed', String(csIsDark()));
go((parseInt(location.hash.slice(1), 10) || 1) - 1);
"""


def page() -> str:
    desc = "A spatial decision system for London's EV charging network: demand with uncertainty, station choice and queues, hub siting under budget and grid constraints."
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slides | ChargeScape London</title><meta name="description" content="{desc}">
<meta property="og:title" content="ChargeScape London"><meta property="og:description" content="{desc}">
<script>{THEME_BOOT_JS}</script>
<style>{tokens_css("../vendor")}{CSS}</style></head><body>
<div class="deck"><div class="stage">
<header class="topbar"><a class="brand" href="../index.html">ChargeScape London</a>
<div class="tools"><span class="counter mono" id="counter" aria-live="polite"></span>
<button type="button" class="nav" id="prev" aria-label="Previous slide">←</button><button type="button" class="nav" id="next" aria-label="Next slide">→</button>
<button type="button" id="theme" aria-pressed="false">Dark</button><button type="button" class="fs" id="fs" aria-pressed="false">Full screen</button></div></header>
<main>{"".join(build())}</main>
</div></div>
<script>{JS}</script></body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("*.html")):
        old.unlink()
    img = OUT / "img"
    if img.exists():
        for f in img.iterdir():
            f.unlink()
        img.rmdir()
    html = page()
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"slides: {html.count('<section class=')} | {len(html) / 1024:.0f} KB | wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
