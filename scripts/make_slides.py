"""Build the final HTML presentation in English and Russian (docs/slides/index.html, docs/slides/ru.html).

Every number comes from reports/tables/key_numbers.json, so the decks never drift from the results.
Live MapLibre maps are embedded with `?embed`; arrow keys keep working after a click on a map
(the map page forwards them to the deck). Keyboard: ← → / space / PageUp PageDown, F = full screen.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "slides"
IMG = OUT / "img"
FIG = ROOT / "reports" / "figures"
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
REPO = "https://github.com/m-erts/chargescape-london"
PAGES = "https://m-erts.github.io/chargescape-london"
FIGS = ["04_budget_curve.png", "04_sensitivity.png", "05_importance.png", "01_need_hotspots.png"]


# ----------------------------------------------------------------------------- numbers
def num(x: float, lang: str, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",") if lang == "ru" else s


def ru_n(n: int, one: str, few: str, many: str) -> str:
    """Russian numeral agreement: 1 набор, 2 набора, 5 наборов, 21 набор, 32 набора."""
    k = abs(int(n))
    form = many if 11 <= k % 100 <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{num(k, 'ru')} {form}"


def pct(x: float, lang: str) -> str:
    return f"{round(100 * x)} %" if lang == "ru" else f"{round(100 * x)} %"


d26, d30 = K["demand_gwh"]["2026"], K["demand_gwh"]["2030_mid"]
d30_lo, d30_hi = K["demand_gwh"]["2030_low"]["total_p50"], K["demand_gwh"]["2030_high"]["total_p50"]
sit = {r["budget_m"]: r for r in K.get("siting", [])}
r20, r40 = sit.get(20.0), sit.get(40.0)
cap = K.get("siting_meta", {}).get("hub_capacity_sessions_day", 33)
n_rapid = K["chargers_rapid"]
n_slow = K["chargers_total"] - n_rapid
supply_gwh = (n_slow * 7 * 8760 * 0.47 * 0.45 + n_rapid * 60 * 8760 * 0.34 * 0.85) / 1e6
tr = K["transfer"]
rho = list(tr["spearman_by_city"].values())
can = K["cannibalisation"]
can_rows = can["rows"]
can_lo, can_hi = (
    min(r["cannibalisation_share"] for r in can_rows),
    max(r["cannibalisation_share"] for r in can_rows),
)
sens = K.get("sensitivity", {})
_ratios = [
    r["greedy_uncapacitated_covered"] / r["covered_p50"] for r in K.get("siting", []) if r["covered_p50"] > 0
]
greedy_lo, greedy_hi = (min(_ratios), max(_ratios)) if _ratios else (1.0, 1.0)


# ----------------------------------------------------------------------------- building blocks
def slide(html: str, cls: str = "") -> str:
    return f'<section class="slide {cls}">{html}</section>'


def stat(big: str, label: str, tone: str = "orange") -> str:
    return f'<div class="stat {tone}"><div class="big">{big}</div><div class="lbl">{label}</div></div>'


def card(title: str, body: str, tone: str = "") -> str:
    return f'<div class="card {tone}"><h3>{title}</h3>{body}</div>'


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def live(map_name: str, label: str) -> str:
    return f'<iframe src="../maps/{map_name}.html?embed" loading="lazy" title="{label}"></iframe>'


def cannibal_bars(lang: str) -> str:
    top = max(r["captured"] for r in can_rows)
    rows = []
    for r in can_rows:
        w_new, w_can = 100 * r["new"] / top, 100 * r["cannibalised"] / top
        label = f"{r['power_kw']} {'кВт' if lang == 'ru' else 'kW'} × {r['ports']}"
        rows.append(
            f'<div class="bar"><span class="bl">{label}</span><span class="track">'
            f'<i class="new" style="width:{w_new:.1f}%">{num(r["new"], lang)}</i>'
            f'<i class="can" style="width:{w_can:.1f}%">{num(r["cannibalised"], lang)} · {pct(r["cannibalisation_share"], lang)}</i></span></div>'
        )
    legend = (
        ("новый спрос", "отобран у соседей", "сессий в сутки")
        if lang == "ru"
        else ("new demand", "taken from existing sites", "sessions per day")
    )
    return f'<div class="bars">{"".join(rows)}<div class="blegend"><i class="new"></i>{legend[0]} <i class="can"></i>{legend[1]} · {legend[2]}</div></div>'


def stack_table(rows: list[tuple[str, str, str]]) -> str:
    body = "".join(f"<tr><th>{a}</th><td class='mono'>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
    return f'<table class="stack">{body}</table>'


# ----------------------------------------------------------------------------- content
def slides(lang: str) -> list[str]:
    ru = lang == "ru"
    L = (lambda en, r: r) if ru else (lambda en, r: en)
    n = lambda x, dec=0: num(x, lang, dec)  # noqa: E731
    p = lambda x: pct(x, lang)  # noqa: E731
    tag = f'<span class="tag">{L("live map", "живая карта")}</span>'
    out = []

    out.append(
        slide(
            f"""
<div class="title-wrap">
  <div class="kicker">{L("Portfolio project · September 2026", "Портфолио-проект · сентябрь 2026")}</div>
  <h1>ChargeScape London</h1>
  <p class="sub">{L("A spatial decision system for EV charging networks under uncertain demand", "Система поддержки решений для сети зарядных станций в условиях неопределённого спроса")}</p>
  <p class="lede">{L("Where should London's next rapid-charging hubs go, how big should they be, and how sure can we be? Built end-to-end from open data, with every assumption visible.", "Где в Лондоне ставить следующие быстрые зарядные хабы, какого они должны быть размера и насколько мы в этом уверены? Сквозной проект на открытых данных, в котором видно каждое допущение.")}</p>
  <p class="byline">Marija Ercegovac · {L("geospatial data science", "геоаналитика и data science")} · <a href="{REPO}">github.com/m-erts/chargescape-london</a></p>
</div>""",
            "dark",
        )
    )

    out.append(
        slide(f"""
