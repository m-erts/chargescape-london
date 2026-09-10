import numpy as np

from chargescape.models.choice import ChoiceParams, choice_probabilities, incremental_demand, utilities


def _setup():
    tt = np.array([[3.0, 8.0, 30.0], [10.0, 4.0, 6.0]])
    price = np.array([50, 60, 40.0])
    power = np.array([50, 150, 22.0])
    ports = np.array([4, 8, 2])
    return tt, price, power, ports


def test_probabilities_sum_to_one_and_respect_max_tt():
    tt, price, power, ports = _setup()
    v = utilities(tt, price, power, ports, None, ChoiceParams(max_tt_min=20))
    p = choice_probabilities(v)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert p[0, 2] == 0.0  # 30 min > max


def test_closer_station_more_likely():
    tt, price, power, ports = _setup()
    v = utilities(tt, np.full(3, 50.0), np.full(3, 50.0), np.full(3, 4.0), None, ChoiceParams())
    p = choice_probabilities(v)
    assert p[0, 0] > p[0, 1]


def test_incremental_split_is_consistent():
    tt, price, power, ports = _setup()
    p = ChoiceParams(outside_utility=0.0)
    v = utilities(tt, price, power, ports, None, p)
    v_cand = utilities(
        np.array([[5.0], [5.0]]), np.array([45.0]), np.array([150.0]), np.array([6.0]), None, p
    )[:, 0]
    res = incremental_demand(np.array([100.0, 100.0]), v, v_cand, outside_utility=0.0)
    assert res["captured"] > 0
    assert abs(res["new"] + res["cannibalised"] - res["captured"]) < 1e-6
    assert 0 <= res["cannibalisation_share"] <= 1
