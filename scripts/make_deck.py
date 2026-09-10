"""Build the project slide deck (reports/ChargeScape_London.pptx) with python-pptx from
reports/tables/key_numbers.json and reports/figures/*.png."""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "reports" / "figures"
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())

NAVY = RGBColor(0x14, 0x21, 0x3D)
ORANGE = RGBColor(0xE4, 0x57, 0x2E)
TEAL = RGBColor(0x0C, 0x7C, 0x70)
INK = RGBColor(0x1A, 0x20, 0x27)
MUTED = RGBColor(0x5B, 0x6B, 0x7A)
PALE = RGBColor(0xEE, 0xF2, 0xF4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD = "Cambria"
BODY = "Calibri"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = 13.333, 7.5


def bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def text(
    slide,
    x,
    y,
    w,
    h,
    s,
    size=16,
    bold=False,
    color=INK,
    font=BODY,
    align=PP_ALIGN.LEFT,
    italic=False,
    line=1.15,
):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = s if isinstance(s, list) else [s]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.name = font
        r.font.color.rgb = color
    return tb


def bullets(slide, x, y, w, h, items, size=15, color=INK, gap=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        r = p.add_run()
        r.text = "•  " + it
        r.font.size = Pt(size)
        r.font.name = BODY
        r.font.color.rgb = color
    return tb


def title(slide, s, sub=None, dark=False):
    text(slide, 0.6, 0.45, W - 1.2, 0.9, s, size=30, bold=True, color=WHITE if dark else NAVY, font=HEAD)
    if sub:
        text(
            slide,
            0.6,
            1.25,
            W - 1.2,
            0.5,
            sub,
            size=14,
            color=RGBColor(0xC8, 0xD3, 0xDC) if dark else MUTED,
            italic=True,
        )


def stat(slide, x, y, w, big, label, color=ORANGE):
    text(slide, x, y, w, 0.9, big, size=40, bold=True, color=color, font=HEAD)
    text(slide, x, y + 0.85, w, 0.7, label, size=12, color=MUTED)


def card(slide, x, y, w, h, head, body, fill=PALE):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.adjustments[0] = 0.06
    shp.shadow.inherit = False
    text(slide, x + 0.25, y + 0.2, w - 0.5, 0.5, head, size=15, bold=True, color=NAVY)
    text(slide, x + 0.25, y + 0.7, w - 0.5, h - 0.9, body, size=12, color=INK, line=1.2)


def picture(slide, name, x, y, w=None, h=None):
    p = FIG / name
    if not p.exists():
        text(slide, x, y, w or 6, 1, f"[figure {name} not generated yet]", size=12, color=MUTED, italic=True)
        return
    kw = {}
    if w:
        kw["width"] = Inches(w)
    if h:
        kw["height"] = Inches(h)
    slide.shapes.add_picture(str(p), Inches(x), Inches(y), **kw)


def footer(slide, n, dark=False):
    text(
        slide,
        0.6,
        H - 0.45,
        8,
        0.3,
        "ChargeScape London · github repository · September 2026",
        size=9,
        color=RGBColor(0xC8, 0xD3, 0xDC) if dark else MUTED,
    )
    text(
        slide,
        W - 1.2,
        H - 0.45,
        0.6,
        0.3,
        str(n),
        size=9,
        color=RGBColor(0xC8, 0xD3, 0xDC) if dark else MUTED,
        align=PP_ALIGN.RIGHT,
    )


d26 = K["demand_gwh"]["2026"]
d30 = K["demand_gwh"]["2030_mid"]
n = 0

# 1 title
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
n += 1
text(s, 0.8, 1.6, 11.5, 1.6, "ChargeScape London", size=52, bold=True, color=WHITE, font=HEAD)
text(
    s,
    0.8,
    3.0,
    11.0,
    1.2,
    "A spatial decision system for EV charging networks under uncertain demand",
    size=24,
    color=RGBColor(0xC8, 0xD3, 0xDC),
    font=HEAD,
)
text(
    s,
    0.8,
    4.4,
    11.0,
    1.4,
    [
        "Where should the next rapid-charging hubs in Greater London go, how many ports and what power —",
        "and how sure can we be? Built end-to-end from open data, with every assumption visible.",
    ],
    size=15,
    color=WHITE,
)
text(
    s,
    0.8,
    6.3,
    11.0,
    0.5,
    "Marija Ercegovac · urban planner turned geospatial data scientist · September 2026",
    size=13,
    color=RGBColor(0xC8, 0xD3, 0xDC),
)
box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.3), Inches(0.6), Inches(1.4), Inches(0.5))
box.fill.solid()
box.fill.fore_color.rgb = ORANGE
box.line.fill.background()
box.adjustments[0] = 0.3
text(s, 11.3, 0.7, 1.4, 0.4, "PORTFOLIO", size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# 2 the problem
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "Charging is an infrastructure business that lives or dies on utilisation",
    "London facts behind the question",
)
stat(s, 0.8, 1.9, 2.8, f"{K['chargers_total']:,}", f"public chargers in London\n(DfT, {K['dft_date']})")
stat(s, 3.9, 1.9, 2.8, f"{K['rapid_share']:.0%}", "of them are 50 kW+ —\nvs 24 % across the UK", color=TEAL)
stat(
    s,
    7.0,
    1.9,
    2.8,
    f"{(K['piv_private'] + K['piv_company']) / 1000:.0f}k",
    "plug-in cars kept in London\n(41 % company-kept)",
    color=NAVY,
)
stat(s, 10.1, 1.9, 2.8, "34 %", "occupancy of rapid units\n(TfL, observed 2025)", color=ORANGE)
card(
    s,
    0.8,
    4.0,
    5.9,
    2.7,
    "The economics",
    "A hub in the wrong hex idles at 5 % and never pays back; the right one runs above 20–30 % with queues. McKinsey and ICCT put the break-even between 15 % and 20 % utilisation — payback halves between 10 % and 20 %.",
)
card(
    s,
    7.0,
    4.0,
    5.9,
    2.7,
    "The analytics gap",
    "Operators describe site selection as a demand model on dozens to hundreds of factors. Public projects almost never predict usage (they predict where chargers already are), carry uncertainty into the decision, model queues and cannibalisation, or say how they would be proven wrong.",
)
footer(s, n)

