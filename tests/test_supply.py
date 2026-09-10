import geopandas as gpd
import numpy as np
from shapely.geometry import Point, box

from chargescape.features.grid import make_h3_grid
from chargescape.features.supply import dedupe_within, harmonise_chargers, supply_features


def test_supply_pipeline_small():
    grid = make_h3_grid(gpd.GeoDataFrame(geometry=[box(-0.12, 51.50, -0.08, 51.52)], crs="EPSG:4326"), 8)
    osm = gpd.GeoDataFrame(
        {
            "osm_id": [1, 2],
            "max_power_kw": [150, None],
            "n_sockets": [4, 1],
            "capacity_int": [4, None],
            "operator": ["a", "b"],
        },
        geometry=[Point(-0.10, 51.51), Point(-0.09, 51.505)],
        crs="EPSG:4326",
    )
    ncr = gpd.GeoDataFrame(
        {
            "chargeDeviceID": ["x", "y"],
            "max_rated_kw": [7, 50],
            "n_connectors": [2, 2],
            "deviceControllerName": ["c", "d"],
        },
        geometry=[Point(-0.1000001, 51.5100001), Point(-0.11, 51.515)],
        crs="EPSG:4326",
    )
    sites = dedupe_within(harmonise_chargers(osm, ncr))
    assert len(sites) == 3  # ncr 'x' sits on top of osm 1 → dropped
    f = supply_features(grid, sites)
    assert f["n_sites_rapid"].sum() == 2 and f["n_sites_slow"].sum() == 1
    assert np.isfinite(f["dist_rapid_m"]).all()
