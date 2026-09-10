"""Demand-side socio-demographic layers for Greater London at LSOA 2021 level.

Sources (all Open Government Licence v3.0):
  * ONS Open Geography Portal (ArcGIS FeatureServer, no key needed): LSOA21 boundaries (BGC),
    LSOA21/OA21 population-weighted centroids, OA21->LSOA21->MSOA21->LAD22 lookup, LAD Dec-2024 boundaries.
  * Census 2021 (England & Wales) topic-summary tables via the nomis API (no key needed for <25k cells/call).
  * English Indices of Deprivation 2025 (MHCLG), File 7, already on LSOA 2021 geography.

Run from the repo root:  PYTHONPATH=src python -m chargescape.data.census
Idempotent: raw responses are cached under data/raw/census/, interim parquet files are rebuilt cheaply.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import geopandas as gpd
import pandas as pd
import requests

from chargescape.utils.http import UA, download, get_json
from chargescape.utils.paths import INTERIM, RAW

log = logging.getLogger("chargescape.census")

RAW_DIR = RAW / "census"
INTERIM_DIR = INTERIM / "census"

# --------------------------------------------------------------------------------------------------
# ONS Open Geography Portal
# --------------------------------------------------------------------------------------------------
ARCGIS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
SERVICES = {
    # Lower layer Super Output Areas (December 2021) Boundaries EW BGC (generalised 20m, clipped to coastline)
    "lsoa21_bgc": "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5",
    # LSOA (Dec 2021) population weighted centroids
    "lsoa21_pwc": "LSOA_PopCentroids_EW_2021_V4",
    # OA (Dec 2021) population weighted centroids
    "oa21_pwc": "OA_December_2021_EW_PWC_V4",
    # OA21 -> LSOA21 -> MSOA21 -> LAD22 exact-fit lookup (table, no geometry)
    "oa_lsoa_msoa_lad_lu": "OA_LSOA_MSOA_EW_DEC_2021_LU_v3",
    # Local Authority Districts (December 2024) Boundaries UK BGC
    "lad24_bgc": "Local_Authority_Districts_December_2024_Boundaries_UK_BGC",
}
BNG = "EPSG:27700"

# ONS statistical definition of Inner London (E13000001): 13 boroughs + City of London.
INNER_LONDON_LAD = {
    "E09000001",
    "E09000007",
    "E09000012",
    "E09000013",
    "E09000014",
    "E09000019",
    "E09000020",
    "E09000022",
    "E09000023",
    "E09000025",
    "E09000028",
    "E09000030",
    "E09000032",
    "E09000033",
}

# --------------------------------------------------------------------------------------------------
# nomis (Census 2021)
# --------------------------------------------------------------------------------------------------
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"
NOMIS_LONDON = "2013265927"  # nomis internal id of region London (E12000007)
GEOG_LSOA = f"{NOMIS_LONDON}TYPE151"  # 2021 LSOAs within London (4,994)
GEOG_MSOA = f"{NOMIS_LONDON}TYPE152"  # 2021 MSOAs within London (983)
NOMIS_MAX_CELLS = 25_000  # hard cap per call without an API key
N_LONDON_LSOA = 4994
N_LONDON_MSOA = 1002  # MSOA 2021 (the 2011 geography had 983)

# table -> (nomis dataset id, category dimension, categories to fetch or None for all)
TABLES: dict[str, tuple[str, str, list[str] | None]] = {
    "TS001": ("NM_2021_1", "c2021_restype_3", None),  # usual residents by residence type
    "TS003": ("NM_2023_1", "c2021_hhcomp_15", ["0"]),  # household composition (total only = household count)
    "TS007A": ("NM_2020_1", "c2021_age_19", None),  # age, five-year bands
    "TS044": ("NM_2062_1", "c2021_acctype_9", None),  # accommodation type
    "TS045": ("NM_2063_1", "c2021_cars_5", None),  # car or van availability
    "TS054": ("NM_2072_1", "c2021_tenure_9", None),  # tenure
    "TS061": ("NM_2078_1", "c2021_ttwmeth_12", None),  # method used to travel to work
    "TS062": ("NM_2079_1", "c2021_nssec_10", None),  # NS-SeC
}
# TS045A (number of cars or vans in the area) is NOT published at LSOA level (OBS_STATUS=Q, missing);
# it is available at MSOA level and is used to calibrate the cars-per-household estimate.
TS045A = ("NM_2324_1", "c2021_cars_total")

# --------------------------------------------------------------------------------------------------
# IMD 2025
# --------------------------------------------------------------------------------------------------
IMD_URL = (
    "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
    "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
)


# ==================================================================================================
# helpers
# ==================================================================================================
def _chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _arcgis_query(service: str, params: dict, *, cache_name: str, layer: int = 0, page: int = 2000) -> list:
    """Paginated FeatureServer query. Returns GeoJSON features (f=geojson) or attribute dicts (f=json).

    Raw pages are concatenated and cached at data/raw/census/geoportal/<cache_name>.json.
    """
    cache = RAW_DIR / "geoportal" / f"{cache_name}.json"
    if cache.exists() and cache.stat().st_size > 2:
        return json.loads(cache.read_text())
    url = f"{ARCGIS}/{service}/FeatureServer/{layer}/query"
    fmt = params.get("f", "json")
    out: list = []
    offset = 0
    while True:
        p = {**params, "resultOffset": offset, "resultRecordCount": page}
        for attempt in range(4):
            try:
                r = requests.post(url, data=p, headers={"User-Agent": UA}, timeout=180)
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    raise RuntimeError(data["error"])
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise
                log.warning("arcgis retry %s (%s)", url, e)
                time.sleep(3 * (attempt + 1))
        feats = data.get("features", [])
        if fmt == "geojson":
            out.extend(feats)
            more = data.get("properties", {}).get("exceededTransferLimit", False)
        else:
            out.extend(f["attributes"] for f in feats)
            more = data.get("exceededTransferLimit", False)
        if not feats or not more:
            break
        offset += len(feats)
        time.sleep(0.3)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def _features_to_gdf(features: list) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame.from_features(features, crs=BNG)
    return gdf


def _in_clause(field: str, codes: list[str]) -> str:
    return f"{field} IN ({','.join(repr(c) for c in codes)})"


# ==================================================================================================
# A. geographies
# ==================================================================================================
def fetch_lookup() -> pd.DataFrame:
    """LSOA21 -> MSOA21 -> LAD22 lookup for the 33 London LADs (from the ONS OA/LSOA/MSOA/LAD exact-fit lookup)."""
    out = INTERIM_DIR / "lsoa21_lookup_london.parquet"
    rows = _arcgis_query(
        SERVICES["oa_lsoa_msoa_lad_lu"],
        {
            "where": "LAD22CD LIKE 'E09%'",
            "outFields": "LSOA21CD,LSOA21NM,MSOA21CD,MSOA21NM,LAD22CD,LAD22NM",
            "returnDistinctValues": "true",
            "orderByFields": "LSOA21CD",
            "f": "json",
        },
        cache_name="lsoa21_msoa21_lad22_london",
        page=1000,
    )
    df = pd.DataFrame(rows).drop_duplicates("LSOA21CD").sort_values("LSOA21CD").reset_index(drop=True)
    df.columns = [c.lower() for c in df.columns]
    df["inner_london"] = df["lad22cd"].isin(INNER_LONDON_LAD)
    assert len(df) == N_LONDON_LSOA, f"expected {N_LONDON_LSOA} London LSOA21, got {len(df)}"
    assert df["lad22cd"].nunique() == 33
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


def fetch_oa_lookup() -> pd.DataFrame:
    """OA21 -> LSOA21 lookup for London (26,369 OAs)."""
    out = INTERIM_DIR / "oa21_lsoa21_lookup_london.parquet"
    rows = _arcgis_query(
        SERVICES["oa_lsoa_msoa_lad_lu"],
        {
            "where": "LAD22CD LIKE 'E09%'",
            "outFields": "OA21CD,LSOA21CD,MSOA21CD,LAD22CD",
            "orderByFields": "OA21CD",
            "f": "json",
        },
        cache_name="oa21_lsoa21_london",
        page=1000,
    )
    df = pd.DataFrame(rows).drop_duplicates("OA21CD")
    df.columns = [c.lower() for c in df.columns]
    df.to_parquet(out, index=False)
    return df


def fetch_geographies() -> dict[str, gpd.GeoDataFrame | pd.DataFrame]:
    """Download London LSOA21 boundaries, LAD24 boroughs, Greater London outline and population-weighted centroids."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    lookup = fetch_lookup()
    codes = lookup["lsoa21cd"].tolist()

    # --- LSOA21 boundaries (BGC), queried by code in chunks so that no non-London LSOA slips in
    feats: list = []
    for i, chunk in enumerate(_chunks(codes, 300)):
        feats += _arcgis_query(
            SERVICES["lsoa21_bgc"],
            {
                "where": _in_clause("LSOA21CD", chunk),
                "outFields": "LSOA21CD,LSOA21NM,BNG_E,BNG_N,LAT,LONG",
                "outSR": 27700,
                "f": "geojson",
            },
            cache_name=f"lsoa21_bgc_london_{i:02d}",
        )
    lsoa = _features_to_gdf(feats)
    lsoa.columns = [c.lower() for c in lsoa.columns]
    lsoa = lsoa.drop_duplicates("lsoa21cd").merge(
        lookup[["lsoa21cd", "msoa21cd", "msoa21nm", "lad22cd", "lad22nm", "inner_london"]],
        on="lsoa21cd",
        how="left",
    )
    lsoa["area_km2"] = lsoa.geometry.area / 1e6
    assert len(lsoa) == N_LONDON_LSOA, f"boundaries: expected {N_LONDON_LSOA}, got {len(lsoa)}"
    lsoa = lsoa.sort_values("lsoa21cd").reset_index(drop=True)
    lsoa.to_parquet(INTERIM_DIR / "lsoa21_london.parquet", index=False)
    lsoa.to_crs(4326).to_parquet(INTERIM_DIR / "lsoa21_london_wgs84.parquet", index=False)

    # --- London boroughs (LAD Dec 2024 BGC) + Greater London dissolve
    lad_feats = _arcgis_query(
        SERVICES["lad24_bgc"],
        {
            "where": "LAD24CD LIKE 'E09%'",
            "outFields": "LAD24CD,LAD24NM,BNG_E,BNG_N,LAT,LONG",
            "outSR": 27700,
            "f": "geojson",
        },
        cache_name="lad24_bgc_london",
    )
    lad = _features_to_gdf(lad_feats)
    lad.columns = [c.lower() for c in lad.columns]
    lad["inner_london"] = lad["lad24cd"].isin(INNER_LONDON_LAD)
    lad["area_km2"] = lad.geometry.area / 1e6
    assert len(lad) == 33
    lad = lad.sort_values("lad24cd").reset_index(drop=True)
    lad.to_parquet(INTERIM_DIR / "lad24_london.parquet", index=False)
    gl = lad.dissolve().reset_index(drop=True)[["geometry"]]
    gl["name"] = "Greater London"
    gl["area_km2"] = gl.geometry.area / 1e6
    gl.to_parquet(INTERIM_DIR / "greater_london.parquet", index=False)

    # --- population weighted centroids (envelope query, then filter to London codes)
    xmin, ymin, xmax, ymax = gl.total_bounds
    env = {
        "geometry": f"{xmin:.0f},{ymin:.0f},{xmax:.0f},{ymax:.0f}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 27700,
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": 27700,
        "f": "geojson",
    }
    pwc = _features_to_gdf(
        _arcgis_query(
            SERVICES["lsoa21_pwc"],
            {**env, "where": "1=1", "outFields": "LSOA21CD"},
            cache_name="lsoa21_pwc_london_bbox",
        )
    )
    pwc.columns = [c.lower() for c in pwc.columns]
    pwc = (
        pwc[pwc["lsoa21cd"].isin(codes)]
        .drop_duplicates("lsoa21cd")
        .sort_values("lsoa21cd")
        .reset_index(drop=True)
    )
    assert len(pwc) == N_LONDON_LSOA, f"LSOA PWC: expected {N_LONDON_LSOA}, got {len(pwc)}"
    pwc["pwc_x"] = pwc.geometry.x
    pwc["pwc_y"] = pwc.geometry.y
    ll = pwc.to_crs(4326)
    pwc["pwc_lon"] = ll.geometry.x
    pwc["pwc_lat"] = ll.geometry.y
    pwc.to_parquet(INTERIM_DIR / "lsoa21_pwc_london.parquet", index=False)

    oa_lu = fetch_oa_lookup()
    oa_pwc = _features_to_gdf(
        _arcgis_query(
            SERVICES["oa21_pwc"],
            {**env, "where": "1=1", "outFields": "OA21CD"},
            cache_name="oa21_pwc_london_bbox",
        )
    )
    oa_pwc.columns = [c.lower() for c in oa_pwc.columns]
    oa_pwc = (
        oa_pwc.merge(oa_lu, on="oa21cd", how="inner")
        .drop_duplicates("oa21cd")
        .sort_values("oa21cd")
        .reset_index(drop=True)
    )
    assert len(oa_pwc) == len(oa_lu), f"OA PWC: expected {len(oa_lu)}, got {len(oa_pwc)}"
    oa_pwc.to_parquet(INTERIM_DIR / "oa21_pwc_london.parquet", index=False)

    log.info(
        "geographies: %d LSOA, %d LAD, %d LSOA PWC, %d OA PWC", len(lsoa), len(lad), len(pwc), len(oa_pwc)
    )
    return {
        "lookup": lookup,
        "lsoa": lsoa,
        "lad": lad,
        "greater_london": gl,
        "lsoa_pwc": pwc,
        "oa_pwc": oa_pwc,
    }


