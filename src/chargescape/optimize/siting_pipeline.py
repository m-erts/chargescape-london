"""Candidate generation and hub siting under budget, capacity, grid and demand uncertainty.

Candidates: hex centroids where a hub is physically plausible (parking / fuel / retail POI present,
or major-road vehicle-km above the city median) and the primary substation is not RED; pre-filtered to
the `max_candidates` hexes with the most unmet demand in their 2-ring neighbourhood.
Costs: per-site capex by configuration (4 × 150 kW default) using ICCT EU cost ranges.
Capacity: sessions/day a hub can serve while keeping P(wait) at the peak hour below 15 % (Erlang C).
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from chargescape.features.grid import neighbours
from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.queueing import erlang_c
from chargescape.optimize.facility import capacitated_mclp, coverage_of, greedy_mclp, robust_capacitated_mclp
from chargescape.utils.io import read_gdf, write_df
from chargescape.utils.paths import PROCESSED, TABLES

HUB_PORTS = 4
HUB_KW = 150
HUB_COST_GBP = 4 * 60_000 + 150_000  # 4 × 150 kW units + civils/grid connection (ICCT EU ranges)
SERVICE_MIN = 38.0
RADIUS_MIN = 8.0  # a hub "serves" a hex if it is within 8 minutes' drive
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


def candidates(
    feats: pd.DataFrame, unmet: np.ndarray | None = None, max_candidates: int = 500
) -> pd.DataFrame:
    plausible = (feats[["poi_parking", "poi_fuel", "poi_retail"]].fillna(0).sum(axis=1) > 0) | (
        feats["vkm_major_total"] > feats["vkm_major_total"].median()
    )
    not_red = ~feats["headroom_rag"].astype(str).str.startswith("RED")
    c = feats[plausible & not_red].copy()
    if unmet is not None and len(c) > max_candidates:
        nb = neighbours(feats["h3"].tolist(), k=2)
        idx = {h: i for i, h in enumerate(feats["h3"])}
        local = np.array([unmet[idx[h]] + sum(unmet[idx[n]] for n in nb.get(h, [])) for h in c["h3"]])
        c = c.iloc[np.argsort(-local)[:max_candidates]]
    c = c.copy()
    c["cost_gbp"] = float(HUB_COST_GBP)
    c.loc[c["demand_pct_of_firm"].fillna(0) > 70, "cost_gbp"] *= (
        1.25  # grid-connection uplift on loaded primaries
    )
    return c.reset_index(drop=True)


def unmet_demand(service: pd.DataFrame, scenario_demand: pd.DataFrame, q: str = "p50") -> np.ndarray:
    """Rapid sessions/day per hex that today's network does not serve within the choice radius, plus
    demand facing long expected waits (counted as unmet in proportion to wait/30 min)."""
    d = (
        (scenario_demand[f"dest_kwh_{q}"].fillna(0) + scenario_demand[f"phv_kwh_{q}"].fillna(0)).to_numpy()
        / KWH_PER_SESSION
        / 365.0
    )
    served = service["served_share"].to_numpy()
    wait = np.nan_to_num(service["expected_wait_min"].to_numpy(), nan=0.0, posinf=120.0)
    return d * (1 - served) + d * served * np.clip(wait / 30.0, 0, 1)


def run(
    res: int = 8,
    scenario: str = "2026",
    budgets_m: tuple[float, ...] = (5, 10, 20, 40),
    robust: bool = True,
    max_candidates: int = 500,
) -> dict:
    t0 = time.time()
    feats = read_gdf(PROCESSED / f"hex_features_r{res}.small.parquet")
    dem_all = pd.read_parquet(PROCESSED / f"demand_r{res}.small.parquet")
    dem = dem_all[dem_all.scenario == scenario].set_index("h3").reindex(feats["h3"]).reset_index()
    service = (
        pd.read_parquet(PROCESSED / f"hex_service_{scenario}.small.parquet")
        .set_index("h3")
        .reindex(feats["h3"])
        .reset_index()
    )
    scen = {q: unmet_demand(service, dem, q) for q in ("p10", "p50", "p90")}
    cand = candidates(feats, unmet=scen["p50"], max_candidates=max_candidates)
    tt, method = travel_time_minutes(feats, cand, name=f"hex_r{res}_to_cand_{scenario}_{max_candidates}")
    tt = np.where(np.isfinite(tt), tt, 1e6)
    cap = hub_capacity_sessions_day()
    capacity = np.full(len(cand), cap)
    cost = cand["cost_gbp"].to_numpy()
    print(
        f"[{time.time() - t0:.0f}s] {len(cand)} candidates, tt via {method}; hub capacity {cap:.0f} sessions/day; unmet P50 {scen['p50'].sum():,.0f} sessions/day"
    )
    results = {
        "method": method,
        "scenario": scenario,
        "n_candidates": int(len(cand)),
        "hub_capacity_sessions_day": cap,
        "radius_min": RADIUS_MIN,
        "hub_cost_gbp": HUB_COST_GBP,
        "runs": [],
    }
    sel_frames = []
    for b in budgets_m:
        budget = b * 1e6
        r = capacitated_mclp(scen["p50"], tt, RADIUS_MIN, cost, capacity, budget, time_limit=90, mip_gap=0.01)
        p_equiv = int(budget // HUB_COST_GBP)
        g = greedy_mclp(scen["p50"], tt, RADIUS_MIN, p_equiv)
        greedy_cov = coverage_of(scen["p50"], tt, RADIUS_MIN, g)
        row = {
            "budget_m": b,
            "n_hubs": len(r.selected),
            "covered_p50": r.covered_demand,
            "total_unmet_p50": r.total_demand,
            "coverage_share": r.coverage_share,
            "greedy_uncapacitated_covered": greedy_cov,
            "status": r.status,
        }
        for j in r.selected:
            sel_frames.append(
                {
                    "budget_m": b,
                    "model": "p50",
                    "h3": cand.loc[j, "h3"],
                    "borough": cand.loc[j, "borough"],
                    "cost_gbp": cost[j],
                    "sessions_day_assigned": float((scen["p50"] * r.assignments[:, j]).sum()),
                }
            )
        if robust:
            rr = robust_capacitated_mclp(
                scen, {"p10": 0.25, "p50": 0.5, "p90": 0.25}, tt, RADIUS_MIN, cost, capacity, budget
            )
            row.update(
                {
                    "robust_n_hubs": len(rr.selected),
                    "robust_overlap_with_p50": len(set(rr.selected) & set(r.selected)),
                    "robust_status": rr.status,
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
                        "sessions_day_assigned": float((scen["p50"] * rr.assignments[:, j]).sum()),
                    }
                )
        results["runs"].append(row)
        print(
            f"[{time.time() - t0:.0f}s] budget £{b}M: {len(r.selected)} hubs cover {r.coverage_share:.1%} of unmet P50 ({r.covered_demand:,.0f}/day); greedy {greedy_cov:,.0f}; robust overlap {row.get('robust_overlap_with_p50', '-')}"
        )
    sel = pd.DataFrame(sel_frames)
    write_df(sel, PROCESSED / f"siting_selected_{scenario}.small.parquet")
    write_df(cand[["h3", "borough", "cost_gbp"]], PROCESSED / f"siting_candidates_{scenario}.small.parquet")
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
    ap.add_argument("--max-candidates", type=int, default=500)
    a = ap.parse_args()
    run(a.res, a.scenario, tuple(float(x) for x in a.budgets.split(",")), max_candidates=a.max_candidates)
