---
id: sessions_palo_alto
title: Palo Alto - Electric Vehicle Charging Station Usage (July 2011 - Dec 2020)
provider: City of Palo Alto (Utilities / Public Works / Planning), CA, USA
url: https://data.paloalto.gov/datasets/194693/electric-vehicle-charging-station-usage-july-2011-dec-2020/
download_url: https://data.paloalto.gov/datasets/194693-electric-vehicle-charging-station-usage-july-2011-dec-2020.download/
licence: ODC Public Domain Dedication and License (PDDL) - linked from the dataset page (verified 2026-09-10)
status: observed
retrieved: 2026-09-10
size_mb: 97 (raw CSV); 9.2 (harmonised parquet)
spatial_unit: point (per-port coordinates in every row, 47 station names / ~25 sites)
temporal: per session, 2011-07-29 .. 2020-12-31 (local time, America/Los_Angeles)
script: src/chargescape/data/sessions_open.py (fetch_palo_alto / harmonise_palo_alto)
raw_path: data/raw/sessions_open/palo_alto/
---

## What it is
ChargePoint back-office export of every session at the City of Palo Alto's public Level-2 (and a few
Level-1) chargers in city garages and lots, July 2011 - December 2020. One row = one plug-in event with
start/end timestamps, total plugged-in duration and actual charging time, energy, port/plug type, station
name + street address + lat/lon, an anonymised driver id and the driver's home ZIP. The portal's web UI
caps exports at 10,000 rows; the `.download/` endpoint above returns the full file (GET only - HEAD gives 405).

## Fields used
| source column | harmonised | note |
|---|---|---|
| Station Name | station_id, station_name | e.g. `PALO ALTO CA / HAMILTON #1`; several names share one address |
| Latitude / Longitude | lat, lon (`lat_source=source_row`) | present on 100% of rows |
| Start Date / End Date | start_ts / end_ts | `m/d/Y H:M`, local Pacific time (tz column) |
| Total Duration (hh:mm:ss) | duration_min | plugged-in (dwell) time |
| Charging Time (hh:mm:ss) | charging_min | time actually drawing power |
| Energy (kWh) | energy_kwh | |
| Port Type / Plug Type / Port Number | port_type / connector | Level 2 = 98%, Level 1 = 2%; J1772 |
| User ID | user_id | SHA-1 hash of `chargescape:palo_alto:<id>` (12 hex); 97% of rows, 21,441 distinct |
| Plug In Event Id | session_id | |
| Address 1, City, Postal Code | stations.address, postcode | |
Dropped: MAC Address, Org Name, GHG/gasoline savings, Fee/Currency, Ended By, Driver Postal Code, County,
System S/N, Model Number (all still in the raw CSV).

## Harmonised outputs (2026-09-10 run)
* `data/interim/sessions_open/palo_alto_sessions.parquet` - 259,415 sessions, 47 stations, 100% with coordinates.
* `data/interim/sessions_open/palo_alto_stations.parquet` - 47 rows (n_sessions, first/last seen, address).
* Median 6.9 kWh (p95 20 kWh); median dwell 125 min, median charging 109 min (charging/dwell ratio 0.99 at the
  median - Level-2 users mostly unplug when charged, but p95 dwell is 354 min).
* Arrivals by hour: peak 11h (8.1%); 07-10h 25%, 11-15h 37%, 16-19h 25%, 20-23h 7%, 00-06h 6%; weekend 24%
  -> a daytime, destination/workplace-parking profile.
* Sessions per year: 1.3k (2011) -> 47-49k (2016-2019) -> 20k (2020, COVID).

## Known issues / caveats
* No power rating per port in the file (Level 2 ~6.6 kW typical; left as null rather than imputed).
* Coordinates are per port and jitter by a few metres within one garage; group by address for site-level work.
* station_id = station name; a renamed or relocated post would split/merge - none obvious in the data.
* All 47 stations are municipal garages/lots in a small, wealthy, early-adopter city: good for dwell / kWh /
  arrival-profile calibration of *destination* charging, weak as a transfer target for London on-street residential.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only palo_alto
```
Idempotent: the CSV is only downloaded if missing; parquet is rebuilt each run.
