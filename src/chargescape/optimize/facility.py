"""Facility location for charging hubs: classic MCLP / p-median via spopt and a capacitated,
budget-constrained MILP (PuLP + HiGHS/CBC) that also supports demand scenarios (P10/P50/P90).

Decision variables
------------------
x_j ∈ {0,1}   open candidate j
y_ij ∈ [0,1]  share of demand of cell i assigned to j (only if t_ij <= radius)
Capacity: sum_i d_i y_ij <= cap_j x_j ; Budget: sum_j cost_j x_j <= B ; Coverage: sum_j y_ij <= 1
Objective: maximise covered demand (optionally minus a small travel-time penalty), and for the
robust variant maximise the weighted sum over scenarios or the worst case.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp


def _solver(msg: bool = False):
    try:
        return pulp.HiGHS(msg=msg)
    except Exception:  # noqa: BLE001
        return pulp.PULP_CBC_CMD(msg=msg)


@dataclass
class SitingResult:
    selected: list[int]
    covered_demand: float
    total_demand: float
    assignments: np.ndarray  # (n_cells, n_candidates) shares
    objective: float
    status: str

    @property
    def coverage_share(self) -> float:
        return self.covered_demand / self.total_demand if self.total_demand > 0 else 0.0


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
    msg: bool = False,
) -> SitingResult:
    """Capacitated maximal covering with a budget. tt in minutes, shape (cells, candidates)."""
    d = np.asarray(demand, float)
    n, m = tt.shape
    feas = np.isfinite(tt) & (tt <= radius_min)
    prob = pulp.LpProblem("cap_mclp", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(m)]
    y = {
        (i, j): pulp.LpVariable(f"y_{i}_{j}", lowBound=0, upBound=1)
        for i in range(n)
        for j in range(m)
        if feas[i, j] and d[i] > 0
    }
    prob += pulp.lpSum(d[i] * (1 - tt_penalty * tt[i, j] / radius_min) * y[i, j] for (i, j) in y)
    for i in range(n):
        js = [j for j in range(m) if (i, j) in y]
        if js:
            prob += pulp.lpSum(y[i, j] for j in js) <= 1
    for j in range(m):
        ij = [(i, j) for i in range(n) if (i, j) in y]
        if ij:
            prob += pulp.lpSum(d[i] * y[i, j] for (i, j) in ij) <= float(capacity[j]) * x[j]
        else:
            prob += x[j] == 0 if (fixed_open is None or j not in fixed_open) else x[j] == 1
    prob += pulp.lpSum(float(cost[j]) * x[j] for j in range(m)) <= budget
    if p_max is not None:
        prob += pulp.lpSum(x) <= p_max
    for j in fixed_open or []:
        prob += x[j] == 1
    prob.solve(_solver(msg))
    sel = [j for j in range(m) if x[j].value() and x[j].value() > 0.5]
    A = np.zeros((n, m))
    for (i, j), var in y.items():
        A[i, j] = var.value() or 0.0
    covered = float((d[:, None] * A).sum())
    return SitingResult(
        sel, covered, float(d.sum()), A, float(pulp.value(prob.objective) or 0.0), pulp.LpStatus[prob.status]
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
    msg: bool = False,
) -> SitingResult:
    """Two-stage scenario model: one set of sites, scenario-specific assignments.
    Maximises the weighted expected coverage, or the worst-case coverage if worst_case=True."""
    names = list(demand_scenarios)
    n, m = tt.shape
    feas = np.isfinite(tt) & (tt <= radius_min)
    prob = pulp.LpProblem("robust_cap_mclp", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(m)]
    y = {
        (s, i, j): pulp.LpVariable(f"y_{s}_{i}_{j}", lowBound=0, upBound=1)
        for s in names
        for i in range(n)
        for j in range(m)
        if feas[i, j] and demand_scenarios[s][i] > 0
    }
    cov = {s: pulp.lpSum(demand_scenarios[s][i] * y[s, i, j] for (ss, i, j) in y if ss == s) for s in names}
    if worst_case:
        z = pulp.LpVariable("z", lowBound=0)
        prob += z
        for s in names:
            prob += z <= cov[s]
    else:
        prob += pulp.lpSum(scenario_weights[s] * cov[s] for s in names)
    for s in names:
        for i in range(n):
            js = [j for j in range(m) if (s, i, j) in y]
            if js:
                prob += pulp.lpSum(y[s, i, j] for j in js) <= 1
        for j in range(m):
            ij = [(s, i, j) for i in range(n) if (s, i, j) in y]
            if ij:
                prob += (
                    pulp.lpSum(demand_scenarios[s][i] * y[s, i, j] for (_, i, j) in ij)
                    <= float(capacity[j]) * x[j]
                )
    prob += pulp.lpSum(float(cost[j]) * x[j] for j in range(m)) <= budget
    prob.solve(_solver(msg))
    sel = [j for j in range(m) if x[j].value() and x[j].value() > 0.5]
    base = names[0]
    A = np.zeros((n, m))
    for (s, i, j), var in y.items():
        if s == base:
            A[i, j] = var.value() or 0.0
    d0 = np.asarray(demand_scenarios[base], float)
    covered = float((d0[:, None] * A).sum())
    return SitingResult(
        sel, covered, float(d0.sum()), A, float(pulp.value(prob.objective) or 0.0), pulp.LpStatus[prob.status]
    )


def greedy_mclp(demand: np.ndarray, tt: np.ndarray, radius_min: float, p: int) -> list[int]:
    """Greedy baseline for MCLP (uncapacitated): useful to show the value of exact optimisation."""
    d = np.asarray(demand, float)
    feas = np.isfinite(tt) & (tt <= radius_min)
    covered = np.zeros(len(d), bool)
    chosen: list[int] = []
    for _ in range(p):
        gains = [((~covered) & feas[:, j]) @ d for j in range(tt.shape[1])]
        j = int(np.argmax(gains))
        if gains[j] <= 0:
            break
        chosen.append(j)
        covered |= feas[:, j]
    return chosen
