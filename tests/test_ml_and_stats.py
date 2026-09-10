import numpy as np
import pandas as pd

from chargescape.features.grid import make_h3_grid
from chargescape.features.spatial_stats import h3_weights, morans_i
from chargescape.models.ml import compare_cv, interval_coverage, pinball_loss


def test_morans_i_detects_gradient():
    import geopandas as gpd
    from shapely.geometry import box

    grid = make_h3_grid(gpd.GeoDataFrame(geometry=[box(-0.2, 51.45, 0.0, 51.55)], crs="EPSG:4326"), 8)
    w = h3_weights(grid["h3"])
    gradient = pd.Series(grid["lon"].to_numpy(), index=grid.index)
    res = morans_i(gradient, w, permutations=99)
    assert res["I"] > 0.5 and res["p_sim"] < 0.05
    noise = pd.Series(np.random.default_rng(0).normal(size=len(grid)), index=grid.index)
    assert abs(morans_i(noise, w, permutations=99)["I"]) < 0.2


def test_compare_cv_runs_and_spatial_is_reported():
    rng = np.random.default_rng(1)
    n = 400
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = 3 * X["a"] - 2 * X["b"] + rng.normal(scale=0.5, size=n)
    groups = np.repeat(np.arange(8), n // 8)
    out = compare_cv(X, y.to_numpy(), groups, num_rounds=100)
    assert set(out["scheme"]) == {"random", "spatial"}
    assert out["R2"].min() > 0.8


def test_pinball_and_coverage():
    y = np.array([1.0, 2.0, 3.0])
    assert pinball_loss(y, y, 0.5) == 0.0
    assert interval_coverage(y, y - 1, y + 1) == 1.0
