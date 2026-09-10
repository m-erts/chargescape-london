"""Refresh the headline-number rows in README.md from reports/tables/key_numbers.json.
Rows are matched by their first cell so the prose around them stays hand-written."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K = json.loads((ROOT / "reports" / "tables" / "key_numbers.json").read_text())
d26 = K["demand_gwh"]["2026"]
d30 = {k: K["demand_gwh"][f"2030_{k}"]["total_p50"] for k in ("low", "mid", "high")}
sit = {r["budget_m"]: r for r in K.get("siting", [])}
r20, r40 = sit.get(20.0), sit.get(40.0)
cap = K.get("siting_meta", {}).get("hub_capacity_sessions_day", 33)

rows = {
    "| Public charging demand 2026 |": f"| Public charging demand 2026 | **{d26['total_p50']:.0f} GWh/yr** P50 (P10–P90 {d26['total_p10']:.0f}–{d26['total_p90']:.0f}); near-home {d26['res_p50']:.0f}, destination {d26['dest_p50']:.0f}, taxi & PHV {d26['phv_p50']:.0f} | structural model on observed inputs |",
    "| Demand 2030 (DFES pathways) |": f"| Demand 2030 (DFES pathways) | {d30['low']:,.0f} / {d30['mid']:,.0f} / {d30['high']:,.0f} GWh/yr (low / mid / high) | model + UKPN DFES 2026 |",
    "| Implied rapid sessions per charger per day |": f"| Implied rapid sessions per charger per day | ≈{K['rapid_sessions_per_charger_day']:.0f} — consistent with TfL's observed 34 % occupancy of rapid units and 38-min sessions | cross-check, notebook 02 |",
    "| Rapid network today": f"| Rapid network today ({K['rapid_sites']} sites, {K['rapid_ports_calibrated']:,} ports after calibration to DfT borough totals) | median 24 h utilisation {K['util24_median']:.0%}; {K['sites_pwait_gt_50']} sites with P(wait) > 0.5 at the peak hour | choice + queue model |",
}
if r20:
    txt = f"{r20['n_hubs']} hubs serve {r20['coverage_share']:.0%} of unmet/queue-constrained rapid demand ({r20['covered_p50']:,.0f} of {r20['total_unmet_p50']:,.0f} sessions/day)"
    if r40:
        txt += f"; £40M → {r40['n_hubs']} hubs, {r40['coverage_share']:.0%}"
    txt += f". Regime is capacity-bound (≈{cap:.0f} sessions/day per 4×150 kW hub at P(wait) ≤ 15 %); greedy uncapacitated coverage overstates by ~1.5–5×"
    rows["| New hubs, £20M budget |"] = f"| New hubs, £20M budget | {txt} | MILP, notebook 04 |"

p = ROOT / "README.md"
lines = p.read_text().split("\n")
out, hit = [], set()
for ln in lines:
    for key, new in rows.items():
        if ln.startswith(key):
            ln = new
            hit.add(key)
            break
    out.append(ln)
p.write_text("\n".join(out))
print("updated rows:", sorted(hit))
missing = set(rows) - hit
if missing:
    print("NOT FOUND:", missing)