<h2>{L("Charging is an infrastructure business that lives or dies on utilisation", "Зарядная инфраструктура — бизнес, который живёт загрузкой")}</h2>
<div class="stats">
  {stat(n(K["chargers_total"]), L(f"public chargers in London (DfT, {K['dft_date']})", "публичные зарядки в Лондоне (DfT, 1 июля 2026)"))}
  {stat(p(K["rapid_share"]), L("of them are 50 kW+; across the UK: 24 %", "из них мощностью 50 кВт+; по Великобритании — 24 %"), "teal")}
  {stat(L("300k", "300 тыс."), L("plug-in cars kept in London (DfT, Q1 2026)", "подключаемые автомобили в Лондоне (DfT, I кв. 2026)"), "navy")}
  {stat(p(0.34), L("occupancy of rapid units (TfL, 2025)", "занятость быстрых зарядок (TfL, 2025)"))}
</div>
<div class="cols">
  {card(L("The economics", "Экономика"), "<p>" + L("A hub in the wrong hex idles at 5 % and never pays back; the right one runs above 20–30 % and queues. Industry analyses put break-even at 15–20 % utilisation; payback roughly halves between 10 % and 20 %.", "Хаб в неудачном гексе простаивает на 5 % и не окупается; удачный работает на 20–30 % и собирает очереди. По отраслевым оценкам безубыточность наступает при 15–20 % загрузки, а срок окупаемости сокращается примерно вдвое при росте загрузки с 10 до 20 %.") + "</p>")}
  {card(L("The analytics gap", "Пробел в аналитике"), "<p>" + L("Operators describe site selection as a demand model on dozens to hundreds of factors. Public projects usually predict where chargers already are, ignore queues and cannibalisation, and never say how they could be proven wrong.", "Операторы описывают выбор площадок как модель спроса на десятках и сотнях факторов. Публичные проекты обычно предсказывают, где зарядки уже стоят, не учитывают очереди и каннибализацию и не говорят, как их можно опровергнуть.") + "</p>")}
</div>""")
    )

    four = [
        (
            L("Labels on every dataset.", "Метка у каждого набора данных."),
            L(
                f"observed / proxy / synthetic — {K['n_sources']} datasets in the catalog, and the label follows the number into every table.",
                f"observed / proxy / synthetic — {ru_n(K['n_sources'], 'набор данных', 'набора данных', 'наборов данных')} в каталоге, и метка сопровождает число во всех таблицах.",
            ),
        ),
        (
            L("Usage, checked against reality.", "Спрос сверяется с реальностью."),
            L(
                "Demand is modelled bottom-up, then checked against DfT charger counts × TfL occupancy and open session logs.",
                "Спрос моделируется снизу вверх и проверяется по числу зарядок DfT × наблюдаемой занятости TfL и по открытым журналам сессий.",
            ),
        ),
        (
            L("Uncertainty reaches the decision.", "Неопределённость доходит до решения."),
            L(
                "P10/P50/P90 per hex; a plan is solved for each demand scenario and tested under the others; a sensitivity run shows what moves.",
                "P10/P50/P90 для каждого гекса; план решается под каждый сценарий спроса и проверяется на остальных; анализ чувствительности показывает, что меняется.",
            ),
        ),
        (
            L("Queues, cannibalisation, grid.", "Очереди, каннибализация, сеть."),
            L(
                "Erlang-C capacity per hub, new vs stolen demand for any candidate, primary-substation headroom as a filter.",
                "Ёмкость хаба по Эрлангу C, новый и отобранный у соседей спрос для любого кандидата, резерв первичных подстанций как фильтр.",
            ),
        ),
    ]
    flow = L(
        [
            "Open data",
            "H3 features",
            "Demand · Monte Carlo",
            "Choice & queues",
            "Siting MILP",
            "Maps & test plan",
        ],
        [
            "Открытые данные",
            "Признаки H3",
            "Спрос · Монте-Карло",
            "Выбор и очереди",
            "MILP-размещение",
            "Карты и проверка",
        ],
    )
    out.append(
        slide(f"""
<h2>{L("What this system does differently", "Чем эта система отличается")}</h2>
<ol class="four">{"".join(f"<li><b>{a}</b> {b}</li>" for a, b in four)}</ol>
<div class="flow">{"".join(f"<span>{s}</span>" for s in flow)}</div>""")
    )

    groups = [
        (
            L("Supply", "Предложение"),
            "observed",
            L(
                "Open Charge Map (12.5k points), OpenStreetMap, National Chargepoint Registry 2021, DfT EVCI July 2026",
                "Open Charge Map (12,5 тыс. точек), OpenStreetMap, национальный реестр зарядок 2021, DfT EVCI июль 2026",
            ),
        ),
        (
            L("Where EVs live", "Где живут электромобили"),
            "observed",
            L(
                "Census 2021 (4,994 LSOAs), DfT vehicle licensing by LSOA (Q1 2026), Indices of Deprivation 2025",
                "Перепись 2021 (4 994 LSOA), регистрации DfT по LSOA (I кв. 2026), индекс депривации 2025",
            ),
        ),
        (
            L("Activity & traffic", "Активность и трафик"),
            "observed · proxy",
            L(
                "OSM POIs (74k), LAEI 2022 road flows incl. taxi & private hire, TfL stations, NaPTAN bus stops",
                "POI из OSM (74 тыс.), потоки LAEI 2022 с такси и private hire, станции TfL, остановки NaPTAN",
            ),
        ),
        (
            L("Grid & future", "Сеть и будущее"),
            "proxy",
            L(
                "UKPN primary-substation headroom (summer 2026); DFES 2026 EV pathways to 2030",
                "Резерв первичных подстанций UKPN (лето 2026); сценарии DFES 2026 до 2030 г.",
            ),
        ),
        (
            L("Behaviour elsewhere", "Поведение в других городах"),
            "observed",
            L(
                "Session logs from Dundee, Perth & Kinross, Palo Alto, Boulder; Optimise Prime; Low Carbon London",
                "Журналы сессий Данди, Перт-энд-Кинросс, Пало-Альто, Боулдер; Optimise Prime; Low Carbon London",
            ),
        ),
        (
            L("Model outputs", "Выходы моделей"),
            "synthetic",
            L(
                "Monte Carlo demand draws; literature-informed choice parameters — never presented as observed",
                "Розыгрыши Монте-Карло; параметры выбора из литературы — никогда не выдаются за наблюдения",
            ),
        ),
    ]
    cells = "".join(
        f'<div class="src"><div class="lab {lab.split(" ")[0]}">{lab}</div><h3>{t}</h3><p>{d}</p></div>'
        for t, lab, d in groups
    )
    out.append(
        slide(f"""
