"""Demand pipeline: build attraction weights, run the structural Monte Carlo model for the
current year and for 2030 DFES scenarios, add a taxi/PHV fleet component, and write
data/processed/demand_r{res}.small.parquet.

Components (annual kWh of public charging per hex)
* res_*   near-home public demand of private EV owners without off-street parking
* dest_*  destination / en-route demand of private EVs, redistributed by an attraction weight
* phv_*   taxi & private-hire demand, redistributed by taxi+PHV vehicle-km (LAEI 2022)
* total_* sum of the three
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from chargescape.models.structural_demand import DemandPriors, structural_demand
from chargescape.utils.io import read_gdf, write_df
from chargescape.utils.paths import PROCESSED


@dataclass
class AttractionWeights:
    """Mix of normalised activity signals (each scaled to sum to one). Documented in methodology."""

    vkm_total: float = 0.45  # en-route: through traffic
    poi_dwell: float = 0.35  # destination: retail + food + leisure + hotel
    rail: float = 0.10  # interchange / park-and-ride style activity
    parking: float = 0.10  # physical opportunity to dwell


@dataclass
class PHVPriors:
    """London taxi & private-hire electrification. Sources in docs/methodology.md."""

    phv_ev_2026: tuple[float, float, float] = (
        14_000,
        20_000,
        26_000,
    )  # ZEC PHVs + taxis on London roads (proxy from TfL licensing)
    annual_km: tuple[float, float, float] = (35_000, 45_000, 55_000)
    kwh_per_km: tuple[float, float, float] = (0.17, 0.20, 0.24)
    public_share: tuple[float, float, float] = (0.70, 0.85, 0.95)
    growth_2030: tuple[float, float, float] = (2.0, 3.0, 4.5)  # multiplier on fleet size by 2030


COMPANY_FACTOR = 0.5  # share of company-kept EVs that behave like resident cars (prior mode; see methodology)


def _norm(x: pd.Series) -> np.ndarray:
    v = x.fillna(0).clip(lower=0).to_numpy(float)
    return v / v.sum() if v.sum() > 0 else np.full(len(v), 1 / len(v))


def attraction(feats: pd.DataFrame, w: AttractionWeights | None = None) -> np.ndarray:
    w = w or AttractionWeights()
    poi = (
        feats[[c for c in ("poi_retail", "poi_food", "poi_leisure", "poi_hotel") if c in feats]].sum(axis=1)
        if any(c in feats for c in ("poi_retail", "poi_food"))
        else pd.Series(np.zeros(len(feats)))
    )
    rail = feats["n_rail_stations"] if "n_rail_stations" in feats else pd.Series(np.zeros(len(feats)))
    park = feats["poi_parking"] if "poi_parking" in feats else pd.Series(np.zeros(len(feats)))
    a = (
        w.vkm_total * _norm(feats["vkm_total"])
        + w.poi_dwell * _norm(poi)
        + w.rail * _norm(rail)
        + w.parking * _norm(park)
    )
    return a / a.sum()


def phv_demand(
    feats: pd.DataFrame, pr: PHVPriors, n: int, rng: np.random.Generator, year: int = 2026
) -> np.ndarray:
    fleet = rng.triangular(*pr.phv_ev_2026, size=n)
    if year >= 2030:
        fleet = fleet * rng.triangular(*pr.growth_2030, size=n)
    energy = (
        fleet
        * rng.triangular(*pr.annual_km, size=n)
        * rng.triangular(*pr.kwh_per_km, size=n)
        * rng.triangular(*pr.public_share, size=n)
    )
    share = _norm(feats["vkm_taxi_phv"])
    return energy[:, None] * share[None, :]


def _quantiles(arr: np.ndarray, name: str) -> dict[str, np.ndarray]:
    return {
        f"{name}_p10": np.percentile(arr, 10, axis=0),
        f"{name}_p50": np.percentile(arr, 50, axis=0),
        f"{name}_p90": np.percentile(arr, 90, axis=0),
        f"{name}_mean": arr.mean(axis=0),
    }


def run(res: int = 8, n_draws: int = 500, seed: int = 42) -> pd.DataFrame:
    feats = read_gdf(PROCESSED / f"hex_features_r{res}.small.parquet")
    feats = pd.DataFrame(feats.drop(columns="geometry"))
    feats["attraction"] = attraction(feats)
    priors = DemandPriors(n_draws=n_draws, seed=seed)
    frames = []
    # Company-kept EVs (salary-sacrifice leases, pool cars) also charge where they are kept, but a
    # few LSOAs host fleet head offices (e.g. 44k PiVs on 1.3k households in Westminster). We include
    # company-kept cars at a discount and cap them at 2x the private count of the hex.
    priv_share = (
        feats["piv_private_est"]
        .fillna(0)
        .div(feats["piv_total_est"].replace(0, np.nan))
        .fillna(0.6)
        .clip(0.2, 1.0)
    )
    bev_priv = feats["bev_private_est"].fillna(0)
    bev_comp = (feats["bev_est"].fillna(0) - bev_priv).clip(lower=0)
    bev_comp_capped = np.minimum(bev_comp, 2.0 * bev_priv)
    phev_priv = feats["phev_est"].fillna(0) * priv_share
    phev_comp_capped = np.minimum(feats["phev_est"].fillna(0) * (1 - priv_share), 2.0 * phev_priv)
    cf = COMPANY_FACTOR
    scenarios = {"2026": (bev_priv + cf * bev_comp_capped, phev_priv + cf * phev_comp_capped)}
    for tag in ("low", "mid", "high"):
        if f"bev_2030_{tag}" in feats:
            # DFES counts are all keeperships; apply the same private share and company discount per hex
            eff = priv_share + cf * (1 - priv_share).clip(upper=2 * priv_share)
            scenarios[f"2030_{tag}"] = (
                feats[f"bev_2030_{tag}"].fillna(0) * eff,
                feats[f"phev_2030_{tag}"].fillna(0) * eff,
            )
    for name, (bev, phev) in scenarios.items():
        cells = pd.DataFrame(
            {
                "h3": feats["h3"],
                "bev": bev.to_numpy(float),
                "phev": phev.to_numpy(float),
                "share_no_offstreet": feats["share_no_offstreet"].fillna(0.4),
                "attraction": feats["attraction"],
            }
        )
        out = structural_demand(cells, priors)
        year = 2030 if name.startswith("2030") else 2026
        ph = phv_demand(feats, PHVPriors(), n_draws, np.random.default_rng(seed + 2), year=year)
        for k, v in _quantiles(ph, "phv_kwh").items():
            out[k] = v
        for q in ("p10", "p50", "p90", "mean"):
            out[f"total_kwh_{q}"] = out[f"res_kwh_{q}"] + out[f"dest_kwh_{q}"] + out[f"phv_kwh_{q}"]
        out.insert(1, "scenario", name)
        frames.append(out)
    demand = pd.concat(frames, ignore_index=True)
    write_df(demand, PROCESSED / f"demand_r{res}.small.parquet")
    return demand


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--draws", type=int, default=500)
    a = ap.parse_args()
    d = run(a.res, a.draws)
    s = (
        d.groupby("scenario")[
            ["res_kwh_p50", "dest_kwh_p50", "phv_kwh_p50", "total_kwh_p10", "total_kwh_p50", "total_kwh_p90"]
        ].sum()
        / 1e6
    )
    print("City totals, GWh/year:\n", s.round(1))
