import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from chargescape.features import travel_time as tt_mod
from chargescape.features.supply import dedupe_within, harmonise_chargers
from chargescape.optimize.siting_pipeline import hub_capacity_sessions_day, unmet_demand
from chargescape.viz.design import DARK, LIGHT, tokens_css
from chargescape.viz.export_maplibre import _breaks, _class_labels, _legend_ramp, _segmented


def test_hub_capacity_grows_with_tolerated_wait_and_ports():
    base = hub_capacity_sessions_day()
    assert 25 < base < 45  # 4 ports, 38-min sessions, P(wait) <= 15 % at the peak hour
    assert hub_capacity_sessions_day(max_wait_prob=0.30) > base
    assert hub_capacity_sessions_day(ports=8) > 2 * base  # pooling: capacity grows faster than ports


def test_unmet_demand_bounds():
    d = pd.DataFrame({"dest_kwh_p50": [17 * 365.0, 34 * 365.0], "phv_kwh_p50": [0.0, 0.0]})
    fully_served = pd.DataFrame({"served_share": [1.0, 1.0], "expected_wait_min": [0.0, 0.0]})
    unserved = pd.DataFrame({"served_share": [0.0, 0.0], "expected_wait_min": [np.nan, np.nan]})
    long_wait = pd.DataFrame({"served_share": [1.0, 1.0], "expected_wait_min": [60.0, 15.0]})
    assert np.allclose(unmet_demand(fully_served, d), 0)
    assert np.allclose(unmet_demand(unserved, d), [1.0, 2.0])
    assert np.allclose(unmet_demand(long_wait, d), [1.0, 1.0])  # wait/30 capped at 1 → 1.0 and 0.5 × 2


def test_three_source_dedupe_prefers_ocm_then_osm():
    ocm = pd.DataFrame(
        {
            "ocm_id": [1],
            "lat": [51.5],
            "lon": [-0.1],
            "operator": ["a"],
            "usage_type": ["Public"],
            "status": ["Operational"],
            "n_points": [4],
            "max_power_kw": [150.0],
            "date_last_verified": ["2026-01-01"],
        }
    )
    osm = gpd.GeoDataFrame(
        {
            "osm_id": [7, 8],
            "max_power_kw": [150.0, 50.0],
            "n_sockets": [4, 2],
            "capacity_int": [4, 2],
            "operator": ["a", "b"],
        },
        geometry=[Point(-0.10002, 51.50002), Point(-0.2, 51.45)],
        crs="EPSG:4326",
    )
    ncr = gpd.GeoDataFrame(
        {"chargeDeviceID": ["x"], "max_rated_kw": [7.0], "n_connectors": [2], "deviceControllerName": ["c"]},
        geometry=[Point(-0.20001, 51.45001)],
        crs="EPSG:4326",
    )
    sites = dedupe_within(harmonise_chargers(osm, ncr, ocm))
    assert sorted(sites.source) == ["ocm", "osm"]  # OSM 7 duplicates OCM 1; NCR x duplicates OSM 8
    assert sites.is_rapid.sum() == 2


def test_travel_time_cache_is_signature_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(tt_mod, "PROCESSED", tmp_path)
    o = pd.DataFrame({"lat": [51.50, 51.52], "lon": [-0.12, -0.10]})
    t1 = pd.DataFrame({"lat": [51.51], "lon": [-0.11]})
    t2 = pd.DataFrame({"lat": [51.60], "lon": [-0.30]})
    a, m = tt_mod.travel_time_minutes(o, t1, name="t", force_approx=True)
    assert m.startswith("approx") and a.shape == (2, 1) and (tmp_path / "tt_t.npz").exists()
    b, _ = tt_mod.travel_time_minutes(o, t2, name="t", force_approx=True)  # same name, different targets
    assert not np.allclose(a, b)  # stale cache is not reused


def test_map_classes_and_legend():
    br = _breaks(pd.Series(np.arange(1, 101, dtype=float)), k=4)
    assert br == sorted(br) and len(br) == 3
    labels = _class_labels(br, " kW")
    assert len(labels) == 4 and labels[0].startswith("under ") and labels[-1].endswith(" and over")
    assert all(dash not in label for label in labels for dash in ("\u2013", "\u2014"))
    html = _legend_ramp("t", br, key="k", hidden=True)
    assert html.count('class="sw r') == 4 and 'data-legend="k"' in html and " hidden" in html
    seg = _segmented("g", "Group", [("a", "A"), ("b", "B")], "b")
    assert seg.count("<button") == 2 and seg.count('aria-pressed="true"') == 1


def test_design_tokens_cover_both_themes():
    assert set(LIGHT) == set(DARK)
    css = tokens_css("../vendor")
    assert "prefers-color-scheme:dark" in css and ':root[data-theme="dark"]' in css
    assert "prefers-reduced-motion" in css and ":focus-visible" in css
    for name, value in LIGHT.items():
        assert f"--{name}:{value}" in css