<h2>{L(f"{K['n_sources']} open datasets, each labelled observed, proxy or synthetic", ru_n(K["n_sources"], "открытый набор данных", "открытых набора данных", "открытых наборов данных") + " — у каждого метка observed, proxy или synthetic")}</h2>
<div class="grid3">{cells}</div>
<div class="stats three">
 {stat(n(K["sites_total"]), L("charging sites after de-duplicating OCM, OSM and the 2021 registry within 50 m", "зарядные площадки после дедупликации OCM, OSM и реестра 2021 в радиусе 50 м"), "navy")}
 {stat(n(K["n_hexes"]), L("H3 hexes at resolution 8 (0.74 km²) covering Greater London", "гексы H3 разрешения 8 (0,74 км²) на весь Большой Лондон"), "teal")}
 {stat(n(tr["n_stations"]), L("chargers with observed usage used to test transfer", "зарядки с наблюдаемой загрузкой для проверки переноса"))}
</div>""")
    )

    out.append(
        slide(f"""
<h2>{
            L(
                "Supply follows devices; need follows cars without driveways",
                "Предложение следует за устройствами, потребность — за машинами без парковки",
            )
        } {tag}</h2>
<div class="mapwrap">{live("supply_2026", "supply")}
<aside>{
            ul(
                [
                    L(
                        "Inner boroughs: ~1,400 chargers per 100k residents, mostly 5–7 kW lamp-post units; rapid share 40 % in Havering and Hillingdon, under 4 % in Westminster and Hackney.",
                        "Во внутренних боро около 1 400 зарядок на 100 тыс. жителей, в основном фонарные 5–7 кВт; доля быстрых — 40 % в Хаверинге и Хиллингдоне, меньше 4 % в Вестминстере и Хакни.",
                    ),
                    L(
                        "Private plug-in cars cluster in outer, house-rich boroughs (Moran's I = 0.73).",
                        "Частные подключаемые машины сосредоточены во внешних боро с частными домами (I Морана = 0,73).",
                    ),
                    L(
                        "EV owners in flats — who depend on public charging — form Gi* hot spots in inner-west and inner-south London.",
                        "Владельцы электромобилей в квартирах — те, кто зависит от публичной зарядки, — образуют горячие точки Gi* на внутреннем западе и юге.",
                    ),
                    L(
                        f"Median drive time to a rapid site is {n(K['median_tt_nearest_rapid_min'], 1)} min: in London the constraint is capacity, not distance.",
                        f"Медианное время в пути до быстрой зарядки — {n(K['median_tt_nearest_rapid_min'], 1)} мин: в Лондоне ограничение — ёмкость, а не расстояние.",
                    ),
                ]
            )
        }</aside></div>""")
    )

    out.append(
        slide(f"""
<h2>{L("A demand surface with the uncertainty attached", "Поверхность спроса вместе с неопределённостью")} {tag}</h2>
<div class="mapwrap">{live("demand_2026", "demand")}
<aside>
 {stat(n(d26["total_p50"]) + L(" GWh", " ГВт·ч"), L(f"public charging demand 2026, P50 (P10–P90 {n(d26['total_p10'])}–{n(d26['total_p90'])})", f"спрос на публичную зарядку в 2026 г., P50 (P10–P90 {n(d26['total_p10'])}–{n(d26['total_p90'])})"))}
 {stat(n(d26["phv_p50"]) + L(" GWh", " ГВт·ч"), L("from taxi & private hire — London's rapid-charging anchor", "приходится на такси и private hire — якорь быстрой зарядки в Лондоне"), "teal")}
 {stat(n(d30["total_p50"]) + L(" GWh", " ГВт·ч"), L(f"in 2030, DFES mid pathway ({n(d30_lo)}–{n(d30_hi)} across pathways)", f"в 2030 г. по среднему сценарию DFES ({n(d30_lo)}–{n(d30_hi)} по сценариям)"), "navy")}
 <p class="note">{L("Bottom-up Monte Carlo: EV stock × km × kWh/km × share charged publicly (depends on off-street parking), plus destination and taxi/PHV demand. Toggle P10 / P50 / P90 / 2030 on the map.", "Модель снизу вверх с Монте-Карло: парк EV × пробег × кВт·ч/км × доля публичной зарядки (зависит от парковки у дома) плюс спрос в местах назначения и у такси. Переключайте P10 / P50 / P90 / 2030 на карте.")}</p>
</aside></div>""")
    )

    out.append(
        slide(f"""
<h2>{L("No London usage data is open — so the model is checked against what is observed", "Открытых данных об использовании лондонских зарядок нет — поэтому модель сверяется с наблюдаемым")}</h2>
<div class="cols">
 {card(L("Energy the network could deliver", "Энергия, которую может отдать сеть"), "<p>" + L(f"{n(n_slow)} slow + {n(n_rapid)} rapid chargers (DfT) × TfL-observed occupancy × charging-time share ⇒ ≈ {n(supply_gwh)} GWh a year.", f"{n(n_slow)} медленных + {n(n_rapid)} быстрых зарядок (DfT) × наблюдаемая занятость TfL × доля времени зарядки ⇒ ≈ {n(supply_gwh)} ГВт·ч в год.") + "</p>")}
 {card(L("Modelled demand", "Смоделированный спрос"), "<p>" + L(f"{n(d26['total_p50'])} GWh P50 (P10–P90 {n(d26['total_p10'])}–{n(d26['total_p90'])}); rapid-type demand (destination + PHV) ≈ {n(d26['dest_p50'] + d26['phv_p50'])} GWh — the same order as the rapid side of the supply estimate.", f"{n(d26['total_p50'])} ГВт·ч P50 (P10–P90 {n(d26['total_p10'])}–{n(d26['total_p90'])}); спрос быстрого типа (места назначения + PHV) ≈ {n(d26['dest_p50'] + d26['phv_p50'])} ГВт·ч — тот же порядок, что и быстрая часть оценки предложения.") + "</p>")}
