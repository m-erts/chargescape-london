"""Allocate rapid-charging demand to existing rapid sites (MNL), then compute queue metrics.

Outputs
* data/processed/rapid_sites_load.small.parquet — per rapid site: expected sessions/day, kWh/day,
  peak utilisation, P(wait), mean wait, required ports for a 10% wait SLA
* data/processed/hex_service.small.parquet — per hex: nearest rapid site (min), demand served /
  unserved within the choice-set radius, expected wait faced by the hex's drivers
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.choice import (
    ChoiceParams,
    allocate_demand,
    choice_probabilities,
    incremental_demand,
    utilities,
)
from chargescape.models.queueing import site_metrics
from chargescape.utils.io import read_gdf, write_df
from chargescape.utils.paths import PROCESSED
from chargescape.utils.reference import borough_name_col, boroughs, charging_sites, dft_la

KWH_PER_RAPID_SESSION = 17.0  # Dundee rapid median 16.2 kWh; UK rapid sessions cluster 15–20 kWh
SERVICE_MIN = 38.0  # Dundee rapid median dwell 35–39 min


def rapid_sites(calibrate: bool = True) -> gpd.GeoDataFrame:
    """Rapid (>=50 kW) sites from OSM 2026 ∪ NCR 2021. Because OSM sees only a fraction of London's
    rapid devices, `calibrate=True` scales the ports of known sites within each borough so that the
    borough total matches the official DfT count of 50 kW+ chargers (1 July 2026). The scale factor is
    stored per site (`port_scale`) so the assumption is visible downstream."""
    s = charging_sites()
    s = s[s.is_rapid].copy().reset_index(drop=True)
    s["lat"], s["lon"] = s.geometry.y, s.geometry.x
    s["ports_known"] = s["n_ports"].fillna(2).clip(lower=1)
    s["power_kw"] = s["max_kw"].fillna(50.0)
    s["price"] = 79.0  # p/kWh, typical London rapid tariff 2026 (bp pulse 79–93p, IONITY 83p)
    lad = boroughs().to_crs(4326)
    name_col = borough_name_col(lad)
    s = gpd.sjoin(s, lad[[name_col, "geometry"]], how="left", predicate="within").rename(
        columns={name_col: "borough"}
    )
    s = s[~s.index.duplicated()].copy()
    s["port_scale"] = 1.0
    if calibrate:
        dft = dft_la()
        dft = dft[(dft.measure == "50kW+ EV chargers") & (dft.geography == "local_authority")]
        dft = dft[dft.date == dft.date.max()].set_index("area_name")["value"]
        known = s.groupby("borough")["ports_known"].sum()
        scale = (dft.reindex(known.index) / known).clip(lower=1.0, upper=15.0).fillna(1.0)
        s["port_scale"] = s["borough"].map(scale).fillna(1.0)
    s["ports"] = np.maximum(1, np.rint(s["ports_known"] * s["port_scale"])).astype(int)
    return s.reset_index(drop=True)


def allocate(
    feats: pd.DataFrame,
    dem: pd.DataFrame,
    sites: pd.DataFrame,
    tt: np.ndarray,
    params: ChoiceParams | None = None,
    service_min: float = SERVICE_MIN,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MNL allocation of rapid-type demand (destination + PHV, P50) to rapid sites, Erlang-C queues per
    site, and a second choice pass in which expected waits enter the utility. Pure function (no I/O)."""
    p = params or ChoiceParams()
    rapid_kwh = (dem["dest_kwh_p50"].fillna(0) + dem["phv_kwh_p50"].fillna(0)).to_numpy()
    sessions_day = rapid_kwh / KWH_PER_RAPID_SESSION / 365.0
    tt_f = np.where(np.isfinite(tt), tt, 1e6)
    price, power, ports = sites["price"].to_numpy(), sites["power_kw"].to_numpy(), sites["ports"].to_numpy()
    pr = choice_probabilities(utilities(tt_f, price, power, ports, None, p))
    served_share = pr.sum(axis=1)  # 0 if no site within max_tt
    site_sessions = allocate_demand(sessions_day, pr)
    qm = site_metrics(site_sessions, ports, service_min=service_min)
    out_sites = sites.drop(columns="geometry", errors="ignore").copy()
    out_sites["sessions_day"] = site_sessions
    out_sites["kwh_day"] = site_sessions * KWH_PER_RAPID_SESSION
    for k, val in qm.items():
        out_sites[k] = val
    out_sites["utilisation_24h"] = out_sites["kwh_day"] / (out_sites["power_kw"] * out_sites["ports"] * 24.0)
    wait = np.nan_to_num(qm["mean_wait_min"], posinf=120.0)
    pr2 = choice_probabilities(utilities(tt_f, price, power, ports, wait, p))
    hex_wait = (pr2 * wait[None, :]).sum(axis=1) / np.maximum(pr2.sum(axis=1), 1e-9)
    near = np.where(tt_f < 1e5, tt_f, np.inf).min(axis=1)
    hex_out = pd.DataFrame(
        {
            "h3": feats["h3"].to_numpy(),
            "rapid_sessions_day": sessions_day,
            "tt_nearest_rapid_min": np.where(np.isfinite(near), near, np.nan),
            "served_share": served_share,
            "unserved_sessions_day": sessions_day * (1 - served_share),
            "expected_wait_min": np.where(served_share > 0, hex_wait, np.nan),
            "n_rapid_within_10min": (tt_f <= 10).sum(axis=1),
        }
    )
    return out_sites, hex_out


