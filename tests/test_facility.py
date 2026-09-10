import numpy as np

from chargescape.optimize.facility import capacitated_mclp, greedy_mclp, robust_capacitated_mclp


def _instance():
    # 5 demand cells, 3 candidates; travel times in minutes
    tt = np.array(
        [
            [2, 9, 20],
            [3, 8, 20],
            [9, 2, 20],
            [9, 3, 20],
            [20, 20, 2],
        ],
        float,
    )
    demand = np.array([10, 10, 10, 10, 50.0])
    return tt, demand


def test_budget_forces_best_single_site():
    tt, d = _instance()
    r = capacitated_mclp(
        d, tt, radius_min=5, cost=np.array([1, 1, 1.0]), capacity=np.array([100, 100, 100.0]), budget=1
    )
    assert r.selected == [2]  # the 50-demand cell
    assert r.covered_demand == 50


def test_capacity_binds():
    tt, d = _instance()
    r = capacitated_mclp(d, tt, radius_min=5, cost=np.ones(3), capacity=np.array([100, 100, 30.0]), budget=3)
    assert set(r.selected) == {0, 1, 2}
    assert abs(r.covered_demand - 70) < 1e-6


def test_greedy_matches_exact_on_easy_instance():
    tt, d = _instance()
    assert greedy_mclp(d, tt, 5, 1) == [2]


def test_robust_picks_site_good_in_all_scenarios():
    tt, d = _instance()
    scen = {"p10": d * 0.5, "p50": d, "p90": d * 1.5}
    w = {"p10": 0.25, "p50": 0.5, "p90": 0.25}
    r = robust_capacitated_mclp(scen, w, tt, 5, np.ones(3), np.full(3, 1000.0), budget=1)
    assert r.selected == [2]
    assert r.status == "Optimal"
