"""Fill the headline-results table in README.md from reports/tables/key_numbers.json.
Rows are matched by their first cell, so the prose around the table stays hand-written."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def rows() -> dict[str, str]:
    d26 = K["demand_gwh"]["2026"]
    d30 = {t: K["demand_gwh"][f"2030_{t}"]["total_p50"] for t in ("low", "mid", "high")}
    src = K["sites_by_source"]
    out = {
        "Public chargers (DfT, 1 July 2026)": (
            f"{K['chargers_total']:,}, of which {K['chargers_rapid']:,} ({100 * K['rapid_share']:.1f} %) are 50 kW+",
            "DfT EVCI · observed",
        ),
        "Charging sites mapped": (
            f"{K['sites_total']:,} after de-duplicating Open Charge Map ({src.get('ocm', 0):,}), OSM ({src.get('osm', 0):,}) and the 2021 registry ({src.get('ncr', 0):,}) within 50 m; {K['rapid_sites']} rapid sites",
            "Open Charge Map, OpenStreetMap, NCR 2021 · observed",
        ),
        "Public charging demand 2026": (
            f"**{d26['total_p50']:.0f} GWh/yr** P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f}); near-home {d26['res_p50']:.0f}, destination {d26['dest_p50']:.0f}, taxi & private hire {d26['phv_p50']:.0f}",
            "structural model on observed inputs",
        ),
        "Demand 2030 (DFES pathways)": (
            f"{d30['low']:,.0f} / {d30['mid']:,.0f} / {d30['high']:,.0f} GWh/yr (low / mid / high)",
            "model + UKPN DFES 2026",
        ),
        "Implied rapid sessions per charger per day": (
            f"≈{K['rapid_sessions_per_charger_day']:.0f} — consistent with TfL's observed 34 % occupancy of rapid units and 38-minute sessions",
            "cross-check, notebook 02",
        ),
        "Rapid network today": (
            f"{K['rapid_sites']} sites, {K['rapid_ports_calibrated']:,} ports after calibration (median factor ×{K['port_scale_median']:.1f}); median 24 h utilisation {pct(K['util24_median'])}; {K['sites_pwait_gt_50']} sites where P(wait) > 0.5 at the peak hour",
            "choice + queue model",
        ),
    }
    can = K["cannibalisation"]["rows"]
    lo, hi = min(r["cannibalisation_share"] for r in can), max(r["cannibalisation_share"] for r in can)
    out["New hub cannibalisation"] = (
        f"{pct(lo)}–{pct(hi)} of a new hub's sessions are taken from existing sites (hub at the hex with most unmet demand, {K['cannibalisation']['candidate']['borough']}; 50 kW × 2 to 300 kW × 8)",
        "logit with outside option, notebook 03",
    )
    sit = {r["budget_m"]: r for r in K.get("siting", [])}
    r20, r40 = sit.get(20.0), sit.get(40.0)
    if r20:
        cap = K["siting_meta"]["hub_capacity_sessions_day"]
        gap = r20.get("mip_gap")
        opt = f"; solved to a {100 * gap:.1f} % MIP gap" if isinstance(gap, float) and gap == gap else ""
        txt = f"{r20['n_hubs']} hubs serve {pct(r20['coverage_share'])} of unmet or queue-constrained rapid demand ({r20['covered_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions/day){opt}"
        if r40:
            txt += f"; £40M → {r40['n_hubs']} hubs, {pct(r40['coverage_share'])}"
        txt += f". Capacity-bound: ≈{cap:.0f} sessions/day per hub at P(wait) ≤ 15 %; greedy uncapacitated coverage overstates it {r20['greedy_uncapacitated_covered'] / r20['covered_p50']:.1f}×"
        out["New hubs, £20M budget"] = (txt, "MILP, notebook 04")
    s = K.get("sensitivity")
    if s:
        out["Siting sensitivity"] = (
            f"across {s['variants']} changed assumptions a median {pct(s['same_or_adjacent_median'])} of hubs stay in the same or an adjacent hex ({pct(s['same_hex_median'])} in exactly the same hex); unmet demand ranges {s['unmet_range'][0]:,}–{s['unmet_range'][1]:,} sessions/day",
            "9 changed assumptions, notebook 04",
        )
    t = K["transfer"]
    rho = list(t["spearman_by_city"].values())
    out["Context features vs observed utilisation"] = (
        f"{t['n_stations']} chargers in 4 cities: R² {t['r2_random']:.2f} with random 5-fold CV, **{t['r2_leave_city_out']:.2f} leave-city-out**; within-city ranking Spearman {min(rho):.2f} to {max(rho):.2f}",
        "LightGBM, notebook 05 · observed target",
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
