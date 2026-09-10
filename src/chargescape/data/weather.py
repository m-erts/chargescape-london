"""Weather: Open-Meteo historical archive (ERA5/ECMWF reanalysis) for central London.

Source: https://archive-api.open-meteo.com/v1/archive  (free tier, no API key, CC BY 4.0,
non-commercial use, <10k calls/day).  We fetch hourly temperature_2m, precipitation and
wind_speed_10m for 2021-01-01..2025-12-31, one request per calendar year, cache the raw JSON
under data/raw/weather/open_meteo/ and write a single tidy parquet to
data/interim/weather/london_hourly.parquet.

Run:  PYTHONPATH=src python -m chargescape.data.weather
Idempotent: cached JSON is reused; the parquet is rebuilt from cache (cheap).
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from chargescape.utils.http import get_json
from chargescape.utils.paths import INTERIM, RAW

API = "https://archive-api.open-meteo.com/v1/archive"
LAT, LON = 51.5074, -0.1278  # Charing Cross, central London
START, END = "2021-01-01", "2025-12-31"
HOURLY = ["temperature_2m", "precipitation", "wind_speed_10m"]

RAW_DIR = RAW / "weather" / "open_meteo"
OUT_DIR = INTERIM / "weather"
OUT = OUT_DIR / "london_hourly.parquet"
META = OUT_DIR / "london_hourly.meta.json"


def _years() -> list[int]:
    return list(range(int(START[:4]), int(END[:4]) + 1))


def fetch_year(year: int) -> dict:
    """Fetch one calendar year (hourly, UTC). Cached on disk by url+params."""
    y0 = max(f"{year}-01-01", START)
    y1 = min(f"{year}-12-31", END)
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": y0,
        "end_date": y1,
        "hourly": ",".join(HOURLY),
        "timezone": "UTC",  # unambiguous; local time is derived below
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "temperature_unit": "celsius",
    }
    return get_json(API, params, cache_dir=RAW_DIR, timeout=180)


def build() -> pd.DataFrame:
    frames = []
    meta = {}
    for y in _years():
        js = fetch_year(y)
        h = js["hourly"]
        df = pd.DataFrame(h)
        df["time_utc"] = pd.to_datetime(df.pop("time"), utc=True)
        frames.append(df)
        meta.setdefault("hourly_units", js.get("hourly_units"))
        meta.setdefault(
            "grid_point",
            {
                "latitude": js.get("latitude"),
                "longitude": js.get("longitude"),
                "elevation": js.get("elevation"),
            },
        )
    out = pd.concat(frames, ignore_index=True).drop_duplicates("time_utc").sort_values("time_utc")
    out["time_local"] = out["time_utc"].dt.tz_convert("Europe/London").dt.tz_localize(None)
    out = out[["time_utc", "time_local", *HOURLY]].reset_index(drop=True)
    for c in HOURLY:
        out[c] = out[c].astype("float32")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    meta.update(
        {
            "source": API,
            "requested_point": {"latitude": LAT, "longitude": LON},
            "variables": HOURLY,
            "start": START,
            "end": END,
            "rows": int(len(out)),
            "first": str(out.time_utc.min()),
            "last": str(out.time_utc.max()),
            "missing": {c: int(out[c].isna().sum()) for c in HOURLY},
            "licence": "CC BY 4.0 (Open-Meteo; ERA5 data from Copernicus Climate Change Service)",
            "attribution": "Weather data by Open-Meteo.com (https://open-meteo.com), CC BY 4.0",
        }
    )
    META.write_text(json.dumps(meta, indent=1, default=str))
    return out


def main() -> int:
    df = build()
    print(f"[weather] wrote {OUT} rows={len(df):,} span={df.time_utc.min()} .. {df.time_utc.max()}")
    print(df.describe().T.to_string())
    print(f"[weather] missing values: { {c: int(df[c].isna().sum()) for c in HOURLY} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
