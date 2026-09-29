"""Offline PPTX version of the deck (reports/ChargeScape_London.pptx).

Same argument as the HTML slides, with static figures instead of live maps. Chrome follows DESIGN.md:
black, white and grey, one blue accent, sharp 1px-bordered blocks. Numbers from key_numbers.json.
"""

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
INK, MUTED, PALE, WHITE, SOFT = (
    RGBColor(0x11, 0x11, 0x11),
    RGBColor(0x66, 0x66, 0x66),
    RGBColor(0xFA, 0xFA, 0xFA),
    RGBColor(0xFF, 0xFF, 0xFF),
    RGBColor(0x88, 0x88, 0x88),
)
BLACK, BORDER, ACCENT = RGBColor(0x00, 0x00, 0x00), RGBColor(0xEA, 0xEA, 0xEA), RGBColor(0x00, 0x70, 0xF3)
NAVY = ORANGE = TEAL = INK  # one text colour; the accent is reserved for data
HEAD = BODY = "Arial"
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
        if isinstance(lines, list) and len(lines) > 1:
            p.space_after = Pt(6)
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
    text(s, 0.6, 0.45, W - 1.2, 0.9, t, size=24, bold=True, color=NAVY, font=HEAD)
    if sub:
        text(s, 0.6, 1.2, W - 1.2, 0.45, sub, size=13, color=MUTED)


def stat(s, x, y, w, big, label, color=ORANGE):
    text(s, x, y, w, 0.8, big, size=34, bold=True, color=color, font=HEAD)
    text(s, x, y + 0.78, w, 0.8, label, size=12, color=MUTED)


def box(s, x, y, w, h, fill=WHITE):
    shp = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = BORDER
    shp.line.width = Pt(0.75)
    shp.shadow.inherit = False
    return shp


def card(s, x, y, w, h, head, body, fill=WHITE, size=12):
    box(s, x, y, w, h, fill)
    text(s, x + 0.25, y + 0.18, w - 0.5, 0.45, head, size=15, bold=True, color=NAVY)
    text(s, x + 0.25, y + 0.65, w - 0.5, h - 0.8, body.split("\n\n") if "\n\n" in body else body, size=size)


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
    bg(s, BLACK if dark else WHITE)
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
        "Built end to end from open data, with every assumption visible.",
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
    "Marija Ercegovac, geospatial data science, github.com/m-erts/chargescape-london",
    size=13,
    color=SOFT,
)

