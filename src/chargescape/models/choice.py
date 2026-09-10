"""Station choice (multinomial logit / Huff) and demand allocation with cannibalisation.

Utility of station j for a driver in origin cell i:
    V_ij = b_tt * tt_ij + b_price * price_j + b_power * log(power_j) + b_wait * wait_j + b_ports * log(ports_j)
Probabilities follow the MNL form; an outside option (do not charge here / charge at home)
can be added with a constant utility. Parameters default to literature-informed values and are
documented in docs/methodology.md; they can be re-estimated when revealed-preference data exist.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ChoiceParams:
    b_tt: float = -0.25  # per minute of travel time
    b_price: float = -0.04  # per p/kWh
    b_power: float = 0.60  # per log(kW)
    b_wait: float = -0.08  # per expected minute of waiting
    b_ports: float = 0.30  # per log(ports)
    outside_utility: float | None = None  # None = drivers always choose one of the stations
    max_tt_min: float = 20.0  # stations beyond this travel time are not considered


def utilities(
    tt_min: np.ndarray,
    price: np.ndarray,
    power_kw: np.ndarray,
    ports: np.ndarray,
    wait_min: np.ndarray | None,
    p: ChoiceParams,
) -> np.ndarray:
    wait = np.zeros_like(price, dtype=float) if wait_min is None else np.asarray(wait_min, float)
    v = (
        p.b_tt * tt_min
        + p.b_price * np.asarray(price, float)[None, :]
        + p.b_power * np.log(np.maximum(np.asarray(power_kw, float), 1.0))[None, :]
        + p.b_wait * wait[None, :]
        + p.b_ports * np.log(np.maximum(np.asarray(ports, float), 1.0))[None, :]
    )
    v = np.where(tt_min <= p.max_tt_min, v, -np.inf)
    return v


def choice_probabilities(v: np.ndarray, outside_utility: float | None = None) -> np.ndarray:
    """Row-wise softmax with optional outside option. Rows with no feasible station get zeros."""
    vmax = np.max(np.where(np.isfinite(v), v, -1e9), axis=1, keepdims=True)
    ev = np.where(np.isfinite(v), np.exp(v - vmax), 0.0)
    denom = ev.sum(axis=1, keepdims=True)
    if outside_utility is not None:
        denom = denom + np.exp(outside_utility - vmax)
    with np.errstate(invalid="ignore", divide="ignore"):
        pr = np.where(denom > 0, ev / denom, 0.0)
    return pr


def allocate_demand(origin_demand: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Expected demand captured by each station: sum_i d_i * P_ij."""
    return (np.asarray(origin_demand, float)[:, None] * probs).sum(axis=0)


def incremental_demand(
    origin_demand: np.ndarray,
    v_existing: np.ndarray,
    v_candidate: np.ndarray,
    outside_utility: float | None = None,
) -> dict[str, float]:
    """Demand captured by a candidate station, split into truly new demand (from the outside option)
    and demand cannibalised from existing stations."""
    p_before = choice_probabilities(v_existing, outside_utility)
    v_after = np.concatenate([v_existing, v_candidate[:, None]], axis=1)
    p_after = choice_probabilities(v_after, outside_utility)
    d = np.asarray(origin_demand, float)
    served_before = (d[:, None] * p_before).sum()
    served_after = (d[:, None] * p_after).sum()
    captured = (d * p_after[:, -1]).sum()
    new = served_after - served_before
    return {
        "captured": float(captured),
        "new": float(new),
        "cannibalised": float(captured - new),
        "cannibalisation_share": float((captured - new) / captured) if captured > 0 else 0.0,
    }
