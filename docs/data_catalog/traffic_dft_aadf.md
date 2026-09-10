---
id: traffic_dft_aadf
title: DfT Road Traffic Statistics - AADF by count point and raw hourly counts, London region
provider: Department for Transport (Road Traffic Statistics, TRA)
url: https://roadtraffic.dft.gov.uk/downloads
download_url: https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/region_id/dft_aadf_region_id_6.csv ; .../rawcount/region_id/dft_rawcount_region_id_6.csv
licence: Open Government Licence v3.0
status: observed
retrieved: 2026-09-10
size_mb: raw 12.3 (AADF) + 69.5 (raw counts); interim 1.3 + 4.0 (parquet)
spatial_unit: point (count point, BNG easting/northing + WGS84 lat/lon; link start/end junctions)
temporal: annual 2000-2025 (AADF); hourly 07:00-18:00 on count days 2000-2025 (raw counts)
script: src/chargescape/data/traffic.py
raw_path: data/raw/traffic/dft/
---

## What it is
DfT's count-point level road traffic estimates for the London region (region_id 6 =
E12000007, all 33 local authorities incl. City of London), latest year **2025**.

* `dft_aadf_london.parquet` - Annual Average Daily Flow per count point x year, both directions
  combined. 56,321 rows, 3,665 count points over 2000-2025; **2025: 2,050 count points
  (1,835 major, 215 minor roads; 739 counted, 1,311 estimated)**.
* `dft_rawcount_london.parquet` - the underlying 12-hour manual counts (per direction, per hour
  07-18h, per count date). 425,472 rows, 3,379 count points; 2025: 484 count points. Useful for
  hour-of-day traffic profiles.
* `data/raw/traffic/dft/all-traffic-data-metadata.pdf` - DfT field definitions.

## Fields used
AADF: `count_point_id, year, local_authority_id, local_authority_name, local_authority_ons
(E09...), road_name, road_type (Major/Minor), road_category (derived: M/A/B/C/U from road
name), start/end_junction_road_name, easting, northing, latitude, longitude, link_length_km,
estimation_method(_detailed), pedal_cycles, two_wheeled_motor_vehicles, cars_and_taxis,
buses_and_coaches, lgvs, all_hgvs, all_motor_vehicles` (vehicles/day).
Raw counts add `direction_of_travel, count_date, hour`.

## Known issues / caveats
- Minor-road count points are a sample; minor-road AADFs are mostly *estimated* (growth-factored
  from a base count), so year-to-year changes at one point are not real signal.
- `road_category` is derived from the road-name prefix (DfT dropped the field from this extract);
  A-roads are not split into trunk/principal.
- Count points are on links, not at junctions; the lat/lon is the count location.
- COVID years 2020-21 are anomalous (fewer counts, lower flows).
- DfT local-authority ids are mapped to ONS codes via `https://roadtraffic.dft.gov.uk/api/local-authorities`
  (snapshot cached in `data/raw/traffic/dft/api/`).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.traffic
```
Idempotent; ~4 s once the CSVs are cached. Full-GB files (`dft_traffic_counts_aadf.zip` 19.5 MB,
`dft_traffic_counts_raw_counts.zip` 88.8 MB) are available at the same bucket if other regions are needed.
