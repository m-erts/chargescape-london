"""Small reference layers shared by models, notebooks and reports.

`features.build` writes compact copies into data/processed/ (committed to the repository), so the
modelling and reporting steps run from a fresh clone without the 4 GB of raw downloads. Each loader
falls back to the full interim file when the compact copy is missing.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from chargescape.utils.io import read_gdf
from chargescape.utils.paths import INTERIM, PROCESSED

BOROUGHS = PROCESSED / "boroughs.small.parquet"
DFT_LA = PROCESSED / "dft_evci_la.small.parquet"
SITES = PROCESSED / "charging_sites.small.parquet"


def boroughs() -> gpd.GeoDataFrame:
    """The 33 London local authorities (ONS LAD 2024, generalised), EPSG:27700."""
    path = BOROUGHS if BOROUGHS.exists() else INTERIM / "census" / "lad24_london.parquet"
    return read_gdf(path).to_crs(27700)


def borough_name_col(gdf: gpd.GeoDataFrame) -> str:
    return next(c for c in gdf.columns if c.lower().startswith("lad") and c.lower().endswith("nm"))


def dft_la() -> pd.DataFrame:
    """DfT EV charging infrastructure statistics for London (tidy long table, all releases)."""
    path = DFT_LA if DFT_LA.exists() else INTERIM / "chargepoints" / "dft_evci_london_la.parquet"
    return pd.read_parquet(path)


def dft_latest_boroughs() -> pd.DataFrame:
    """Borough x measure table for the latest DfT release (chargers, 50 kW+, per 100k)."""
    d = dft_la()
    la = d[(d.geography == "local_authority") & (d.date == d.date.max())]
    return la.pivot_table(index="area_name", columns="measure", values="value")


def charging_sites() -> gpd.GeoDataFrame:
    """De-duplicated charging sites (Open Charge Map ∪ OSM ∪ NCR 2021), WGS84."""
    path = SITES if SITES.exists() else PROCESSED / "charging_sites.parquet"
    return read_gdf(path).to_crs(4326)


def write_reference_copies(sites: gpd.GeoDataFrame) -> None:
    """Called by features.build: refresh the committed compact copies."""
    from chargescape.utils.io import write_df, write_gdf

    write_gdf(sites.to_crs(4326), SITES)
    lad = read_gdf(INTERIM / "census" / "lad24_london.parquet")
    keep = [c for c in lad.columns if c.lower().startswith("lad24") or c == "geometry"]
    write_gdf(lad[keep], BOROUGHS)
    write_df(pd.read_parquet(INTERIM / "chargepoints" / "dft_evci_london_la.parquet"), DFT_LA)