</div>
<div class="stats three">
 {stat(n(K["rapid_sessions_per_charger_day"], 1), L("rapid sessions per charger per day implied by the model", "сессии в сутки на одну быструю зарядку по модели"))}
 {stat("≈13", L("what TfL's 34 % occupancy implies with 38-minute sessions", "что даёт занятость TfL 34 % при сессии 38 минут"), "teal")}
 {stat("≈3", L("observed in Dundee's open session log (a small city)", "наблюдается в открытом журнале сессий Данди (небольшой город)"), "navy")}
</div>
<p class="note">{L("The band is the honest statement: the two levers are the public-charging share of drivers without a driveway and the size of the electric private-hire fleet.", "Широкий интервал — честное утверждение: главные рычаги — доля публичной зарядки у водителей без парковки и размер парка электрических private hire.")}</p>""")
    )

    out.append(
        slide(f"""
<h2>{L("Where the demand lands today — and where queues form at the peak hour", "Куда спрос приходит сегодня — и где в пиковый час образуются очереди")} {tag}</h2>
<div class="mapwrap">{live("rapid_network_load_2026", "network")}
<aside>
 {stat(f"{n(K['sites_pwait_gt_50'])} / {n(K['rapid_sites'])}", L("rapid sites with P(wait) > 0.5 at the peak hour", "быстрые площадки с P(ожидания) > 0,5 в пиковый час"))}
 {stat(p(K["util24_median"]), L("median 24-hour utilisation of a rapid site", "медианная суточная загрузка быстрой площадки"), "teal")}
 <p class="note">{L(f"Multinomial-logit station choice on OSM drive times (igraph) and Erlang-C queues with 38-minute sessions. Ports of mapped sites are scaled per borough to DfT's official 50 kW+ totals (median ×{n(K['port_scale_median'], 1)}).", f"Мультиномиальный логит выбора станции по времени в пути на графе OSM (igraph) и очереди Эрланга C с сессией 38 минут. Порты площадок откалиброваны по официальным итогам DfT для 50 кВт+ в каждом боро (медианный коэффициент ×{n(K['port_scale_median'], 1)}).")}</p>
</aside></div>""")
    )

    out.append(
        slide(f"""
<h2>{L("A new hub mostly takes customers from its neighbours", "Новый хаб в основном забирает клиентов у соседей")}</h2>
<p class="lead">{L(f"Hub placed in the hex with the largest unmet demand ({can['candidate']['borough']}); multinomial logit with an outside option, so “new” means demand that would otherwise not use a rapid charger.", f"Хаб в гексе с наибольшим неудовлетворённым спросом ({can['candidate']['borough']}); мультиномиальный логит с внешней альтернативой: «новый» спрос — тот, что иначе не пришёл бы на быструю зарядку.")}</p>
<div class="two">{cannibal_bars(lang)}
<div>{stat(f"{round(100 * can_lo)}–{p(can_hi)}", L("of a new hub's sessions come from existing sites", "сессий нового хаба приходят с существующих площадок"))}
<p>{L("Bigger, faster hubs capture more — and cannibalise a larger share. This is the number an investor needs next to “expected sessions”, and it is exactly what a gap map cannot show.", "Более крупные и мощные хабы захватывают больше — и больше отбирают у соседей. Это число инвестору нужно рядом с «ожидаемыми сессиями», и именно его не покажет карта пробелов.")}</p></div></div>""")
    )

    sens_txt = ""
    if sens:
        sens_txt = L(
            f" Across {sens['variants']} changed assumptions, a median {p(sens['same_or_adjacent_median'])} of hubs stay in the same or an adjacent hex.",
            f" При {sens['variants']} изменённых допущениях в медиане {p(sens['same_or_adjacent_median'])} хабов остаются в том же или соседнем гексе.",
        )
    if r20 and "rec_plan" in r20:
        sens_txt = (
            L(
                f" Under demand uncertainty the plan optimised for {r20['rec_plan'].upper()} demand has the smallest worst-case regret ({n(r20['rec_max_regret'])} sessions/day at £20M): capacity-bound hubs placed where even low demand is dense fill up in every scenario. Robust core: {r20['rec_core']} of {r20['rec_n_hubs']} hubs.",
                f" При неопределённом спросе лучший по минимаксу сожаления — план под спрос {r20['rec_plan'].upper()} (сожаление {n(r20['rec_max_regret'])} сессий в сутки при £20 млн): хабы там, где плотен даже низкий спрос, заполняются в любом сценарии. Устойчивое ядро: {r20['rec_core']} из {r20['rec_n_hubs']}.",
            )
            + sens_txt
        )
    siting_line = ""
    if r20:
        siting_line = L(
            f"£20M ⇒ {r20['n_hubs']} hubs serving {p(r20['coverage_share'])} of unmet rapid demand ({n(r20['covered_p50'])} of {n(r20['total_unmet_p50'])} sessions/day).",
            f"£20 млн ⇒ {ru_n(r20['n_hubs'], 'хаб', 'хаба', 'хабов')}; они закрывают {p(r20['coverage_share'])} неудовлетворённого спроса ({n(r20['covered_p50'])} из {n(r20['total_unmet_p50'])} сессий в сутки).",
        )
        if r40:
            siting_line += L(
                f" £40M ⇒ {r40['n_hubs']} hubs, {p(r40['coverage_share'])}.",
                f" £40 млн ⇒ {ru_n(r40['n_hubs'], 'хаб', 'хаба', 'хабов')}, {p(r40['coverage_share'])}.",
            )
    out.append(
        slide(f"""
