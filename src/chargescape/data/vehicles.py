"""DfT / DVLA vehicle licensing statistics for Greater London (demand side: EV uptake and car stock).

Tables (all Open Government Licence v3.0, Department for Transport + DVLA; release of 15 July 2026, data to end
of 2026 Q1 = 31 March 2026):

  VEH0145  df_VEH0145.csv  Licensed plug-in vehicles (PiVs) at end of quarter by fuel type, keepership and LSOA: UK
  VEH0135  df_VEH0135.csv  Licensed ultra low emission vehicles (ULEVs) at end of quarter by fuel type, keepership
                           and LSOA: UK
  VEH0125  df_VEH0125.csv  Vehicles at end of quarter by licence status, body type, keepership and LSOA: UK (~240 MB)
  VEH0142  veh0142.ods     Licensed PiVs at end of quarter by body type, fuel type, keepership and upper/lower tier
                           local authority: UK (time series from 2009 Q4)

The LSOA files are already on LSOA 2021 geography (column LSOA21CD), so they join directly to the census layer.

Disclosure control in the source (observed, not documented by DfT): counts of 1-4 are shown as "[c]" (the smallest
visible non-zero value is 5), and many small fuel x keepership rows are omitted altogether, so the files are NOT a
full cross-product and summing component rows under-counts. Published "Total" rows (Fuel = Total, Keepership = Total,
BodyType = Total) are therefore used as the authoritative figures; component rows are kept as partial information.

Run from the repo root:  PYTHONPATH=src python -m chargescape.data.vehicles
Idempotent: raw files are cached under data/raw/vehicles/, interim parquet files are rebuilt from them.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

from chargescape.utils.http import download
from chargescape.utils.paths import INTERIM, RAW

log = logging.getLogger("chargescape.vehicles")

RAW_DIR = RAW / "vehicles"
INTERIM_DIR = INTERIM / "vehicles"
CENSUS_DIR = INTERIM / "census"

DFT_FILES = {
    "VEH0145": {
        "url": "https://assets.publishing.service.gov.uk/media/6a54d2ea9e9c95844ae64da1/df_VEH0145.csv",
        "file": "df_VEH0145.csv",
        "title": "Licensed plug-in vehicles (PiVs) at the end of the quarter by fuel type, keepership and LSOA: UK",
    },
    "VEH0135": {
        "url": "https://assets.publishing.service.gov.uk/media/6a54d2eb2467584757371e08/df_VEH0135.csv",
        "file": "df_VEH0135.csv",
        "title": "Licensed ultra low emission vehicles (ULEVs) at the end of the quarter by fuel type, keepership and LSOA: UK",
    },
    "VEH0125": {
        "url": "https://assets.publishing.service.gov.uk/media/6a54d2f5a6586e258d371d73/df_VEH0125.csv",
        "file": "df_VEH0125.csv",
        "title": "Vehicles at the end of the quarter by licence status, body type, keepership and LSOA: UK",
    },
    "VEH0142": {
        "url": "https://assets.publishing.service.gov.uk/media/6a56140b2cbe5d1c179a6454/veh0142.ods",
        "file": "veh0142.ods",
        "title": "Licensed PiVs at the end of the quarter by body type, fuel type, keepership and upper and lower tier local authority: UK",
    },
}
LANDING_DATA_FILES = (
    "https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files"
)
LANDING_DATA_TABLES = (
    "https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-tables"
)

# A "[c]" cell hides a count of 1..4 (smallest visible non-zero value in the files is 5): midpoint used for estimates.
SUPPRESSED_EST = 2.5

# extra ONS codes kept in the LA time series next to the 33 London boroughs
LA_CONTEXT_CODES = {"E12000007": "London", "E92000001": "England", "K02000001": "United Kingdom"}

QUARTER_RE = re.compile(r"^(\d{4}) Q([1-4])$")


# ==================================================================================================
# helpers
# ==================================================================================================
def _london_lsoas() -> pd.DataFrame:
    p = CENSUS_DIR / "lsoa21_lookup_london.parquet"
    if p.exists():
        return pd.read_parquet(p)
    from chargescape.data.census import fetch_lookup  # lazy import: hits the ONS geoportal

    return fetch_lookup()


def quarter_end(q: str) -> pd.Timestamp:
    m = QUARTER_RE.match(q)
    y, n = int(m.group(1)), int(m.group(2))
    return pd.Timestamp(year=y, month=3 * n, day=1) + pd.offsets.MonthEnd(0)


def _to_long(df: pd.DataFrame, id_cols: list[str]) -> pd.DataFrame:
    """Melt DfT wide quarter columns into long format with numeric value + marker ('c' for [c], 'z' for [z], ...)."""
    qcols = [c for c in df.columns if QUARTER_RE.match(c)]
    long = df.melt(id_vars=id_cols, value_vars=qcols, var_name="quarter", value_name="raw")
    raw = long["raw"].astype("string").str.strip()
    long["value"] = pd.to_numeric(raw.str.replace(",", "", regex=False), errors="coerce").astype("float64")
    long["marker"] = raw.where(raw.str.startswith("[", na=False)).str.strip("[]")
    long["period_end"] = long["quarter"].map({q: quarter_end(q) for q in qcols})
    long = long.drop(columns="raw")
    return long.sort_values(id_cols + ["period_end"]).reset_index(drop=True)


def _read_lsoa_file(
    table: str, codes: set[str], id_cols: list[str], min_year: int | None = None
) -> pd.DataFrame:
    """Download a DfT LSOA-level CSV (cached) and return the London rows in long format."""
    meta = DFT_FILES[table]
    path = download(meta["url"], RAW_DIR / meta["file"], timeout=600)
    head = pd.read_csv(path, nrows=0)
    usecols = [
        c
        for c in head.columns
        if c in id_cols or (QUARTER_RE.match(c) and (min_year is None or int(c[:4]) >= min_year))
    ]
    parts = []
    for chunk in pd.read_csv(path, dtype=str, usecols=usecols, chunksize=250_000):
        parts.append(chunk[chunk["LSOA21CD"].isin(codes)])
    df = pd.concat(parts, ignore_index=True)
    ren = {"LSOA21CD": "lsoa21cd", "LSOA21NM": "lsoa21nm"}
    df = df.rename(columns=ren)
    long = _to_long(df, [ren.get(c, c) for c in id_cols])
    long.insert(0, "table", table)
    return long


# ---------------------------------------------------------------------------------------- ODS reader
_NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_NS_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def read_ods_sheet(path: Path, sheet: str) -> list[list]:
    """Minimal stdlib ODS reader (odfpy is not installed). Returns rows as lists of cell values."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    for tbl in root.iter(f"{_NS_T}table"):
        if tbl.get(f"{_NS_T}name") != sheet:
            continue
        rows: list[list] = []
        for row in tbl.iter(f"{_NS_T}table-row"):
            rrep = int(row.get(f"{_NS_T}number-rows-repeated", "1"))
            cells: list = []
            for cell in row:
                if cell.tag not in (f"{_NS_T}table-cell", f"{_NS_T}covered-table-cell"):
                    continue
                crep = int(cell.get(f"{_NS_T}number-columns-repeated", "1"))
                vt = cell.get(f"{_NS_O}value-type")
                if vt in ("float", "percentage", "currency"):
                    val: object = float(cell.get(f"{_NS_O}value"))
                elif vt == "date":
                    val = cell.get(f"{_NS_O}date-value")
                else:
                    ps = cell.findall(f".//{_NS_X}p")
                    val = "\n".join("".join(p.itertext()) for p in ps) if ps else None
                if crep > 1000:  # filler up to the sheet's column limit
                    crep = 1
                cells.extend([val] * crep)
            while cells and cells[-1] in (None, ""):
                cells.pop()
            if rrep > 1000:  # filler up to the sheet's row limit
                rrep = 1
            rows.extend([list(cells) for _ in range(rrep)])
        return rows
    raise KeyError(f"sheet {sheet!r} not found in {path}")