# 2 problem
s = new()
title(s, "Charging is an infrastructure business that lives or dies on utilisation")
stat(s, 0.8, 1.6, 2.9, f"{K['chargers_total']:,}", f"public chargers in London (DfT, {K['dft_date']})")
stat(s, 3.9, 1.6, 2.9, f"{100 * K['rapid_share']:.0f}%", "rated 50 kW or more. UK: 24%", TEAL)
stat(s, 7.0, 1.6, 2.9, "300k", "plug-in cars kept in London (DfT, Q1 2026)", NAVY)
stat(s, 10.1, 1.6, 2.9, "34%", "occupancy of rapid units (TfL, 2025)")
card(
    s,
    0.8,
    3.7,
    5.9,
    2.9,
    "The economics",
    "A hub in the wrong place idles at 5% and never pays back. A hub in the right place runs above 20% and starts to queue. Industry analyses put break-even at 15 to 20% utilisation.",
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
        f"Observed, proxy or synthetic. {K['n_sources']} datasets in the catalog, and the label follows each number into every table.",
    ),
    (
        "Usage, checked against reality",
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
]
for i, (h, b) in enumerate(items):
    x, y = 0.8 + (i % 2) * 6.2, 1.6 + (i // 2) * 2.0
    box(s, x, y, 0.5, 0.5)
    text(s, x, y + 0.11, 0.5, 0.35, str(i + 1), size=13, color=MUTED, align=PP_ALIGN.CENTER)
    text(s, x + 0.7, y, 5.3, 0.45, h, size=17, bold=True, color=NAVY, font=HEAD)
    text(s, x + 0.7, y + 0.5, 5.3, 1.3, b, size=13)
steps = ["Open data", "H3 features", "Demand", "Choice and queues", "Siting MILP", "Maps and test plan"]
for i, st in enumerate(steps):
    x = 0.6 + i * 2.05
    box(s, x, 5.9, 2.05, 0.7, PALE)
    text(s, x + 0.15, 6.12, 1.75, 0.35, st, size=11, bold=True, align=PP_ALIGN.CENTER)
footer(s, n)

# 4 data
s = new()
title(s, f"{K['n_sources']} open sources, each labelled observed, proxy or synthetic")
groups = [
    (
        "Supply: observed",
        "Open Charge Map (12.5k points), OpenStreetMap, National Chargepoint Registry 2021, DfT EVCI July 2026",
    ),
    (
        "Where EVs live: observed",
        "Census 2021 (4,994 LSOAs), DfT vehicle licensing by LSOA (Q1 2026), Indices of Deprivation 2025",
    ),
    (
        "Activity: observed, proxy",
        "OSM POIs (74k), LAEI 2022 road flows with taxi and private hire, TfL stations, NaPTAN",
    ),
    (
        "Grid and future: proxy",
        "UKPN primary-substation headroom (summer 2026), DFES 2026 EV pathways to 2030",
    ),
    (
        "Behaviour elsewhere: observed",
        "Session logs from Dundee, Perth and Kinross, Palo Alto, Boulder. Optimise Prime, Low Carbon London",
    ),
    (
        "Model outputs: synthetic",
        "Monte Carlo demand draws and literature-informed choice parameters, never presented as observed",
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
    "Supply follows devices. Need follows cars without driveways.",
    "Live map: m-erts.github.io/chargescape-london/maps/supply_2026.html",
)
picture(s, "panel_supply.png", 0.6, 1.75, h=4.9)
text(
    s,
    0.6,
    6.7,
    6.3,
    0.3,
    "Private plug-in cars per 1,000 households (grey) and sites of 50 kW or more (blue)",
    size=10,
    color=MUTED,
)
bullets(
    s,
    7.4,
    1.9,
    5.4,
    4.9,
    [
        "Inner boroughs: about 1,400 chargers per 100,000 residents, mostly lamp-post units of 5 to 7 kW. Rapid share is 40% in Havering and 39% in Hillingdon, under 4% in Westminster and Hackney.",
        "Private plug-in cars cluster in outer, house-rich boroughs (Moran's I = 0.73).",
        "EV owners in flats, who depend on public charging, form Gi* hot spots in inner-west and inner-south London.",
        f"Median drive time to a rapid site is {K['median_tt_nearest_rapid_min']} min. In London the constraint is capacity, not distance.",
    ],
    size=13,
)
footer(s, n)

# 6 demand
s = new()
title(
    s,
    "A demand surface with the uncertainty attached",
    "Live map: …/maps/demand_2026.html (switch between P10, P50, P90 and 2030)",
)
picture(s, "panel_demand.png", 0.6, 1.75, h=4.9)
text(s, 0.6, 6.7, 6.3, 0.3, "Public charging demand 2026, P50, six quantile classes", size=10, color=MUTED)
stat(
    s,
    7.4,
    1.9,
    5.4,
    f"{d26['total_p50']:.0f} GWh",
    f"public charging demand 2026, P50 (P10 to P90: {d26['total_p10']:.0f} to {d26['total_p90']:.0f})",
)
stat(
    s,
    7.4,
    3.45,
    5.4,
    f"{d26['phv_p50']:.0f} GWh",
    "from taxi and private hire, the anchor of rapid charging in London",
)
stat(s, 7.4, 5.0, 5.4, f"{d30['total_p50']:,.0f} GWh", "in 2030, DFES mid pathway")
footer(s, n)

# 7 calibration
s = new()
title(s, "London publishes no charger usage, so the model is checked against what is observed")
card(
    s,
    0.8,
    1.6,
    5.9,
    2.1,
    "Energy the network could deliver",
    f"{n_slow:,} slow and {n_rapid:,} rapid chargers (DfT) x occupancy observed by TfL x time spent charging gives about {supply_gwh:,.0f} GWh a year.",
)
card(
    s,
    7.0,
    1.6,
    5.9,
    2.1,
    "Modelled demand",
    f"{d26['total_p50']:.0f} GWh P50 (P10 to P90: {d26['total_p10']:.0f} to {d26['total_p90']:.0f}). Rapid-type demand is about {d26['dest_p50'] + d26['phv_p50']:.0f} GWh, the same order as the rapid side of the supply estimate.",
)
stat(
    s,
    0.8,
    4.2,
    3.9,
    f"{K['rapid_sessions_per_charger_day']}",
    "rapid sessions per charger per day implied by the model",
)
stat(s, 4.9, 4.2, 3.9, "13", "implied by TfL occupancy of 34% with 38-minute sessions", TEAL)
stat(s, 9.0, 4.2, 3.9, "3", "observed in the open session log of Dundee", NAVY)
text(
    s,
    0.8,
    6.1,
    12.0,
    0.7,
    "The interval is the honest statement. The two levers are the public share of drivers without a driveway and the size of the electric private-hire fleet.",
    size=12,
    color=MUTED,
)
footer(s, n)

# 8 queues
s = new()
title(
    s,
    "Where demand lands today, and where queues form at the peak hour",
    "Live map: …/maps/rapid_network_load_2026.html",
)
picture(s, "panel_queues.png", 0.6, 1.75, h=4.9)
text(
    s,
    0.6,
    6.7,
    6.3,
    0.3,
    "Rapid sites sized by sessions per day, blue where P(wait) is high",
    size=10,
    color=MUTED,
)
stat(
    s,
    7.4,
    1.9,
    5.4,
    f"{K['sites_pwait_gt_50']} / {K['rapid_sites']}",
    "rapid sites with P(wait) above 0.5 in the peak hour",
)
stat(s, 7.4, 3.45, 5.4, f"{100 * K['util24_median']:.0f}%", "median 24-hour utilisation of a rapid site")
text(
    s,
    7.4,
    5.0,
    5.4,
    1.5,
    f"Logit station choice on OSM drive times. Erlang C queues with 38-minute sessions. Ports are scaled per borough to DfT totals, median factor {K['port_scale_median']:.1f}.",
    size=12,
    color=MUTED,
)
footer(s, n)

# 9 cannibalisation (native chart)
s = new()
title(
    s,
    "A new hub mostly takes customers from its neighbours",
    f"A hub in the hex with the largest unmet demand, in {can['candidate']['borough']}. Logit with an outside option.",
)
cd = CategoryChartData()
cd.categories = [f"{r['power_kw']} kW x {r['ports']}" for r in can["rows"]]
cd.add_series("new demand", [round(r["new"], 1) for r in can["rows"]])
cd.add_series("captured from existing sites", [round(r["cannibalised"], 1) for r in can["rows"]])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.6), Inches(1.7), Inches(7.6), Inches(4.8), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Sessions per day captured by the new hub"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
for ser, col in zip(ch.series, [ACCENT, INK], strict=True):
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
ch.value_axis.major_gridlines.format.line.color.rgb = BORDER
ch.value_axis.tick_labels.font.size = Pt(10)
ch.category_axis.tick_labels.font.size = Pt(11)
lo = min(r["cannibalisation_share"] for r in can["rows"])
hi = max(r["cannibalisation_share"] for r in can["rows"])
stat(
    s,
    8.7,
    2.0,
    4.2,
    f"{100 * lo:.0f} to {100 * hi:.0f}%",
    "of the sessions of a new hub are taken from existing sites",
)
text(
    s,
    8.7,
    3.6,
    4.2,
    2.6,
    "Larger and faster hubs capture more sessions and take a larger share from their neighbours. An investor needs this number next to expected sessions. A gap map cannot show it.",
    size=13,
)
footer(s, n)

# 10 siting
s = new()
title(
    s,
    "Siting 4 x 150 kW hubs under budget, capacity and grid limits",
    "Live map: …/maps/siting_hubs.html (budgets £5M to £40M, one plan per demand scenario)",
)
picture(s, "panel_hubs.png", 0.6, 1.75, h=4.9)
text(
    s,
    0.6,
    6.7,
    6.3,
    0.3,
    "Unmet rapid demand (grey) and the recommended £20M plan. Blue hubs form the robust core.",
    size=10,
    color=MUTED,
)
cd = CategoryChartData()
cd.categories = [f"£{int(b)}M" for b in sorted(sit)]
cd.add_series("exact, with capacity", [round(sit[b]["covered_p50"]) for b in sorted(sit)])
cd.add_series(
    "greedy, capacity ignored", [round(sit[b]["greedy_uncapacitated_covered"]) for b in sorted(sit)]
)
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(7.3), Inches(1.7), Inches(5.6), Inches(3.3), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Unmet sessions per day served, by budget"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(10)
for ser, col in zip(ch.series, [INK, SOFT], strict=True):
    ser.smooth = False
    ser.format.line.color.rgb = col
    ser.format.line.width = Pt(2)
    ser.marker.format.fill.solid()
    ser.marker.format.fill.fore_color.rgb = col
    ser.marker.format.line.color.rgb = col
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = BORDER
ch.value_axis.tick_labels.font.size = Pt(10)
ch.category_axis.tick_labels.font.size = Pt(10)
if r20:
    line = f"£20M: {r20['rec_n_hubs']} hubs serve {100 * r20['rec_share_p50']:.0f}% of unmet rapid demand ({r20['rec_share_p50'] * r20['total_unmet_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions per day)."
    if r40:
        line += f" £40M: {r40['rec_n_hubs']} hubs, {100 * r40['rec_share_p50']:.0f}%."
    extra = (
        f" Across {sens['variants']} changed assumptions a median of {100 * sens['same_or_adjacent_median']:.0f}% of hubs stay in the same or an adjacent hex."
        if sens
        else ""
    )
    if "rec_plan" in r20:
        extra = (
            f" Under demand uncertainty the {r20['rec_plan'].upper()} plan has the smallest worst-case regret ({r20['rec_max_regret']:,.0f} sessions per day). Robust core: {r20['rec_core']} of {r20['rec_n_hubs']} hubs."
            + extra
        )
    text(
        s,
        7.4,
        5.15,
        5.5,
        1.9,
        [line, f"One hub serves about {cap:.0f} sessions per day at P(wait) of 15% or less.{extra}"],
        size=12,
    )
footer(s, n)

# 11 transfer
s = new()
title(s, "Do context features explain observed usage? A negative result, on purpose")
imp = tr["importance"][:8][::-1]
cd = CategoryChartData()
cd.categories = [f["label"] for f in imp]
cd.add_series("share of model gain, %", [round(100 * f["gain_share"], 1) for f in imp])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.6), Inches(1.7), Inches(6.3), Inches(4.9), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Share of model gain, %"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
ch.has_legend = False
ch.series[0].format.fill.solid()
ch.series[0].format.fill.fore_color.rgb = INK
ch.plots[0].gap_width = 60
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = BORDER
ch.value_axis.tick_labels.font.size = Pt(10)
ch.category_axis.tick_labels.font.size = Pt(10)
stat(s, 7.2, 1.7, 2.8, f"{tr['r2_random']:.2f}", "R² with random 5-fold CV", TEAL)
stat(s, 10.1, 1.7, 2.8, f"{tr['r2_leave_city_out']:.2f}", "R² when the test city is unseen")
bullets(
    s,
    7.2,
    3.6,
    5.7,
    3.2,
    [
        f"{tr['n_stations']} chargers with open session logs in four cities. LightGBM on OSM context, population and charger power.",
        f"Charger power and the level of each city dominate. Rankings do not transfer reliably (rank correlation {min(rho):.2f} to {max(rho):.2f} by city).",
        "A site-selection model has to be validated in a city it has not seen, against observed usage.",
    ],
    size=12,
)
footer(s, n)

