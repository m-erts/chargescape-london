"""Open, *observed* public EV-charging session datasets from other cities.

Used to (a) calibrate behavioural parameters (session kWh, duration, dwell, arrival profiles) and
(b) run a "utilisation model transfer" experiment (train on cities with observed per-charger usage,
test whether OSM + population features explain utilisation, then discuss transfer to London).

Sources (all open, no account/key needed):

  dundee       Dundee City Council - "Public EV Charge Point Usage" CSVs on ArcGIS Hub (Jul 2021 - Aug 2025)
               + legacy CKAN CSVs 2017-2019 (portal migrated in 2025; fetched from the Wayback Machine when
               archived) + two charger layers with coordinates.                       OGL v3
  pkc          Perth & Kinross Council - three annual session CSVs (Sep 2016 - Aug 2019) + charging-points
               layer with coordinates.                                                OGL v3
  leeds        Leeds City Council via Data Mill North - quarterly CSVs 2014-Q2 .. 2021-Q1 (car-park names,
               no coordinates).                                                       OGL v3
  palo_alto    City of Palo Alto - "Electric Vehicle Charging Station Usage (July 2011 - Dec 2020)", one CSV
               with lat/lon, port type, hashed user id.                               PDDL
  boulder      City of Boulder - "Electric Vehicle Charging Station Data" (2018 ->), ArcGIS Hub table with
               street addresses (geocoded to points with Nominatim, flagged as such). CC0
  paris_belib  Ville de Paris - Belib' real-time availability + static PDC list (one snapshot per day;
               ODbL) and the EDF "Smarter Mobility Data Challenge" 15-min occupancy series 2020-07 ..
               2021-02 for 91 stations (ODbL).
  cps          ChargePlace Scotland public locations feed (OCPI-style JSON, coordinates for CPS charge-point
               IDs used by Dundee/PKC) + list of the network's monthly session files (documented only).
  urbanev      UrbanEV (Shenzhen) - zone-level hourly occupancy / duration / volume + station coordinates
               (GCJ-02) from the GitHub repo.                                         CC0 1.0

Run:
    PYTHONPATH=src python -m chargescape.data.sessions_open [--only dundee,pkc,...] [--skip-large] [--no-geocode]

Idempotent: raw files are only downloaded when missing; interim parquet files are rebuilt on each run.
Outputs: data/raw/sessions_open/<source>/...  and  data/interim/sessions_open/<source>_sessions.parquet /
<source>_stations.parquet (+ occupancy tables for Paris / UrbanEV) and summary.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from chargescape.utils.http import UA, download
from chargescape.utils.paths import INTERIM, RAW, ROOT

SRC_RAW = RAW / "sessions_open"
SRC_INTERIM = INTERIM / "sessions_open"
TODAY = datetime.now(UTC).strftime("%Y%m%d")
RETRIEVED = datetime.now(UTC).strftime("%Y-%m-%d")

SESSION_COLS = [
    "city",
    "station_id",
    "station_name",
    "lat",
    "lon",
    "lat_source",
    "start_ts",
    "end_ts",
    "tz",
    "duration_min",
    "charging_min",
    "energy_kwh",
    "port_type",
    "power_kw",
    "connector",
    "user_id",
    "postcode",
    "session_id",
    "source_file",
]
STATION_COLS = [
    "city",
    "station_id",
    "station_name",
    "lat",
    "lon",
    "lat_source",
    "address",
    "postcode",
    "power_kw",
    "n_sessions",
    "first_seen",
    "last_seen",
    "source",
]

# --------------------------------------------------------------------------------------------------
# Source registry (verified 2026-09-10)
# --------------------------------------------------------------------------------------------------
ARCGIS_ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{id}/data"

DUNDEE_HUB_ITEMS = {  # ArcGIS Hub, owner dundeecity; all CSV items
    "2021H2": "189b838f51e74f6bb77509d91c47d7c0",
    "2022": "f1a6b5df441d4606821d5f1a78e92d7e",
    "2023": "80df5f177b8c4a94b2bc692835801e8e",
    "2024": "8b443deaf9174b7aa9d3e10eaa906422",
    "2024_dup": "701795ab29c04e4bbf21f6a4be3404cd",  # same size as 2024 - deduplicated on SDR ID
    "2025_JanAug": "e185a3a1cfc948a69ada76e950b9d447",
}
DUNDEE_LEGACY_BASE = "https://data.dundeecity.gov.uk/dataset/ab3c487f-77c9-4157-a89f-ac9c95ae1b00/resource"
DUNDEE_LEGACY_CKAN = [  # "Electric Vehicle Charging Sessions Dundee" (CKAN, OGL v3) - portal retired 2025
    "bf478c38-9aa4-44b4-943a-77d643149a74/download/cp-locations.csv",
    "d2bf2085-922f-4c29-9682-788fb47b5b4d/download/cp-data-dec-mar-2018.csv",
    "d748579a-f05f-47e6-a76b-e76d1e2e9589/download/cpdata.csv",
    "dd6186a4-5d1a-431a-93c4-0be142ff8e10/download/charge-sessions-june-sept.csv",
    "f4c07f77-39f8-4f1b-9477-225d893dcf80/download/cp-data-mar-may-2018.csv",
]
DUNDEE_STATION_LAYERS = {
    "all_public_chargers": "https://services.arcgis.com/GlZ1P6ksdiXNYhvC/arcgis/rest/services/All%20public%20chargers%20one%20layer/FeatureServer/0",
    "ev_charging_points_view": "https://services.arcgis.com/GlZ1P6ksdiXNYhvC/arcgis/rest/services/EV_charging_points_View_/FeatureServer/0",
}

PKC_ITEMS = {
    "2016_2017": "79cec80b01764d9db32961c3476c9346",
    "2017_2018": "93748dde99cd45468a5e9c08f61c1953",
    "2018_2019": "ca6cae3df2624832a2eaf678f2eabee8",
}
PKC_STATION_LAYER = "https://services-eu1.arcgis.com/WD0cvOmDKf7CA0Xy/arcgis/rest/services/Electric_Vehicle_Charging_Points/FeatureServer/10"

LEEDS_BASE = "https://datamillnorth.org/download/2lx68"
LEEDS_FILES = {  # Data Mill North dataset 2lx68 (OGL v3)
    "2014_Q2": "672e32a5-353b-4ad5-966b-91fbad24a8ae/2014%20EVCP%20use%20Q2.csv",
    "2014_Q3Q4": "5e5ecccc-716e-483c-9a3a-5468322751db/2014%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2015_Q1Q2": "f88b51ab-dbeb-4174-93db-3eba3a02b2dd/2015%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2015_Q3Q4": "83f468b2-4cc7-47c5-bbcf-fd33148eb7db/2015%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2016_Q1Q2": "2b800d9a-54d6-4533-825c-f70df425b19f/2016%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2016_Q3Q4": "691cd547-825d-47d8-92d9-ae15a8dad669/2016%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2017_Q1Q2": "28d63a20-87dd-4351-adb3-e62523a71d2e/2017%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2017_Q3Q4": "27c664e0-50b6-4504-83e0-874970aa9cc6/2017%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2018_Q1Q2": "5b804f8c-5eb1-49ff-89c3-528e088d552c/2018%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2018_Q3Q4": "abb4a150-22f3-4c93-9fd7-d421813d96ce/2018%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2019_Q1Q2": "5e6417b4-27a9-41fb-9505-509934e4dc0d/2019%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2019_Q3Q4": "bffbd0db-90b5-429a-9259-72cb90726da4/2019%20EVCP%20use%20Q3%20and%20Q4.csv",
    "2020_Q1Q2": "9541db2e-c3e4-4f75-8f5a-8100054df0f6/2020%20EVCP%20use%20Q1%20and%20Q2.csv",
    "2020_Q3": "cef9ca1b-2b6c-4dd3-a5dd-09ea3e8ac4db/2020%20EVCP%20use%20Q3.csv",
    "2020_Q4": "b8b07a16-f62a-4b54-8ae9-54cfe7b8681c/2020%20EVCP%20use%20Q4.csv",
    "2021_Q1": "fc2f9674-6952-43c8-be63-e18b4a26047e/2021%20EVCP%20use%20Q1.csv",
}

PALO_ALTO_URL = "https://data.paloalto.gov/datasets/194693-electric-vehicle-charging-station-usage-july-2011-dec-2020.download/"
PALO_ALTO_PAGE = (
    "https://data.paloalto.gov/datasets/194693/electric-vehicle-charging-station-usage-july-2011-dec-2020/"
)

BOULDER_ITEM = "95992b3938be4622b07f0b05eba95d4c"
BOULDER_CSV = f"https://open-data.bouldercolorado.gov/api/download/v1/items/{BOULDER_ITEM}/csv?layers=0"
BOULDER_FS = "https://services.arcgis.com/ePKBjXrBZ2vEEgWd/arcgis/rest/services/Electric_Vehicle_Charging_Station_Data/FeatureServer/0"
BOULDER_DICT = "https://webappsprod.bouldercolorado.gov/opendata/ev_datadictionary.csv"

PARIS_API = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets"
PARIS_RT = "belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel"
PARIS_STATIC = "belib-points-de-recharge-pour-vehicules-electriques-donnees-statiques"
EDF_RAW = "https://gitlab.com/smarter-mobility-data-challenge/tutorials/-/raw/master/0.%20Input%20Data/"
EDF_FILES = {"train.csv": 172, "test.csv": 14}  # approx MB; *_uci.csv variants are the same data re-exported

CPS_LOCATIONS = "https://info.smartcharging.uk/public_feed/locations/2463"
CPS_TARIFFS = "https://info.smartcharging.uk/public_feed/locations/2463/tariffs"
CPS_MONTHLY_PAGE = "https://chargeplacescotland.org/monthly-charge-point-performance/"
CPS_STRATHCLYDE_ZIP = "https://pureportal.strath.ac.uk/files/247978433/ScotPublicCharging.zip"

URBANEV_RAW = "https://raw.githubusercontent.com/IntelligentSystemsLab/UrbanEV/main/"
URBANEV_FILES = [
    "LICENSE",
    "readme.md",
    "data/adj.csv",
    "data/distance.csv",
    "data/duration.csv",
    "data/e_price.csv",
    "data/inf.csv",
    "data/inf_raw.csv",
    "data/occupancy.csv",
    "data/poi.csv",
    "data/s_price.csv",
    "data/volume-11kW.csv",
    "data/volume.csv",
    "data/weather_airport.csv",
    "data/weather_central.csv",
    "data/weather_header.txt",
    "data/SZ_districts/SZ_districts.shp",
    "data/SZ_districts/SZ_districts.dbf",
    "data/SZ_districts/SZ_districts.shx",
    "data/SZ_districts/SZ_districts.prj",
    "data/SZ_districts/readme.md",
]

LARGE_MB = 100


# --------------------------------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[sessions_open] {msg}", flush=True)


def _save_meta(dir_: Path, meta: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    meta = {"retrieved": RETRIEVED, **meta}
    (dir_ / "_source.json").write_text(json.dumps(meta, indent=2))


def _try_download(
    url: str, dest: Path, *, retries: int = 3, timeout: int = 300, headers: dict | None = None
) -> Path | None:
    try:
        return download(url, dest, retries=retries, timeout=timeout, headers=headers)
    except Exception as e:  # noqa: BLE001
        log(f"  ! download failed: {url} -> {e}")
        return None


def _looks_like_html(path: Path) -> bool:
    try:
        head = path.open("rb").read(300).lstrip().lower()
    except OSError:
        return False
    return head.startswith((b"<!doctype html", b"<html", b"{", b"<?xml"))


def _read_csv(path: Path) -> pd.DataFrame:
    last = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc, low_memory=False, skipinitialspace=True)
            break
        except UnicodeDecodeError as e:
            last = e
    else:
        raise last  # type: ignore[misc]
    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in df.columns if c and not c.lower().startswith("unnamed")]
    return df.loc[:, keep]


def _norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")


def _hash_id(city: str, uid) -> str | None:
    if uid is None or (isinstance(uid, float) and pd.isna(uid)) or str(uid).strip() in ("", "nan"):
        return None
    return hashlib.sha1(f"chargescape:{city}:{str(uid).strip()}".encode()).hexdigest()[:12]


def _norm_cp(s) -> str | None:
    """Normalise a charge-point identifier: '51516', 'APT51593', 'FC16939' -> the 4-6 digit core."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().upper()
    if not s or s == "NAN":
        return None
    m = re.search(r"(\d{4,6})", s)
    return m.group(1) if m else s


