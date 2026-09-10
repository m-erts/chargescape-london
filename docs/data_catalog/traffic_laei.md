---
id: traffic_laei
title: London Atmospheric Emissions Inventory (LAEI) 2022 and 2019 - road traffic flows and speeds
provider: Greater London Authority / Transport for London (GLA and TfL Air Quality team)
url: https://data.london.gov.uk/dataset/london-atmospheric-emissions-inventory--laei--2022 ; https://data.london.gov.uk/dataset/london-atmospheric-emissions-inventory--laei--2019
download_url: https://data.london.gov.uk/download/2lg5g/95w/LAEI2022-Traffic-Flows-and-Speeds-Major-and-Minor-Roads-GIS.zip (11.5 MB) ; https://data.london.gov.uk/download/e758q/64fa10ab-7b0a-4de7-b4d9-5f7a3b471ed1/laei-2019-major-roads-final-unique-toids-flows-speeds-osgb.zip (10.2 MB)
licence: not stated in the London Datastore metadata for the 2019/2022 packages (license field empty); earlier LAEI editions (2013, 2016) are OGL v2 and GLA Datastore default terms are OGL - treat as OGL with GLA/TfL attribution, confirm before commercial reuse
status: observed (2022 base-year modelled flows, calibrated to counts; 2019 base year)
retrieved: 2026-09-10
size_mb: raw 21.7 (two zips); interim 8.3 + 1.3 + 8.8 (GeoParquet)
spatial_unit: road link (OS MasterMap TOID, 79,437 links, EPSG:27700) ; 1 km grid squares (minor roads, 3,460 cells)
temporal: static, base year 2022 (LAEI 2022) and 2019 (LAEI 2019)
script: src/chargescape/data/traffic.py
raw_path: data/raw/traffic/laei/
---

## What it is
The LAEI is the GLA/TfL emissions inventory; its traffic layer is the best openly available
**link-level** flow map for London (modelled AADF on every major road TOID, calibrated to DfT/TfL
counts). No login is needed - the files are plain downloads from the London Datastore.

* `laei2022_major_roads_flows.parquet` - 79,437 major-road links (Greater London + out to the
  M25; `in_gla` flag). Per link: `length_m, road_classification, speed_other_vehicles_kph,
  speed_buses_kph` and AADF by vehicle type: `aadf_motorcycles, aadf_taxis, aadf_cars,
  aadf_phvs, aadf_lgvs, aadf_hgvs_rigid, aadf_hgvs_articulated, aadf_tfl_buses,
  aadf_non_tfl_buses, aadf_coaches` (+ derived `aadf_total`). Note the separate **PHV** and
  **taxi** flows - directly relevant to Uber/PHV charging demand.
* `laei2022_minor_roads_vkm_1km.parquet` - 1 km grid, annual vehicle-km by the same vehicle
  types + `speed_kph` (minor roads are not mapped link by link).
* `laei2019_major_roads_flows.parquet` - same links, 2019 base year (`f_car, f_phv, f_taxi, ...,
  tot_aadt19, sp_kph`), for a pre-/post-pandemic comparison.

Checked but **not** downloaded (too large / emissions rather than flows): LAEI 2022 major-road
emissions GIS (458 MB), LAEI 2019 major-road-links emissions shapefile (318 MB), concentration
grids (130-560 MB). All are open downloads if needed later.

## Fields used
See above; geometry is MultiLineString in EPSG:27700 (2022 major), MultiPolygon in EPSG:4326
(2022 minor grid), LineString EPSG:27700 (2019). Column names were lower-cased and dots
replaced by underscores.

## Known issues / caveats
- Flows are modelled/calibrated, not counted; treat as a smooth spatial prior, and use the DfT
  count points as ground truth where they exist.
- 2022 is the base year (post-pandemic traffic ~ -5..-10% vs 2019 in central London); LAEI 2022
  also ships 2025/2030 *forecast* emissions but not forecast flows in the downloaded file.
- TOIDs are OS MasterMap ids; they can be joined to OSM only via geometry.
- Licence field is empty on the Datastore record - see front matter.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.traffic
```
