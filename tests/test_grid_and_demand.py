import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from chargescape.features.grid import areal_interpolate, make_h3_grid, neighbours
from chargescape.models.structural_demand import DemandPriors, structural_demand


def test_grid_covers_box_and_interpolation_conserves_mass():
    b = gpd.GeoDataFrame(geometry=[box(-0.15, 51.49, -0.05, 51.53)], crs="EPSG:4326")
    grid = make_h3_grid(b, resolution=8)
    assert len(grid) > 10 and grid.crs.to_string() == "EPSG:4326"
    src = gpd.GeoDataFrame(
        {"pop": [1000.0, 3000.0], "rate": [0.2, 0.6]},
        geometry=[box(-0.15, 51.49, -0.10, 51.53), box(-0.10, 51.49, -0.05, 51.53)],
        crs="EPSG:4326",
    )
    out = areal_interpolate(src, grid, extensive=["pop"], intensive=["rate"])
    # centroid-selected hexes may extend slightly beyond the box, so mass is conserved up to edge effects
    assert 0.9 * 4000 <= out["pop"].sum() <= 1.05 * 4000
    assert out["rate"].dropna().between(0.2 - 1e-9, 0.6 + 1e-9).all()  # edge hexes outside sources are NaN by design
    nb = neighbours(grid["h3"])
    assert all(len(v) <= 6 for v in nb.values())


def test_structural_demand_quantiles_ordered_and_scale_with_evs():
    cells = pd.DataFrame(
        {
            "h3": ["a", "b"],
            "bev": [100.0, 200.0],
            "phev": [50.0, 50.0],
            "share_no_offstreet": [0.3, 0.8],
            "attraction": [1.0, 1.0],
        }
    )
    out = structural_demand(cells, DemandPriors(n_draws=200))
    assert (out["total_kwh_p10"] <= out["total_kwh_p50"]).all() and (
        out["total_kwh_p50"] <= out["total_kwh_p90"]
    ).all()
    assert out.loc[1, "res_kwh_p50"] > out.loc[0, "res_kwh_p50"]
    assert np.isclose(out["dest_kwh_p50"].iloc[0], out["dest_kwh_p50"].iloc[1], rtol=0.05)