def read_veh0142(path: Path) -> pd.DataFrame:
    """Parse the VEH0142 sheet into a wide DataFrame (one row per body type x fuel x keepership x area)."""
    rows = read_ods_sheet(path, "VEH0142")
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "Units")
    header = [str(c).strip() for c in rows[hdr_i]]
    data = [r + [None] * (len(header) - len(r)) for r in rows[hdr_i + 1 :] if len(r) >= 7 and r[5]]
    return pd.DataFrame([r[: len(header)] for r in data], columns=header)


# ==================================================================================================
# latest-quarter snapshots (built from the published Total rows)
# ==================================================================================================
def _pick(s: pd.DataFrame, out: pd.DataFrame, mask: pd.Series, name: str, missing_as_zero: bool) -> None:
    """Copy one published cell per LSOA into `out` as <name> (NaN if suppressed) + <name>_est + <name>_flag.

    flag: 'ok' observed, 'c' suppressed (1-4, est = SUPPRESSED_EST), 'missing' row absent from the file
    (est = 0 for Total rows where absence means nothing to total, else NaN).
    """
    r = s[mask].drop_duplicates("lsoa21cd").set_index("lsoa21cd")
    val = r["value"].reindex(out.index)
    mk = r["marker"].reindex(out.index)
    present = out.index.isin(r.index)
    out[name] = val
    flag = pd.Series("missing", index=out.index)
    flag[present] = "ok"
    flag[mk.eq("c").fillna(False).to_numpy()] = "c"
    out[f"{name}_flag"] = flag
    est = val.copy()
    est[flag == "c"] = SUPPRESSED_EST
    if missing_as_zero:
        est[flag == "missing"] = 0.0
    out[f"{name}_est"] = est