_DATE_FORMATS = [
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
]


def _smart_datetime(s: pd.Series, year_hint: tuple[int, int] | None = None) -> pd.Series:
    """Parse a date(/time) column whose format is unknown (UK d/m/Y vs US m/d/Y vs ISO).

    The format is chosen on a sample by the number of rows it parses (ambiguous d/m vs m/d resolves
    itself because the wrong one fails on days > 12), optionally restricted to a plausible year range.
    """
    s = s.astype(str).str.strip()
    sample = s.sample(min(len(s), 3000), random_state=0) if len(s) else s
    best_fmt, best_score = None, -1
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(sample, format=fmt, errors="coerce")
        ok = parsed.notna()
        if year_hint is not None:
            ok &= parsed.dt.year.between(year_hint[0], year_hint[1])
        score = int(ok.sum())
        if score > best_score:
            best_fmt, best_score = fmt, score
    out = pd.to_datetime(s, format=best_fmt, errors="coerce")
    rest = out.isna() & s.ne("") & s.str.lower().ne("nan")
    if (
        rest.any()
    ):  # files mixing formats (e.g. Boulder switches to ISO in mid-2023): second pass on the remainder
        dayfirst = best_fmt.startswith("%d")
        for fmt in [f for f in _DATE_FORMATS if f != best_fmt and f.startswith(("%Y", best_fmt[:2]))]:
            out.loc[rest] = pd.to_datetime(s[rest], format=fmt, errors="coerce")
            rest = out.isna() & s.ne("") & s.str.lower().ne("nan")
            if not rest.any():
                break
        if rest.any():
            out.loc[rest] = pd.to_datetime(s[rest], errors="coerce", dayfirst=dayfirst, format="mixed")
    return out


def _time_to_td(t: pd.Series) -> pd.Series:
    t = t.astype(str).str.strip()
    t = t.where(t.str.count(":") >= 2, t + ":00")
    return pd.to_timedelta(t, errors="coerce")


def _combine(date_s: pd.Series, time_s: pd.Series | None, year_hint=None) -> pd.Series:
    d = _smart_datetime(date_s, year_hint)
    if time_s is None:
        return d
    return d.dt.normalize() + _time_to_td(time_s)


def _duration_min(s: pd.Series) -> pd.Series:
    """'HH:MM:SS' (hours may exceed 24) or numeric minutes -> minutes."""
    s = s.astype(str).str.strip()
    td = pd.to_timedelta(s.where(s.str.contains(":"), None), errors="coerce")
    num = pd.to_numeric(s.where(~s.str.contains(":"), None), errors="coerce")
    return (td.dt.total_seconds() / 60).fillna(num)


def _geojson_points(path: Path) -> pd.DataFrame:
    gj = json.loads(Path(path).read_text())
    rows = []
    for f in gj.get("features", []):
        p = dict(f.get("properties") or {})
        g = f.get("geometry") or {}
        if g and g.get("type") == "Point" and g.get("coordinates"):
            p["lon"], p["lat"] = g["coordinates"][:2]
        rows.append(p)
    return pd.DataFrame(rows)


def _fs_geojson(layer_url: str, dest: Path) -> Path | None:
    url = f"{layer_url}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"
    return _try_download(url, dest)


def _empty_sessions() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in SESSION_COLS})