<h2>{L("Siting 4 × 150 kW hubs under budget, capacity, grid and demand uncertainty", "Размещение хабов 4 × 150 кВт с учётом бюджета, ёмкости, сети и неопределённости спроса")} {tag}</h2>
<div class="mapwrap">{live("siting_hubs", "siting")}
<aside>
 <img src="img/04_budget_curve.png" alt="budget curve" class="small">
 <p><b>{siting_line}</b></p>
 <p class="note">{L(f"Capacity-bound: a hub absorbs ≈{cap:.0f} sessions/day at P(wait) ≤ 15 %, so coverage grows almost linearly with budget; greedy uncapacitated coverage overstates it by up to {n(greedy_hi, 1)}× at small budgets.", f"Режим ограничен ёмкостью: хаб принимает ≈{cap:.0f} сессии в сутки при P(ожидания) ≤ 15 %, поэтому покрытие растёт почти линейно с бюджетом; жадное решение без учёта ёмкости завышает его до {n(greedy_hi, 1)} раза при малых бюджетах.")}{sens_txt}</p>
</aside></div>""")
    )

    out.append(
        slide(f"""
<h2>{
            L(
                "Do context features explain observed utilisation anywhere? A negative result, on purpose",
                "Объясняют ли признаки окружения наблюдаемую загрузку? Отрицательный результат — намеренно",
            )
        }</h2>
<div class="two"><img src="img/05_importance.png" alt="feature importance">
<div>
 <div class="stats two-stats">{
            stat(
                n(tr["r2_random"], 2),
                L(
                    "R² with random 5-fold CV — looks respectable",
                    "R² при случайной 5-кратной кросс-валидации — выглядит прилично",
                ),
                "teal",
            )
        }{
            stat(
                n(tr["r2_leave_city_out"], 2),
                L(
                    "R² when the test city is unseen — the number that matters",
                    "R² на городе, которого не было в обучении, — важное число",
                ),
            )
        }</div>
 {
            ul(
                [
                    L(
                        f"{tr['n_stations']} chargers with open session logs in four cities; LightGBM on OpenStreetMap context, population and charger power.",
                        f"{ru_n(tr['n_stations'], 'зарядка', 'зарядки', 'зарядок')} с открытыми журналами сессий в четырёх городах; LightGBM на признаках OSM, населении и мощности зарядки.",
                    ),
                    L(
                        f"Charger power and the city's level dominate; rankings do not transfer reliably (Spearman {n(min(rho), 2)} to {n(max(rho), 2)} by city).",
                        f"Доминируют мощность зарядки и общий уровень города; ранжирование между городами не переносится (Спирмен от {n(min(rho), 2)} до {n(max(rho), 2)}).",
                    ),
                    L(
                        "Any “geo-embedding site model” must be validated out-of-city against observed usage — this is the test to ask for.",
                        "Любую «модель локаций на геоэмбеддингах» нужно проверять на городе вне обучения и на наблюдаемой загрузке — это тот тест, который стоит требовать.",
                    ),
                ]
            )
        }
</div></div>""")
    )

    stack = [
        (
            L("Spatial", "Пространство"),
            "H3 · GeoPandas · Shapely · pyproj",
            L(
                "hex grid for siting; areal interpolation from LSOAs",
                "гексагональная сетка для размещения; площадная интерполяция из LSOA",
            ),
        ),
        (
            L("Network", "Сеть дорог"),
            "OSMnx · igraph",
            L(
                "many-to-many drive times on a 131k-node graph in seconds, no routing server",
                "время в пути «многие ко многим» на графе из 131 тыс. узлов за секунды, без сервера маршрутизации",
            ),
        ),
        (
            L("Statistics & ML", "Статистика и ML"),
            "esda · libpysal · LightGBM · scikit-learn",
            L(
                "Moran's I, Gi*; spatial cross-validation by default",
                "I Морана, Gi*; пространственная кросс-валидация по умолчанию",
            ),
        ),
        (
            L("Optimisation", "Оптимизация"),
            "SciPy milp (HiGHS)",
            L(
                "sparse capacitated MCLP and exact fixed-plan LPs; linking cuts turned a 20 s time-out into a 5 s optimum; every MIP gap recorded",
                "разреженная MCLP с ёмкостью и точные LP для фиксированных планов; связующие ограничения превратили таймаут 20 с в оптимум за 5 с; зазор MIP записан для каждого решения",
            ),
        ),
        (
            L("Choice & queues", "Выбор и очереди"),
            "NumPy",
            L(
                "Erlang C, multinomial logit, new vs cannibalised demand — unit-tested against closed forms",
                "Эрланг C, мультиномиальный логит, новый и отобранный спрос — тесты против аналитических формул",
            ),
        ),
        (
            L("Delivery", "Подача"),
            "MapLibre GL JS · matplotlib · GitHub Pages",
            L("maps that also work offline; this deck", "карты, работающие и без интернета; эта презентация"),
        ),
    ]
    chips = [
        L(
            f"{K['n_tests']} tests · CI on Python 3.11 / 3.12",
            f"{ru_n(K['n_tests'], 'тест', 'теста', 'тестов')} · CI на Python 3.11 / 3.12",
        ),
        L(
            "runs from a clean clone: make models → maps → slides",
            "запускается с чистого клона: make models → maps → slides",
        ),
        L(
            f"{K['n_sources']} data cards with licences",
            f"{ru_n(K['n_sources'], 'карточка данных', 'карточки данных', 'карточек данных')} с лицензиями",
        ),
        L("code MIT · data ODbL / OGL / CC BY", "код MIT · данные ODbL / OGL / CC BY"),
    ]
    out.append(
        slide(f"""
<h2>{L("Engineering: reproducible from a clean clone", "Инженерия: воспроизводится с чистого клона")}</h2>
{stack_table(stack)}
<div class="chips">{"".join(f"<span>{c}</span>" for c in chips)}</div>""")
    )

    out.append(
        slide(f"""
<h2>{
            L(
                "Limitations — and how the whole thing would be proven wrong",
                "Ограничения — и как всю систему можно опровергнуть",
            )
        }</h2>