# ==================================================================================================
# B. Census 2021 via nomis
# ==================================================================================================
def _nomis_codelist(ds: str, dim: str) -> list[tuple[str, str]]:
    d = get_json(f"{NOMIS}/{ds}/{dim}.def.sdmx.json", cache_dir=RAW_DIR / "nomis" / "meta")
    # nomis serialises numeric codes as JSON ints; keep everything as str for URL building and label mapping
    return [
        (str(c["value"]), c["description"]["value"])
        for c in d["structure"]["codelists"]["codelist"][0]["code"]
    ]


def _nomis_csv(ds: str, dim: str, cats: list[str], geography: str, cache_tag: str) -> pd.DataFrame:
    params = {
        "geography": geography,
        dim: ",".join(cats),
        "measures": "20100",
        "select": f"GEOGRAPHY_CODE,GEOGRAPHY_NAME,{dim.upper()},{dim.upper()}_NAME,OBS_VALUE,OBS_STATUS,RECORD_COUNT",
    }
    url = f"{NOMIS}/{ds}.data.csv?{urlencode(params)}"
    dest = RAW_DIR / "nomis" / f"{cache_tag}.csv"
    download(url, dest)
    df = pd.read_csv(dest, dtype=str)
    if "GEOGRAPHY_CODE" not in df.columns:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"nomis returned an unexpected payload for {url}")
    n_expected = int(df["RECORD_COUNT"].iloc[0]) if len(df) else 0
    if len(df) != n_expected:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"nomis truncated response for {cache_tag}: {len(df)} of {n_expected} rows")
    return df


