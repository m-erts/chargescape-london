---
id: transit_tfl_stations
title: TfL rail-based stations (tube, DLR, Overground, Elizabeth line, tram, National Rail) and cycle-hire docks
provider: Transport for London — Unified API (anonymous access); National Rail gap filled from DfT NaPTAN
url: https://api-portal.tfl.gov.uk/
download_url: https://api.tfl.gov.uk/StopPoint/Mode/{tube|dlr|overground|elizabeth-line|tram|national-rail} ; https://api.tfl.gov.uk/BikePoint ; https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv&atcoAreaCodes=910
licence: TfL Open Data licence (OGL-based) — "Powered by TfL Open Data"; NaPTAN OGL v3 (© Crown copyright, DfT)
status: observed
retrieved: 2026-09-10
size_mb: 0.08 (stations parquet) + 0.07 (bikepoints parquet); raw JSON 23.6 MB
spatial_unit: point (station / docking station), EPSG:4326
temporal: static snapshot 2026-09-10 (BikePoint dock counts are near-static; live bike counts are not stored)
script: src/chargescape/data/transit.py (fetch_tfl_stations, fetch_tfl_bikepoints)
raw_path: data/raw/transit/
---

**Powered by TfL Open Data.** Contains OS data © Crown copyright and database rights 2016 and Geomni UK Map
data © and database rights [2019] (TfL attribution requirements).

## What it is
`data/interim/transit/tfl_stations.parquet` — one row per station-level StopPoint (`stopType` ∈
NaptanMetroStation, NaptanRailStation; platforms, entrances, access areas and HUB interchanges are dropped)
for the six rail-based modes. TfL's `StopPoint/Mode/{modes}` endpoint is called **one mode at a time** (the
combined six-mode call, and the national-rail call on its own, time out server-side with HTTP 500/504);
responses are cached as `data/raw/transit/tfl_stoppoints_{mode}.json`.

* 740 stations, 706 inside the Greater London boundary (the remainder are Elizabeth line / Overground /
  Metropolitan & Central line stations beyond the boundary: Brentwood, Iver, Bushey, Amersham, Epping …).
* By mode (any station serving it): tube 272 · DLR 45 · Overground 115 · Elizabeth line 43 · tram 39 ·
  National Rail 368. Inside Greater London: tube 256 · DLR 45 · Overground 107 · Elizabeth line 33 · tram 39
  · National Rail 355.
* Sources: `tfl` 511 rows; `naptan_910` 229 rows. TfL could not serve `StopPoint/Mode/national-rail`
  (repeated 504 "query timeout", also for `StopPoint/Type/NaptanRailStation`), so National Rail stations
  come from NaPTAN ATCO area 910 (2,661 active GB stations, 355 inside London): TfL ids are `910G` +
  TIPLOC, NaPTAN codes are `9100` + TIPLOC, so the two merge exactly — 70 TfL rows gained the
  `national-rail` mode flag and 229 pure National Rail stations were added (no `lines` for those rows).

`data/interim/transit/tfl_bikepoints.parquet` — 800 Santander Cycles docking stations, 21,035 docks (4
temporary), with install dates; used as a central-London activity/amenity proxy.

## Fields used
Stations: `id` (TfL StopPoint id: `940G…` tube/DLR/tram, `910G…` rail), `naptan_id`, `name`, `modes` (list,
all modes TfL lists incl. bus), `modes_str`, `rail_modes_str`, `mode_tube` … `mode_national_rail` (bool),
`lat`, `lon`, `geometry`, `stop_type`, `hub_naptan_code`, `station_naptan`, `lines` (line ids, TfL rows
only), `n_lines`, `query_modes`, `source` (tfl / naptan_910), `in_greater_london`, `retrieved_utc`.
Bikepoints: `id`, `name`, `lat`, `lon`, `geometry`, `terminal_name`, `nb_docks`, `installed`, `locked`,
`temporary`, `install_date`.

## Known issues / caveats
* TfL models some interchanges as separate StopPoints per operator (e.g. Abbey Wood `910GABWD` National
  Rail and `910GABWDXR` Elizabeth line), so multi-operator stations can appear twice within ~50 m. For
  "distance to nearest station" this is harmless; for station counts dedupe on `hub_naptan_code` / name or
  spatially.
* `lines` and `hub_naptan_code` are empty for NaPTAN-sourced rows; TfL-sourced rows keep them.
* Anonymous TfL access is rate-limited (~50 req/min) and occasionally 5xx; the client backs off on 429
  (honouring `Retry-After`) and retries 5xx, and fails fast (2 attempts, 90 s) for national-rail before
  using the NaPTAN fallback. A fresh run therefore takes ~3–4 min while TfL's national-rail query is broken.
* `modes` may include `bus`, `river-bus`, `cable-car` etc. as listed by TfL; use `rail_modes_str` for the
  six rail modes only.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.transit --only stations bikepoints           # uses cached raw JSON if present
PYTHONPATH=src python -m chargescape.data.transit --only stations --force              # re-query TfL
```