# 3 what is different
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(s, "Four things this system does that gap maps do not")
items = [
    (
        "Labels on every dataset",
        "observed / proxy / synthetic — 23 sources in the catalog, and the label follows the number into every table.",
    ),
    (
        "Usage, checked against reality",
        "Demand is modelled bottom-up, then checked against DfT charger counts × TfL occupancy and open session logs.",
    ),
    (
        "Uncertainty reaches the decision",
        "P10/P50/P90 per hex; a robust MILP picks hubs that hold across scenarios; the overlap with the P50 answer says which sites are safe.",
    ),
    (
        "Queues, cannibalisation, grid",
        "Erlang-C capacity per hub, new vs stolen demand for any candidate, primary-substation headroom as a filter.",
    ),
]
for i, (h, b) in enumerate(items):
    x = 0.8 + (i % 2) * 6.2
    y = 1.9 + (i // 2) * 2.55
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(0.55), Inches(0.55))
    circ.fill.solid()
    circ.fill.fore_color.rgb = [ORANGE, TEAL, NAVY, ORANGE][i]
    circ.line.fill.background()
    text(s, x, y + 0.1, 0.55, 0.4, str(i + 1), size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    text(s, x + 0.75, y, 5.2, 0.5, h, size=18, bold=True, color=NAVY, font=HEAD)
    text(s, x + 0.75, y + 0.55, 5.2, 1.7, b, size=13, color=INK, line=1.25)
footer(s, n)

# 4 pipeline
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "Pipeline: open data → hex features → demand → choice & queues → siting",
    "Reproducible on a laptop: make data · make features · make models · make maps",
)
steps = [
    (
        "Open data",
        "DfT · ONS · OSM PBF · UKPN DFES & headroom · TfL · LAEI · Dundee/PKC/Palo Alto/Boulder sessions",
    ),
    (
        "H3 res-8 features",
        "areal interpolation of Census & EV licensing; POIs; vehicle-km; transit; substation headroom; igraph drive times",
    ),
    (
        "Structural demand",
        "EV stock × km × kWh/km × public share; 500 Monte Carlo draws; taxi/PHV layer; DFES 2030 pathways",
    ),
    (
        "Choice & queues",
        "MNL station choice on drive times; Erlang-C per site; incremental vs cannibalised demand",
    ),
    ("Siting", "capacitated MCLP + robust two-stage MILP (HiGHS); budget, capacity, grid filter"),
    ("Delivery", "deck.gl maps, notebooks, model card, post-hoc validation plan"),
]
for i, (h, b) in enumerate(steps):
    x = 0.6 + i * 2.05
    shp = s.shapes.add_shape(
        MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON, Inches(x), Inches(2.0), Inches(2.0), Inches(0.8)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = [NAVY, TEAL, ORANGE, TEAL, NAVY, MUTED][i]
    shp.line.fill.background()
    text(s, x + 0.35, 2.2, 1.5, 0.5, h, size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    text(s, x + 0.1, 3.0, 1.85, 2.6, b, size=11, color=INK, line=1.2)
card(
    s,
    0.8,
    5.6,
    11.7,
    1.3,
    "Validation stance",
    "Spatial cross-validation by default (random K-fold shown only to expose its optimism); consistency with observed aggregates; and a named observable — utilisation of hubs opened after July 2026 — that would confirm or refute each recommendation.",
)
footer(s, n)

# 5 supply audit
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(s, "Supply follows devices; need follows cars without driveways", "Notebook 01 — all observed data")
picture(s, "01_hex_supply_demand.png", 0.6, 1.8, h=5.2)
bullets(
    s,
    7.4,
    1.9,
    5.4,
    4.8,
    [
        "Inner boroughs have ~1,400 chargers per 100k residents, mostly 5–7 kW lamp-post units; rapid share is 40 % in Havering and Hillingdon, under 4 % in Westminster and Hackney.",
        "Private plug-in cars cluster in outer, house-rich boroughs (Barnet, Bromley, Croydon); Moran's I = 0.73 — strongly clustered.",
        "The group that depends on public charging — EV owners in flats — forms Gi* hot spots in inner-west and inner-south London.",
        f"On the road network, median drive time to a rapid site is {K['median_tt_nearest_rapid_min']} min: distance is rarely the binding constraint in London; capacity and queues are.",
    ],
    size=13,
)
footer(s, n)

# 6 demand
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "A demand surface with the uncertainty attached",
    "Notebook 02 — structural Monte Carlo model on observed inputs",
)
picture(s, "02_demand_p50_uncertainty.png", 0.6, 1.8, w=12.1)
stat(
    s,
    0.8,
    5.35,
    3.0,
    f"{d26['total_p50']:.0f} GWh",
    f"public charging demand 2026, P50\n(P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f})",
)
stat(
    s,
    4.1,
    5.35,
    3.0,
    f"{d26['phv_p50']:.0f} GWh",
    "of it from taxi & private hire —\nLondon's rapid-charging anchor",
    color=TEAL,
)
stat(
    s,
    7.4,
    5.35,
    3.0,
    f"{d30['total_p50']:.0f} GWh",
    "in 2030, DFES mid pathway\n(low–high 1,100–1,410)",
    color=NAVY,
)
text(
    s,
    10.6,
    5.5,
    2.3,
    1.2,
    "Near-home 78 · destination 55 · PHV 152 GWh. Priors and mix are documented in the model card.",
    size=11,
    color=MUTED,
)
footer(s, n)

# 7 calibration
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "No London usage data is open — so the model is checked against what is observed",
    "Notebook 02, section 2",
)
card(
    s,
    0.8,
    1.9,
    5.9,
    2.2,
    "Supply-implied energy",
    "28.8k slow + 2.5k rapid chargers (DfT) × TfL-observed occupancy (47 % slow, 34 % rapid) × charging-time share ⇒ ≈ 760 GWh/yr the network could be delivering.",
)
card(
    s,
    7.0,
    1.9,
    5.9,
    2.2,
    "Modelled demand",
    f"{d26['total_p50']:.0f} GWh P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f}); rapid-type (destination + PHV) ≈ {d26['dest_p50'] + d26['phv_p50']:.0f} GWh — the same order of magnitude as the rapid side of the supply estimate.",
)
stat(
    s,
    0.8,
    4.5,
    3.4,
    f"{K['rapid_sessions_per_charger_day']}",
    "implied rapid sessions per charger per day",
    color=ORANGE,
)
stat(s, 4.4, 4.5, 3.4, "≈13", "what TfL's 34 % occupancy implies with 38-min sessions", color=TEAL)
stat(s, 8.0, 4.5, 3.4, "≈3", "observed in Dundee's open session log (small city)", color=NAVY)
text(
    s,
    0.8,
    6.3,
    12.0,
    0.6,
    "The band is the honest statement: the two levers are the public-charging share of drivers without a driveway and the size of the electric PHV fleet — both named as the first things to calibrate once operator data exist.",
    size=12,
    color=MUTED,
    italic=True,
)
footer(s, n)

