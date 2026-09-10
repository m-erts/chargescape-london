"""Supervised utilities: spatial cross-validation, LightGBM point + quantile models, metrics.

Spatial CV is the default: random K-fold on spatially autocorrelated data overstates skill.
`spatial_group_splits` accepts any grouping (borough, H3 res-6 parent, city) and returns
leave-group-out folds; `compare_cv` reports random vs spatial scores side by side.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold


@dataclass
class CVResult:
    scheme: str
    mae: float
    r2: float
    per_fold: pd.DataFrame
    oof: np.ndarray


def _default_params(objective: str = "regression", alpha: float | None = None) -> dict:
    p = {
        "objective": objective,
        "learning_rate": 0.03,
        "num_leaves": 31,
        "min_data_in_leaf": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbose": -1,
        "seed": 42,
    }
    if alpha is not None:
        p["alpha"] = alpha
    return p


def fit_lgbm(
    X: pd.DataFrame, y: np.ndarray, params: dict | None = None, num_rounds: int = 600
) -> lgb.Booster:
    return lgb.train(params or _default_params(), lgb.Dataset(X, y), num_boost_round=num_rounds)


def fit_quantiles(
    X: pd.DataFrame, y: np.ndarray, quantiles: Iterable[float] = (0.1, 0.5, 0.9), num_rounds: int = 600
) -> dict[float, lgb.Booster]:
    return {
        q: lgb.train(_default_params("quantile", alpha=q), lgb.Dataset(X, y), num_boost_round=num_rounds)
        for q in quantiles
    }


def cross_validate(
    X: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray | None,
    n_splits: int = 5,
    params: dict | None = None,
    num_rounds: int = 400,
    log_target: bool = False,
) -> CVResult:
    """Leave-group-out CV if groups given, else random K-fold. Returns OOF predictions and scores."""
    y = np.asarray(y, float)
    yt = np.log1p(y) if log_target else y
    splitter = (
        GroupKFold(n_splits=n_splits)
        if groups is not None
        else KFold(n_splits=n_splits, shuffle=True, random_state=42)
    )
    oof = np.full(len(y), np.nan)
    rows = []
    for k, (tr, te) in enumerate(splitter.split(X, yt, groups)):
        m = lgb.train(
            params or _default_params(), lgb.Dataset(X.iloc[tr], yt[tr]), num_boost_round=num_rounds
        )
        pred = m.predict(X.iloc[te])
        oof[te] = np.expm1(pred) if log_target else pred
        rows.append(
            {
                "fold": k,
                "n_test": len(te),
                "mae": mean_absolute_error(y[te], oof[te]),
                "r2": r2_score(y[te], oof[te]) if len(te) > 2 else np.nan,
            }
        )
    pf = pd.DataFrame(rows)
    return CVResult(
        "spatial" if groups is not None else "random", mean_absolute_error(y, oof), r2_score(y, oof), pf, oof
    )


def compare_cv(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, **kw) -> pd.DataFrame:
    a = cross_validate(X, y, None, **kw)
    b = cross_validate(X, y, groups, **kw)
    return pd.DataFrame(
        [{"scheme": a.scheme, "MAE": a.mae, "R2": a.r2}, {"scheme": b.scheme, "MAE": b.mae, "R2": b.r2}]
    )


def pinball_loss(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = np.asarray(y) - np.asarray(q_pred)
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def interval_coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    y = np.asarray(y)
    return float(np.mean((y >= lo) & (y <= hi)))
