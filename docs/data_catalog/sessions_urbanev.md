---
id: sessions_urbanev
title: UrbanEV - open benchmark of EV charging demand in Shenzhen (zone-level hourly)
provider: IntelligentSystemsLab (Sun Yat-sen University / PolyU) - Li, Qu, Tan, You, Zhu, Fan (Scientific Data 2025)
url: https://github.com/IntelligentSystemsLab/UrbanEV ; https://doi.org/10.5061/dryad.np5hqc04z
download_url: https://raw.githubusercontent.com/IntelligentSystemsLab/UrbanEV/main/data/<file>.csv (occupancy, duration, volume, volume-11kW, e_price, s_price, inf, inf_raw, adj, distance, poi, weather_*)
licence: CC0 1.0 Universal (LICENSE in repo, verified; GitHub API reports spdx CC0-1.0)
status: observed
retrieved: 2026-09-10
size_mb: 116 (raw repo data/ folder incl. 32 MB poi.csv); 9.8 (parquet)
spatial_unit: traffic zone (275 zones) + station points (1,587 raw / 1,362 filtered; GCJ-02 coordinates)
temporal: hourly, 2022-09-01 .. 2023-02-28 (4,344 hours)
script: src/chargescape/data/sessions_open.py (fetch_urbanev / harmonise_urbanev)
raw_path: data/raw/sessions_open/urbanev/
---

## What it is
The best open spatio-temporal charging-demand benchmark: six months of public-charging status scraped
every 5 min from 1,682 stations / 24,798 piles in Shenzhen, cleaned and aggregated to **275 traffic
zones x hourly**: occupancy (%), charging duration (pile-hours), volume (kWh, pile-rated and an
11 kW-capped vehicle-side alternative), electricity and service prices, plus static covariates (zone
adjacency, distances, POIs by 3 classes, area/perimeter, weather at two stations). The GitHub `data/`
folder is the zone-level hourly set used in the Scientific Data paper; 5-min zone-level and raw
station-level series live on Dryad / Google Drive (not fetched - several GB).

## Fields used
* `urbanev_stations.parquet` (1,587 stations from `inf_raw.csv`): station_id, lon_gcj02, lat_gcj02,
  n_piles, zone_id (TAZ), area, perimeter, `in_filtered_set` (True for the 1,362 stations kept in `inf.csv`).
  **Coordinates are GCJ-02** (Chinese offset datum) - convert to WGS84 (e.g. `eviltransform`) before any OSM join.
* `urbanev_zone_hourly.parquet` (1,194,600 rows = 275 zones x 4,344 h): ts, zone_id, occupancy_pct,
  duration_h, volume_kwh, volume_11kw_kwh, e_price_yuan_kwh, s_price_yuan_kwh (long format, melted from
  the wide CSVs). `adj.csv`, `distance.csv`, `poi.csv`, `weather_*.csv` are kept raw for the forecasting
  module.

## Harmonised outputs (2026-09-10 run)
* Zone-hour medians: occupancy 11 % (mean 17.9 %, max 373 % - the "occupancy" is a count of busy piles per
  zone divided by a fixed base, so >100 % occurs), duration 7 pile-h, volume 54 kWh.
* Diurnal occupancy is **night-peaked** (21 % at 01h vs 15 % at 15-17h): overnight charging by ride-hailing/
  taxi fleets and residents at cheap night tariffs - the opposite of the Western destination profiles.

## Known issues / caveats
* No per-session records: only zone aggregates. Use it for the forecasting/benchmark module, not for kWh/dwell
  calibration.
* `volume.csv` overestimates energy (pile-rated power x occupied hours); the paper recommends `volume-11kW` for
  DC stations. Occupancy counts *unavailable* piles (busy + faulty), duration/volume count only charging piles.
* Zone ids in the hourly files are a subset (275) of the TAZ ids in `inf_raw.csv`; SZ_districts shapefile is
  district-level (10 polygons), not the TAZ geometry - TAZ polygons are not published.
* Transfer to London: land-use/price regime very different; useful as a stress-test of model architectures
  (GCN/LSTM baselines shipped in the repo), not of behavioural parameters.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only urbanev
```