def _latest_ev_snapshot(ev: pd.DataFrame) -> pd.DataFrame:
    latest_q = ev.loc[ev["period_end"].idxmax(), "quarter"]
    s = ev[ev["quarter"] == latest_q]
    out = pd.DataFrame(index=pd.Index(sorted(s["lsoa21cd"].unique()), name="lsoa21cd"))
    out["quarter"] = latest_q
    out["period_end"] = quarter_end(latest_q)
    F, K = s["Fuel"], s["Keepership"]
    _pick(s, out, (F == "Total") & (K == "Total"), "piv_total", missing_as_zero=True)
    _pick(s, out, (F == "Total") & (K == "Private"), "piv_private", missing_as_zero=True)
    _pick(s, out, (F == "Total") & (K == "Company"), "piv_company", missing_as_zero=False)
    # company row is omitted for ~30% of London LSOAs: derive it from the published total and private counts
    resid = (out["piv_total_est"] - out["piv_private_est"]).clip(lower=0)
    out["piv_company_est"] = out["piv_company_est"].fillna(resid)
    fuels = {
        "bev": "Battery electric",
        "phev_petrol": "Plug-in hybrid electric (petrol)",
        "phev_diesel": "Plug-in hybrid electric (diesel)",
        "reev": "Range extended electric",
    }
    for name, fuel in fuels.items():
        _pick(s, out, (F == fuel) & (K == "Total"), name, missing_as_zero=False)
    _pick(s, out, (F == "Battery electric") & (K == "Private"), "bev_private", missing_as_zero=False)
    # fill omitted fuel rows from the residual against the published total when it is identifiable
    est_cols = [f"{n}_est" for n in fuels]
    known = out[est_cols].fillna(0).sum(axis=1)
    resid = (out["piv_total_est"] - known).clip(lower=0)
    n_missing = out[est_cols].isna().sum(axis=1)
    for c in est_cols:
        m = out[c].isna()
        out.loc[m & (n_missing == 1), c] = resid[m & (n_missing == 1)]
        out.loc[m & (resid == 0), c] = 0.0
    out["bev_share_of_piv"] = out["bev_est"] / out["piv_total_est"].where(out["piv_total_est"] > 0)
    out["private_share_of_piv"] = out["piv_private_est"] / out["piv_total_est"].where(
        out["piv_total_est"] > 0
    )
    return out.reset_index()


def _latest_vehicle_snapshot(veh: pd.DataFrame) -> pd.DataFrame:
    latest_q = veh.loc[veh["period_end"].idxmax(), "quarter"]
    s = veh[veh["quarter"] == latest_q]
    out = pd.DataFrame(index=pd.Index(sorted(s["lsoa21cd"].unique()), name="lsoa21cd"))
    out["quarter"] = latest_q
    out["period_end"] = quarter_end(latest_q)
    B, K, L = s["BodyType"], s["Keepership"], s["LicenceStatus"]
    _pick(s, out, (B == "Cars") & (K == "Total") & (L == "Licensed"), "cars_licensed", True)
    _pick(s, out, (B == "Cars") & (K == "Private") & (L == "Licensed"), "cars_licensed_private", True)
    _pick(s, out, (B == "Cars") & (K == "Company") & (L == "Licensed"), "cars_licensed_company", False)
    out["cars_licensed_company_est"] = out["cars_licensed_company_est"].fillna(
        (out["cars_licensed_est"] - out["cars_licensed_private_est"]).clip(lower=0)
    )
    _pick(s, out, (B == "Cars") & (K == "Total") & (L == "SORN"), "cars_sorn", True)
    _pick(s, out, (B == "Total") & (K == "Total") & (L == "Licensed"), "vehicles_licensed", True)
    _pick(s, out, (B == "Motorcycles") & (K == "Total") & (L == "Licensed"), "motorcycles_licensed", True)
    _pick(
        s, out, (B == "Other vehicles") & (K == "Total") & (L == "Licensed"), "other_vehicles_licensed", True
    )
    return out.reset_index()


