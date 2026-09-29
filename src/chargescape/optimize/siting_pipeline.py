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

import h3
import numpy as np
import pandas as pd

from chargescape.features.grid import neighbours
from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.queueing import erlang_c
from chargescape.optimize.facility import capacitated_mclp, coverage_of, evaluate_plan, greedy_mclp
from chargescape.utils.io import read_gdf, write_df
from chargescape.utils.paths import PROCESSED, TABLES

HUB_PORTS = 4
HUB_KW = 150
HUB_COST_GBP = 4 * 60_000 + 150_000  # 4 × 150 kW units + civils/grid connection (ICCT EU ranges)
SERVICE_MIN = 38.0
RADIUS_MIN = 8.0  # a hub "serves" a hex if it is within 8 minutes' drive
KWH_PER_SESSION = 17.0
TIME_LIMIT = 300.0  # seconds per MILP
MIP_GAP = 0.01  # stop when proven within 1 % of optimal


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


WEIGHTS = {"p10": 0.25, "p50": 0.5, "p90": 0.25}


def _adjacent_core(plans: dict[str, list[str]]) -> set[str]:
    """Hexes of the P50 plan that have a hub in the same or an adjacent hex in every other scenario plan."""
    rings = {
        q: set().union(*(h3.grid_disk(x, 1) for x in hexes)) if hexes else set() for q, hexes in plans.items()
    }
    return {x for x in plans["p50"] if all(x in rings[q] for q in plans if q != "p50")}


def annotate_selection(sel: pd.DataFrame, sweep: pd.DataFrame) -> pd.DataFrame:
    """Flag, for every budget and plan, the hubs in the robust core (a hub in the same or an adjacent hex
    in every other scenario plan; `core_exact` = the same hex) and the recommended plan (smallest maximum
    regret across scenarios)."""
    sel = sel.copy()
    rec = dict(zip(sweep["budget_m"], sweep["best_plan_by_minimax_regret"], strict=True))
    sel["core"], sel["core_exact"], sel["recommended"] = False, False, False
    for b, grp in sel.groupby("budget_m"):
        hexes = {q: set(g.h3) for q, g in grp.groupby("model")}
        rings = {q: set().union(*(h3.grid_disk(x, 1) for x in hs)) for q, hs in hexes.items()}
        for idx, row in grp.iterrows():
            others = [q for q in hexes if q != row.model]
            sel.at[idx, "core"] = all(row.h3 in rings[q] for q in others)
            sel.at[idx, "core_exact"] = all(row.h3 in hexes[q] for q in others)
            sel.at[idx, "recommended"] = row.model == rec.get(b)
    return sel