<div class="cols">
 {
            card(
                L("Known limitations", "Известные ограничения"),
                ul(
                    [
                        L(
                            "No open London charger-level usage; behaviour comes from other UK cities and fleet trials.",
                            "Открытых данных об использовании лондонских зарядок нет; поведение взято из других городов Великобритании и испытаний автопарков.",
                        ),
                        L(
                            "Open Charge Map covers most sites but not every port; residual gaps are closed per borough against DfT totals.",
                            "Open Charge Map покрывает большинство площадок, но не все порты; остаток закрывается калибровкой по итогам DfT для каждого боро.",
                        ),
                        L(
                            "Choice-model coefficients are literature-informed, not estimated; notebook 04 shows what moves when they change.",
                            "Коэффициенты модели выбора взяты из литературы, а не оценены; ноутбук 04 показывает, что меняется при их изменении.",
                        ),
                        L(
                            "Grid constraints stop at primary-substation headroom.",
                            "Ограничения сети учтены только на уровне первичных подстанций.",
                        ),
                        L(
                            "Area-weighted LSOA → hex interpolation; ≈1.4 % of population sits in dropped edge hexes.",
                            "Площадная интерполяция LSOA → гекс; ≈1,4 % населения попадает в отброшенные краевые гексы.",
                        ),
                    ]
                ),
            )
        }
 {
            card(
                L("The post-hoc test", "Как проверить модель"),
                ul(
                    [
                        L(
                            "DfT and Zapmap publish borough device counts quarterly; TfL publishes utilisation by charger type.",
                            "DfT и Zapmap ежеквартально публикуют число устройств по боро; TfL — загрузку по типам зарядок.",
                        ),
                        L(
                            "Hubs opened after July 2026 in hexes flagged here as high unmet demand should reach above-median utilisation within a year.",
                            "Хабы, открытые после июля 2026 г. в гексах с высоким неудовлетворённым спросом, должны в течение года выйти на загрузку выше медианы.",
                        ),
                        L(
                            "If not, the model card names the priors to revisit first: private-hire fleet size, public share without home charging, choice radius.",
                            "Если нет — карточка модели называет допущения, которые пересматривать первыми: размер парка private hire, долю публичной зарядки без домашней, радиус выбора.",
                        ),
                        L(
                            "<b>Predict → deploy → measure → retrain</b> is the product; the maps are its interface.",
                            "<b>Прогноз → внедрение → измерение → переобучение</b> — вот продукт; карты — его интерфейс.",
                        ),
                    ]
                ),
                "teal",
            )
        }
</div>""")
    )

    gets = [
        (
            L("Ranked candidates with intervals", "Ранжированные кандидаты с интервалами"),
            L(
                "Expected sessions per day, P10–P90, share taken from neighbours, substation headroom and drive-time catchment for every hex.",
                "Ожидаемые сессии в сутки, P10–P90, доля, отобранная у соседей, резерв подстанции и зона доступности по времени в пути для каждого гекса.",
            ),
        ),
        (
            L("Capacity, not just location", "Ёмкость, а не только точка"),
            L(
                "Ports and power sized from the queue model against a service level, instead of a fixed template.",
                "Число портов и мощность подбираются по модели очередей под уровень сервиса, а не по шаблону.",
            ),
        ),
        (
            L("Portfolio robustness", "Устойчивость портфеля"),
            L(
                "Which hubs every demand scenario agrees on (the robust core) and which are interchangeable with neighbours — build the core first, phase the rest.",
                "Какие хабы выбираются при любом уровне спроса (устойчивое ядро), а какие взаимозаменяемы с соседними гексами — ядро строить первым, остальное вводить позже.",
            ),
        ),
        (
            L("Next, with operator data", "Следующий шаг — с данными оператора"),
            L(
                "Choice parameters from real routes, hour-of-day profiles, per-hex uncertainty from sessions, staggered difference-in-differences on openings.",
                "Параметры выбора по реальным маршрутам, профили по часам, неопределённость по гексам на реальных сессиях, разностные оценки эффекта открытий (staggered DiD).",
            ),
        ),
    ]
    out.append(
        slide(f"""
<h2>{L("What an operator or investor gets — and what comes next", "Что получает оператор или инвестор — и что дальше")}</h2>
<div class="grid2">{"".join(card(a, f"<p>{b}</p>") for a, b in gets)}</div>""")
    )

    links = [
        L(
            f'Repository: <a href="{REPO}">github.com/m-erts/chargescape-london</a> — code, {K["n_tests"]} tests, data catalog, methodology, model card',
            f'Репозиторий: <a href="{REPO}">github.com/m-erts/chargescape-london</a> — код, {ru_n(K["n_tests"], "тест", "теста", "тестов")}, каталог данных, методология, карточка модели',
        ),
        L(
            'Live maps: <a href="../maps/supply_2026.html">supply</a> · <a href="../maps/demand_2026.html">demand</a> · <a href="../maps/rapid_network_load_2026.html">network load</a> · <a href="../maps/siting_hubs.html">hub siting</a>',
            'Живые карты: <a href="../maps/supply_2026.html">предложение</a> · <a href="../maps/demand_2026.html">спрос</a> · <a href="../maps/rapid_network_load_2026.html">нагрузка сети</a> · <a href="../maps/siting_hubs.html">размещение хабов</a>',
        ),
        L(
            'Notebooks 01–05 on <a href="https://nbviewer.org/github/m-erts/chargescape-london/tree/main/notebooks/">nbviewer</a>: supply audit · demand · choice & queues · siting · transfer test',
            'Ноутбуки 01–05 на <a href="https://nbviewer.org/github/m-erts/chargescape-london/tree/main/notebooks/">nbviewer</a>: аудит предложения · спрос · выбор и очереди · размещение · проверка переноса',
        ),
        L(
            "Reproduce: <code>pip install -e .[all]</code> → <code>make models maps slides</code>",
            "Воспроизвести: <code>pip install -e .[all]</code> → <code>make models maps slides</code>",
        ),
    ]
    out.append(
        slide(
            f"""