# ==================================================================================================
# main acquisition
# ==================================================================================================
def fetch_vehicle_stats(include_veh0125: bool = True) -> dict[str, pd.DataFrame]:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    lookup = _london_lsoas()
    codes = set(lookup["lsoa21cd"])
    lad = lookup[["lsoa21cd", "lad22cd", "lad22nm", "inner_london"]]
    out: dict[str, pd.DataFrame] = {}

    # --- VEH0145 plug-in vehicles by fuel x keepership x LSOA21 (all quarters, as published)
    ev = _read_lsoa_file("VEH0145", codes, ["LSOA21CD", "LSOA21NM", "Fuel", "Keepership"]).merge(
        lad, on="lsoa21cd", how="left"
    )
    ev.to_parquet(INTERIM_DIR / "ev_by_lsoa_london.parquet", index=False)
    log.info(
        "VEH0145 London: %d rows, %d LSOAs, fuels=%s, keepership=%s",
        len(ev),
        ev["lsoa21cd"].nunique(),
        sorted(ev["Fuel"].unique()),
        sorted(ev["Keepership"].unique()),
    )
    out["ev_long"] = ev
    snap = _latest_ev_snapshot(ev)

    # --- VEH0135 ULEVs by fuel x keepership x LSOA21
    ulev = _read_lsoa_file("VEH0135", codes, ["LSOA21CD", "LSOA21NM", "Fuel", "Keepership"]).merge(
        lad, on="lsoa21cd", how="left"
    )
    ulev.to_parquet(INTERIM_DIR / "ulev_by_lsoa_london.parquet", index=False)
    out["ulev_long"] = ulev

    # --- VEH0125 all vehicles by licence status x body type x keepership x LSOA21 (denominator for EV share)
    if include_veh0125:
        veh = _read_lsoa_file(
            "VEH0125",
            codes,
            ["LSOA21CD", "LSOA21NM", "BodyType", "Keepership", "LicenceStatus"],
            min_year=2019,
        ).merge(lad, on="lsoa21cd", how="left")
        veh.to_parquet(INTERIM_DIR / "vehicles_by_lsoa_london.parquet", index=False)
        out["vehicles_long"] = veh
        vsnap = _latest_vehicle_snapshot(veh)
        vsnap.to_parquet(INTERIM_DIR / "vehicles_by_lsoa_london_latest.parquet", index=False)
        out["vehicles_latest"] = vsnap
        snap = snap.merge(vsnap.drop(columns=["quarter", "period_end"]), on="lsoa21cd", how="left")
        snap["piv_share_of_licensed_cars"] = snap["piv_total_est"] / snap["cars_licensed_est"].where(
            snap["cars_licensed_est"] > 0
        )
        snap["piv_private_share_of_private_cars"] = (
            snap["piv_private_est"] / snap["cars_licensed_private_est"].where(snap["cars_licensed_private_est"] > 0)
        )

    # --- census denominators (when the census pipeline has run)
    feat_p = CENSUS_DIR / "lsoa21_london_features.parquet"
    if feat_p.exists():
        feat = pd.read_parquet(feat_p, columns=["lsoa21cd", "households", "population", "cars_est"])
        snap = snap.merge(feat, on="lsoa21cd", how="left")
        hh = snap["households"].where(snap["households"] > 0)
        snap["piv_per_1000_hh"] = 1000 * snap["piv_total_est"] / hh
        snap["piv_private_per_1000_hh"] = 1000 * snap["piv_private_est"] / hh  # residential demand proxy
        snap["piv_per_1000_pop"] = (
            1000 * snap["piv_total_est"] / snap["population"].where(snap["population"] > 0)
        )
    else:
        log.warning(
            "census features not found (%s); run chargescape.data.census first for per-household rates",
            feat_p,
        )
    snap = snap.merge(lad, on="lsoa21cd", how="left")
    snap.to_parquet(INTERIM_DIR / "ev_by_lsoa_london_latest.parquet", index=False)
    out["ev_latest"] = snap

    # --- VEH0142 local-authority time series (33 boroughs + London region + England + UK)
    ods = download(DFT_FILES["VEH0142"]["url"], RAW_DIR / DFT_FILES["VEH0142"]["file"], timeout=600)
    la = read_veh0142(ods)
    keep = la["ONS Code"].str.startswith("E09") | la["ONS Code"].isin(LA_CONTEXT_CODES)
    la = la[keep].drop(columns=[c for c in ("Units", "ONS Sort") if c in la.columns])
    la = la.rename(columns={"ONS Code": "ons_code", "ONS Geography": "area_name"})
    la_long = _to_long(la, ["BodyType", "Fuel", "Keepership", "ons_code", "area_name"])
    la_long.insert(0, "table", "VEH0142")
    la_long.to_parquet(INTERIM_DIR / "ev_by_la_london_timeseries.parquet", index=False)
    out["ev_la_timeseries"] = la_long
    log.info(
        "VEH0142 London subset: %d rows, %d areas, latest quarter %s",
        len(la_long),
        la_long["ons_code"].nunique(),
        la_long.loc[la_long["period_end"].idxmax(), "quarter"],
    )
    return out


