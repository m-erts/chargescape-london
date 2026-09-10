"""M/M/c (Erlang C) queueing for charging sites: utilisation, waiting probability, mean wait.

A site with c identical ports, Poisson arrivals at rate lam (per hour) and exponential service
with mean 1/mu hours. This is the textbook baseline; the empirical service-time distribution from
open session data is used elsewhere for a discrete-event check.
"""

from __future__ import annotations

import math

import numpy as np


def utilisation(lam: float, mu: float, c: int) -> float:
    return lam / (c * mu)


def erlang_c(lam: float, mu: float, c: int) -> float:
    """Probability an arriving vehicle has to wait (all c ports busy). Returns 1.0 if unstable."""
    rho = utilisation(lam, mu, c)
    if rho >= 1:
        return 1.0
    a = lam / mu
    s = sum(a**k / math.factorial(k) for k in range(c))
    last = a**c / math.factorial(c) / (1 - rho)
    return last / (s + last)


def mean_wait_minutes(lam: float, mu: float, c: int) -> float:
    """Expected waiting time in queue (minutes). inf if unstable."""
    rho = utilisation(lam, mu, c)
    if rho >= 1:
        return float("inf")
    pw = erlang_c(lam, mu, c)
    return 60.0 * pw / (c * mu - lam)


def required_ports(lam: float, mu: float, max_wait_prob: float = 0.10, c_max: int = 40) -> int:
    """Smallest number of ports such that P(wait) <= max_wait_prob."""
    for c in range(1, c_max + 1):
        if utilisation(lam, mu, c) < 1 and erlang_c(lam, mu, c) <= max_wait_prob:
            return c
    return c_max


def peak_arrival_rate(sessions_per_day: float, peak_share: float = 0.09) -> float:
    """Arrivals per hour in the peak hour given a daily count and the peak-hour share
    (~9% of daily sessions in the busiest hour is typical of open session datasets)."""
    return sessions_per_day * peak_share


def site_metrics(
    sessions_per_day: np.ndarray, ports: np.ndarray, service_min: float = 40.0, peak_share: float = 0.09
) -> dict[str, np.ndarray]:
    """Vectorised site-level queue metrics at the peak hour."""
    mu = 60.0 / service_min
    lam = peak_arrival_rate(np.asarray(sessions_per_day, float), peak_share)
    ports = np.asarray(ports, int)
    rho = np.array([utilisation(lam_i, mu, c) for lam_i, c in zip(lam, ports, strict=True)])
    pw = np.array([erlang_c(lam_i, mu, c) for lam_i, c in zip(lam, ports, strict=True)])
    wq = np.array([mean_wait_minutes(lam_i, mu, c) for lam_i, c in zip(lam, ports, strict=True)])
    return {"peak_lambda_per_h": lam, "utilisation_peak": rho, "p_wait": pw, "mean_wait_min": wq}
