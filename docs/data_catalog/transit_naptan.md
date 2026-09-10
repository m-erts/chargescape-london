---
id: transit_naptan_bus_stops_london
title: NaPTAN bus stops, London (ATCO area 490)
provider: Department for Transport — National Public Transport Access Nodes (NaPTAN); stop data maintained by TfL
url: https://www.gov.uk/government/publications/national-public-transport-access-node-schema
download_url: https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv&atcoAreaCodes=490
licence: OGL v3 (© Crown copyright, DfT); TfL-maintained stop data — "Powered by TfL Open Data"
status: observed
retrieved: 2026-09-10
size_mb: 4.5 (raw CSV, 21,287 rows) → 1.6 (parquet)
spatial_unit: point (bus stop), EPSG:4326 (+ OSGB36 easting/northing as published)
temporal: static snapshot 2026-09-10 (NaPTAN is updated continuously)
script: src/chargescape/data/transit.py (fetch_naptan_bus_stops)
raw_path: data/raw/transit/naptan_atco490_london.csv
---

## What it is
All NaPTAN access nodes for ATCO administrative area **490 = London** (the TfL area), filtered to active bus
stops: `data/interim/transit/naptan_bus_stops_london.parquet`, **20,050 stops** (StopType BCT on-street
bus/coach stop 20,022; BCS bus-station bay 28; no BCQ variable bays exist in area 490), 20,042 of them inside
the Greater London OSM boundary. BusStopType: MKD marked 18,860 · HAR hail-and-ride 1,126 · CUS custom 36 ·
blank 28 (bus-station bays). Raw StopType mix before filtering: BCT 20,025 · TMU 642 (tram/metro entrances)
· RSE 550 (rail-station entrances) · FTD 42 (ferry) · BCS 28; three bus-type rows were not `active`.
Latitude 51.293–51.685, longitude −0.499–0.298.

The same API also supplies `data/raw/transit/naptan_atco910_rail_stations.csv` (ATCO 910, GB National Rail
stations, 0.55 MB) used as the National Rail fallback in `transit_tfl_stations.md`.

## Fields used
`atco_code` (primary key, unique), `naptan_code` (SMS code), `common_name`, `indicator` (e.g. "Stop U",
"->S"), `bearing`, `street`, `landmark`, `locality_name`, `parent_locality_name`, `stop_type`,
`bus_stop_type`, `timing_status`, `easting`, `northing`, `lon`, `lat`, `geometry`, `status`,
`modification_datetime`, `in_greater_london`, `boundary_source`, `retrieved_utc`.

## Known issues / caveats
* ATCO area 490 is administrative, not the OSM boundary: 8 stops sit just outside Greater London and stops
  of neighbouring areas (e.g. 040 Buckinghamshire, 150 Essex) that lie inside London are not included —
  negligible for density features.
* Hail-and-ride sections (HAR) are represented as points at the section start; there is no stop pole.
* NaPTAN has no patronage or frequency data; combine with TfL bus-route/timetable data if service level
  matters. Coordinates are as published (many are pole positions to ±5 m).
* The API allows 200 requests/hour per client (X-Rate-Limit headers) and rejects HEAD; the download is
  cached and only refreshed with `--force`.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.transit --only bus
PYTHONPATH=src python -m chargescape.data.transit --only bus --force   # re-download today's NaPTAN
```
