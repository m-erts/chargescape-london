"""Facility location for charging hubs: capacitated, budget-constrained maximal covering as a
sparse MILP solved with HiGHS through scipy.optimize.milp, a two-stage robust variant over demand
scenarios, and greedy / p-median baselines.

Decision variables
------------------
x_j ∈ {0,1}   open candidate j
y_ij ∈ [0,1]  share of demand of cell i assigned to j (only for feasible pairs t_ij <= radius)
Capacity: Σ_i d_i y_ij <= cap_j x_j ; Budget: Σ_j cost_j x_j <= B ; Coverage: Σ_j y_ij <= 1
Objective: maximise covered demand (optionally minus a small travel-time penalty).
The sparse formulation builds models with ~10^6 variables in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass
class SitingResult:
    selected: list[int]
    covered_demand: float
    total_demand: float
    assignments: np.ndarray  # (n_cells, n_candidates) shares for the base scenario
    objective: float
    status: str

    @property
    def coverage_share(self) -> float:
        return self.covered_demand / self.total_demand if self.total_demand > 0 else 0.0


def _feasible_pairs(tt: np.ndarray, radius_min: float, demand: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    feas = np.isfinite(tt) & (tt <= radius_min) & (demand[:, None] > 0)
    ii, jj = np.nonzero(feas)
    return ii, jj


def capacitated_mclp(
    demand: np.ndarray,
    tt: np.ndarray,
    radius_min: float,
    cost: np.ndarray,
    capacity: np.ndarray,
    budget: float,
    p_max: int | None = None,
    tt_penalty: float = 0.0,
    fixed_open: list[int] | None = None,
    time_limit: float = 300.0,
    mip_gap: float = 0.005,
) -> SitingResult:
    """Capacitated maximal covering with a budget. tt in minutes, shape (cells, candidates)."""
    d = np.asarray(demand, float)
    n, m = tt.shape
    ii, jj = _feasible_pairs(tt, radius_min, d)
    k = len(ii)
    nv = m + k  # x then y
    c = np.zeros(nv)
    c[m:] = -d[ii] * (1 - tt_penalty * tt[ii, jj] / radius_min)
    rows, cols, vals, lb, ub = [], [], [], [], []
    r = 0
    # coverage: Σ_j y_ij <= 1 for each i with pairs
    for i_idx, grp in _group(ii, n):
        rows += [r] * len(grp)
        cols += (m + grp).tolist()
        vals += [1.0] * len(grp)
        lb.append(-np.inf)
        ub.append(1.0)
        r += 1
    # capacity: Σ_i d_i y_ij - cap_j x_j <= 0 for each j
    for j_idx, grp in _group(jj, m):
        rows += [r] * (len(grp) + 1)
        cols += (m + grp).tolist() + [j_idx]
        vals += d[ii[grp]].tolist() + [-float(capacity[j_idx])]
        lb.append(-np.inf)
        ub.append(0.0)
        r += 1
    # budget
    rows += [r] * m
    cols += list(range(m))
    vals += [float(x) for x in cost]
    lb.append(-np.inf)
    ub.append(float(budget))
    r += 1
    if p_max is not None:
        rows += [r] * m
        cols += list(range(m))
        vals += [1.0] * m
        lb.append(-np.inf)
        ub.append(float(p_max))
        r += 1
    A = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    integrality = np.zeros(nv)
    integrality[:m] = 1
    xlb = np.zeros(nv)
    xub = np.ones(nv)
    for j in fixed_open or []:
        xlb[j] = 1
    res = milp(
        c,
        constraints=LinearConstraint(A, lb, ub),
        integrality=integrality,
        bounds=Bounds(xlb, xub),
        options={"time_limit": time_limit, "mip_rel_gap": mip_gap, "disp": False},
    )
    if res.x is None:
        return SitingResult([], 0.0, float(d.sum()), np.zeros((n, m)), 0.0, res.message)
    x = res.x[:m]
    y = res.x[m:]
    sel = [j for j in range(m) if x[j] > 0.5]
    Aasg = np.zeros((n, m))
    Aasg[ii, jj] = y
    covered = float((d[:, None] * Aasg).sum())
    return SitingResult(
        sel, covered, float(d.sum()), Aasg, float(-res.fun), "Optimal" if res.status == 0 else res.message
    )


def robust_capacitated_mclp(
    demand_scenarios: dict[str, np.ndarray],
    scenario_weights: dict[str, float],
    tt: np.ndarray,
    radius_min: float,
    cost: np.ndarray,
    capacity: np.ndarray,
    budget: float,
    worst_case: bool = False,
    time_limit: float = 600.0,
    mip_gap: float = 0.005,
) -> SitingResult:
    """Two-stage scenario model: one set of sites, scenario-specific assignments.
    Maximises the weighted expected coverage, or the worst-case coverage if worst_case=True."""
    names = list(demand_scenarios)
    n, m = tt.shape
    dmax = np.max(np.stack([np.asarray(demand_scenarios[s], float) for s in names]), axis=0)
    ii, jj = _feasible_pairs(tt, radius_min, dmax)
    k = len(ii)
    S = len(names)
    nv = m + S * k + (1 if worst_case else 0)
    c = np.zeros(nv)
    rows, cols, vals, lb, ub = [], [], [], [], []
    r = 0
    cov_rows = []
    for s_idx, s in enumerate(names):
        d = np.asarray(demand_scenarios[s], float)
        off = m + s_idx * k
        if not worst_case:
            c[off : off + k] = -scenario_weights[s] * d[ii]
        for i_idx, grp in _group(ii, n):
            rows += [r] * len(grp)
            cols += (off + grp).tolist()
            vals += [1.0] * len(grp)
            lb.append(-np.inf)
            ub.append(1.0)
            r += 1
        for j_idx, grp in _group(jj, m):
            rows += [r] * (len(grp) + 1)
            cols += (off + grp).tolist() + [j_idx]
            vals += d[ii[grp]].tolist() + [-float(capacity[j_idx])]
            lb.append(-np.inf)
            ub.append(0.0)
            r += 1
        if worst_case:  # z - Σ d_i y_ij <= 0
            rows += [r] * (k + 1)
            cols += (off + np.arange(k)).tolist() + [nv - 1]
            vals += (-d[ii]).tolist() + [1.0]
            lb.append(-np.inf)
            ub.append(0.0)
            cov_rows.append(r)
            r += 1
    if worst_case:
        c[nv - 1] = -1.0
    rows += [r] * m
    cols += list(range(m))
    vals += [float(x) for x in cost]
    lb.append(-np.inf)
    ub.append(float(budget))
    r += 1
    A = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    integrality = np.zeros(nv)
    integrality[:m] = 1
    xub = np.ones(nv)
    if worst_case:
        xub[nv - 1] = np.inf
    res = milp(
        c,
        constraints=LinearConstraint(A, lb, ub),
        integrality=integrality,
        bounds=Bounds(np.zeros(nv), xub),
        options={"time_limit": time_limit, "mip_rel_gap": mip_gap, "disp": False},
    )
    if res.x is None:
        return SitingResult(
            [], 0.0, float(np.asarray(demand_scenarios[names[0]]).sum()), np.zeros((n, m)), 0.0, res.message
        )
    x = res.x[:m]
    sel = [j for j in range(m) if x[j] > 0.5]
    base = names[0]
    y0 = res.x[m : m + k]
    Aasg = np.zeros((n, m))
    Aasg[ii, jj] = y0
    d0 = np.asarray(demand_scenarios[base], float)
    covered = float((d0[:, None] * Aasg).sum())
    return SitingResult(
        sel, covered, float(d0.sum()), Aasg, float(-res.fun), "Optimal" if res.status == 0 else res.message
    )


def _group(keys: np.ndarray, nkeys: int):
    """Yield (key, positions) for each key with at least one position, in O(k log k)."""
    order = np.argsort(keys, kind="stable")
    sk = keys[order]
    bounds = np.flatnonzero(np.diff(sk)) + 1
    starts = np.r_[0, bounds]
    ends = np.r_[bounds, len(sk)]
    for s, e in zip(starts, ends, strict=True):
        yield int(sk[s]), order[s:e]


def greedy_mclp(demand: np.ndarray, tt: np.ndarray, radius_min: float, p: int) -> list[int]:
    """Greedy baseline for MCLP (uncapacitated): useful to show the value of exact optimisation."""
    d = np.asarray(demand, float)
    feas = np.isfinite(tt) & (tt <= radius_min)
    covered = np.zeros(len(d), bool)
    chosen: list[int] = []
    for _ in range(p):
        gains = ((~covered)[:, None] & feas).T @ d
        j = int(np.argmax(gains))
        if gains[j] <= 0:
            break
        chosen.append(j)
        covered |= feas[:, j]
    return chosen


def coverage_of(demand: np.ndarray, tt: np.ndarray, radius_min: float, sites: list[int]) -> float:
    """Uncapacitated covered demand of a site set."""
    if not sites:
        return 0.0
    feas = np.isfinite(tt[:, sites]) & (tt[:, sites] <= radius_min)
    return float(np.asarray(demand, float)[feas.any(axis=1)].sum())
