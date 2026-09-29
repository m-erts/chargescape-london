"""Fill the headline-results table in README.md from reports/tables/key_numbers.json.
Rows are matched by their first cell, so the prose around the table stays hand-written."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def rows() -> dict[str, str]:
    d26 = K["demand_gwh"]["2026"]
    d30 = {t: K["demand_gwh"][f"2030_{t}"]["total_p50"] for t in ("low", "mid", "high")}
    src = K["sites_by_source"]
    out = {
        "Public chargers (DfT, 1 July 2026)": (
            f"{K['chargers_total']:,}, of which {K['chargers_rapid']:,} ({100 * K['rapid_share']:.1f}%) are 50 kW or more",
            "DfT EVCI, observed",
        ),
        "Charging sites mapped": (
            f"{K['sites_total']:,} after de-duplicating Open Charge Map ({src.get('ocm', 0):,}), OSM ({src.get('osm', 0):,}) and the 2021 registry ({src.get('ncr', 0):,}) within 50 m; {K['rapid_sites']} rapid sites",
            "Open Charge Map, OpenStreetMap, NCR 2021, observed",
        ),
        "Public charging demand 2026": (
            f"**{d26['total_p50']:.0f} GWh/yr** P50 (P10 to P90: {d26['total_p10']:.0f} to {d26['total_p90']:.0f}); near-home {d26['res_p50']:.0f}, destination {d26['dest_p50']:.0f}, taxi and private hire {d26['phv_p50']:.0f}",
            "structural model on observed inputs",
        ),
        "Demand 2030 (DFES pathways)": (
            f"{d30['low']:,.0f} / {d30['mid']:,.0f} / {d30['high']:,.0f} GWh/yr (low / mid / high)",
            "model and UKPN DFES 2026",
        ),
        "Implied rapid sessions per charger per day": (
            f"about {K['rapid_sessions_per_charger_day']:.0f}, consistent with the 34% occupancy of rapid units observed by TfL and 38-minute sessions",
            "cross-check, notebook 02",
        ),
        "Rapid network today": (
            f"{K['rapid_sites']} sites, {K['rapid_ports_calibrated']:,} ports after calibration (median factor {K['port_scale_median']:.1f}); median 24 h utilisation {pct(K['util24_median'])}; {K['sites_pwait_gt_50']} sites where P(wait) is above 0.5 in the peak hour",
            "choice and queue model",
        ),
    }
    can = K["cannibalisation"]["rows"]
    lo, hi = min(r["cannibalisation_share"] for r in can), max(r["cannibalisation_share"] for r in can)
    out["New hub cannibalisation"] = (
        f"{100 * lo:.0f} to {pct(hi)} of the sessions of a new hub are taken from existing sites (hub in the hex with the largest unmet demand, {K['cannibalisation']['candidate']['borough']}; from 50 kW x 2 to 300 kW x 8)",
        "logit with outside option, notebook 03",
    )
    sit = {r["budget_m"]: r for r in K.get("siting", [])}
    r20, r40 = sit.get(20.0), sit.get(40.0)
    ratios = [
        r["greedy_uncapacitated_covered"] / r["covered_p50"]
        for r in K.get("siting", [])
        if r["covered_p50"] > 0
    ]
    if r20:
        cap = K["siting_meta"]["hub_capacity_sessions_day"]
        gap = r20.get("mip_gap")
        opt = ", proven optimal" if isinstance(gap, float) and gap == gap and gap < 0.005 else ""
        txt = f"{r20['n_hubs']} hubs serve {pct(r20['coverage_share'])} of unmet or queue-constrained rapid demand ({r20['covered_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions per day){opt}"
        if r40:
            txt += f"; £40M gives {r40['n_hubs']} hubs, {pct(r40['coverage_share'])}"
        txt += f". One hub serves about {cap:.0f} sessions per day at P(wait) of 15% or less; a greedy estimate without capacity overstates coverage by up to {max(ratios):.1f} times at small budgets"
        out["New hubs, £20M budget"] = (txt, "MILP, notebook 04")
    if r20 and "rec_plan" in r20:
        cons = [r for r in K["siting"] if r["rec_plan"] == "p10"]
        span = (
            f"£{min(r['budget_m'] for r in cons):.0f}M to £{max(r['budget_m'] for r in cons):.0f}M"
            if cons
            else ""
        )
        txt = (
            f"at {span} the plan optimised for pessimistic (P10) demand has the smallest maximum regret ({r20['rec_max_regret']:,.0f} sessions per day at £20M): hubs placed where even low demand is dense fill up under any scenario"
            if cons
            else f"the recommended plan at £20M is the {r20['rec_plan'].upper()} plan"
        )
        if r40:
            txt += f"; at £40M the {r40['rec_plan'].upper()} plan is best. Robust core at £20M: {r20['rec_core']} of {r20['rec_n_hubs']} hubs chosen in the same or an adjacent hex by all three scenario plans"
        out["Planning under demand uncertainty"] = (
            txt,
            "scenario plans and exact cross-evaluation, notebook 04",
        )
    s = K.get("sensitivity")
    if s:
        out["Siting sensitivity"] = (
            f"across {s['variants']} changed assumptions a median of {pct(s['same_or_adjacent_median'])} of hubs stay in the same or an adjacent hex ({pct(s['same_hex_median'])} in exactly the same hex); unmet demand ranges from {s['unmet_range'][0]:,} to {s['unmet_range'][1]:,} sessions per day",
            "9 changed assumptions, notebook 04",
        )
    t = K["transfer"]
    rho = list(t["spearman_by_city"].values())
    out["Context features vs observed utilisation"] = (
        f"{t['n_stations']} chargers in 4 cities: R² {t['r2_random']:.2f} with random 5-fold CV, **{t['r2_leave_city_out']:.2f} with one city held out**; rank correlation within a city from {min(rho):.2f} to {max(rho):.2f}",
        "LightGBM, notebook 05, observed target",
    )
    return out


def main() -> None:
    p = ROOT / "README.md"
    lines = p.read_text().split("\n")
    todo = rows()
    hit = set()
    for i, ln in enumerate(lines):
        for key, (val, status) in todo.items():
            if ln.startswith(f"| {key} |"):
                lines[i] = f"| {key} | {val} | {status} |"
                hit.add(key)
    p.write_text("\n".join(lines))
    missing = set(todo) - hit
    print(f"README: updated {len(hit)} rows" + (f"; not found: {sorted(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
