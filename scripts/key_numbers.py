"""Collect headline numbers from processed tables into reports/tables/key_numbers.json
(used by the README, the slide deck and the maps index)."""

from __future__ import annotations

import json

import pandas as pd

from chargescape.utils.paths import INTERIM, PROCESSED, TABLES


def main() -> dict:
    k: dict = {}
    f = pd.read_parquet(
        PROCESSED / "hex_features_r8.small.parquet",
        columns=[
            "h3",
            "population",
            "piv_private_est",
            "piv_company_est",
            "bev_est",
            "n_sites_rapid",
            "n_sites_slow",
        ],
    )
    k["n_hexes"] = int(len(f))
    k["population_in_hexes"] = int(f.population.sum())
    k["piv_private"] = int(f.piv_private_est.sum())
    k["piv_company"] = int(f.piv_company_est.sum())
    dft = pd.read_parquet(INTERIM / "chargepoints" / "dft_evci_london_la.parquet")
    la = dft[(dft.geography == "local_authority") & (dft.date == dft.date.max())].pivot_table(
        index="area_name", columns="measure", values="value"
    )
    k["dft_date"] = str(dft.date.max().date())
    k["chargers_total"] = int(la["EV chargers"].sum())
    k["chargers_rapid"] = int(la["50kW+ EV chargers"].sum())
    k["rapid_share"] = round(k["chargers_rapid"] / k["chargers_total"], 3)
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
    k["sites_pwait_gt_50"] = int((s.p_wait > 0.5).sum())
    k["util24_median"] = round(float(s.utilisation_24h.median()), 3)
    k["rapid_sessions_day_total"] = round(float(s.sessions_day.sum()), 0)
    k["rapid_sessions_per_charger_day"] = round(k["rapid_sessions_day_total"] / k["chargers_rapid"], 1)
    h = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet")
    k["median_tt_nearest_rapid_min"] = round(float(h.tt_nearest_rapid_min.median()), 1)
    k["unserved_sessions_day"] = round(float(h.unserved_sessions_day.sum()), 0)
    sw = TABLES / "siting_budget_sweep_2026.csv"
    if sw.exists():
        sweep = pd.read_csv(sw)
        k["siting"] = sweep.to_dict(orient="records")
        meta = json.loads((TABLES / "siting_meta_2026.json").read_text())
        k["siting_meta"] = meta
    sf = pd.read_parquet(PROCESSED / "station_features.small.parquet", columns=["city", "sessions_per_day"])
    k["transfer_stations"] = int(sf[sf.city != "london"].sessions_per_day.notna().sum())
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "key_numbers.json").write_text(json.dumps(k, indent=2, default=str))
    print(json.dumps(k, indent=1, default=str)[:1500])
    return k


if __name__ == "__main__":
    main()