def run(
    res: int = 8,
    scenario: str = "2026",
    budgets_m: tuple[float, ...] = (5, 10, 20, 40),
    max_candidates: int = 500,
) -> dict:
    """Budget sweep. For every budget: the capacitated MCLP is solved for each demand scenario (P10, P50,
    P90); each plan is then evaluated exactly under every scenario (fixed-plan assignment LP), which gives
    expected coverage and regret per plan, and the robust core — P50 hubs whose hex, or a neighbouring hex,
    is chosen whatever the demand level. (A single two-stage robust MILP is available as
    `facility.robust_capacitated_mclp`; on this instance HiGHS does not close its gap within minutes, so
    the pipeline uses this exact scenario analysis instead.)"""
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
    scen = {q: unmet_demand(service, dem, q) for q in ("p50", "p10", "p90")}
    cand = candidates(feats, unmet=scen["p50"], max_candidates=max_candidates)
    tt, method = travel_time_minutes(feats, cand, name=f"hex_r{res}_to_cand_{scenario}_{max_candidates}")
    tt = np.where(np.isfinite(tt), tt, 1e6)
    cap = hub_capacity_sessions_day()
    capacity = np.full(len(cand), cap)
    cost = cand["cost_gbp"].to_numpy()
    print(
        f"[{time.time() - t0:.0f}s] {len(cand)} candidates, tt via {method}; hub capacity {cap:.0f} sessions/day; unmet P10/P50/P90 {scen['p10'].sum():,.0f}/{scen['p50'].sum():,.0f}/{scen['p90'].sum():,.0f} sessions/day"
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
    sel_frames, cross_rows = [], []
    for b in budgets_m:
        budget = b * 1e6
        plans = {
            q: capacitated_mclp(
                scen[q], tt, RADIUS_MIN, cost, capacity, budget, time_limit=TIME_LIMIT, mip_gap=MIP_GAP
            )
            for q in ("p50", "p10", "p90")
        }
        r = plans["p50"]
        g = greedy_mclp(scen["p50"], tt, RADIUS_MIN, int(budget // HUB_COST_GBP))
        cover = {
            (q, s_): evaluate_plan(plans[q].selected, scen[s_], tt, RADIUS_MIN, capacity)
            for q in plans
            for s_ in scen
        }
        best = {s_: max(cover[(q, s_)] for q in plans) for s_ in scen}
        for q in plans:
            for s_ in scen:
                cross_rows.append(
                    {
                        "budget_m": b,
                        "plan": q,
                        "scenario": s_,
                        "covered": cover[(q, s_)],
                        "unmet_total": float(scen[s_].sum()),
                        "share": cover[(q, s_)] / float(scen[s_].sum()),
                        "regret": best[s_] - cover[(q, s_)],
                    }
                )
        expected = {q: sum(WEIGHTS[s_] * cover[(q, s_)] for s_ in scen) for q in plans}
        max_regret = {q: max(best[s_] - cover[(q, s_)] for s_ in scen) for q in plans}
        hexes = {q: [cand.loc[j, "h3"] for j in plans[q].selected] for q in plans}
        exact_core = set(hexes["p50"]) & set(hexes["p10"]) & set(hexes["p90"])
        near_core = _adjacent_core(hexes)
        row = {
            "budget_m": b,
            "n_hubs": len(r.selected),
            "covered_p50": r.covered_demand,
            "total_unmet_p50": r.total_demand,
            "coverage_share": r.coverage_share,
            "greedy_uncapacitated_covered": coverage_of(scen["p50"], tt, RADIUS_MIN, g),
            "status": r.status,
            "mip_gap": r.gap,
            "mip_gap_p10_plan": plans["p10"].gap,
            "mip_gap_p90_plan": plans["p90"].gap,
            "p50_plan_share_if_p10": cover[("p50", "p10")] / float(scen["p10"].sum()),
            "p50_plan_share_if_p90": cover[("p50", "p90")] / float(scen["p90"].sum()),
            "p50_plan_max_regret": max_regret["p50"],
            "best_plan_by_expected": max(expected, key=expected.get),
            "best_plan_by_minimax_regret": min(max_regret, key=max_regret.get),
            "core_same_hex": len(exact_core),
            "core_same_or_adjacent": len(near_core),
        }
        for q in plans:
            for j in plans[q].selected:
                h = cand.loc[j, "h3"]
                sel_frames.append(
                    {
                        "budget_m": b,
                        "model": q,
                        "h3": h,
                        "borough": cand.loc[j, "borough"],
                        "cost_gbp": cost[j],
                        "sessions_day_assigned": float((scen[q] * plans[q].assignments[:, j]).sum()),
                        "core": bool(q == "p50" and h in near_core),
                        "core_exact": bool(q == "p50" and h in exact_core),
                    }
                )
        results["runs"].append(row)
        print(
            f"[{time.time() - t0:.0f}s] £{b:.0f}M: {len(r.selected)} hubs cover {r.coverage_share:.1%} (gap {r.gap:.2%}); P50 plan under P10/P90: {row['p50_plan_share_if_p10']:.1%}/{row['p50_plan_share_if_p90']:.1%}; max regret {row['p50_plan_max_regret']:.0f}/day; core {row['core_same_hex']} same hex, {row['core_same_or_adjacent']} same-or-adjacent"
        )
    write_df(
        annotate_selection(pd.DataFrame(sel_frames), pd.DataFrame(results["runs"])),
        PROCESSED / f"siting_selected_{scenario}.small.parquet",
    )
    write_df(cand[["h3", "borough", "cost_gbp"]], PROCESSED / f"siting_candidates_{scenario}.small.parquet")
    TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results["runs"]).to_csv(TABLES / f"siting_budget_sweep_{scenario}.csv", index=False)
    pd.DataFrame(cross_rows).to_csv(TABLES / f"siting_scenarios_{scenario}.csv", index=False)
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
