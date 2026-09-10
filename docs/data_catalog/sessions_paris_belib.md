---
id: sessions_paris_belib
title: Paris Belib' - real-time availability (snapshot) + EDF Smarter Mobility Data Challenge 15-min occupancy
provider: Ville de Paris - Direction de la Voirie et des Déplacements (opendata.paris.fr); operator TotalEnergies Marketing France; EDF R&D (challenge series)
url: https://opendata.paris.fr/explore/dataset/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel/ ; https://gitlab.com/smarter-mobility-data-challenge/tutorials
download_url: https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/belib-points-de-recharge-pour-vehicules-electriques-disponibilite-temps-reel/exports/json ; https://gitlab.com/smarter-mobility-data-challenge/tutorials/-/raw/master/0.%20Input%20Data/train.csv
licence: ODbL (both Paris datasets - verified in API metadata); EDF challenge data ODbL, code GPLv3 (LICENSE.md in repo)
status: observed
retrieved: 2026-09-10
size_mb: 194 (raw: EDF train.csv 172 + test.csv 14 + daily JSON snapshots ~4); 2.4 (occupancy parquet)
spatial_unit: point (charge point / station)
temporal: real-time status snapshot (one per run-day, dataset refreshes every ~5 min); EDF series 15-min, 2020-07-03 .. 2021-02-18 (train; test = 2021-02-19 .. 2021-03-xx covariates only)
script: src/chargescape/data/sessions_open.py (fetch_paris_belib / harmonise_paris_belib)
raw_path: data/raw/sessions_open/paris_belib/
---

## What it is
Two things bundled because they describe the same network:

1. **Belib' real-time availability** (`...-disponibilite-temps-reel`, 1,969 charge points / PDC on
   2026-09-10) - status per PDC (`Disponible`, `Occupé (en charge)`, `En maintenance`, `Inconnu`,
   `Mise en service planifiée`), `last_updated`, address, arrondissement, lat/lon. Plus the **static** list
   (`...-donnees-statiques`, 1,887 PDC in 379 stations) with nominal power, plug types, commissioning date.
   Only the Belib' network (TotalEnergies-operated on-street posts, mostly 3 x 22 kW AC per station,
   some 50 kW DC) is supervised; "Paris Recharge" legacy points are not.
2. **EDF Smarter Mobility Data Challenge** (2023) - EDF R&D polled the same API every 15 minutes from
   July 2020 and published the series for 91 stations (3 plugs each, 4 areas) as `train.csv`
   (`date, Station, Available, Charging, Passive, Other, tod, dow, trend, Latitude, Longitude, Postcode, area`)
   and `test.csv` (covariates only, labels withheld). `*_uci.csv` are the same tables re-exported for the UCI
   repository and were not downloaded.

## Fields used
Static -> `paris_belib_stations.parquet` (station_id = `id_station_itinerance`, lat/lon, n_pdc,
power_kw_max, statut, date_mise_en_service) and `paris_belib_pdc_static.parquet` (per PDC, plug flags).
Real-time -> `paris_belib_realtime_snapshots.parquet` (one row per PDC per snapshot file: statut, occupied,
available, last_updated, lat/lon). EDF -> `paris_belib_occupancy_15min.parquet` (ts, station_id,
available/charging/passive/other counts, n_plugs, occupancy_rate = (charging+passive)/n_plugs, lat/lon,
postcode, area) and `paris_belib_edf_stations.parquet` (91 stations, mean occupancy).

## Harmonised outputs (2026-09-10 run)
* Snapshot: 1,969 PDC; 1,095 available, 780 occupied (40% instantaneous occupancy at ~16:00 CEST on a
  Thursday), 53 maintenance, 38 unknown; 98.6% with coordinates. 379 stations, 100% with coordinates.
* EDF series: 1,851,083 station-quarter-hours, 91 stations, 2020-07-03 .. 2021-02-18, mean occupancy 17.3%
  (COVID period; French lockdown 2 = Nov-Dec 2020), flat diurnal shape (14% at 04-07h to 20% at 11-12h) -
  consistent with residential on-street charging where cars sit overnight.

## Building an occupancy time series (crawler design - not built here)
* Endpoint: `GET /api/explore/v2.1/catalog/datasets/<rt-dataset>/exports/json` (full dump, ~1 MB) or
  `/records?limit=100&offset=…` (paged, 100/page, `select=id_pdc,statut_pdc,last_updated`).
  Dataset `data_processed` metadata shows it refreshes roughly every 5 minutes (last_updated values are
  synchronous within a refresh); a 5-min poll is enough; 15-min was EDF's choice.
* Store each poll as `(poll_ts, id_pdc, statut_pdc, last_updated)`; de-duplicate on `(id_pdc,
  last_updated)` to recover **status change events**, then reconstruct sessions as
  `Occupé` -> `Disponible` intervals per PDC (gives arrival time, dwell; *no energy*). Occupancy per
  station per hour = mean over polls of occupied/(n_pdc - maintenance - unknown).
* Caveats: `Inconnu` and `En maintenance` must be excluded from the denominator; PDC ids change when
  posts are replaced (`FR*V75*E…` scheme); polls can be stale (`last_updated` lagging) - keep both
  timestamps. Publication under ODbL requires share-alike + attribution ("Ville de Paris - Belib'").
* Run as a cron/`launchd` job calling `fetch_paris_belib()` (already idempotent per day; change the file
  stamp to minutes for a real crawler) - or use ODS's `/exports/csv?timezone=UTC` for smaller payloads.

## Known issues / caveats
* Snapshot vs EDF series are different eras of the network (91 legacy Belib' stations in 2020 vs 379
  stations / 1,887 PDC in 2026 after the Autolib' posts were replaced) - ids do not match.
* EDF `test.csv` has no labels; `train.csv` has gaps (network outages) and the challenge organisers
  imputed nothing.
* No energy anywhere in these datasets - use for occupancy/dwell/arrival profiles only.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only paris_belib   # add --skip-large to skip train.csv
```