# ==================================================================================================
def _summary(res: dict[str, pd.DataFrame]) -> None:
    snap = res["ev_latest"]
    q = snap["quarter"].iloc[0]
    print(f"\n=== VEH0145 plug-in vehicles, London LSOA21, {q} (end {snap['period_end'].iloc[0].date()}) ===")
    print(
        f"LSOAs: {len(snap)}   PiVs published total: {snap['piv_total'].sum():,.0f} "
        f"(suppressed LSOAs: {(snap['piv_total_flag'] == 'c').sum()}; est {snap['piv_total_est'].sum():,.0f})"
    )
    print(
        f"  private {snap['piv_private_est'].sum():,.0f} | company {snap['piv_company_est'].sum():,.0f} | "
        f"BEV {snap['bev_est'].sum():,.0f} | PHEV petrol {snap['phev_petrol_est'].sum():,.0f} | "
        f"PHEV diesel {snap['phev_diesel_est'].sum():,.0f} | REEV {snap['reev_est'].sum():,.0f}"
    )
    for c in ("piv_total", "piv_private", "piv_company", "bev", "phev_petrol", "phev_diesel", "reev"):
        print(f"  {c:12s} flags: {snap[f'{c}_flag'].value_counts().to_dict()}")
    if "cars_licensed_est" in snap:
        print(
            f"licensed cars (VEH0125 {q}): {snap['cars_licensed_est'].sum():,.0f}  -> PiV share of licensed cars: "
            f"{snap['piv_total_est'].sum() / snap['cars_licensed_est'].sum():.2%}"
        )
    if "piv_per_1000_hh" in snap:
        b = snap.groupby("lad22nm").agg(piv=("piv_total_est", "sum"), piv_private=("piv_private_est", "sum"),
                                        hh=("households", "sum"), cars_private=("cars_licensed_private_est", "sum"))
        b["piv_per_1000_hh"] = 1000 * b["piv"] / b["hh"]
        b["private_piv_per_1000_hh"] = 1000 * b["piv_private"] / b["hh"]
        b["private_piv_share_private_cars"] = b["piv_private"] / b["cars_private"]
        b = b.sort_values("private_piv_per_1000_hh", ascending=False)
        print("boroughs ranked by PRIVATE PiVs per 1,000 households (company-kept vehicles sit at registered offices):")
        print(pd.concat([b.head(5), b.tail(3)]).round(3).to_string())
    la = res["ev_la_timeseries"]
    print(
        "VEH0142 categories: BodyType",
        sorted(la["BodyType"].unique()),
        "| Fuel",
        sorted(la["Fuel"].unique()),
        "| Keepership",
        sorted(la["Keepership"].unique()),
    )
    ldn = la[la["ons_code"] == "E12000007"]
    tot = ldn[(ldn["BodyType"] == "Total") & (ldn["Fuel"] == "Total") & (ldn["Keepership"] == "Total")]
    ts = tot[tot["quarter"].str.endswith("Q1") & (tot["period_end"].dt.year >= 2020)]
    print(
        "London region PiVs (all body types, all keepers), Q1 series:\n",
        ts[["quarter", "value"]].to_string(index=False),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    res = fetch_vehicle_stats()
    _summary(res)


if __name__ == "__main__":
    main()