def fetch_nomis_table(
    table: str,
    ds: str,
    dim: str,
    cats: list[str] | None,
    geography: str = GEOG_LSOA,
    n_geog: int | None = N_LONDON_LSOA,
) -> pd.DataFrame:
    """Fetch one Census 2021 table for all areas of `geography` as a tidy frame (one row per area x category).

    n_geog: expected number of areas (asserted), or None to accept whatever nomis returns.
    """
    codelist = _nomis_codelist(ds, dim)
    labels = dict(codelist)
    if cats is None:
        cats = [c for c, _ in codelist]
    per_call = max(1, NOMIS_MAX_CELLS // (n_geog or N_LONDON_LSOA))  # 5 cats x 4,994 LSOAs = 24,970 < 25,000
    parts = []
    for i, chunk in enumerate(_chunks(cats, per_call)):
        parts.append(_nomis_csv(ds, dim, chunk, geography, f"{table}_{geography}_{i:02d}"))
        time.sleep(0.5)
    raw = pd.concat(parts, ignore_index=True)
    tidy = pd.DataFrame(
        {
            "geography_code": raw["GEOGRAPHY_CODE"],
            "geography_name": raw["GEOGRAPHY_NAME"],
            "table": table,
            "category_code": raw[dim.upper()].astype(int),
            "category": raw[dim.upper()].map(labels),
            "value": pd.to_numeric(raw["OBS_VALUE"], errors="coerce").astype("Int64"),
            "obs_status": raw["OBS_STATUS"],
        }
    )
    n_areas = tidy["geography_code"].nunique()
    if n_geog is not None:
        assert n_areas == n_geog, f"{table}: {n_areas} areas, expected {n_geog}"
    assert len(tidy) == n_areas * len(cats), f"{table}: {len(tidy)} rows, expected {n_areas * len(cats)}"
    return tidy


def fetch_census_tables() -> dict[str, pd.DataFrame]:
    """Fetch all configured Census 2021 tables for London LSOA21 and save tidy parquet per table."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for table, (ds, dim, cats) in TABLES.items():
        tidy = fetch_nomis_table(table, ds, dim, cats)
        tidy.to_parquet(INTERIM_DIR / f"{table.lower()}_lsoa21_london.parquet", index=False)
        out[table] = tidy
        log.info("%s: %d rows, %d categories", table, len(tidy), tidy["category_code"].nunique())
    # MSOA-level calibration set for the car-count estimate (TS045A is not published at LSOA level).
    ts045a = fetch_nomis_table("TS045A", TS045A[0], TS045A[1], ["0"], GEOG_MSOA, n_geog=N_LONDON_MSOA)
    ts045_msoa = fetch_nomis_table(
        "TS045", TABLES["TS045"][0], TABLES["TS045"][1], None, GEOG_MSOA, n_geog=N_LONDON_MSOA
    )
    ts045a.to_parquet(INTERIM_DIR / "ts045a_msoa21_london.parquet", index=False)
    ts045_msoa.to_parquet(INTERIM_DIR / "ts045_msoa21_london.parquet", index=False)
    out["TS045A_msoa"] = ts045a
    out["TS045_msoa"] = ts045_msoa
    return out


# ==================================================================================================
# B2. IMD 2025
# ==================================================================================================
_IMD_DOMAIN = [  # matched in this order (longest / most specific prefixes first)
    ("income deprivation affecting children index (idaci)", "idaci"),
    ("income deprivation affecting older people (idaopi)", "idaopi"),
    ("index of multiple deprivation (imd)", "imd"),
    ("education, skills and training", "education"),
    ("health deprivation and disability", "health"),
    ("barriers to housing and services", "barriers"),
    ("living environment", "living_env"),
    ("employment", "employment"),
    ("income", "income"),
    ("crime", "crime"),
]


def _imd_col(name: str) -> str:
    s = name.strip()
    fixed = {
        "LSOA code (2021)": "lsoa21cd",
        "LSOA name (2021)": "lsoa21nm",
        "Local Authority District code (2024)": "lad24cd",
        "Local Authority District name (2024)": "lad24nm",
    }
    if s in fixed:
        return fixed[s]
    low = s.lower()
    low = re.sub(r"\(where 1 is most deprived[^)]*\)?", "", low)  # one source header is truncated before ")"
    low = re.sub(r"\(rate\)", "", low).strip()
    for k, v in _IMD_DOMAIN:
        if low.startswith(k):
            rest = low[len(k) :].strip()
            rest = re.sub(r"[^a-z0-9]+", "_", rest).strip("_")
            return f"{v}_{rest}" if rest else v
    return re.sub(r"[^a-z0-9]+", "_", low).strip("_")


def fetch_imd(lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    """English Indices of Deprivation 2025, File 7 (all ranks/scores/deciles + population denominators), London LSOA21."""
    if lookup is None:
        lookup = fetch_lookup()
    dest = RAW_DIR / "imd" / Path(IMD_URL).name
    download(IMD_URL, dest)
    df = pd.read_csv(dest, encoding="utf-8-sig")
    df.columns = [_imd_col(c) for c in df.columns]
    df = df[df["lsoa21cd"].isin(lookup["lsoa21cd"])].copy()
    assert len(df) == N_LONDON_LSOA, f"IMD: expected {N_LONDON_LSOA} London LSOAs, got {len(df)}"
    # London-relative rank / decile (England deciles are heavily skewed for London)
    df["imd_rank_london"] = df["imd_rank"].rank(method="first").astype(int)
    df["imd_decile_london"] = pd.qcut(df["imd_rank_london"], 10, labels=False) + 1
    df = df.sort_values("lsoa21cd").reset_index(drop=True)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM_DIR / "imd2025_lsoa21_london.parquet", index=False)
    return df


# ==================================================================================================
# C. wide feature table
# ==================================================================================================
def _wide(tidy: pd.DataFrame, prefix: str) -> pd.DataFrame:
    w = tidy.pivot(index="geography_code", columns="category_code", values="value")
    w.columns = [f"{prefix}_{c}" for c in w.columns]
    return w.astype("float64")


def _share(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den.where(den > 0)).astype("float64")


def cars_3plus_multiplier(msoas: set[str] | None = None) -> float:
    """Mean number of cars in '3 or more cars' households, London-wide, from TS045A vs TS045 at MSOA level.

    TS045A (total cars or vans in the area) is not published at LSOA level, so the LSOA car stock is estimated
    as 1*hh_1_car + 2*hh_2_cars + k3*hh_3plus_cars with k3 chosen so that the estimate reproduces the published
    London MSOA total exactly. Falls back to 3.0 if the MSOA files are missing.
    """
    try:
        a = pd.read_parquet(INTERIM_DIR / "ts045a_msoa21_london.parquet")
        m = _wide(pd.read_parquet(INTERIM_DIR / "ts045_msoa21_london.parquet"), "c")
    except FileNotFoundError:
        log.warning("TS045A MSOA calibration files missing; using 3.0 cars for '3 or more' households")
        return 3.0
    if msoas is not None:
        m = m[m.index.isin(msoas)]
    tot = a.set_index("geography_code")["value"].astype(float).reindex(m.index)
    return float((tot - m["c_2"] - 2 * m["c_3"]).sum() / m["c_4"].sum())


def build_lsoa_features(save: bool = True) -> pd.DataFrame:
    """Join geographies, census tables and IMD into one wide LSOA21 table with clean feature names."""
    p = INTERIM_DIR
    lookup = pd.read_parquet(p / "lsoa21_lookup_london.parquet")
    lsoa = gpd.read_parquet(p / "lsoa21_london.parquet")[["lsoa21cd", "area_km2"]]
    pwc = gpd.read_parquet(p / "lsoa21_pwc_london.parquet")[
        ["lsoa21cd", "pwc_x", "pwc_y", "pwc_lon", "pwc_lat"]
    ]
    t = {k: pd.read_parquet(p / f"{k.lower()}_lsoa21_london.parquet") for k in TABLES}

    f = (
        lookup.merge(lsoa, on="lsoa21cd", how="left")
        .merge(pwc, on="lsoa21cd", how="left")
        .set_index("lsoa21cd")
    )

    # TS001 population
    w = _wide(t["TS001"], "p")
    f["population"] = w["p_0"]
    f["population_in_households"] = w["p_1"]
    f["population_communal"] = w["p_2"]

    # TS003 household count (cross-check for TS045 total)
    f["households_ts003"] = _wide(t["TS003"], "h")["h_0"]

    # TS045 cars / vans
    w = _wide(t["TS045"], "c")
    f["households"] = w["c_0"]
    f["hh_no_car"] = w["c_1"]
    f["hh_1_car"] = w["c_2"]
    f["hh_2_cars"] = w["c_3"]
    f["hh_3plus_cars"] = w["c_4"]
    k3 = cars_3plus_multiplier(set(lookup["msoa21cd"]))
    log.info("cars_est: mean cars in '3 or more' households calibrated on MSOA TS045A = %.4f", k3)
    f["cars_est"] = f["hh_1_car"] + 2 * f["hh_2_cars"] + k3 * f["hh_3plus_cars"]
    f["cars_per_household"] = _share(f["cars_est"], f["households"])
    f["share_no_car"] = _share(f["hh_no_car"], f["households"])
    f["share_1_car"] = _share(f["hh_1_car"], f["households"])
    f["share_2plus_cars"] = _share(f["hh_2_cars"] + f["hh_3plus_cars"], f["households"])
    # TS044 accommodation type (households)
    w = _wide(t["TS044"], "a")
    f["n_detached"] = w["a_1"]
    f["n_semi_detached"] = w["a_2"]
    f["n_terraced"] = w["a_3"]
    f["n_flat_purpose_built"] = w["a_4"]
    f["n_flat_converted"] = w["a_5"] + w["a_6"]
    f["n_flat_commercial"] = w["a_7"]
    f["n_caravan_temporary"] = w["a_8"]
    f["share_detached"] = _share(w["a_1"], w["a_0"])
    f["share_semi_detached"] = _share(w["a_2"], w["a_0"])
    f["share_terraced"] = _share(w["a_3"], w["a_0"])
    f["share_detached_semi"] = _share(w["a_1"] + w["a_2"], w["a_0"])
    f["share_house"] = _share(w["a_1"] + w["a_2"] + w["a_3"], w["a_0"])
    f["share_flat"] = _share(w["a_4"] + w["a_5"] + w["a_6"] + w["a_7"], w["a_0"])
    f["share_flat_purpose_built"] = _share(w["a_4"], w["a_0"])

    # TS054 tenure (households)
    w = _wide(t["TS054"], "t")
    f["share_owner_occupied"] = _share(w["t_1001"], w["t_0"])
    f["share_owned_outright"] = _share(w["t_1"], w["t_0"])
    f["share_shared_ownership"] = _share(w["t_1002"], w["t_0"])
    f["share_social_rented"] = _share(w["t_1003"], w["t_0"])
    f["share_private_rented"] = _share(w["t_1004"], w["t_0"])
    f["share_rent_free"] = _share(w["t_8"], w["t_0"])

    # TS061 travel to work (residents 16+ in employment, incl. those working from home)
    w = _wide(t["TS061"], "w")
    f["workers_16plus"] = w["w_0"]
    f["share_wfh"] = _share(w["w_1"], w["w_0"])
    f["share_drive_to_work"] = _share(w["w_7"], w["w_0"])
    f["share_drive_to_work_excl_wfh"] = _share(w["w_7"], w["w_0"] - w["w_1"])
    f["share_car_passenger"] = _share(w["w_8"], w["w_0"])
    f["share_public_transport"] = _share(w["w_2"] + w["w_3"] + w["w_4"], w["w_0"])
    f["share_active_travel"] = _share(w["w_9"] + w["w_10"], w["w_0"])

    # TS062 NS-SeC (residents 16+)
    w = _wide(t["TS062"], "s")
    f["residents_16plus"] = w["s_0"]
    f["share_nssec_higher_managerial"] = _share(w["s_1"], w["s_0"])
    f["share_nssec_managerial_professional"] = _share(w["s_1"] + w["s_2"], w["s_0"])
    f["share_nssec_intermediate"] = _share(w["s_3"], w["s_0"])
    f["share_nssec_small_employers"] = _share(w["s_4"], w["s_0"])
    f["share_nssec_routine_semiroutine"] = _share(w["s_6"] + w["s_7"], w["s_0"])
    f["share_nssec_never_worked_ltu"] = _share(w["s_8"], w["s_0"])
    f["share_nssec_students"] = _share(w["s_9"], w["s_0"])

    # TS007A age bands
    w = _wide(t["TS007A"], "g")
    f["share_age_under_20"] = _share(w[["g_1", "g_2", "g_3", "g_4"]].sum(axis=1), w["g_0"])
    f["share_age_20_39"] = _share(w[["g_5", "g_6", "g_7", "g_8"]].sum(axis=1), w["g_0"])
    f["share_age_40_64"] = _share(w[["g_9", "g_10", "g_11", "g_12", "g_13"]].sum(axis=1), w["g_0"])
    f["share_age_65plus"] = _share(w[["g_14", "g_15", "g_16", "g_17", "g_18"]].sum(axis=1), w["g_0"])

    # densities
    f["pop_density_km2"] = _share(f["population"], f["area_km2"])
    f["hh_density_km2"] = _share(f["households"], f["area_km2"])

    # IMD 2025
    imd = pd.read_parquet(p / "imd2025_lsoa21_london.parquet").set_index("lsoa21cd")
    keep = [
        c
        for c in imd.columns
        if re.match(
            r"^(imd|income|employment|barriers|living_env|health|crime|education|idaci|idaopi)_(score|rank|decile)",
            c,
        )
    ]
    keep = list(
        dict.fromkeys(keep + ["imd_rank_london", "imd_decile_london"])
    )  # dedupe: regex already matches these
    f = f.join(imd[keep], how="left")

    f = f.reset_index()
    f.attrs["cars_3plus_multiplier"] = k3  # informational only (attrs are not persisted to parquet)
    if save:
        f.to_parquet(p / "lsoa21_london_features.parquet", index=False)
    return f


# ==================================================================================================
def _summary(f: pd.DataFrame) -> None:
    print("\n=== lsoa21_london_features ===")
    print(f"rows: {len(f)}  cols: {f.shape[1]}")
    print(f"population total: {f['population'].sum():,.0f}   households: {f['households'].sum():,.0f}")
    print(
        f"cars_est total: {f['cars_est'].sum():,.0f}  (3+ multiplier {f.attrs.get('cars_3plus_multiplier', float('nan')):.3f})"
    )
    na = f.isna().sum()
    na = na[na > 0]
    print("columns with missing values:" if len(na) else "no missing values", dict(na) if len(na) else "")
    print("columns:", list(f.columns))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    g = fetch_geographies()
    fetch_census_tables()
    fetch_imd(g["lookup"])
    f = build_lsoa_features()
    _summary(f)


if __name__ == "__main__":
    main()