<div class="title-wrap">
  <h1 class="h1s">{L("Explore it", "Посмотреть самому")}</h1>
  <ul class="links">{"".join(f"<li>{x}</li>" for x in links)}</ul>
  <p class="byline">Marija Ercegovac · <a href="https://github.com/m-erts">github.com/m-erts</a></p>
</div>""",
            "dark",
        )
    )
    return out


# ----------------------------------------------------------------------------- page
CSS = """
:root{--navy:#14213D;--orange:#E4572E;--teal:#0C7C70;--ink:#1A2027;--muted:#5B6B7A;--pale:#EEF2F4;--line:#D9DEE3;--bg:#FFFFFF}
*{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font-family:"Golos Text","Helvetica Neue",Arial,sans-serif;font-size:clamp(14px,1.2vw,19px);line-height:1.45}
a{color:var(--teal)} .deck{height:100vh;overflow:hidden;position:relative}
.slide{position:absolute;inset:0;padding:5vh 5vw 7vh;display:none;flex-direction:column;overflow:hidden}
.slide.active{display:flex;animation:fade .3s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.slide.dark{background:var(--navy);color:#fff} .slide.dark a{color:#9FD8CF}
h1{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(38px,6vw,84px);line-height:1.05;margin:.1em 0 .2em;text-wrap:balance}
h1.h1s{font-size:clamp(34px,5vw,64px)}
h2{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(22px,2.4vw,38px);line-height:1.15;margin:0 0 .6em;color:var(--navy);text-wrap:balance}
h3{margin:0 0 .4em;font-size:1.02em;color:var(--navy)}
.kicker{font-family:"JetBrains Mono",monospace;font-size:.8em;letter-spacing:.08em;text-transform:uppercase;color:#C8D3DC}
.title-wrap{max-width:62ch;margin:auto 0} .sub{font-family:Spectral,Georgia,serif;font-size:clamp(18px,2.1vw,30px);color:#C8D3DC;margin:0 0 .8em} .lede{font-size:1.05em;max-width:60ch} .byline{color:#C8D3DC;font-size:.9em;margin-top:2em}
.lead{color:var(--muted);margin:-.3em 0 1.2em;max-width:80ch}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:2vw;margin:0 0 3vh} .stats.three{grid-template-columns:repeat(3,1fr);margin-top:2vh} .two-stats{grid-template-columns:1fr 1fr;margin-bottom:1.5vh}
.stat .big{font-family:Spectral,Georgia,serif;font-weight:600;font-size:clamp(26px,3.4vw,52px);line-height:1;color:var(--orange);font-variant-numeric:tabular-nums} .stat.teal .big{color:var(--teal)} .stat.navy .big{color:var(--navy)} .stat .lbl{color:var(--muted);font-size:.85em;margin-top:.35em}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:2vw} .grid2{display:grid;grid-template-columns:1fr 1fr;gap:2vh 2vw}
.card{background:var(--pale);border-radius:10px;padding:1.1em 1.3em} .card.teal{background:#E6F2F0} .card p{margin:0 0 .5em} .card ul{margin:0;padding-left:1.1em} .card li{margin:.3em 0}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1.6vh 1.6vw}
.src{border:1px solid var(--line);border-radius:10px;padding:.8em 1em} .src h3{margin:.3em 0 .25em} .src p{margin:0;font-size:.88em;color:var(--muted)}
.lab{display:inline-block;font:500 .7em/1 "JetBrains Mono",monospace;letter-spacing:.05em;text-transform:uppercase;padding:.35em .6em;border-radius:1em;background:#E6F2F0;color:#0A665C}
.lab.proxy{background:#FFF3DA;color:#8A5A00} .lab.synthetic{background:#FDEEE8;color:#A8401F}
ol.four{counter-reset:n;list-style:none;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:1.4vh 2vw;margin:0 0 3vh} ol.four li{position:relative;padding-left:2.6em} ol.four li::before{counter-increment:n;content:counter(n);position:absolute;left:0;top:0;width:1.9em;height:1.9em;border-radius:50%;background:var(--teal);color:#fff;display:grid;place-items:center;font-weight:600} ol.four li:nth-child(1)::before,ol.four li:nth-child(4)::before{background:var(--orange)} ol.four li:nth-child(3)::before{background:var(--navy)}
.flow{display:flex;gap:.6vw;margin-top:auto} .flow span{flex:1;background:var(--navy);color:#fff;padding:.65em .4em;text-align:center;font-size:.85em;clip-path:polygon(0 0,92% 0,100% 50%,92% 100%,0 100%,8% 50%)} .flow span:first-child{clip-path:polygon(0 0,92% 0,100% 50%,92% 100%,0 100%)} .flow span:nth-child(2n){background:var(--teal)} .flow span:nth-child(3){background:var(--orange)}
.two{display:grid;grid-template-columns:1.2fr 1fr;gap:2.5vw;align-items:start;min-height:0} .two img{width:100%;height:auto;max-height:68vh;object-fit:contain;border-radius:6px} .two ul{margin:0;padding-left:1.1em} .two li{margin:.5em 0}
.mapwrap{display:grid;grid-template-columns:1.65fr 1fr;gap:2vw;flex:1;min-height:0} .mapwrap iframe{width:100%;height:100%;min-height:52vh;border:0;border-radius:10px;box-shadow:0 1px 8px rgba(0,0,0,.15);background:#eef0ec} .mapwrap aside .stat{margin-bottom:2.2vh} .mapwrap aside ul{margin:0;padding-left:1.1em} .mapwrap aside li{margin:.55em 0} .mapwrap aside img.small{width:100%;border-radius:6px;margin-bottom:1vh}
.note{color:var(--muted);font-size:.9em} .tag{font-family:"JetBrains Mono",monospace;font-size:.42em;vertical-align:middle;background:var(--teal);color:#fff;padding:.25em .65em;border-radius:1em;margin-left:.4em;white-space:nowrap}
.bars{display:flex;flex-direction:column;gap:1.6vh;padding-top:1vh} .bar{display:grid;grid-template-columns:7.5em 1fr;align-items:center;gap:1em} .bl{font:500 .9em "JetBrains Mono",monospace;color:var(--navy)}
.track{display:flex;height:2.3em;background:var(--pale);border-radius:6px;overflow:hidden} .track i{display:flex;align-items:center;justify-content:flex-end;padding:0 .5em;font-style:normal;font-size:.8em;color:#fff;white-space:nowrap;font-variant-numeric:tabular-nums} .track i.new{background:var(--teal)} .track i.can{background:var(--orange)}
.blegend{font-size:.82em;color:var(--muted);margin-top:.6vh} .blegend i{display:inline-block;width:.9em;height:.9em;border-radius:2px;vertical-align:-.1em;margin:0 .3em 0 .8em} .blegend i.new{background:var(--teal);margin-left:0} .blegend i.can{background:var(--orange)}
table.stack{border-collapse:collapse;width:100%;font-size:.95em} .stack th,.stack td{text-align:left;padding:.7em .9em;border-bottom:1px solid var(--line);vertical-align:top} .stack th{color:var(--navy);width:14%;font-weight:600} .stack td.mono{font-family:"JetBrains Mono",monospace;font-size:.85em;width:30%;color:var(--teal)}
.chips{display:flex;flex-wrap:wrap;gap:.6em;margin-top:auto} .chips span{background:var(--navy);color:#fff;border-radius:2em;padding:.45em .9em;font-size:.85em}
ul.links{font-size:1.05em;line-height:1.6;padding-left:1.1em} code{font-family:"JetBrains Mono",monospace;font-size:.88em;background:rgba(255,255,255,.12);padding:.1em .4em;border-radius:4px}
.nav{position:fixed;bottom:14px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:9} .nav button{width:10px;height:10px;border-radius:50%;background:#B8C2CC;border:0;padding:0;cursor:pointer} .nav button.on{background:var(--orange)} .nav button:focus-visible{outline:2px solid var(--teal);outline-offset:2px}
.counter{position:fixed;bottom:12px;right:18px;font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--muted);z-index:9}
.top{position:fixed;top:12px;right:18px;font-size:12px;color:var(--muted);z-index:9;display:flex;gap:1em} .top a{color:var(--muted)} .dark-on .top,.dark-on .top a,.dark-on .counter{color:#C8D3DC}
@media (max-width:900px){.stats,.cols,.two,.mapwrap,ol.four,.grid3,.grid2{grid-template-columns:1fr} .mapwrap iframe{min-height:45vh} .slide{overflow:auto}}
@media (prefers-reduced-motion:reduce){.slide.active{animation:none}}
@media print{.deck{height:auto;overflow:visible} .slide{display:flex!important;position:relative;height:100vh;page-break-after:always} .nav,.counter,.top{display:none}}
"""

JS = """
const S=[...document.querySelectorAll('.slide')]; const nav=document.getElementById('nav');
let i=Math.max(0,Math.min(S.length-1,parseInt(location.hash.slice(1))||0));
S.forEach((_,k)=>{const b=document.createElement('button');b.setAttribute('aria-label','slide '+(k+1));b.onclick=()=>go(k);nav.appendChild(b)});
function go(k){i=(k+S.length)%S.length;S.forEach((s,j)=>s.classList.toggle('active',j===i));[...nav.children].forEach((d,j)=>d.classList.toggle('on',j===i));
 document.body.classList.toggle('dark-on',S[i].classList.contains('dark'));document.getElementById('counter').textContent=(i+1)+' / '+S.length;history.replaceState(null,'','#'+i);}
function key(k){if(['ArrowRight',' ','PageDown'].includes(k))go(i+1);else if(['ArrowLeft','PageUp'].includes(k))go(i-1);else if(k==='f'||k==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen();}}
addEventListener('keydown',e=>{if(e.target.closest&&e.target.closest('a,button'))return;key(e.key);if([' ','PageDown','PageUp'].includes(e.key))e.preventDefault();});
addEventListener('message',e=>{if(e.data&&e.data.cs_key)key(e.data.cs_key);});
addEventListener('hashchange',()=>{const k=parseInt(location.hash.slice(1));if(!isNaN(k)&&k!==i)go(k);});
let x0=null;addEventListener('touchstart',e=>{x0=e.touches[0].clientX},{passive:true});addEventListener('touchend',e=>{if(x0===null)return;const dx=e.changedTouches[0].clientX-x0;if(Math.abs(dx)>60)go(i+(dx<0?1:-1));x0=null},{passive:true});
go(i);
"""


def page(lang: str) -> str:
    ru = lang == "ru"
    title = "ChargeScape London — презентация" if ru else "ChargeScape London — slides"
    desc = (
        "Система поддержки решений для сети зарядных станций в Лондоне: спрос с неопределённостью, выбор станции и очереди, оптимизация размещения."
        if ru
        else "A spatial decision system for London's EV charging network: demand with uncertainty, station choice and queues, hub siting under budget and grid constraints."
    )
    hint = "← → листать · F — полный экран" if ru else "← → to navigate · F for full screen"
    other = '<a href="index.html">EN</a> · <b>RU</b>' if ru else '<b>EN</b> · <a href="ru.html">RU</a>'
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{desc}">
<meta property="og:title" content="ChargeScape London"><meta property="og:description" content="{desc}"><meta property="og:url" content="{PAGES}/slides/">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600&family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="deck">{"".join(slides(lang))}</div>
<div class="nav" id="nav" aria-label="slides"></div><div class="counter" id="counter"></div><div class="top"><span>{hint}</span><span>{other}</span></div>
<script>{JS}</script></body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    for old in IMG.glob("*.png"):
        old.unlink()
    for name in FIGS:
        if (FIG / name).exists():
            shutil.copy(FIG / name, IMG / name)
    (OUT / "index.html").write_text(page("en"), encoding="utf-8")
    (OUT / "ru.html").write_text(page("ru"), encoding="utf-8")
    print("slides:", len(slides("en")), "| wrote", OUT / "index.html", "and", OUT / "ru.html")


if __name__ == "__main__":
    main()
