---
id: weather_open_meteo
title: Open-Meteo historical weather archive, hourly, central London
provider: Open-Meteo (ERA5 / ECMWF reanalysis via Copernicus C3S)
url: https://open-meteo.com/en/docs/historical-weather-api
download_url: https://archive-api.open-meteo.com/v1/archive?latitude=51.5074&longitude=-0.1278&start_date=2021-01-01&end_date=2025-12-31&hourly=temperature_2m,precipitation,wind_speed_10m&timezone=UTC
licence: CC BY 4.0 (Open-Meteo; underlying ERA5 data (C) ECMWF / Copernicus). Free tier is non-commercial only, <10,000 calls/day, 5,000/h, 600/min
status: observed
retrieved: 2026-09-10
size_mb: 0.9 (parquet) + 1.6 (raw JSON cache)
spatial_unit: point (nearest reanalysis grid cell to 51.5074, -0.1278; API reports 51.4938, -0.1630, 16 m)
temporal: hourly 2021-01-01 00:00 .. 2025-12-31 23:00 UTC (43,824 rows, no gaps, no nulls)
script: src/chargescape/data/weather.py
raw_path: data/raw/weather/open_meteo/
---

## What it is
Hourly reanalysis weather for one central-London point, pulled one calendar year per request
from the Open-Meteo *Historical Weather* (archive) API. No API key. Values are ERA5 /
ERA5-Land model output, not station observations, but at hourly/city scale they track London
station data closely and, unlike Met Office MIDAS, need no registration.

Output: `data/interim/weather/london_hourly.parquet` + `london_hourly.meta.json`
(units, grid point, row count, attribution string).

## Fields used
| column | unit | note |
|---|---|---|
| `time_utc` | timestamp, UTC | hour start |
| `time_local` | naive timestamp, Europe/London | derived; use for day-of-week / hour-of-day features |
| `temperature_2m` | degC | 2 m air temperature |
| `precipitation` | mm | total (rain + showers + snow water eq.) in the hour |
| `wind_speed_10m` | km/h | 10 m wind speed (NB km/h, not m/s) |

2021-25 summary: temperature mean 11.7 degC (min -10.3, max 37.9); precipitation mean 0.085 mm/h,
max 14.7 mm/h; wind mean 13.9 km/h, max 68 km/h.

## Known issues / caveats
- Single point for the whole of Greater London: fine for temporal demand modelling (cold-weather
  range loss, rain -> fewer trips), not for spatial variation.
- Reanalysis is smoother than station data (extremes under-estimated by ~1-2 degC).
- Free tier terms: non-commercial use only; attribution "Weather data by Open-Meteo.com" required.
- Archive data lag is ~5 days; 2025 is complete as of 2026-09-10.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.weather
```
Idempotent: JSON responses are cached by URL+params hash under `data/raw/weather/open_meteo/`;
delete the cache to force a re-download.