# 8 choice & queues
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "Where the demand lands today — and where queues form at the peak hour",
    "Notebook 03 — MNL station choice on drive times + Erlang-C queues",
)
picture(s, "03_site_load_queues.png", 0.6, 1.8, w=8.2)
stat(
    s,
    9.2,
    1.9,
    3.6,
    f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
    "rapid sites with P(wait) > 0.5 at the peak hour",
    color=ORANGE,
)
stat(s, 9.2, 3.5, 3.6, f"{K['util24_median']:.0%}", "median 24 h utilisation of a rapid site", color=TEAL)
text(
    s,
    9.2,
    5.1,
    3.7,
    1.8,
    [
        "Supply calibrated to DfT borough counts: OSM maps ~15 % of rapid devices.",
        "For any candidate hub the model splits captured demand into new vs cannibalised — typically 70–80 % is taken from existing sites within 20 minutes.",
    ],
    size=11,
    color=INK,
    line=1.2,
)
footer(s, n)

# 9 siting
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "Siting new 4 × 150 kW hubs under budget, capacity, grid and demand uncertainty",
    "Notebook 04 — capacitated MCLP + robust two-stage MILP (HiGHS)",
)
picture(s, "04_selected_hubs.png", 0.6, 1.8, h=5.1)
picture(s, "04_budget_curve.png", 7.4, 1.8, w=5.4)
sit = K.get("siting")
if sit:
    r20 = next((r for r in sit if abs(r["budget_m"] - 20) < 1e-6), sit[-1])
    text(
        s,
        7.4,
        5.4,
        5.5,
        1.5,
        [
            f"£{r20['budget_m']:.0f}M ⇒ {r20['n_hubs']} hubs serving {r20['coverage_share']:.0%} of unmet rapid demand ({r20['covered_p50']:,.0f} sessions/day of {r20['total_unmet_p50']:,.0f}).",
            f"Robust solution overlaps with P50 on {r20.get('robust_overlap_with_p50', '-')} of {r20['n_hubs']} sites; greedy uncapacitated would claim {r20['greedy_uncapacitated_covered']:,.0f}/day — the gap is demand a hub cannot absorb at an acceptable wait.",
        ],
        size=12,
        color=INK,
        line=1.2,
    )
