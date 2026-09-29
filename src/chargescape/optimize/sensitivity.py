"""Sensitivity of the siting result to behavioural and service assumptions.

Every variant re-runs the choice + queue allocation and the capacitated MCLP at one budget on the
*same* candidate set as the base run, so differences come from the assumption alone. Reported per
variant: unmet rapid demand, hubs selected, coverage, exact overlap with the base solution and the
share of hubs that sit in, or next to, a base hub's hex (the degeneracy-tolerant measure: many
near-equivalent hub sets exist when every hub is full).

Run: PYTHONPATH=src python -m chargescape.optimize.sensitivity [--budget 20]
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

import h3
import numpy as np
import pandas as pd

from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.allocation_pipeline import allocate, load_inputs
from chargescape.models.choice import ChoiceParams
from chargescape.optimize.facility import capacitated_mclp
from chargescape.optimize.siting_pipeline import (
    MIP_GAP,
    RADIUS_MIN,
    TIME_LIMIT,
    hub_capacity_sessions_day,
    unmet_demand,
)
from chargescape.utils.paths import PROCESSED, TABLES

VARIANTS: list[tuple[str, dict]] = [
    ("base", {}),
    ("travel-time coefficient −0.15/min (less distance-sensitive)", {"b_tt": -0.15}),
    ("travel-time coefficient −0.40/min (more distance-sensitive)", {"b_tt": -0.40}),
    ("power coefficient 0.3 (power matters less)", {"b_power": 0.3}),
    ("power coefficient 1.0 (power matters more)", {"b_power": 1.0}),
    ("choice set 15 min", {"max_tt_min": 15.0}),
    ("choice set 30 min", {"max_tt_min": 30.0}),
    ("service level P(wait) ≤ 30 %", {"_service": 0.30}),
    ("coverage radius 6 min", {"_radius": 6.0}),
    ("coverage radius 10 min", {"_radius": 10.0}),
]


def _near(selected: list[str], base: set[str]) -> float:
    if not selected:
        return float("nan")
    ring = set().union(*(h3.grid_disk(b, 1) for b in base)) if base else set()
    return float(np.mean([s in ring for s in selected]))


def run(res: int = 8, scenario: str = "2026", budget_m: float = 20.0) -> pd.DataFrame:
    feats, dem, sites, tt_sites, _ = load_inputs(res, scenario)
    cand = pd.read_parquet(PROCESSED / f"siting_candidates_{scenario}.small.parquet")
    cand = cand.merge(feats[["h3", "lat", "lon"]], on="h3", how="left")
    tt_cand, method = travel_time_minutes(feats, cand, name=f"hex_r{res}_to_cand_{scenario}_{len(cand)}")
    tt_cand = np.where(np.isfinite(tt_cand), tt_cand, 1e6)
    cost = cand["cost_gbp"].to_numpy()
    rows, base_sel = [], None
    for label, kw in VARIANTS:
        t0 = time.time()
        service = kw.get("_service", 0.15)
        radius = kw.get("_radius", RADIUS_MIN)
        params = replace(ChoiceParams(), **{k: v for k, v in kw.items() if not k.startswith("_")})
        _, hex_out = allocate(feats, dem, sites, tt_sites, params)
        unmet = unmet_demand(hex_out, dem, "p50")
        cap = hub_capacity_sessions_day(max_wait_prob=service)
        r = capacitated_mclp(
            unmet,
            tt_cand,
            radius,
            cost,
            np.full(len(cand), cap),
            budget_m * 1e6,
            time_limit=TIME_LIMIT,
            mip_gap=MIP_GAP,
        )
        sel = [cand.h3.iloc[j] for j in r.selected]
        if base_sel is None:
            base_sel = set(sel)
        rows.append(
            {
                "variant": label,
                "unmet_sessions_day": float(unmet.sum()),
                "hub_capacity_sessions_day": cap,
                "n_hubs": len(sel),
                "coverage_share": r.coverage_share,
                "same_hex_as_base": len(set(sel) & base_sel) / max(len(sel), 1),
                "same_or_adjacent_hex": _near(sel, base_sel),
                "status": r.status,
                "mip_gap": r.gap,
                "seconds": round(time.time() - t0, 1),
            }
        )
        print(
            f"{label:62s} unmet {unmet.sum():7,.0f}/day  hubs {len(sel):3d}  coverage {r.coverage_share:5.1%}  overlap {rows[-1]['same_hex_as_base']:.0%} / near {rows[-1]['same_or_adjacent_hex']:.0%}"
        )
    out = pd.DataFrame(rows)
    out.attrs["travel_time_method"] = method
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(TABLES / f"sensitivity_{scenario}_budget{int(budget_m)}m.csv", index=False)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--scenario", default="2026")
    ap.add_argument("--budget", type=float, default=20.0)
    a = ap.parse_args()
    run(a.res, a.scenario, a.budget)
