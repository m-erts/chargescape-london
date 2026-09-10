---
id: sessions_chargeplace_scotland
title: ChargePlace Scotland - public locations feed (coordinates for CPS charge-point IDs) and inventory of Scotland-wide session data
provider: ChargePlace Scotland (Transport Scotland network); feed served by SmartCharging (info.smartcharging.uk); University of Strathclyde (CC BY research copy)
url: https://chargeplacescotland.org/network-performance-2/ ; https://chargeplacescotland.org/monthly-charge-point-performance/ ; https://pureportal.strath.ac.uk/en/datasets/scottish-public-electric-vehicle-charging-chargeplace-scotland-oc/
download_url: https://info.smartcharging.uk/public_feed/locations/2463 (JSON, ~7 MB) ; tariffs https://info.smartcharging.uk/public_feed/locations/2463/tariffs
licence: feed - advertised as "Open Data API Access" on chargeplacescotland.org, no explicit licence text; monthly session files - none stated (site footer "all rights reserved"); Strathclyde zip - CC BY 4.0
status: observed (feed snapshot); inventory for the rest
retrieved: 2026-09-10
size_mb: 7.4 (feed + tariffs snapshots); 0.2 (parquet)
spatial_unit: point (location -> EVSE -> connector)
temporal: static snapshot per run-day (EVSE status is live)
script: src/chargescape/data/sessions_open.py (fetch_cps / harmonise_cps)
raw_path: data/raw/sessions_open/chargeplace_scotland/
---

## What it is
1. **Locations feed** (OCPI-like): 1,484 locations, 5,280 EVSE/connector rows, 2,376 distinct charge-point
   ids (`physical_reference`, e.g. `52118`; `evse_id` `GB*CPS*E52118*1`), name, address, postcode, lat/lon,
   connector standard, max kW (22 kW: 2,232 rows; 7 kW: 1,964; 50 kW: 682), live status. Used to attach
   coordinates to Dundee/PKC `CP ID`s missing from the councils' own layers (`lat_source = cps_public_feed`).
   -> `cps_stations.parquet`.
2. **Monthly charge-point performance page** - 152 files (Oct 2022 -> Jul 2026) of which 27 are
   Scotland-wide **session files** (`Site, CP ID, Connector Type, Connector, Currency, Amount, Consum(kWh),
   Duration, Start`, ~11 MB xlsx/csv per month, e.g. `.../wp-content/uploads/2025/09/Sessions-AUG-25.csv`).
   Link list saved to `monthly_performance_links.txt`. **Not bulk-downloaded**: no licence is stated.
   Same layout as the Dundee files, so `parse_cps_style()` would ingest them unchanged if terms are cleared.
3. **Strathclyde "Scottish Public Electric Vehicle Charging - ChargePlace Scotland Oct 2022 - Mar 2024"**
   (DOI 10.15129/1f431af7-5caa-4840-a9ab-c1f3b521e033, CC BY 4.0, 144 MB `ScotPublicCharging.zip`): sessions
   with charge-point id, duration, kWh, local authority, **postcode**, speed, amount paid + SIMD / urban-rural /
   accessibility context. The file URL sits behind a Cloudflare browser challenge (HTTP 403 for any
   non-browser client, tested with several user agents / cookies) - download manually in a browser into
   `data/raw/sessions_open/chargeplace_scotland/` and it becomes the best UK utilisation-transfer set
   (Scotland-wide, ~2,400 chargers, postcode-locatable).
4. Also checked: gov.scot FOI 202500480850 (monthly per-LA aggregates + asset register, Jul 2021 - Sep 2025,
   xlsx) - aggregates only; Stirling Council "electric vehicle charging points" (locations, no sessions);
   no session data found for Edinburgh, Glasgow, Aberdeen, Fife on Open Data Scotland (index of 11,886 datasets).

## Other UK councils checked (15-minute sweep, 2026-09-10)
* Leeds (sessions 2014-2021, OGL) -> ingested, see `sessions_leeds.md`.
* Calderdale: quarterly session counts + kWh per site (aggregate). Nottingham, Coventry, Oxford (Go Ultra Low
  Oxford), Milton Keynes: no session-level open data found (Oxford GULO was a trial report; MK/Coventry publish
  charger locations only). Wokingham and Dover FOI refusals cite commercial sensitivity (s.43(2)).
* data.gov.uk search for "electric vehicle charging sessions/usage/transactions" returns only GLA's
  Optimise Prime (already catalogued separately).
* DfT "Electric Chargepoint Open Data Collection" procurement (2024) signals future national real-time open
  data; nothing published yet.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only cps
```
