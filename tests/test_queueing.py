import math

from chargescape.models.queueing import erlang_c, mean_wait_minutes, required_ports, utilisation


def test_mm1_matches_closed_form():
    lam, mu = 3.0, 4.0  # rho = 0.75
    assert math.isclose(erlang_c(lam, mu, 1), 0.75, rel_tol=1e-9)
    # M/M/1 Wq = rho / (mu - lam) hours
    assert math.isclose(mean_wait_minutes(lam, mu, 1), 60 * 0.75 / (mu - lam), rel_tol=1e-9)


def test_unstable_returns_one():
    assert erlang_c(10, 1, 2) == 1.0
    assert utilisation(10, 1, 2) == 5.0


def test_required_ports_monotone():
    c1 = required_ports(lam=6, mu=1.5, max_wait_prob=0.2)
    c2 = required_ports(lam=6, mu=1.5, max_wait_prob=0.05)
    assert c2 >= c1 >= 5  # rho<1 needs at least 5 ports