def load_inputs(
    res: int = 8, scenario: str = "2026"
) -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame, np.ndarray, str]:
    feats = read_gdf(PROCESSED / f"hex_features_r{res}.small.parquet")
    dem = pd.read_parquet(PROCESSED / f"demand_r{res}.small.parquet")
    dem = dem[dem.scenario == scenario].set_index("h3").reindex(feats["h3"]).reset_index()
    sites = rapid_sites()
    tt, method = travel_time_minutes(feats, sites, name=f"hex_r{res}_to_rapid")
    return feats, dem, sites, tt, method


def run(
    res: int = 8, scenario: str = "2026", params: ChoiceParams | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    feats, dem, sites, tt, method = load_inputs(res, scenario)
    out_sites, hex_out = allocate(feats, dem, sites, tt, params)
    write_df(out_sites, PROCESSED / f"rapid_sites_load_{scenario}.small.parquet")
    write_df(hex_out, PROCESSED / f"hex_service_{scenario}.small.parquet")
    return out_sites, hex_out, method


def candidate_increment(
    res: int = 8,
    scenario: str = "2026",
    configs: tuple[tuple[int, int], ...] = ((50, 2), (150, 4), (150, 8), (300, 8)),
    price: float = 79.0,
) -> tuple[pd.DataFrame, dict]:
    """New vs cannibalised demand for a hub placed in the hex with the largest unmet or queue-constrained
    rapid demand, for several hub configurations (kW, ports). Uses an outside option (utility 0) so that
    'new' demand is demand that would otherwise not charge at a rapid site."""
    feats, dem, sites, tt, _ = load_inputs(res, scenario)
    svc = (
        pd.read_parquet(PROCESSED / f"hex_service_{scenario}.small.parquet")
        .set_index("h3")
        .reindex(feats["h3"])
    )
    demand = (
        (dem["dest_kwh_p50"].fillna(0) + dem["phv_kwh_p50"].fillna(0)).to_numpy()
        / KWH_PER_RAPID_SESSION
        / 365.0
    )
    p = ChoiceParams(outside_utility=0.0)
    tt_f = np.where(np.isfinite(tt), tt, 1e6)
    v = utilities(
        tt_f, sites["price"].to_numpy(), sites["power_kw"].to_numpy(), sites["ports"].to_numpy(), None, p
    )
    pressure = svc["unserved_sessions_day"].fillna(0).to_numpy() + demand * np.clip(
        svc["expected_wait_min"].fillna(0).to_numpy() / 30, 0, 1
    )
    cand = feats.iloc[[int(np.argmax(pressure))]][["h3", "lat", "lon", "borough"]]
    ttc, _ = travel_time_minutes(feats, cand, name=f"hex_r{res}_to_{cand.h3.iloc[0]}")
    ttc = np.where(np.isfinite(ttc), ttc, 1e6)
    rows = []
    for kw, n_ports in configs:
        vc = utilities(ttc, np.array([price]), np.array([float(kw)]), np.array([float(n_ports)]), None, p)[
            :, 0
        ]
        r = incremental_demand(demand, v, vc, outside_utility=0.0)
        r.update({"power_kw": kw, "ports": n_ports})
        rows.append(r)
    out = pd.DataFrame(rows)[
        ["power_kw", "ports", "captured", "new", "cannibalised", "cannibalisation_share"]
    ]
    return out, {"h3": cand.h3.iloc[0], "borough": cand.borough.iloc[0]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--scenario", default="2026")
    a = ap.parse_args()
    s, h, m = run(a.res, a.scenario)
    print("travel-time method:", m)
    print(
        f"rapid sites: {len(s)}; sessions/day total {s.sessions_day.sum():,.0f}; median per site {s.sessions_day.median():.1f}"
    )
    print(
        f"sites with P(wait)>0.2 at peak: {(s.p_wait > 0.2).sum()}; utilisation_24h median {s.utilisation_24h.median():.2%}"
    )
    print(
        f"hex demand unserved (no rapid within {ChoiceParams().max_tt_min:.0f} min): {h.unserved_sessions_day.sum():,.0f} of {h.rapid_sessions_day.sum():,.0f} sessions/day"
    )