else:
    text(s, 7.4, 5.4, 5.5, 1.2, "[siting results pending]", size=12, color=MUTED, italic=True)
footer(s, n)

# 10 transfer test
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "Do context features explain observed utilisation anywhere? A negative result, on purpose",
    f"Notebook 05 — {K['transfer_stations']} chargers with open session logs in four cities",
)
picture(s, "05_importance.png", 0.6, 1.8, h=4.9)
stat(s, 7.2, 1.9, 2.8, "0.70", "R² with random 5-fold CV\n(looks respectable)", color=TEAL)
stat(s, 10.1, 1.9, 2.8, "−0.25", "R² with leave-city-out CV\n(the number that matters)", color=ORANGE)
bullets(
    s,
    7.2,
    3.9,
    5.7,
    2.9,
    [
        "Charger power and the city's level dominate; OpenStreetMap context adds little that transfers.",
        "Rankings do not transfer reliably either (Spearman −0.3 to +0.6 by city); a level-free target barely helps.",
        "Implication: any 'geo-embedding site model' must be validated out-of-city against observed usage — this is the test to ask for.",
    ],
    size=12,
)
footer(s, n)

# 11 limitations & falsifiability
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(s, "Limitations — and how the whole thing would be proven wrong")
card(
    s,
    0.8,
    1.9,
    5.9,
    4.6,
    "Known limitations",
    "• No open London charger-level usage; behaviour from other UK cities and fleet trials.\n• OSM's hub bias and a 2021 registry snapshot: unmapped rapid devices enter as scaled ports, not positions.\n• Choice-model coefficients are literature-informed, not estimated.\n• Grid constraint stops at primary-substation headroom.\n• Area-weighted LSOA→hex interpolation; ≈1.4 % of population in dropped edge hexes.",
)
card(
    s,
    7.0,
    1.9,
    5.9,
    4.6,
    "The post-hoc test",
    "DfT/Zapmap publish borough device counts quarterly; TfL publishes utilisation by charger type.\n\nHubs opened after July 2026 in hexes flagged here as high unmet demand should reach above-median utilisation within a year.\n\nIf they do not, the model card names the priors to revisit first: PHV fleet size, public share without home charging, choice radius.\n\nPredict → deploy → measure → retrain is the product; the maps are its interface.",
    fill=RGBColor(0xE6, 0xF2, 0xF0),
)
footer(s, n)

