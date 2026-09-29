"""Offline PPTX version of the final deck (reports/ChargeScape_London.pptx), same structure as the HTML
slides but with static figures instead of live maps. Numbers from reports/tables/key_numbers.json."""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "reports" / "figures"
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
NAVY, ORANGE, TEAL = RGBColor(0x14, 0x21, 0x3D), RGBColor(0xE4, 0x57, 0x2E), RGBColor(0x0C, 0x7C, 0x70)
INK, MUTED, PALE, WHITE, SOFT = (
    RGBColor(0x1A, 0x20, 0x27),
    RGBColor(0x5B, 0x6B, 0x7A),
    RGBColor(0xEE, 0xF2, 0xF4),
    RGBColor(0xFF, 0xFF, 0xFF),
    RGBColor(0xC8, 0xD3, 0xDC),
)
HEAD, BODY = "Cambria", "Calibri"
W, H = 13.333, 7.5
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
BLANK = prs.slide_layouts[6]


def bg(s, color):
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = color


def text(s, x, y, w, h, lines, size=16, bold=False, color=INK, font=BODY, align=PP_ALIGN.LEFT, italic=False):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, ln in enumerate(lines if isinstance(lines, list) else [lines]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = 1.15
        r = p.add_run()
        r.text = ln
        r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
        r.font.color.rgb = color
    return tb


def bullets(s, x, y, w, h, items, size=14):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(7)
        r = p.add_run()
        r.text = "•  " + it
        r.font.size, r.font.name = Pt(size), BODY
        r.font.color.rgb = INK


def title(s, t, sub=None):
    text(s, 0.6, 0.4, W - 1.2, 0.9, t, size=28, bold=True, color=NAVY, font=HEAD)
    if sub:
        text(s, 0.6, 1.2, W - 1.2, 0.45, sub, size=13, color=MUTED, italic=True)


def stat(s, x, y, w, big, label, color=ORANGE):
    text(s, x, y, w, 0.8, big, size=34, bold=True, color=color, font=HEAD)
    text(s, x, y + 0.78, w, 0.8, label, size=12, color=MUTED)


def card(s, x, y, w, h, head, body, fill=PALE, size=12):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.adjustments[0] = 0.05
    shp.shadow.inherit = False
    text(s, x + 0.25, y + 0.18, w - 0.5, 0.45, head, size=15, bold=True, color=NAVY)
    text(s, x + 0.25, y + 0.65, w - 0.5, h - 0.8, body, size=size)


def picture(s, name, x, y, w=None, h=None):
    p = FIG / name
    if p.exists():
        s.shapes.add_picture(
            str(p),
            Inches(x),
            Inches(y),
            **({"width": Inches(w)} if w else {}),
            **({"height": Inches(h)} if h else {}),
        )


def footer(s, n):
    text(
        s,
        0.6,
        H - 0.42,
        9,
        0.3,
        "ChargeScape London · github.com/m-erts/chargescape-london",
        size=9,
        color=MUTED,
    )
    text(s, W - 1.2, H - 0.42, 0.6, 0.3, str(n), size=9, color=MUTED, align=PP_ALIGN.RIGHT)


d26, d30 = K["demand_gwh"]["2026"], K["demand_gwh"]["2030_mid"]
sit = {r["budget_m"]: r for r in K.get("siting", [])}
r20, r40 = sit.get(20.0), sit.get(40.0)
cap = K.get("siting_meta", {}).get("hub_capacity_sessions_day", 33)
tr = K["transfer"]
rho = list(tr["spearman_by_city"].values())
can = K["cannibalisation"]
sens = K.get("sensitivity", {})
n_rapid, n_slow = K["chargers_rapid"], K["chargers_total"] - K["chargers_rapid"]
supply_gwh = (n_slow * 7 * 8760 * 0.47 * 0.45 + n_rapid * 60 * 8760 * 0.34 * 0.85) / 1e6
n = 0


def new(dark=False):
    global n
    n += 1
    s = prs.slides.add_slide(BLANK)
    bg(s, NAVY if dark else WHITE)
    return s


# 1 title
s = new(True)
text(s, 0.8, 1.5, 11.5, 1.4, "ChargeScape London", size=52, bold=True, color=WHITE, font=HEAD)
text(
    s,
    0.8,
    2.9,
    11.5,
    1.1,
    "A spatial decision system for EV charging networks under uncertain demand",
    size=24,
    color=SOFT,
    font=HEAD,
)
text(
    s,
    0.8,
    4.3,
    11.0,
    1.2,
    [
        "Where should London's next rapid-charging hubs go, how big should they be, and how sure can we be?",
        "Built end-to-end from open data, with every assumption visible.",
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
    "Marija Ercegovac · geospatial data science · github.com/m-erts/chargescape-london",
    size=13,
    color=SOFT,
)

# 2 problem
s = new()
title(s, "Charging is an infrastructure business that lives or dies on utilisation")
stat(s, 0.8, 1.6, 2.9, f"{K['chargers_total']:,}", f"public chargers in London (DfT, {K['dft_date']})")
stat(s, 3.9, 1.6, 2.9, f"{100 * K['rapid_share']:.0f} %", "of them are 50 kW+; UK: 24 %", TEAL)
stat(s, 7.0, 1.6, 2.9, "300k", "plug-in cars kept in London (DfT, Q1 2026)", NAVY)
stat(s, 10.1, 1.6, 2.9, "34 %", "occupancy of rapid units (TfL, 2025)")
card(
    s,
    0.8,
    3.7,
    5.9,
    2.9,
    "The economics",
    "A hub in the wrong hex idles at 5 % and never pays back; the right one runs above 20–30 % and queues. Industry analyses put break-even at 15–20 % utilisation; payback roughly halves between 10 % and 20 %.",
)
card(
    s,
    7.0,
    3.7,
    5.9,
    2.9,
    "The analytics gap",
    "Operators describe site selection as a demand model on dozens to hundreds of factors. Public projects usually predict where chargers already are, ignore queues and cannibalisation, and never say how they could be proven wrong.",
)
footer(s, n)

# 3 approach
s = new()
title(s, "What this system does differently")
items = [
    (
        "Labels on every dataset",
        f"observed / proxy / synthetic — {K['n_sources']} sources in the catalog; the label follows the number into every table.",
    ),
    (
        "Usage, checked against reality",
        "Demand modelled bottom-up, then checked against DfT charger counts × TfL occupancy and open session logs.",
    ),
    (
        "Uncertainty reaches the decision",
        "P10/P50/P90 per hex; a plan is solved for each demand scenario and tested under the others; a sensitivity run shows what moves.",
    ),
    (
        "Queues, cannibalisation, grid",
        "Erlang-C capacity per hub, new vs stolen demand for any candidate, primary-substation headroom as a filter.",
    ),
]
for i, (h, b) in enumerate(items):
    x, y = 0.8 + (i % 2) * 6.2, 1.6 + (i // 2) * 2.0
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(0.5), Inches(0.5))
    c.fill.solid()
    c.fill.fore_color.rgb = [ORANGE, TEAL, NAVY, ORANGE][i]
    c.line.fill.background()
    text(s, x, y + 0.09, 0.5, 0.35, str(i + 1), size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    text(s, x + 0.7, y, 5.3, 0.45, h, size=17, bold=True, color=NAVY, font=HEAD)
    text(s, x + 0.7, y + 0.5, 5.3, 1.3, b, size=13)
steps = ["Open data", "H3 features", "Demand · MC", "Choice & queues", "Siting MILP", "Maps & test plan"]
for i, st in enumerate(steps):
    x = 0.6 + i * 2.05
    shp = s.shapes.add_shape(
        MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON, Inches(x), Inches(5.9), Inches(2.0), Inches(0.7)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = [NAVY, TEAL, ORANGE, TEAL, NAVY, MUTED][i]
    shp.line.fill.background()
    text(s, x + 0.3, 6.1, 1.5, 0.35, st, size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
footer(s, n)

# 4 data
s = new()
title(s, f"{K['n_sources']} open sources, each labelled observed, proxy or synthetic")
groups = [
    (
        "Supply · observed",
        "Open Charge Map (12.5k points), OpenStreetMap, National Chargepoint Registry 2021, DfT EVCI July 2026",
    ),
    (
        "Where EVs live · observed",
        "Census 2021 (4,994 LSOAs), DfT vehicle licensing by LSOA (Q1 2026), Indices of Deprivation 2025",
    ),
    (
        "Activity & traffic · observed / proxy",
        "OSM POIs (74k), LAEI 2022 road flows incl. taxi & private hire, TfL stations, NaPTAN",
    ),
    (
        "Grid & future · proxy",
        "UKPN primary-substation headroom (summer 2026); DFES 2026 EV pathways to 2030",
    ),
    (
        "Behaviour elsewhere · observed",
        "Session logs from Dundee, Perth & Kinross, Palo Alto, Boulder; Optimise Prime; Low Carbon London",
    ),
    (
        "Model outputs · synthetic",
        "Monte Carlo demand draws; literature-informed choice parameters — never presented as observed",
    ),
]
for i, (h, b) in enumerate(groups):
    card(s, 0.8 + (i % 3) * 4.1, 1.5 + (i // 3) * 1.95, 3.9, 1.8, h, b, size=11)
stat(s, 0.8, 5.55, 3.9, f"{K['sites_total']:,}", "charging sites after de-duplication within 50 m", NAVY)
stat(s, 4.9, 5.55, 3.9, f"{K['n_hexes']:,}", "H3 hexes at resolution 8 (0.74 km²)", TEAL)
stat(s, 9.0, 5.55, 3.9, f"{tr['n_stations']}", "chargers with observed usage (transfer test)")
footer(s, n)

# 5 supply
s = new()
title(
    s,
    "Supply follows devices; need follows cars without driveways",
    "Live map: m-erts.github.io/chargescape-london/maps/supply_2026.html",
)
picture(s, "01_hex_supply_demand.png", 0.6, 1.75, h=5.2)
bullets(
    s,
    7.4,
    1.9,
    5.4,
    4.9,
    [
        "Inner boroughs: ~1,400 chargers per 100k residents, mostly 5–7 kW lamp-post units; rapid share 40 % in Havering and Hillingdon, under 4 % in Westminster and Hackney.",
        "Private plug-in cars cluster in outer, house-rich boroughs (Moran's I = 0.73).",
        "EV owners in flats — who depend on public charging — form Gi* hot spots in inner-west and inner-south London.",
        f"Median drive time to a rapid site is {K['median_tt_nearest_rapid_min']} min: in London the constraint is capacity, not distance.",
    ],
    size=13,
)
footer(s, n)

# 6 demand
s = new()
title(
    s,
    "A demand surface with the uncertainty attached",
    "Live map: …/maps/demand_2026.html (toggle P10 / P50 / P90 / 2030)",
)
picture(s, "02_demand_p50_uncertainty.png", 0.6, 1.75, w=12.1)
stat(
    s,
    0.8,
    5.35,
    3.6,
    f"{d26['total_p50']:.0f} GWh",
    f"public charging demand 2026, P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f})",
)
stat(
    s,
    4.7,
    5.35,
    3.6,
    f"{d26['phv_p50']:.0f} GWh",
    "from taxi & private hire — London's rapid-charging anchor",
    TEAL,
)
stat(s, 8.6, 5.35, 3.9, f"{d30['total_p50']:,.0f} GWh", "in 2030, DFES mid pathway", NAVY)
footer(s, n)

# 7 calibration
s = new()
title(s, "No London usage data is open — so the model is checked against what is observed")
card(
    s,
    0.8,
    1.6,
    5.9,
    2.1,
    "Energy the network could deliver",
    f"{n_slow:,} slow + {n_rapid:,} rapid chargers (DfT) × TfL-observed occupancy × charging-time share ⇒ ≈ {supply_gwh:,.0f} GWh a year.",
)
card(
    s,
    7.0,
    1.6,
    5.9,
    2.1,
    "Modelled demand",
    f"{d26['total_p50']:.0f} GWh P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f}); rapid-type demand ≈ {d26['dest_p50'] + d26['phv_p50']:.0f} GWh — the same order as the rapid side of the supply estimate.",
)
stat(
    s,
    0.8,
    4.2,
    3.9,
    f"{K['rapid_sessions_per_charger_day']}",
    "rapid sessions per charger per day implied by the model",
)
stat(s, 4.9, 4.2, 3.9, "≈13", "what TfL's 34 % occupancy implies with 38-minute sessions", TEAL)
stat(s, 9.0, 4.2, 3.9, "≈3", "observed in Dundee's open session log", NAVY)
text(
    s,
    0.8,
    6.1,
    12.0,
    0.7,
    "The band is the honest statement: the two levers are the public-charging share of drivers without a driveway and the size of the electric private-hire fleet.",
    size=12,
    color=MUTED,
    italic=True,
)
footer(s, n)

# 8 queues
s = new()
title(
    s,
    "Where the demand lands today — and where queues form at the peak hour",
    "Live map: …/maps/rapid_network_load_2026.html",
)
picture(s, "03_site_load_queues.png", 0.6, 1.75, w=8.3)
stat(
    s,
    9.3,
    1.9,
    3.6,
    f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
    "rapid sites with P(wait) > 0.5 at the peak hour",
)
stat(
    s, 9.3, 3.5, 3.6, f"{100 * K['util24_median']:.0f} %", "median 24-hour utilisation of a rapid site", TEAL
)
text(
    s,
    9.3,
    5.1,
    3.7,
    1.8,
    f"Logit station choice on OSM drive times, Erlang-C queues with 38-minute sessions; ports scaled per borough to DfT 50 kW+ totals (median ×{K['port_scale_median']:.1f}).",
    size=11,
)
footer(s, n)

# 9 cannibalisation (native chart)
s = new()
title(
    s,
    "A new hub mostly takes customers from its neighbours",
    f"Hub at the hex with the largest unmet demand ({can['candidate']['borough']}); logit with an outside option",
)
cd = CategoryChartData()
cd.categories = [f"{r['power_kw']} kW × {r['ports']}" for r in can["rows"]]
cd.add_series("new demand", [round(r["new"], 1) for r in can["rows"]])
cd.add_series("taken from existing sites", [round(r["cannibalised"], 1) for r in can["rows"]])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.6), Inches(1.7), Inches(7.6), Inches(4.8), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Sessions per day captured by the new hub"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
for ser, col in zip(ch.series, [TEAL, ORANGE], strict=True):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
plot = ch.plots[0]
plot.gap_width = 60
plot.has_data_labels = True
plot.data_labels.number_format = "0"
plot.data_labels.number_format_is_linked = False
plot.data_labels.position = XL_LABEL_POSITION.CENTER
plot.data_labels.font.size = Pt(11)
plot.data_labels.font.color.rgb = WHITE
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xDD, 0xE2, 0xE6)
ch.value_axis.tick_labels.font.size = Pt(10)
ch.category_axis.tick_labels.font.size = Pt(11)
lo = min(r["cannibalisation_share"] for r in can["rows"])
hi = max(r["cannibalisation_share"] for r in can["rows"])
stat(s, 8.7, 2.0, 4.2, f"{100 * lo:.0f}–{100 * hi:.0f} %", "of a new hub's sessions come from existing sites")
text(
    s,
    8.7,
    3.6,
    4.2,
    2.6,
    "Bigger, faster hubs capture more — and cannibalise a larger share. This is the number an investor needs next to “expected sessions”, and it is exactly what a gap map cannot show.",
    size=13,
)
footer(s, n)

# 10 siting
s = new()
title(
    s,
    "Siting 4 × 150 kW hubs under budget, capacity, grid and demand uncertainty",
    "Live map: …/maps/siting_hubs.html (budgets £5–40M, P50 vs robust)",
)
picture(s, "04_selected_hubs.png", 0.6, 1.7, h=5.2)
picture(s, "04_budget_curve.png", 7.4, 1.7, w=5.2)
if r20:
    line = f"£20M ⇒ {r20['n_hubs']} hubs serve {100 * r20['coverage_share']:.0f} % of unmet rapid demand ({r20['covered_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions/day)."
    if r40:
        line += f" £40M ⇒ {r40['n_hubs']} hubs, {100 * r40['coverage_share']:.0f} %."
    extra = (
        f" Across {sens['variants']} changed assumptions a median {100 * sens['same_or_adjacent_median']:.0f} % of hubs stay in the same or an adjacent hex."
        if sens
        else ""
    )
    if "rec_plan" in r20:
        extra = (
            f" Under demand uncertainty the {r20['rec_plan'].upper()} plan has the smallest worst-case regret ({r20['rec_max_regret']:,.0f} sessions/day); robust core {r20['rec_core']} of {r20['rec_n_hubs']} hubs."
            + extra
        )
    text(
        s,
        7.4,
        5.45,
        5.5,
        1.6,
        [line, f"Capacity-bound: ≈{cap:.0f} sessions/day per hub at P(wait) ≤ 15 %.{extra}"],
        size=12,
    )
footer(s, n)

# 11 transfer
s = new()
title(s, "Do context features explain observed utilisation anywhere? A negative result, on purpose")
picture(s, "05_importance.png", 0.6, 1.7, h=3.9)
stat(s, 7.2, 1.7, 2.8, f"{tr['r2_random']:.2f}", "R² with random 5-fold CV", TEAL)
stat(s, 10.1, 1.7, 2.8, f"{tr['r2_leave_city_out']:.2f}", "R² when the test city is unseen")
bullets(
    s,
    7.2,
    3.6,
    5.7,
    3.2,
    [
        f"{tr['n_stations']} chargers with open session logs in four cities; LightGBM on OSM context, population and charger power.",
        f"Charger power and the city's level dominate; rankings do not transfer reliably (Spearman {min(rho):.2f} to {max(rho):.2f} by city).",
        "Any “geo-embedding site model” must be validated out-of-city against observed usage.",
    ],
    size=12,
)
footer(s, n)

# 12 stack
s = new()
title(s, "Engineering: reproducible from a clean clone")
rows = [
    ("Spatial", "H3 · GeoPandas · Shapely · pyproj", "hex grid for siting; areal interpolation from LSOAs"),
    (
        "Network",
        "OSMnx · igraph",
        "many-to-many drive times on a 131k-node graph in seconds, no routing server",
    ),
    (
        "Statistics & ML",
        "esda · libpysal · LightGBM · scikit-learn",
        "Moran's I, Gi*; spatial cross-validation by default",
    ),
    (
        "Optimisation",
        "SciPy milp / linprog (HiGHS)",
        "sparse capacitated MCLP and exact fixed-plan LPs; MIP gap recorded per solve",
    ),
    ("Choice & queues", "NumPy", "Erlang C, multinomial logit, new vs cannibalised demand — unit-tested"),
    (
        "Delivery",
        "MapLibre GL JS · matplotlib · GitHub Pages",
        "offline-capable maps, HTML slides EN/RU, this PPTX",
    ),
]
tbl = s.shapes.add_table(len(rows), 3, Inches(0.8), Inches(1.5), Inches(11.8), Inches(3.9)).table
tbl.columns[0].width, tbl.columns[1].width, tbl.columns[2].width = Inches(2.2), Inches(4.0), Inches(5.6)
for i, (a, b, c) in enumerate(rows):
    for j, v in enumerate((a, b, c)):
        cell = tbl.cell(i, j)
        cell.text = v
        cell.fill.solid()
        cell.fill.fore_color.rgb = PALE if i % 2 == 0 else WHITE
        para = cell.text_frame.paragraphs[0]
        para.runs[0].font.size = Pt(12)
        para.runs[0].font.name = BODY
        para.runs[0].font.bold = j == 0
        para.runs[0].font.color.rgb = TEAL if j == 1 else (NAVY if j == 0 else INK)
chips = [
    f"{K['n_tests']} tests · CI on Python 3.11 / 3.12",
    "make models → maps → slides",
    f"{K['n_sources']} data cards with licences",
    "code MIT · data ODbL / OGL / CC BY",
]
for i, c in enumerate(chips):
    shp = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8 + i * 3.0), Inches(5.9), Inches(2.85), Inches(0.55)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = NAVY
    shp.line.fill.background()
    shp.adjustments[0] = 0.5
    text(s, 0.9 + i * 3.0, 6.02, 2.65, 0.35, c, size=11, color=WHITE, align=PP_ALIGN.CENTER)
footer(s, n)

# 13 limitations
s = new()
title(s, "Limitations — and how the whole thing would be proven wrong")
card(
    s,
    0.8,
    1.5,
    5.9,
    5.2,
    "Known limitations",
    "• No open London charger-level usage; behaviour from other UK cities and fleet trials.\n• Open Charge Map covers most sites but not every port; residual gaps closed per borough against DfT totals.\n• Choice coefficients are literature-informed; notebook 04 shows what moves when they change.\n• Grid constraints stop at primary-substation headroom.\n• Area-weighted LSOA → hex interpolation; ≈1.4 % of population in dropped edge hexes.",
)
card(
    s,
    7.0,
    1.5,
    5.9,
    5.2,
    "The post-hoc test",
    "DfT and Zapmap publish borough device counts quarterly; TfL publishes utilisation by charger type.\n\nHubs opened after July 2026 in hexes flagged here as high unmet demand should reach above-median utilisation within a year.\n\nIf not, the model card names the priors to revisit first: private-hire fleet size, public share without home charging, choice radius.\n\nPredict → deploy → measure → retrain is the product; the maps are its interface.",
    fill=RGBColor(0xE6, 0xF2, 0xF0),
)
footer(s, n)

# 14 value
s = new()
title(s, "What an operator or investor gets — and what comes next")
gets = [
    (
        "Ranked candidates with intervals",
        "Expected sessions per day, P10–P90, share taken from neighbours, substation headroom and drive-time catchment for every hex.",
    ),
    (
        "Capacity, not just location",
        "Ports and power sized from the queue model against a service level, instead of a fixed template.",
    ),
    (
        "Portfolio robustness",
        "Which hubs every demand scenario agrees on (the robust core) and which are interchangeable with neighbours — build the core first, phase the rest.",
    ),
    (
        "Next, with operator data",
        "Choice parameters from real routes, hour-of-day profiles, per-hex uncertainty from sessions, staggered difference-in-differences on openings.",
    ),
]
for i, (h, b) in enumerate(gets):
    card(s, 0.8 + (i % 2) * 6.2, 1.5 + (i // 2) * 2.55, 5.9, 2.3, h, b, size=13)
footer(s, n)

# 15 links
s = new(True)
text(s, 0.8, 1.3, 11.5, 1.0, "Explore it", size=40, bold=True, color=WHITE, font=HEAD)
text(
    s,
    0.8,
    2.5,
    11.8,
    3.6,
    [
        "Repository: github.com/m-erts/chargescape-london",
        "Slides with live maps: m-erts.github.io/chargescape-london/slides/ (Russian: /slides/ru.html)",
        "Maps: m-erts.github.io/chargescape-london/maps/",
        "Notebooks 01–05: supply audit · demand · choice & queues · siting · transfer test",
        "Reproduce: pip install -e .[all] → make models maps slides",
    ],
    size=16,
    color=WHITE,
)
text(s, 0.8, 6.3, 11.5, 0.5, "Marija Ercegovac · github.com/m-erts", size=13, color=SOFT)

out = ROOT / "reports" / "ChargeScape_London.pptx"
prs.save(out)
print("wrote", out, "slides:", len(prs.slides))