# 12 stack
s = new()
title(s, "Reproducible from a clean clone")
rows = [
    (
        "Spatial",
        "H3, GeoPandas, Shapely, pyproj",
        "Equal-area hex grid and areal interpolation from census units",
    ),
    (
        "Network",
        "OSMnx, igraph",
        "Drive times on a graph of 131,000 nodes in seconds, no routing server",
    ),
    (
        "Statistics and ML",
        "esda, libpysal, LightGBM, scikit-learn",
        "Moran's I, Gi*, spatial cross-validation by default",
    ),
    (
        "Optimisation",
        "SciPy milp and linprog (HiGHS)",
        "Sparse MILP, exact evaluation of plans, every MIP gap recorded",
    ),
    ("Choice and queues", "NumPy", "Erlang C and logit, tested against closed forms"),
    (
        "Delivery",
        "MapLibre GL JS, matplotlib, GitHub Pages",
        "Maps that also work offline, HTML slides, this PPTX",
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
        para.runs[0].font.color.rgb = INK if j < 2 else MUTED
chips = [
    f"{K['n_tests']} tests, CI on Python 3.11 and 3.12",
    "make models maps slides",
    f"{K['n_sources']} data cards with licences",
    "Code MIT, data ODbL, OGL, CC BY",
]
for i, c in enumerate(chips):
    box(s, 0.8 + i * 3.0, 5.9, 2.85, 0.55)
    text(s, 0.9 + i * 3.0, 6.04, 2.65, 0.35, c, size=11, align=PP_ALIGN.CENTER)
footer(s, n)

# 13 limitations
s = new()
title(s, "Limitations, and how this could be proven wrong")
card(
    s,
    0.8,
    1.5,
    5.9,
    5.2,
    "Known limitations",
    "London publishes no charger-level usage. Behaviour comes from other UK cities and fleet trials.\n\nOpen Charge Map covers most sites but not every port. The rest is closed per borough against DfT totals.\n\nChoice coefficients come from the literature, not from estimation. The sensitivity table shows what they move.\n\nGrid constraints stop at the headroom of primary substations.\n\nInterpolation is area-weighted from census units. About 1.4% of residents fall in dropped edge hexes.",
)
card(
    s,
    7.0,
    1.5,
    5.9,
    5.2,
    "The test",
    "DfT and Zapmap publish device counts by borough every quarter. TfL publishes utilisation by charger type.\n\nHubs opened after July 2026 in hexes flagged here should reach above-median utilisation within a year.\n\nIf not, the model card names the priors to revisit first: private-hire fleet size, public share without home charging, choice radius.\n\nPredict, deploy, measure, retrain. That loop is the product. The maps are its interface.",
    fill=PALE,
)
footer(s, n)

# 14 value
s = new()
title(s, "What an operator or investor gets, and what comes next")
gets = [
    (
        "Ranked candidates with intervals",
        "Expected sessions per day with P10 to P90, the share taken from neighbours, substation headroom and drive-time catchment for every hex.",
    ),
    (
        "Capacity, not just location",
        "Ports and power sized from the queue model against a service level, not from a template.",
    ),
    (
        "A robust plan",
        "The hubs every demand scenario agrees on are built first. The rest are phased as utilisation data arrive.",
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
        "Slides with live maps: m-erts.github.io/chargescape-london/slides/",
        "Maps: m-erts.github.io/chargescape-london/maps/",
        "Notebooks 01 to 05: supply audit, demand, choice and queues, siting, transfer test",
        "Reproduce: pip install -e .[all], then make models maps slides",
    ],
    size=16,
    color=WHITE,
)
text(s, 0.8, 6.3, 11.5, 0.5, "Marija Ercegovac, github.com/m-erts", size=13, color=SOFT)

out = ROOT / "reports" / "ChargeScape_London.pptx"
prs.save(out)
print("wrote", out, "slides:", len(prs.slides))