def _finalise_sessions(df: pd.DataFrame) -> pd.DataFrame:
    for c in SESSION_COLS:
        if c not in df.columns:
            df[c] = None
    df = df[SESSION_COLS].copy()
    for c in ("lat", "lon", "duration_min", "charging_min", "energy_kwh", "power_kw"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("start_ts", "end_ts"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    # derive duration from timestamps where the source has none
    m = df["duration_min"].isna() & df["start_ts"].notna() & df["end_ts"].notna()
    df.loc[m, "duration_min"] = (df.loc[m, "end_ts"] - df.loc[m, "start_ts"]).dt.total_seconds() / 60
    m = df["end_ts"].isna() & df["start_ts"].notna() & df["duration_min"].notna()
    df.loc[m, "end_ts"] = df.loc[m, "start_ts"] + pd.to_timedelta(df.loc[m, "duration_min"], unit="m")
    for c in (
        "city",
        "station_id",
        "station_name",
        "lat_source",
        "tz",
        "port_type",
        "connector",
        "user_id",
        "postcode",
        "session_id",
        "source_file",
    ):
        df[c] = df[c].astype("string")
    return df.sort_values(["start_ts", "station_id"], kind="stable").reset_index(drop=True)


def _station_table(
    sessions: pd.DataFrame, coords: pd.DataFrame | None, city: str, source: str
) -> pd.DataFrame:
    """One row per station_id: name, coordinates (from the session rows or a coords table), activity."""
    g = sessions.groupby("station_id", dropna=True)
    st = pd.DataFrame(
        {
            "station_name": g["station_name"].agg(
                lambda x: x.dropna().mode().iloc[0] if x.notna().any() else None
            ),
            "postcode": g["postcode"].agg(lambda x: x.dropna().mode().iloc[0] if x.notna().any() else None),
            "n_sessions": g.size(),
            "first_seen": g["start_ts"].min(),
            "last_seen": g["start_ts"].max(),
            "lat": g["lat"].median(),
            "lon": g["lon"].median(),
            "lat_source": g["lat_source"].agg(lambda x: x.dropna().iloc[0] if x.notna().any() else None),
            "power_kw": g["power_kw"].max(),
        }
    ).reset_index()
    st["city"] = city
    st["source"] = source
    st["address"] = None
    if coords is not None and len(coords):
        c = coords.drop_duplicates("station_id").set_index("station_id")
        for col in ("lat", "lon", "lat_source", "address", "power_kw", "station_name"):
            if col in c.columns:
                fill = st["station_id"].map(c[col])
                st[col] = st[col].where(st[col].notna(), fill)
    for c in STATION_COLS:
        if c not in st.columns:
            st[c] = None
    st = st[STATION_COLS]
    for c in ("lat", "lon", "power_kw"):
        st[c] = pd.to_numeric(st[c], errors="coerce")
    return st.sort_values("n_sessions", ascending=False).reset_index(drop=True)


def parse_cps_style(
    df: pd.DataFrame, city: str, source_file: str, tz: str, year_hint=None
) -> pd.DataFrame | None:
    """Parse the UK council / ChargePlace-Scotland back-office export family.

    Handles the three layouts seen in the wild:
      PKC/Leeds : [Charging event|_id], [User ID], CP ID, Connector, Start Date, Start Time, End Date, End Time,
                  Total kWh, Site, Model
      Dundee    : SDR ID, Site, CP ID, Connector Type, Consum(kWh), Duration, Start, End, Postcode
    """
    cols = {_norm_col(c): c for c in df.columns}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    c_cp = col("cp_id", "chargepoint_id", "charge_point_id", "cpid", "charger_id")
    c_kwh = col("total_kwh", "consum_kwh", "energy_kwh", "kwh", "energy", "total_energy_kwh")
    if c_cp is None or c_kwh is None:
        log(f"  ! {source_file}: cannot find CP ID / kWh columns in {list(df.columns)} - skipped")
        return None
    c_site = col("site", "site_name", "location", "station")
    c_sd, c_st = col("start_date", "date"), col("start_time")
    c_ed, c_et = col("end_date"), col("end_time")
    c_start, c_end = (
        col("start", "start_date_time", "plug_in", "start_datetime"),
        col("end", "end_date_time", "plug_out", "end_datetime"),
    )
    c_dur = col("duration", "total_duration", "duration_hh_mm_ss")
    c_conn = col("connector", "connector_id", "connector_no")
    c_ctype = col("connector_type", "type", "charger_type")
    c_model = col("model", "charger_model")
    c_user = col("user_id", "unique_user_id", "user", "rfid")
    c_pc = col("postcode", "post_code")
    c_sid = col("charging_event", "sdr_id", "session_id", "transaction_id", "id")

    out = pd.DataFrame(index=df.index)
    out["city"] = city
    out["station_id"] = df[c_cp].map(_norm_cp)
    out["station_name"] = df[c_site].str.strip() if c_site else None
    if c_sd is not None:
        out["start_ts"] = _combine(df[c_sd], df[c_st] if c_st else None, year_hint)
    elif c_start is not None:
        out["start_ts"] = _smart_datetime(df[c_start], year_hint)
    if c_ed is not None:
        out["end_ts"] = _combine(df[c_ed], df[c_et] if c_et else None, year_hint)
    elif c_end is not None:
        out["end_ts"] = _smart_datetime(df[c_end], year_hint)
    out["tz"] = tz
    out["duration_min"] = _duration_min(df[c_dur]) if c_dur else None
    out["energy_kwh"] = pd.to_numeric(df[c_kwh].str.replace(",", ""), errors="coerce")
    ptype = None
    if c_ctype is not None:
        ptype = df[c_ctype].str.strip().str.lower()
    elif c_model is not None:
        ptype = df[c_model].str.strip()
    out["port_type"] = ptype
    if c_model is not None:
        kw = df[c_model].str.extract(r"(\d+(?:\.\d+)?)\s*kW", flags=re.I)[0]
        out["power_kw"] = pd.to_numeric(kw, errors="coerce")
        out.loc[
            df[c_model].str.contains("rapid", case=False, na=False) & out["power_kw"].isna(), "power_kw"
        ] = 50
    out["connector"] = df[c_conn].str.strip() if c_conn else None
    out["user_id"] = df[c_user].map(lambda u: _hash_id(city, u)) if c_user else None
    out["postcode"] = df[c_pc].str.strip().str.upper() if c_pc else None
    out["session_id"] = df[c_sid].str.strip() if c_sid else None
    out["source_file"] = source_file
    return out


# --------------------------------------------------------------------------------------------------
# 1. Dundee
# --------------------------------------------------------------------------------------------------
def fetch_dundee() -> Path:
    d = SRC_RAW / "dundee"
    (d / "hub").mkdir(parents=True, exist_ok=True)
    (d / "legacy_ckan").mkdir(parents=True, exist_ok=True)
    for name, item in DUNDEE_HUB_ITEMS.items():
        _try_download(
            ARCGIS_ITEM_DATA.format(id=item), d / "hub" / f"public_ev_charge_point_usage_{name}.csv"
        )
    for name, url in DUNDEE_STATION_LAYERS.items():
        _fs_geojson(url, d / f"stations_{name}.geojson")
    # Legacy CKAN portal (2017-2019 sessions) - retired; try the Wayback Machine, tolerate absence.
    for rel in DUNDEE_LEGACY_CKAN:
        dest = d / "legacy_ckan" / rel.split("/")[-1]
        if dest.exists():
            continue
        wb = f"https://web.archive.org/web/2id_/{DUNDEE_LEGACY_BASE}/{rel}"
        p = _try_download(wb, dest, retries=1, timeout=120)
        if p is not None and _looks_like_html(p):
            log(f"  ! Wayback returned HTML (not archived): {rel}")
            p.unlink()
        time.sleep(3)
    _save_meta(
        d,
        {
            "provider": "Dundee City Council",
            "landing": "https://data.dundeecity.gov.uk/ (ArcGIS Hub; search 'Public EV Charge Point Usage')",
            "hub_items": {
                k: f"https://data.dundeecity.gov.uk/datasets/dundeecity::public-ev-charge-point-usage-dundee-city-council-{k}"
                for k in DUNDEE_HUB_ITEMS
            },
            "hub_download_pattern": ARCGIS_ITEM_DATA,
            "legacy_ckan": [f"{DUNDEE_LEGACY_BASE}/{r}" for r in DUNDEE_LEGACY_CKAN],
            "legacy_ckan_licence": "Open Government Licence 3.0 (stated on the archived CKAN dataset page)",
            "station_layers": DUNDEE_STATION_LAYERS,
            "licence": "OGL v3 (council open-data portal); Hub items carry no per-item licence text",
        },
    )
    return d


def harmonise_dundee() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = SRC_RAW / "dundee"
    frames = []
    for f in sorted((d / "hub").glob("*.csv")) + sorted((d / "legacy_ckan").glob("*.csv")):
        if f.name == "cp-locations.csv" or f.name.endswith("_2024_dup.csv"):
            continue  # older Jan-2025 upload of the 2024 file (113,607 rows) superseded by the Jul-2025 re-upload
        df = _read_csv(f)
        s = parse_cps_style(df, "dundee", f.name, "Europe/London", year_hint=(2016, 2026))
        if s is not None:
            frames.append(s)
    if not frames:
        return _empty_sessions(), pd.DataFrame(columns=STATION_COLS)
    sessions = pd.concat(frames, ignore_index=True)
    n0 = len(sessions)
    key = sessions["session_id"].where(
        sessions["session_id"].notna(),
        sessions[["station_id", "connector", "start_ts", "energy_kwh"]].astype(str).agg("|".join, axis=1),
    )
    sessions = sessions.loc[~key.duplicated()].copy()
    log(f"  dundee: dropped {n0 - len(sessions):,} duplicate rows (repeated SDR IDs)")

    # coordinates: council layers first, then the CPS network feed
    coords = []
    p = d / "stations_all_public_chargers.geojson"
    if p.exists():
        g = _geojson_points(p)
        g["station_id"] = g["Charge_Point_ID"].map(_norm_cp)
        g["power_kw"] = pd.to_numeric(
            g["Power_Capacity"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
        )
        coords.append(
            pd.DataFrame(
                {
                    "station_id": g["station_id"],
                    "lat": g["lat"],
                    "lon": g["lon"],
                    "station_name": g["Site_Name"],
                    "power_kw": g["power_kw"],
                    "lat_source": "dcc_layer_all_public_chargers",
                }
            )
        )
    p = d / "stations_ev_charging_points_view.geojson"
    if p.exists():
        g = _geojson_points(p)
        g["station_id"] = g["chargepoint_ID"].map(_norm_cp)
        coords.append(
            pd.DataFrame(
                {
                    "station_id": g["station_id"],
                    "lat": g["lat"],
                    "lon": g["lon"],
                    "power_kw": pd.to_numeric(g["Powerkw"], errors="coerce"),
                    "lat_source": "dcc_layer_ev_charging_points_view",
                }
            )
        )
    legacy_loc = d / "legacy_ckan" / "cp-locations.csv"
    if legacy_loc.exists():
        g = _read_csv(legacy_loc)
        cols = {_norm_col(c): c for c in g.columns}
        c_id = next(
            (cols[k] for k in ("cp_id", "chargepoint_id", "id", "charge_point_id") if k in cols), None
        )
        c_lat = next((cols[k] for k in ("lat", "latitude", "y") if k in cols), None)
        c_lon = next((cols[k] for k in ("lon", "long", "longitude", "x") if k in cols), None)
        if c_id and c_lat and c_lon:
            coords.append(
                pd.DataFrame(
                    {
                        "station_id": g[c_id].map(_norm_cp),
                        "lat": pd.to_numeric(g[c_lat], errors="coerce"),
                        "lon": pd.to_numeric(g[c_lon], errors="coerce"),
                        "lat_source": "dcc_legacy_ckan_cp_locations",
                    }
                )
            )
    cps = _cps_coords()
    if cps is not None:
        coords.append(cps)
    coords_df = (
        pd.concat(coords, ignore_index=True).dropna(subset=["station_id", "lat", "lon"]) if coords else None
    )
    if coords_df is not None:
        coords_df = coords_df.drop_duplicates("station_id")
        m = coords_df.set_index("station_id")
        sessions["lat"] = sessions["station_id"].map(m["lat"])
        sessions["lon"] = sessions["station_id"].map(m["lon"])
        sessions["lat_source"] = sessions["station_id"].map(m["lat_source"])
        if "power_kw" not in sessions or sessions["power_kw"].isna().all():
            sessions["power_kw"] = sessions["station_id"].map(m["power_kw"])
    # postcode-centroid fallback for charge points absent from the council layers / CPS feed
    miss = sessions["lat"].isna() & sessions["postcode"].notna()
    if miss.any():
        cent = _postcode_centroids(
            sessions.loc[miss, "postcode"].unique().tolist(), SRC_RAW / "_geocode" / "postcodes_io.json"
        )
        pc = sessions.loc[miss, "postcode"].str.replace(r"\s+", " ", regex=True).str.upper()
        sessions.loc[miss, "lat"] = pc.map(lambda p: cent.get(p, (None, None))[0])
        sessions.loc[miss, "lon"] = pc.map(lambda p: cent.get(p, (None, None))[1])
        sessions.loc[miss & sessions["lat"].notna(), "lat_source"] = "postcode_centroid_postcodes_io"
        log(f"  dundee: postcode centroids filled {int((miss & sessions['lat'].notna()).sum()):,} rows")
    # last resort: a charge point whose site name matches located charge points (same hub) takes their centroid
    miss = sessions["lat"].isna() & sessions["station_name"].notna()
    if miss.any():
        site = sessions.loc[~sessions["lat"].isna()].groupby("station_name")[["lat", "lon"]].median()
        sessions.loc[miss, "lat"] = sessions.loc[miss, "station_name"].map(site["lat"])
        sessions.loc[miss, "lon"] = sessions.loc[miss, "station_name"].map(site["lon"])
        sessions.loc[miss & sessions["lat"].notna(), "lat_source"] = "same_site_name_centroid"
    sessions = _finalise_sessions(sessions)
    stations = _station_table(
        sessions, coords_df, "dundee", "dundee_hub_csv+dcc_layers+cps_feed+postcodes_io"
    )
    return sessions, stations


# --------------------------------------------------------------------------------------------------
# 2. Perth & Kinross
# --------------------------------------------------------------------------------------------------
def fetch_pkc() -> Path:
    d = SRC_RAW / "perth_kinross"
    d.mkdir(parents=True, exist_ok=True)
    for name, item in PKC_ITEMS.items():
        _try_download(ARCGIS_ITEM_DATA.format(id=item), d / f"ev_charge_station_use_{name}.csv")
    _fs_geojson(PKC_STATION_LAYER, d / "stations_electric_vehicle_charging_points.geojson")
    _save_meta(
        d,
        {
            "provider": "Perth & Kinross Council",
            "landing": "https://data.pkc.gov.uk/ (ArcGIS Hub)",
            "items": {
                k: f"https://www.arcgis.com/sharing/rest/content/items/{v}" for k, v in PKC_ITEMS.items()
            },
            "station_layer": PKC_STATION_LAYER,
            "licence": "Open Government Licence v3 (per-item licenseInfo: 'an acknowledgement of the source is required')",
        },
    )
    return d


def _unswap_daymonth(ts: pd.Series) -> pd.Series:
    """Undo an upstream day/month swap for rows with day <= 12.

    The PKC CSVs were exported from d/m/Y source dates through a m/d/Y parser: dates with day <= 12 were
    silently swapped, dates with day > 12 were kept.  Swapping them back makes the (time-sorted) files
    strictly monotone and puts >99.5% of rows inside each file's nominal Sep-Aug window.
    """
    ok = ts.notna() & (ts.dt.day <= 12)
    if not ok.any():
        return ts
    t = ts[ok]
    swapped = pd.to_datetime({"year": t.dt.year, "month": t.dt.day, "day": t.dt.month}, errors="coerce") + (
        t - t.dt.normalize()
    )
    out = ts.copy()
    out.loc[ok] = swapped
    return out


def harmonise_pkc() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = SRC_RAW / "perth_kinross"
    frames = []
    for f in sorted(d.glob("ev_charge_station_use_*.csv")):
        y = re.findall(r"(\d{4})", f.name)
        hint = (int(y[0]), int(y[-1])) if y else None
        s = parse_cps_style(_read_csv(f), "perth_kinross", f.name, "Europe/London", year_hint=hint)
        if s is not None:
            frames.append(s)
    if not frames:
        return _empty_sessions(), pd.DataFrame(columns=STATION_COLS)
    sessions = pd.concat(frames, ignore_index=True)
    sessions["start_ts"] = _unswap_daymonth(sessions["start_ts"])
    sessions["end_ts"] = _unswap_daymonth(sessions["end_ts"])
    log("  pkc: corrected upstream day/month swap on dates with day <= 12 (see _unswap_daymonth)")
    sessions["session_id"] = sessions["source_file"] + "#" + sessions["session_id"].astype(str)
    coords_df = None
    p = d / "stations_electric_vehicle_charging_points.geojson"
    if p.exists():
        g = _geojson_points(p)
        g["station_id"] = g["Id"].map(_norm_cp)
        kw = pd.concat(
            [
                pd.to_numeric(g["OUTPUT1_kW"], errors="coerce"),
                pd.to_numeric(g["OUTPUT2_kW"], errors="coerce"),
            ],
            axis=1,
        ).max(axis=1)
        coords_df = pd.DataFrame(
            {
                "station_id": g["station_id"],
                "lat": g["lat"],
                "lon": g["lon"],
                "address": (
                    g["CP_Name"].fillna("") + ", " + g["ADDRESS"].fillna("") + ", " + g["LOCATION"].fillna("")
                ).str.strip(", "),
                "power_kw": kw,
                "lat_source": "pkc_layer_electric_vehicle_charging_points",
            }
        )
        cps = _cps_coords()
        if cps is not None:
            coords_df = pd.concat([coords_df, cps], ignore_index=True)
        coords_df = coords_df.dropna(subset=["station_id", "lat", "lon"]).drop_duplicates("station_id")
        m = coords_df.set_index("station_id")
        sessions["lat"] = sessions["station_id"].map(m["lat"])
        sessions["lon"] = sessions["station_id"].map(m["lon"])
        sessions["lat_source"] = sessions["station_id"].map(m["lat_source"])
        sessions["power_kw"] = sessions["power_kw"].where(
            sessions["power_kw"].notna(), sessions["station_id"].map(m["power_kw"])
        )
    sessions = _finalise_sessions(sessions)
    stations = _station_table(sessions, coords_df, "perth_kinross", "pkc_hub_csv+pkc_layer+cps_feed")
    return sessions, stations


# --------------------------------------------------------------------------------------------------
# 3. Leeds (Data Mill North)
# --------------------------------------------------------------------------------------------------
def fetch_leeds() -> Path:
    d = SRC_RAW / "leeds"
    d.mkdir(parents=True, exist_ok=True)
    for name, rel in LEEDS_FILES.items():
        _try_download(f"{LEEDS_BASE}/{rel}", d / f"evcp_use_{name}.csv")
    _save_meta(
        d,
        {
            "provider": "Leeds City Council (Data Mill North)",
            "landing": "https://datamillnorth.org/dataset/2lx68",
            "files": {k: f"{LEEDS_BASE}/{v}" for k, v in LEEDS_FILES.items()},
            "licence": "Open Government Licence v3",
            "note": "Council car-park chargepoints; sites given by name only (no coordinates).",
        },
    )
    return d


def harmonise_leeds() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = SRC_RAW / "leeds"
    frames = []
    for f in sorted(d.glob("evcp_use_*.csv")):
        y = int(re.findall(r"(\d{4})", f.name)[0])
        s = parse_cps_style(_read_csv(f), "leeds", f.name, "Europe/London", year_hint=(y - 1, y + 1))
        if s is not None:
            frames.append(s)
    if not frames:
        return _empty_sessions(), pd.DataFrame(columns=STATION_COLS)
    sessions = pd.concat(frames, ignore_index=True)
    sessions = sessions.loc[~sessions["session_id"].duplicated() | sessions["session_id"].isna()].copy()
    sessions = _finalise_sessions(sessions)
    stations = _station_table(sessions, None, "leeds", "datamillnorth_csv")
    return sessions, stations


# --------------------------------------------------------------------------------------------------
# 4. Palo Alto
# --------------------------------------------------------------------------------------------------
def fetch_palo_alto() -> Path:
    d = SRC_RAW / "palo_alto"
    d.mkdir(parents=True, exist_ok=True)
    _try_download(
        PALO_ALTO_URL,
        d / "ev_charging_station_usage_2011_2020.csv",
        timeout=600,
        headers={"Accept": "text/csv,*/*"},
    )
    _save_meta(
        d,
        {
            "provider": "City of Palo Alto (Utilities / Public Works / Planning)",
            "landing": PALO_ALTO_PAGE,
            "download": PALO_ALTO_URL,
            "licence": "ODC Public Domain Dedication and License (PDDL) - linked from the dataset page",
            "mirror": "https://openenergyhub.ornl.gov/explore/dataset/electric-vehicle-charging-station-usage-july-2011-dec-2020/",
        },
    )
    return d


def harmonise_palo_alto() -> tuple[pd.DataFrame, pd.DataFrame]:
    f = SRC_RAW / "palo_alto" / "ev_charging_station_usage_2011_2020.csv"
    if not f.exists():
        return _empty_sessions(), pd.DataFrame(columns=STATION_COLS)
    df = _read_csv(f)
    cols = {_norm_col(c): c for c in df.columns}
    c = lambda k: df[cols[k]] if k in cols else pd.Series(pd.NA, index=df.index, dtype="string")  # noqa: E731
    out = pd.DataFrame(index=df.index)
    out["city"] = "palo_alto"
    out["station_id"] = c("station_name").str.strip()
    out["station_name"] = c("station_name").str.strip()
    out["lat"] = pd.to_numeric(c("latitude"), errors="coerce")
    out["lon"] = pd.to_numeric(c("longitude"), errors="coerce")
    out["lat_source"] = "source_row"
    out["start_ts"] = _smart_datetime(c("start_date"), (2011, 2021))
    out["end_ts"] = _smart_datetime(c("end_date"), (2011, 2021))
    out["tz"] = "America/Los_Angeles"
    out["duration_min"] = _duration_min(c("total_duration_hh_mm_ss"))
    out["charging_min"] = _duration_min(c("charging_time_hh_mm_ss"))
    out["energy_kwh"] = pd.to_numeric(c("energy_kwh"), errors="coerce")
    out["port_type"] = c("port_type").str.strip()
    out["power_kw"] = None
    out["connector"] = (c("plug_type").fillna("") + " #" + c("port_number").fillna("")).str.strip(" #")
    out["user_id"] = c("user_id").map(lambda u: _hash_id("palo_alto", u))
    out["postcode"] = c("postal_code").str.strip()
    out["session_id"] = c("plug_in_event_id").str.strip()
    out["source_file"] = f.name
    extra = pd.DataFrame(
        {
            "station_id": out["station_id"],
            "address": (
                c("address_1").fillna("") + ", " + c("city").fillna("") + " " + c("postal_code").fillna("")
            ).str.strip(", "),
        }
    )
    sessions = _finalise_sessions(out)
    stations = _station_table(
        sessions, extra.drop_duplicates("station_id"), "palo_alto", "palo_alto_opendata_csv"
    )
    return sessions, stations


# --------------------------------------------------------------------------------------------------
# 5. Boulder
# --------------------------------------------------------------------------------------------------
def _fetch_boulder_via_featureserver(dest: Path) -> Path | None:
    """Fallback: page through the FeatureServer (maxRecordCount 1000)."""
    rows, offset = [], 0
    while True:
        r = requests.get(
            f"{BOULDER_FS}/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "orderByFields": "ObjectId2",
            },
            headers={"User-Agent": UA},
            timeout=120,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
        rows += [f["attributes"] for f in feats]
        if len(feats) < 1000:
            break
        offset += 1000
    pd.DataFrame(rows).to_csv(dest, index=False)
    return dest


def _clean(x) -> str:
    x = "" if x is None or x is pd.NA or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
    return "" if x.lower() == "nan" else x


def _boulder_query(street, city, postcode) -> dict | None:
    """Structured Nominatim query for a Boulder station address (same key on fetch and harmonise side)."""
    street = _clean(street)
    if not street:
        return None
    return {
        "street": street,
        "city": _clean(city) or "Boulder",
        "state": "Colorado",
        "postalcode": _clean(postcode),
        "country": "USA",
    }


def _nominatim_geocode(queries: list[dict], cache_path: Path) -> dict:
    """Structured Nominatim geocoding with an on-disk cache and the 1 req/s usage policy."""
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for q in queries:
        key = json.dumps(q, sort_keys=True)
        if key in cache:
            continue
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={**q, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": UA},
                timeout=60,
            )
            r.raise_for_status()
            res = r.json()
            cache[key] = (
                {
                    "lat": float(res[0]["lat"]),
                    "lon": float(res[0]["lon"]),
                    "display_name": res[0].get("display_name"),
                }
                if res
                else None
            )
        except Exception as e:  # noqa: BLE001
            log(f"  ! nominatim failed for {q}: {e}")
            cache[key] = None
        time.sleep(1.2)
        cache_path.write_text(json.dumps(cache, indent=1))
    return cache


def fetch_boulder(geocode: bool = True) -> Path:
    d = SRC_RAW / "boulder"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "electric_vehicle_charging_station_data.csv"
    if _try_download(BOULDER_CSV, dest, timeout=600) is None or _looks_like_html(dest):
        if dest.exists():
            dest.unlink()
        log("  boulder: hub CSV export unavailable, paging FeatureServer instead")
        _fetch_boulder_via_featureserver(dest)
    _try_download(BOULDER_DICT, d / "ev_datadictionary.csv")
    if geocode and dest.exists():
        df = _read_csv(dest)
        cols = {_norm_col(c): c for c in df.columns}
        addr = df[
            [
                cols["address"],
                cols["city"],
                cols.get("zip_postal_code", cols.get("postal_code", cols["city"])),
            ]
        ].drop_duplicates()
        queries = []
        for _, row in addr.iterrows():
            q = _boulder_query(*row.tolist())
            if q is not None:
                queries.append(q)
        log(f"  boulder: geocoding {len(queries)} distinct addresses via Nominatim (cached)")
        _nominatim_geocode(queries, d / "geocode_nominatim.json")
    _save_meta(
        d,
        {
            "provider": "City of Boulder, CO",
            "landing": f"https://open-data.bouldercolorado.gov/datasets/{BOULDER_ITEM}_0",
            "download": BOULDER_CSV,
            "feature_server": BOULDER_FS,
            "data_dictionary": BOULDER_DICT,
            "licence": "CC0 1.0 (licenseInfo on the Hub item)",
            "geocoding": "station street addresses geocoded with Nominatim (OSM, ODbL); flagged lat_source='nominatim_geocode'",
        },
    )
    return d


def harmonise_boulder() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = SRC_RAW / "boulder"
    f = d / "electric_vehicle_charging_station_data.csv"
    if not f.exists():
        return _empty_sessions(), pd.DataFrame(columns=STATION_COLS)
    df = _read_csv(f)
    content_cols = [c for c in df.columns if _norm_col(c) not in ("objectid", "objectid2", "fid")]
    n0 = len(df)
    df = df.drop_duplicates(subset=content_cols).reset_index(drop=True)
    log(
        f"  boulder: dropped {n0 - len(df):,} exact duplicate transactions (source table holds overlapping loads)"
    )
    cols = {_norm_col(c): c for c in df.columns}

    def pick(*cands):
        for k in cands:
            if k in cols:
                return df[cols[k]]
        return pd.Series(pd.NA, index=df.index, dtype="string")

    out = pd.DataFrame(index=df.index)
    out["city"] = "boulder"
    out["station_id"] = pick("station_name").str.strip()
    out["station_name"] = pick("station_name").str.strip()
    out["start_ts"] = _smart_datetime(
        pick("start_date_time", "start_date___time", "start_date"), (2017, 2026)
    )
    out["end_ts"] = _smart_datetime(pick("end_date_time", "end_date___time", "end_date"), (2017, 2026))
    out["tz"] = "America/Denver"
    out["duration_min"] = _duration_min(
        pick("total_duration_hh_mm_ss", "total_duration__hh_mm_ss_", "total_duration")
    )
    out["charging_min"] = _duration_min(
        pick("charging_time_hh_mm_ss", "charging_time__hh_mm_ss_", "charging_time")
    )
    out["energy_kwh"] = pd.to_numeric(pick("energy_kwh", "energy__kwh_"), errors="coerce")
    out["port_type"] = pick("port_type").str.strip()
    out["postcode"] = pick("zip_postal_code", "postal_code").str.strip()
    out["session_id"] = pick("objectid", "objectid2")
    out["source_file"] = f.name
    address = (
        pick("address").fillna("").str.strip()
        + ", "
        + pick("city").fillna("").str.strip()
        + " "
        + out["postcode"].fillna("")
    ).str.strip(", ")
    # geocoded coordinates (address level)
    cache_p = d / "geocode_nominatim.json"
    if cache_p.exists():
        cache = json.loads(cache_p.read_text())
        lat, lon = [], []
        for street, city, pc in zip(pick("address"), pick("city"), out["postcode"], strict=False):
            q = _boulder_query(street, city, pc)
            hit = cache.get(json.dumps(q, sort_keys=True)) if q is not None else None
            lat.append(hit["lat"] if hit else None)
            lon.append(hit["lon"] if hit else None)
        out["lat"], out["lon"] = lat, lon
        out["lat_source"] = (
            pd.Series(lat, index=out.index).notna().map({True: "nominatim_geocode", False: None})
        )
    extra = pd.DataFrame({"station_id": out["station_id"], "address": address}).drop_duplicates("station_id")
    sessions = _finalise_sessions(out)
    stations = _station_table(sessions, extra, "boulder", "boulder_hub_csv+nominatim")
    return sessions, stations


# --------------------------------------------------------------------------------------------------
# 6. Paris Belib' (snapshot + EDF challenge series)
# --------------------------------------------------------------------------------------------------
def fetch_paris_belib(skip_large: bool = False) -> Path:
    d = SRC_RAW / "paris_belib"
    (d / "realtime").mkdir(parents=True, exist_ok=True)
    (d / "edf_smdc").mkdir(parents=True, exist_ok=True)
    # one snapshot per UTC day (idempotent within a day); a crawler would do this every 5-15 min
    _try_download(f"{PARIS_API}/{PARIS_RT}/exports/json", d / "realtime" / f"belib_realtime_{TODAY}.json")
    _try_download(f"{PARIS_API}/{PARIS_STATIC}/exports/json", d / f"belib_static_{TODAY}.json")
    for name in (PARIS_RT, PARIS_STATIC):
        _try_download(f"{PARIS_API}/{name}", d / f"metadata_{name[:60]}.json")
    for fname, mb in EDF_FILES.items():
        if skip_large and mb > LARGE_MB:
            log(f"  paris: skipping {fname} (~{mb} MB) because --skip-large")
            continue
        _try_download(f"{EDF_RAW}{fname}", d / "edf_smdc" / fname, timeout=900)
    _try_download(
        "https://gitlab.com/smarter-mobility-data-challenge/tutorials/-/raw/master/LICENSE.md",
        d / "edf_smdc" / "LICENSE.md",
    )
    _save_meta(
        d,
        {
            "provider": "Ville de Paris (DVD) / TotalEnergies Marketing France (operator); EDF R&D (challenge series)",
            "realtime_dataset": f"https://opendata.paris.fr/explore/dataset/{PARIS_RT}/",
            "static_dataset": f"https://opendata.paris.fr/explore/dataset/{PARIS_STATIC}/",
            "api_export": f"{PARIS_API}/{PARIS_RT}/exports/json",
            "api_records": f"{PARIS_API}/{PARIS_RT}/records?limit=100&offset=0",
            "licence": "ODbL (both Paris datasets); EDF SMDC data ODbL, code GPLv3",
            "edf_repo": "https://gitlab.com/smarter-mobility-data-challenge/tutorials (0. Input Data/train.csv, test.csv)",
            "edf_paper": "https://arxiv.org/abs/2306.06142",
        },
    )
    return d


def harmonise_paris_belib() -> dict[str, pd.DataFrame]:
    d = SRC_RAW / "paris_belib"
    out: dict[str, pd.DataFrame] = {}
    # --- stations from the static PDC list
    statics = sorted(d.glob("belib_static_*.json"))
    if statics:
        recs = json.loads(statics[-1].read_text())
        st = pd.json_normalize(recs)
        st["lat"] = st["coordonneesxy.lat"] if "coordonneesxy.lat" in st else None
        st["lon"] = st["coordonneesxy.lon"] if "coordonneesxy.lon" in st else None
        st["power_kw"] = pd.to_numeric(st.get("puissance_nominale"), errors="coerce")
        st["station_id"] = st["id_station_itinerance"].fillna(st["id_station_local"])
        stations = (
            st.groupby("station_id")
            .agg(
                station_name=("nom_station", "first"),
                address=("adresse_station", "first"),
                arrondissement=("arrondissement", "first"),
                lat=("lat", "median"),
                lon=("lon", "median"),
                n_pdc=("id_pdc_itinerance", "nunique"),
                power_kw_max=("power_kw", "max"),
                statut=("statut_pdc", lambda x: x.mode().iloc[0] if len(x) else None),
                date_mise_en_service=("date_mise_en_service", "min"),
            )
            .reset_index()
        )
        stations.insert(0, "city", "paris")
        stations["snapshot_file"] = statics[-1].name
        out["paris_belib_stations"] = stations
        pdc = st[
            [
                c
                for c in (
                    "id_pdc_itinerance",
                    "id_pdc_local",
                    "station_id",
                    "nom_station",
                    "statut_pdc",
                    "puissance_nominale",
                    "prise_type_2",
                    "prise_type_combo_ccs",
                    "prise_type_chademo",
                    "prise_type_ef",
                    "arrondissement",
                    "adresse_station",
                    "lat",
                    "lon",
                    "date_mise_en_service",
                    "date_maj",
                )
                if c in st.columns
            ]
        ].copy()
        out["paris_belib_pdc_static"] = pdc
    # --- latest real-time snapshot (one row per PDC with status)
    rts = sorted((d / "realtime").glob("belib_realtime_*.json"))
    if rts:
        frames = []
        for p in rts:
            rt = pd.json_normalize(json.loads(p.read_text()))
            rt["snapshot_file"] = p.name
            frames.append(rt)
        rt = pd.concat(frames, ignore_index=True)
        rt = rt.rename(columns={"coordonneesxy.lat": "lat", "coordonneesxy.lon": "lon"})
        rt["last_updated"] = pd.to_datetime(rt["last_updated"], errors="coerce", utc=True)
        rt["occupied"] = rt["statut_pdc"].eq("Occupé (en charge)")
        rt["available"] = rt["statut_pdc"].eq("Disponible")
        out["paris_belib_realtime_snapshots"] = rt[
            [
                c
                for c in (
                    "snapshot_file",
                    "id_pdc",
                    "statut_pdc",
                    "occupied",
                    "available",
                    "last_updated",
                    "arrondissement",
                    "adresse_station",
                    "lat",
                    "lon",
                )
                if c in rt.columns
            ]
        ]
    # --- EDF Smarter Mobility Data Challenge 15-min occupancy (train has labels; test only covariates)
    tr = d / "edf_smdc" / "train.csv"
    if tr.exists():
        occ = pd.read_csv(tr, dtype={"Station": str, "Postcode": str})
        occ["date"] = pd.to_datetime(occ["date"], errors="coerce")
        occ = occ.rename(
            columns={
                "date": "ts",
                "Station": "station_id",
                "Available": "available",
                "Charging": "charging",
                "Passive": "passive",
                "Other": "other",
                "Latitude": "lat",
                "Longitude": "lon",
                "Postcode": "postcode",
                "area": "area",
            }
        )
        occ["n_plugs"] = occ[["available", "charging", "passive", "other"]].sum(axis=1)
        occ["occupancy_rate"] = (occ["charging"] + occ["passive"]) / occ["n_plugs"].where(occ["n_plugs"] > 0)
        occ.insert(0, "city", "paris")
        out["paris_belib_occupancy_15min"] = occ[
            [
                "city",
                "ts",
                "station_id",
                "available",
                "charging",
                "passive",
                "other",
                "n_plugs",
                "occupancy_rate",
                "lat",
                "lon",
                "postcode",
                "area",
            ]
        ]
        est = (
            occ.groupby("station_id")
            .agg(
                lat=("lat", "first"),
                lon=("lon", "first"),
                postcode=("postcode", "first"),
                area=("area", "first"),
                n_plugs=("n_plugs", "max"),
                mean_occupancy=("occupancy_rate", "mean"),
                first_ts=("ts", "min"),
                last_ts=("ts", "max"),
                n_obs=("ts", "size"),
            )
            .reset_index()
        )
        est.insert(0, "city", "paris")
        out["paris_belib_edf_stations"] = est
    return out


# --------------------------------------------------------------------------------------------------
# 7. ChargePlace Scotland network feed (coordinates for CPS charge-point IDs)
# --------------------------------------------------------------------------------------------------
def fetch_cps() -> Path:
    d = SRC_RAW / "chargeplace_scotland"
    d.mkdir(parents=True, exist_ok=True)
    _try_download(CPS_LOCATIONS, d / f"cps_locations_{TODAY}.json")
    _try_download(CPS_TARIFFS, d / f"cps_tariffs_{TODAY}.json")
    # monthly session files published by the network (licence not stated -> listed, not bulk-downloaded)
    try:
        html = requests.get(CPS_MONTHLY_PAGE, headers={"User-Agent": UA}, timeout=60).text
        links = sorted(
            set(re.findall(r'href="(https://chargeplacescotland\.org/wp-content/uploads/[^"]+)"', html))
        )
        (d / "monthly_performance_links.txt").write_text("\n".join(links) + "\n")
        log(
            f"  cps: {len(links)} monthly performance files listed ({sum('ession' in u for u in links)} session files)"
        )
    except Exception as e:  # noqa: BLE001
        log(f"  ! cps monthly page: {e}")
    _save_meta(
        d,
        {
            "provider": "ChargePlace Scotland (Transport Scotland network, operated by Swarco/SmartCharging feed)",
            "locations_feed": CPS_LOCATIONS,
            "tariffs_feed": CPS_TARIFFS,
            "monthly_performance_page": CPS_MONTHLY_PAGE,
            "monthly_sessions_licence": "not stated (site footer: all rights reserved) - not bulk downloaded",
            "strathclyde_cc_by": {
                "url": CPS_STRATHCLYDE_ZIP,
                "doi": "10.15129/1f431af7-5caa-4840-a9ab-c1f3b521e033",
                "licence": "CC BY 4.0",
                "size_mb": 144,
                "note": "Oct 2022 - Mar 2024 sessions; direct download is behind a Cloudflare browser challenge (HTTP 403 for scripts)",
            },
            "licence": "feed: open API advertised on chargeplacescotland.org/network-performance-2 (no explicit licence text)",
        },
    )
    return d


def _postcode_centroids(postcodes: list[str], cache_path: Path) -> dict[str, tuple[float, float]]:
    """UK postcode -> (lat, lon) centroid via postcodes.io (ONS Postcode Directory, OGL; no key), cached."""
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted(
        {re.sub(r"\s+", " ", p.strip().upper()) for p in postcodes if isinstance(p, str) and p.strip()}
        - set(cache)
    )
    for i in range(0, len(todo), 100):
        chunk = todo[i : i + 100]
        try:
            r = requests.post(
                "https://api.postcodes.io/postcodes",
                json={"postcodes": chunk},
                headers={"User-Agent": UA},
                timeout=60,
            )
            r.raise_for_status()
            for item in r.json().get("result", []):
                res = item.get("result")
                cache[item["query"]] = [res["latitude"], res["longitude"]] if res else None
        except Exception as e:  # noqa: BLE001
            log(f"  ! postcodes.io failed: {e}")
            break
        time.sleep(0.5)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1))
    return {k: tuple(v) for k, v in cache.items() if v}


def _cps_coords() -> pd.DataFrame | None:
    files = sorted((SRC_RAW / "chargeplace_scotland").glob("cps_locations_*.json"))
    if not files:
        return None
    st = _cps_stations(files[-1])
    return (
        pd.DataFrame(
            {
                "station_id": st["station_id"],
                "lat": st["lat"],
                "lon": st["lon"],
                "station_name": st["station_name"],
                "address": st["address"],
                "power_kw": st["power_kw"],
                "lat_source": "cps_public_feed",
            }
        )
        .dropna(subset=["station_id", "lat", "lon"])
        .drop_duplicates("station_id")
    )


def _cps_stations(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text())
    rows = []
    for L in data.get("data", []):
        c = L.get("coordinates") or {}
        for e in L.get("evses", []):
            kw = max([(k.get("max_electric_power") or 0) / 1000 for k in e.get("connectors", [])] or [None])
            rows.append(
                {
                    "city": "scotland_cps",
                    "location_id": L.get("id"),
                    "station_id": _norm_cp(e.get("physical_reference")),
                    "evse_id": e.get("evse_id"),
                    "station_name": L.get("name"),
                    "address": ", ".join(
                        x for x in (L.get("address"), L.get("city"), L.get("postal_code")) if x
                    ),
                    "postcode": L.get("postal_code"),
                    "town": L.get("city"),
                    "lat": pd.to_numeric(c.get("latitude"), errors="coerce"),
                    "lon": pd.to_numeric(c.get("longitude"), errors="coerce"),
                    "power_kw": kw,
                    "connector_standards": ";".join(
                        sorted({k.get("standard", "") for k in e.get("connectors", [])})
                    ),
                    "status": e.get("status"),
                    "last_updated": e.get("last_updated"),
                    "snapshot_file": path.name,
                }
            )
    return pd.DataFrame(rows)


def harmonise_cps() -> dict[str, pd.DataFrame]:
    files = sorted((SRC_RAW / "chargeplace_scotland").glob("cps_locations_*.json"))
    if not files:
        return {}
    return {"cps_stations": _cps_stations(files[-1])}


# --------------------------------------------------------------------------------------------------
# 8. UrbanEV (Shenzhen)
# --------------------------------------------------------------------------------------------------
def fetch_urbanev() -> Path:
    d = SRC_RAW / "urbanev"
    d.mkdir(parents=True, exist_ok=True)
    for rel in URBANEV_FILES:
        _try_download(URBANEV_RAW + rel, d / rel, retries=2, timeout=600)
    _save_meta(
        d,
        {
            "provider": "IntelligentSystemsLab (SYSU / PolyU) - UrbanEV",
            "repo": "https://github.com/IntelligentSystemsLab/UrbanEV",
            "dryad": "https://doi.org/10.5061/dryad.np5hqc04z",
            "paper": "https://doi.org/10.1038/s41597-025-04874-4",
            "licence": "CC0 1.0 Universal",
            "note": "zone-level hourly data (275 zones, 1,362 stations, 17,532 piles), 2022-09-01 .. 2023-02-28; station coordinates are GCJ-02",
        },
    )
    return d


def _melt_wide(path: Path, value_name: str) -> pd.DataFrame | None:
    if not path.exists():
        return None
    w = pd.read_csv(path)
    tcol = w.columns[0]
    w[tcol] = pd.to_datetime(w[tcol], errors="coerce")
    long = w.melt(id_vars=[tcol], var_name="zone_id", value_name=value_name)
    return long.rename(columns={tcol: "ts"})


def harmonise_urbanev() -> dict[str, pd.DataFrame]:
    d = SRC_RAW / "urbanev" / "data"
    out: dict[str, pd.DataFrame] = {}
    if (d / "inf_raw.csv").exists():
        st = pd.read_csv(d / "inf_raw.csv", dtype={"station_id": str, "TAZID": str})
        st = st.rename(
            columns={
                "longitude": "lon_gcj02",
                "latitude": "lat_gcj02",
                "charge_count": "n_piles",
                "TAZID": "zone_id",
            }
        )
        kept = (
            set(pd.read_csv(d / "inf.csv", dtype={"station_id": str})["station_id"])
            if (d / "inf.csv").exists()
            else set()
        )
        st["in_filtered_set"] = st["station_id"].isin(kept)
        st.insert(0, "city", "shenzhen")
        st["crs_note"] = "GCJ-02 (needs conversion to WGS84 before joining OSM)"
        out["urbanev_stations"] = st
    parts = [
        _melt_wide(d / "occupancy.csv", "occupancy_pct"),
        _melt_wide(d / "duration.csv", "duration_h"),
        _melt_wide(d / "volume.csv", "volume_kwh"),
        _melt_wide(d / "volume-11kW.csv", "volume_11kw_kwh"),
        _melt_wide(d / "e_price.csv", "e_price_yuan_kwh"),
        _melt_wide(d / "s_price.csv", "s_price_yuan_kwh"),
    ]
    parts = [p for p in parts if p is not None]
    if parts:
        z = parts[0]
        for p in parts[1:]:
            z = z.merge(p, on=["ts", "zone_id"], how="outer")
        z.insert(0, "city", "shenzhen")
        out["urbanev_zone_hourly"] = z.sort_values(["ts", "zone_id"]).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------------------------------
# Summaries, orchestration
# --------------------------------------------------------------------------------------------------
def summarise_sessions(name: str, s: pd.DataFrame, stations: pd.DataFrame | None = None) -> dict:
    out: dict = {"dataset": name, "rows": int(len(s))}
    if not len(s):
        return out
    ts = s["start_ts"].dropna()
    if len(ts):
        out["start"], out["end"] = str(ts.min().date()), str(ts.max().date())
        h = ts.dt.hour.value_counts(normalize=True).reindex(range(24), fill_value=0.0)
        wk = (ts.dt.dayofweek >= 5).mean()
        out["hourly_profile"] = (
            f"peak {int(h.idxmax()):02d}h ({h.max():.1%}); 07-10h {h.loc[7:10].sum():.0%}; "
            f"11-15h {h.loc[11:15].sum():.0%}; 16-19h {h.loc[16:19].sum():.0%}; "
            f"20-23h {h.loc[20:23].sum():.0%}; 00-06h {h.loc[0:6].sum():.0%}; weekend {wk:.0%}"
        )
        out["hourly_shares"] = [round(float(x), 4) for x in h.values]
    out["n_stations"] = int(s["station_id"].nunique())
    out["share_rows_with_coords"] = round(float(s["lat"].notna().mean()), 3)
    if stations is not None and len(stations):
        out["share_stations_with_coords"] = round(float(stations["lat"].notna().mean()), 3)
    out["median_kwh"] = round(float(s["energy_kwh"].median()), 2) if s["energy_kwh"].notna().any() else None
    out["median_duration_min"] = (
        round(float(s["duration_min"].median()), 1) if s["duration_min"].notna().any() else None
    )
    if s["charging_min"].notna().any():
        out["median_charging_min"] = round(float(s["charging_min"].median()), 1)
    out["share_users_known"] = round(float(s["user_id"].notna().mean()), 3)
    issues = []
    z = float((s["energy_kwh"] <= 0.05).mean())
    if z > 0.02:
        issues.append(f"{z:.1%} sessions with <=0.05 kWh")
    neg = float((s["duration_min"] <= 0).mean())
    if neg > 0.005:
        issues.append(f"{neg:.1%} non-positive durations")
    longd = float((s["duration_min"] > 24 * 60).mean())
    if longd > 0.005:
        issues.append(f"{longd:.1%} sessions > 24 h")
    miss_ts = float(s["start_ts"].isna().mean())
    if miss_ts > 0.001:
        issues.append(f"{miss_ts:.1%} unparsable start timestamps")
    big = float((s["energy_kwh"] > 150).mean())
    if big > 0.001:
        issues.append(f"{big:.2%} sessions > 150 kWh")
    dup = float(s.duplicated(subset=["station_id", "connector", "start_ts", "energy_kwh"]).mean())
    if dup > 0.001:
        issues.append(f"{dup:.1%} duplicate (station, connector, start, kWh) rows")
    out["issues"] = issues
    return out


def _write(name: str, df: pd.DataFrame) -> Path:
    SRC_INTERIM.mkdir(parents=True, exist_ok=True)
    p = SRC_INTERIM / f"{name}.parquet"
    df.to_parquet(p, index=False)
    log(f"  wrote {p.relative_to(ROOT)}  rows={len(df):,}  size={p.stat().st_size / 1e6:.1f} MB")
    return p


SESSION_SOURCES = {
    "dundee": (fetch_dundee, harmonise_dundee),
    "pkc": (fetch_pkc, harmonise_pkc),
    "leeds": (fetch_leeds, harmonise_leeds),
    "palo_alto": (fetch_palo_alto, harmonise_palo_alto),
    "boulder": (fetch_boulder, harmonise_boulder),
}
TABLE_SOURCES = {  # sources that yield dict[name -> DataFrame] instead of (sessions, stations)
    "cps": (fetch_cps, harmonise_cps),
    "paris_belib": (fetch_paris_belib, harmonise_paris_belib),
    "urbanev": (fetch_urbanev, harmonise_urbanev),
}
ORDER = [
    "cps",
    "dundee",
    "pkc",
    "leeds",
    "palo_alto",
    "boulder",
    "paris_belib",
    "urbanev",
]  # cps first: coords for Dundee/PKC


def harmonise(only: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Build all harmonised tables from files already in data/raw/sessions_open (no downloads)."""
    tables: dict[str, pd.DataFrame] = {}
    for name in ORDER:
        if only and name not in only:
            continue
        if name in SESSION_SOURCES:
            s, st = SESSION_SOURCES[name][1]()
            tables[f"{name}_sessions"], tables[f"{name}_stations"] = s, st
        else:
            tables.update(TABLE_SOURCES[name][1]())
    return tables


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated subset of: " + ",".join(ORDER))
    ap.add_argument(
        "--skip-large", action="store_true", help=f"skip downloads larger than ~{LARGE_MB} MB (EDF train.csv)"
    )
    ap.add_argument("--no-geocode", action="store_true", help="do not call Nominatim for Boulder addresses")
    ap.add_argument("--no-fetch", action="store_true", help="only rebuild parquet from existing raw files")
    args = ap.parse_args(argv)
    only = [x.strip() for x in args.only.split(",")] if args.only else None

    SRC_RAW.mkdir(parents=True, exist_ok=True)
    SRC_INTERIM.mkdir(parents=True, exist_ok=True)
    summary: dict = {"run": datetime.now(UTC).isoformat(timespec="seconds"), "datasets": [], "failures": {}}
    for name in ORDER:
        if only and name not in only:
            continue
        t0 = time.time()
        log(f"=== {name} ===")
        try:
            if not args.no_fetch:
                fetch = (SESSION_SOURCES.get(name) or TABLE_SOURCES.get(name))[0]
                if name == "boulder":
                    fetch(geocode=not args.no_geocode)
                elif name == "paris_belib":
                    fetch(skip_large=args.skip_large)
                else:
                    fetch()
            if name in SESSION_SOURCES:
                sessions, stations = SESSION_SOURCES[name][1]()
                _write(f"{name}_sessions", sessions)
                _write(f"{name}_stations", stations)
                rep = summarise_sessions(name, sessions, stations)
                summary["datasets"].append(rep)
                log(
                    f"  {json.dumps({k: v for k, v in rep.items() if k != 'hourly_shares'}, ensure_ascii=False)}"
                )
            else:
                for tname, df in TABLE_SOURCES[name][1]().items():
                    _write(tname, df)
                    rep = {"dataset": tname, "rows": int(len(df)), "columns": list(map(str, df.columns))[:20]}
                    for tcol in ("ts", "last_updated"):
                        if tcol in df.columns and df[tcol].notna().any():
                            rep["start"], rep["end"] = str(df[tcol].min())[:10], str(df[tcol].max())[:10]
                    for idcol in ("station_id", "zone_id", "id_pdc"):
                        if idcol in df.columns:
                            rep[f"n_{idcol}"] = int(df[idcol].nunique())
                    if "lat" in df.columns:
                        rep["share_rows_with_coords"] = round(float(df["lat"].notna().mean()), 3)
                    summary["datasets"].append(rep)
                    log(f"  {json.dumps(rep, ensure_ascii=False, default=str)}")
        except Exception as e:  # noqa: BLE001
            summary["failures"][name] = f"{type(e).__name__}: {e}"
            log(f"  !! {name} FAILED: {e}\n{traceback.format_exc()}")
        log(f"  ({time.time() - t0:.0f}s)")
    (SRC_INTERIM / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    log(f"summary -> {SRC_INTERIM / 'summary.json'}")
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
