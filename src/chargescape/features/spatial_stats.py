"""Spatial autocorrelation and hotspot statistics on the H3 grid (esda / libpysal)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from esda.getisord import G_Local
from esda.moran import Moran, Moran_Local
from libpysal.weights import W

from chargescape.features.grid import neighbours


def h3_weights(cells: pd.Series, k: int = 1) -> W:
    """Row-standardised contiguity weights from H3 k-ring neighbours."""
    nb = neighbours(cells.tolist(), k=k)
    ids = cells.tolist()
    w = W({c: nb.get(c, []) for c in ids}, id_order=ids, silence_warnings=True)
    w.transform = "R"
    return w


def morans_i(values: pd.Series, w: W, permutations: int = 999, seed: int = 0) -> dict[str, float]:
    np.random.seed(seed)
    m = Moran(values.to_numpy(float), w, permutations=permutations)
    return {"I": float(m.I), "EI": float(m.EI), "p_sim": float(m.p_sim), "z_sim": float(m.z_sim)}


def local_hotspots(
    values: pd.Series, w: W, permutations: int = 999, seed: int = 0, alpha: float = 0.05
) -> pd.DataFrame:
    """Getis-Ord Gi* hot/cold spots and LISA cluster labels aligned with `values` index."""
    np.random.seed(seed)
    x = values.to_numpy(float)
    g = G_Local(x, w, transform="R", permutations=permutations, star=True)
    lisa = Moran_Local(x, w, permutations=permutations)
    quad = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}
    out = pd.DataFrame(
        {
            "gi_z": g.Zs,
            "gi_p": g.p_sim,
            "lisa_q": [quad.get(int(q), "ns") for q in lisa.q],
            "lisa_p": lisa.p_sim,
        },
        index=values.index,
    )
    out["hotspot"] = np.where(
        (out.gi_p < alpha) & (out.gi_z > 0),
        "hot",
        np.where((out.gi_p < alpha) & (out.gi_z < 0), "cold", "ns"),
    )
    out["lisa"] = np.where(out.lisa_p < alpha, out.lisa_q, "ns")
    return out