# 12 what an operator gets
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
n += 1
title(
    s,
    "What an operator or investor gets from this",
    "The same stack applies to any city with open geodata — and improves the moment usage data are plugged in",
)
cards = [
    (
        "Ranked candidates with intervals",
        "Every hex: expected sessions/day, P10–P90, share taken from neighbours, headroom label, drive-time catchment.",
    ),
    (
        "Capacity, not just location",
        "Ports and power sized from the queue model against a service level, instead of a fixed template.",
    ),
    (
        "Portfolio robustness",
        "Which sites hold under low demand and which depend on the optimistic tail — phase the latter.",
    ),
    (
        "A learning loop",
        "Aggregate calibration now; revealed-preference choice parameters and per-hex uncertainty once the network reports.",
    ),
]
for i, (h, b) in enumerate(cards):
    card(s, 0.8 + (i % 2) * 6.2, 1.9 + (i // 2) * 2.4, 5.9, 2.2, h, b)
footer(s, n)

# 13 links
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
n += 1
text(s, 0.8, 1.4, 11.5, 1.0, "Explore it", size=40, bold=True, color=WHITE, font=HEAD)
text(
    s,
    0.8,
    2.6,
    11.5,
    3.6,
    [
        "Repository: github.com/OWNER/chargescape-london — code, 16 tests, data catalog with 23 source cards, methodology and model card",
        "Notebooks 01–05: supply audit · demand surface · choice & queues · siting · utilisation transfer",
        "Interactive maps (deck.gl, no keys): demand 2026 · rapid network load & queues · selected hubs under a £20M budget",
        "Reproduce: pip install -e . → make data → make features → make models → make maps",
    ],
    size=16,
    color=WHITE,
    line=1.4,
)
text(
    s,
    0.8,
    6.3,
    11.5,
    0.5,
    "Marija Ercegovac · mercegovacm@gmail.com",
    size=13,
    color=RGBColor(0xC8, 0xD3, 0xDC),
)

out = ROOT / "reports" / "ChargeScape_London.pptx"
prs.save(out)
print("wrote", out, "slides:", len(prs.slides))
