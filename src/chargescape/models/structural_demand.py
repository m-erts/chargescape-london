"""Structural (bottom-up) model of public charging energy demand with parameter uncertainty.

This is the planning-grade approach used by NREL EVI-Pro, the German StandortTOOL and TfL's
own strategy modelling: demand is derived from the EV stock, how far cars are driven, how much
energy they use and how much of that energy must be charged publicly, which depends on access to
home charging. Every parameter has an explicit prior; Monte Carlo sampling propagates the
uncertainty into P10/P50/P90 demand per cell instead of a single point estimate.

Two demand components are produced per hex:
* `res_kwh`   – "near-home" public demand (slow/fast AC on-street) located where EV owners live
  and lack off-street parking;
* `dest_kwh`  – "destination / en-route" demand (rapid DC) located where activity happens,
  redistributed from residence to activity cells using an attraction weight (POI, jobs, traffic).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class DemandPriors:
    """Triangular priors (low, mode, high). Units in comments. Sources in docs/methodology.md."""

    annual_km: tuple[float, float, float] = (9_000, 11_500, 14_000)  # km/yr per car (UK NTS ~7,400 mi)
    kwh_per_km: tuple[float, float, float] = (0.16, 0.19, 0.24)  # incl. winter/heating penalty
    public_share_home_access: tuple[float, float, float] = (
        0.05,
        0.12,
        0.25,
    )  # share of energy charged publicly if home charging available
    public_share_no_home: tuple[float, float, float] = (0.55, 0.75, 0.95)  # if no off-street parking
    rapid_share_of_public: tuple[float, float, float] = (
        0.25,
        0.40,
        0.60,
    )  # share of public energy delivered at rapid/ultra-rapid hubs
    phev_factor: tuple[float, float, float] = (0.25, 0.40, 0.55)  # PHEV electric km share vs BEV
    seed: int = 42
    n_draws: int = 500
    extra: dict = field(default_factory=dict)


def _tri(rng: np.random.Generator, p: tuple[float, float, float], n: int) -> np.ndarray:
    lo, mode, hi = p
    return rng.triangular(lo, mode, hi, size=n)


def structural_demand(
    cells: pd.DataFrame,
    priors: DemandPriors | None = None,
    attraction_col: str = "attraction",
    bev_col: str = "bev",
    phev_col: str = "phev",
    no_home_col: str = "share_no_offstreet",
) -> pd.DataFrame:
    """Compute annual public charging demand (kWh) per cell with Monte Carlo uncertainty.

    Required columns in `cells`: h3, bev, phev (counts kept in the cell), share_no_offstreet
    (0..1, share of EV-owning households without off-street parking), attraction (>=0 weight that
    sums to anything; it is normalised internally).
    Returns a DataFrame with P10/P50/P90 (and mean) for res_kwh, dest_kwh, total_kwh.
    """
    pr = priors or DemandPriors()
    rng = np.random.default_rng(pr.seed)
    n = pr.n_draws
    bev = cells[bev_col].to_numpy(float)
    phev = cells[phev_col].to_numpy(float)
    no_home = np.clip(cells[no_home_col].to_numpy(float), 0, 1)
    attr = cells[attraction_col].to_numpy(float)
    attr = attr / attr.sum() if attr.sum() > 0 else np.full(len(attr), 1 / len(attr))

    km = _tri(rng, pr.annual_km, n)
    kpk = _tri(rng, pr.kwh_per_km, n)
    ps_home = _tri(rng, pr.public_share_home_access, n)
    ps_nohome = _tri(rng, pr.public_share_no_home, n)
    rapid = _tri(rng, pr.rapid_share_of_public, n)
    phf = _tri(rng, pr.phev_factor, n)

    # (draws, cells)
    ev_equiv = bev[None, :] + phf[:, None] * phev[None, :]
    energy = ev_equiv * (km * kpk)[:, None]  # total annual electric energy of cars kept in cell
    public_share = (1 - no_home)[None, :] * ps_home[:, None] + no_home[None, :] * ps_nohome[:, None]
    public = energy * public_share
    res = public * (1 - rapid)[:, None]  # stays near home
    dest_total = (public * rapid[:, None]).sum(axis=1, keepdims=True)  # pooled city-wide
    dest = dest_total * attr[None, :]  # redistributed to activity cells

    def q(a: np.ndarray, name: str) -> dict[str, np.ndarray]:
        return {
            f"{name}_p10": np.percentile(a, 10, axis=0),
            f"{name}_p50": np.percentile(a, 50, axis=0),
            f"{name}_p90": np.percentile(a, 90, axis=0),
            f"{name}_mean": a.mean(axis=0),
        }

    out = pd.DataFrame({"h3": cells["h3"].values})
    for name, arr in (("res_kwh", res), ("dest_kwh", dest), ("total_kwh", res + dest)):
        for k, v in q(arr, name).items():
            out[k] = v
    return out


def kwh_to_sessions(kwh_per_year: np.ndarray, kwh_per_session: float = 20.0) -> np.ndarray:
    """Convert annual energy to sessions per day (kWh/session default from open session data)."""
    return kwh_per_year / kwh_per_session / 365.0
