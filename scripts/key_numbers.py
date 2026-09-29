"""Collect every headline number used by the README, the slide decks and the maps index into
reports/tables/key_numbers.json, computed from the committed processed tables (no raw data needed)."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from chargescape.models.allocation_pipeline import candidate_increment
from chargescape.models.ml import cross_validate
from chargescape.utils.paths import DOCS, PROCESSED, ROOT, TABLES
from chargescape.utils.reference import charging_sites, dft_la


def transfer_metrics() -> dict:
    """Same protocol as notebook 05: LightGBM on station context, log target, random vs leave-city-out CV."""
    sf = pd.read_parquet(PROCESSED / "station_features.small.parquet")
    train = sf[sf.city != "london"].dropna(subset=["sessions_per_day"]).copy()
    train = train[train.active_days >= 60]
    feat_cols = [
        c
        for c in sf.columns
        if c.startswith(("poi_", "parking_capacity", "dist_", "pop_"))
        and pd.api.types.is_numeric_dtype(sf[c])
    ] + ["power_kw_f", "is_rapid_f"]
    for d in (sf, train):
        d["power_kw_f"] = d["power_kw"].fillna(d.groupby("city")["power_kw"].transform("median")).fillna(7.0)
        d["is_rapid_f"] = (d["power_kw_f"] >= 50).astype(int)
    X = train[feat_cols].astype(float)
    y = train["sessions_per_day"].to_numpy()
    g = train["city"].to_numpy()
    r_rand = cross_validate(X, y, None, n_splits=5, num_rounds=300, log_target=True)
    r_city = cross_validate(X, y, g, n_splits=4, num_rounds=300, log_target=True)
    rho = {c: float(spearmanr(y[g == c], r_city.oof[g == c]).correlation) for c in sorted(set(g))}
    return {
        "n_stations": int(len(train)),
        "cities": sorted(set(g)),
        "r2_random": round(float(r_rand.r2), 3),
        "r2_leave_city_out": round(float(r_city.r2), 3),
        "spearman_by_city": {k: round(v, 2) for k, v in rho.items()},
    }


def main() -> dict:
    k: dict = {}
    f = pd.read_parquet(
        PROCESSED / "hex_features_r8.small.parquet",
        columns=["h3", "population", "piv_private_est", "piv_company_est", "bev_est"],
    )
    k["n_hexes"] = int(len(f))
    k["population_in_hexes"] = int(f.population.sum())
    k["piv_private"] = int(f.piv_private_est.sum())
    k["piv_company"] = int(f.piv_company_est.sum())
    dft = dft_la()
    la = dft[(dft.geography == "local_authority") & (dft.date == dft.date.max())].pivot_table(
        index="area_name", columns="measure", values="value"
    )
    k["dft_date"] = str(dft.date.max().date())
    k["chargers_total"] = int(la["EV chargers"].sum())
    k["chargers_rapid"] = int(la["50kW+ EV chargers"].sum())
    k["rapid_share"] = round(k["chargers_rapid"] / k["chargers_total"], 3)
    sites = charging_sites()
    k["sites_total"] = int(len(sites))
    k["sites_by_source"] = {s: int(n) for s, n in sites["source"].value_counts().items()}
    d = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
    t = (
        d.groupby("scenario")[
            ["total_kwh_p10", "total_kwh_p50", "total_kwh_p90", "res_kwh_p50", "dest_kwh_p50", "phv_kwh_p50"]
        ].sum()
        / 1e6
    )
    k["demand_gwh"] = {
        s: {c.replace("_kwh", ""): round(v, 0) for c, v in row.items()} for s, row in t.iterrows()
    }
    s = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
    k["rapid_sites"] = int(len(s))
    k["rapid_ports_calibrated"] = int(s.ports.sum())
    k["rapid_ports_known"] = int(s.ports_known.sum())
    k["port_scale_median"] = round(float(s.port_scale.median()), 2)
    k["sites_pwait_gt_50"] = int((s.p_wait > 0.5).sum())
    k["util24_median"] = round(float(s.utilisation_24h.median()), 3)
    k["rapid_sessions_day_total"] = round(float(s.sessions_day.sum()), 0)
    k["rapid_sessions_per_charger_day"] = round(k["rapid_sessions_day_total"] / k["chargers_rapid"], 1)
    h = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet")
    k["median_tt_nearest_rapid_min"] = round(float(h.tt_nearest_rapid_min.median()), 1)
    k["unserved_sessions_day"] = round(float(h.unserved_sessions_day.sum()), 0)
    sw = TABLES / "siting_budget_sweep_2026.csv"
    if sw.exists():
        k["siting"] = pd.read_csv(sw).to_dict(orient="records")
        k["siting_meta"] = json.loads((TABLES / "siting_meta_2026.json").read_text())
        cross = pd.read_csv(TABLES / "siting_scenarios_2026.csv")
        sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
        for row in k["siting"]:
            b, rec = row["budget_m"], row["best_plan_by_minimax_regret"]
            cr = cross[(cross.budget_m == b) & (cross.plan == rec)].set_index("scenario")
            sr = sel[(sel.budget_m == b) & (sel.model == rec)]
            row.update(
                {
                    "rec_plan": rec,
                    "rec_n_hubs": int(len(sr)),
                    "rec_core": int(sr.core.sum()),
                    "rec_max_regret": float(cr.regret.max()),
                    "rec_share_p10": float(cr.loc["p10", "share"]),
                    "rec_share_p50": float(cr.loc["p50", "share"]),
                    "rec_share_p90": float(cr.loc["p90", "share"]),
                }
            )
    sens = TABLES / "sensitivity_2026_budget20m.csv"
    if sens.exists():
        sv = pd.read_csv(sens)
        alt = sv[sv.variant != "base"]
        k["sensitivity"] = {
            "variants": int(len(alt)),
            "same_or_adjacent_min": round(float(alt.same_or_adjacent_hex.min()), 2),
            "same_or_adjacent_median": round(float(alt.same_or_adjacent_hex.median()), 2),
            "same_hex_median": round(float(alt.same_hex_as_base.median()), 2),
            "unmet_range": [
                round(float(sv.unmet_sessions_day.min())),
                round(float(sv.unmet_sessions_day.max())),
            ],
            "rows": sv.to_dict(orient="records"),
        }
    inc, cand = candidate_increment()
    k["cannibalisation"] = {"candidate": cand, "rows": inc.round(3).to_dict(orient="records")}
    k["transfer"] = transfer_metrics()
    k["n_sources"] = len(
        [
            p
            for p in (DOCS / "data_catalog").glob("*.md")
            if not p.name.startswith("_") and p.name != "README.md"
        ]
    )
    k["n_tests"] = sum(
        len(re.findall(r"^def test_", p.read_text(), flags=re.M)) for p in (ROOT / "tests").glob("test_*.py")
    )
    k["n_notebooks"] = len(list((ROOT / "notebooks").glob("*.ipynb")))
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "key_numbers.json").write_text(
        json.dumps(k, indent=2, default=lambda o: o.item() if isinstance(o, np.generic) else str(o))
    )
    print(
        {kk: k[kk] for kk in ("sites_total", "rapid_sites", "sites_pwait_gt_50", "n_sources", "n_tests")},
        k["transfer"],
        k["cannibalisation"]["rows"][1],
    )
    return k


if __name__ == "__main__":
    main()
