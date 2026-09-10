"""Candidate generation and hub siting under budget, capacity, grid and demand uncertainty.

Candidates: hex centroids where a hub is physically plausible (parking / fuel / retail POI present,
or major-road vehicle-km above the city median) and the primary substation is not RED.
Costs: per-site capex by configuration (4 × 150 kW default) using UK/EU cost ranges from ICCT.
Capacity: sessions/day a hub can serve at an acceptable wait level (from Erlang C).
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.queueing import erlang_c
from chargescape.optimize.facility import capacitated_mclp, greedy_mclp, robust_capacitated_mclp
from chargescape.utils.io import read_gdf, write_df
from chargescape.utils.paths import PROCESSED, TABLES

HUB_PORTS = 4
HUB_KW = 150
HUB_COST_GBP = (
    4 * 60_000 + 150_000
)  # 4 × 150 kW units + civils/grid connection (ICCT EU ranges, order of magnitude)
SERVICE_MIN = 38.0
RADIUS_MIN = 8.0  # coverage radius: a hub "serves" a hex if it is within 8 minutes' drive
KWH_PER_SESSION = 17.0


def hub_capacity_sessions_day(
    ports: int = HUB_PORTS,
    service_min: float = SERVICE_MIN,
    max_wait_prob: float = 0.15,
    peak_share: float = 0.09,
) -> float:
    """Largest daily session count such that P(wait) at the peak hour stays below max_wait_prob."""
    mu = 60.0 / service_min
    lo, hi = 0.0, ports * mu / peak_share
    for _ in range(50):
        mid = (lo + hi) / 2
        if erlang_c(mid * peak_share, mu, ports) <= max_wait_prob:
            lo = mid
        else:
            hi = mid
    return lo


def candidates(feats: pd.DataFrame) -> pd.DataFrame:
    plausible = (feats[["poi_parking", "poi_fuel", "poi_retail"]].fillna(0).sum(axis=1) > 0) | (
        feats["vkm_major_total"] > feats["vkm_major_total"].median()
    )
    not_red = ~feats["headroom_rag"].astype(str).str.startswith("RED")
    c = feats[plausible & not_red].copy()
    c["cost_gbp"] = HUB_COST_GBP
    # crude grid-connection uplift where the primary is already loaded > 70% of firm capacity
    c.loc[c["demand_pct_of_firm"].fillna(0) > 70, "cost_gbp"] *= 1.25
    return c.reset_index(drop=True)


def unmet_demand(
    feats: pd.DataFrame, service: pd.DataFrame, scenario_demand: pd.DataFrame, q: str = "p50"
) -> np.ndarray:
    """Rapid sessions/day per hex that today's network does not serve within the choice radius, plus
    demand at sites with heavy queues (treated as unmet)."""
    d = (
        (scenario_demand[f"dest_kwh_{q}"].fillna(0) + scenario_demand[f"phv_kwh_{q}"].fillna(0)).to_numpy()
        / KWH_PER_SESSION
        / 365.0
    )
    unserved = d * (1 - service["served_share"].to_numpy())
    congested = (
        d
        * service["served_share"].to_numpy()
        * np.clip(np.nan_to_num(service["expected_wait_min"].to_numpy(), nan=0.0) / 30.0, 0, 1)
    )
    return unserved + congested


def run(
    res: int = 8, scenario: str = "2026", budgets_m: tuple[float, ...] = (5, 10, 20, 40), robust: bool = True
) -> dict:
    feats = read_gdf(PROCESSED / f"hex_features_r{res}.small.parquet")
    dem_all = pd.read_parquet(PROCESSED / f"demand_r{res}.small.parquet")
    dem = dem_all[dem_all.scenario == scenario].set_index("h3").reindex(feats["h3"]).reset_index()
    service = (
        pd.read_parquet(PROCESSED / f"hex_service_{scenario}.small.parquet")
        .set_index("h3")
        .reindex(feats["h3"])
        .reset_index()
    )
    cand = candidates(feats)
    tt, method = travel_time_minutes(feats, cand, name=f"hex_r{res}_to_cand")
    tt = np.where(np.isfinite(tt), tt, 1e6)
    cap = hub_capacity_sessions_day()
    capacity = np.full(len(cand), cap)
    cost = cand["cost_gbp"].to_numpy()
    scen = {q: unmet_demand(feats, service, dem, q) for q in ("p10", "p50", "p90")}
    results = {
        "method": method,
        "scenario": scenario,
        "n_candidates": int(len(cand)),
        "hub_capacity_sessions_day": cap,
        "runs": [],
    }
    sel_frames = []
    for b in budgets_m:
        budget = b * 1e6
        r = capacitated_mclp(scen["p50"], tt, RADIUS_MIN, cost, capacity, budget)
        p_equiv = int(budget // HUB_COST_GBP)
        g = greedy_mclp(scen["p50"], tt, RADIUS_MIN, p_equiv)
        greedy_cov = (
            float(
                (
                    scen["p50"][:, None]
                    * ((tt[:, g] <= RADIUS_MIN) if g else np.zeros((len(scen["p50"]), 0), bool))
                )
                .any(axis=1)
                .astype(float)
                .__mul__(scen["p50"])
                .sum()
            )
            if g
            else 0.0
        )
        row = {
            "budget_m": b,
            "n_hubs": len(r.selected),
            "covered_p50": r.covered_demand,
            "total_unmet_p50": r.total_demand,
            "coverage_share": r.coverage_share,
            "greedy_covered_uncapacitated": greedy_cov,
            "status": r.status,
        }
        if robust:
            rr = robust_capacitated_mclp(
                scen, {"p10": 0.25, "p50": 0.5, "p90": 0.25}, tt, RADIUS_MIN, cost, capacity, budget
            )
            row.update(
                {
                    "robust_n_hubs": len(rr.selected),
                    "robust_overlap_with_p50": len(set(rr.selected) & set(r.selected)),
                }
            )
            for j in rr.selected:
                sel_frames.append(
                    {
                        "budget_m": b,
                        "model": "robust",
                        "h3": cand.loc[j, "h3"],
                        "borough": cand.loc[j, "borough"],
                        "cost_gbp": cost[j],
                    }
                )
        for j in r.selected:
            served = float((scen["p50"] * r.assignments[:, j]).sum())
            sel_frames.append(
                {
                    "budget_m": b,
                    "model": "p50",
                    "h3": cand.loc[j, "h3"],
                    "borough": cand.loc[j, "borough"],
                    "cost_gbp": cost[j],
                    "sessions_day_assigned": served,
                }
            )
        results["runs"].append(row)
        print(
            f"budget £{b}M: {len(r.selected)} hubs, covers {r.coverage_share:.1%} of unmet P50 demand ({r.covered_demand:,.0f} sessions/day); greedy uncapacitated {greedy_cov:,.0f}"
        )
    sel = pd.DataFrame(sel_frames)
    write_df(sel, PROCESSED / f"siting_selected_{scenario}.small.parquet")
    TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results["runs"]).to_csv(TABLES / f"siting_budget_sweep_{scenario}.csv", index=False)
    (TABLES / f"siting_meta_{scenario}.json").write_text(
        json.dumps({k: v for k, v in results.items() if k != "runs"}, indent=2)
    )
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--scenario", default="2026")
    ap.add_argument("--budgets", default="5,10,20,40")
    a = ap.parse_args()
    run(a.res, a.scenario, tuple(float(x) for x in a.budgets.split(",")))
