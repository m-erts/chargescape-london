---
id: chargepoints_london_datastore
title: London Datastore – "Electric Vehicle Charging Site" (TfL rapid charging points, 2019 snapshot)
provider: Greater London Authority (GLA Environment Team; data from Transport for London)
url: https://data.london.gov.uk/dataset/electric_vehicle_charging_site/
download_url: https://data.london.gov.uk/download/2lzpg/8ef9c743-c01d-4329-8239-8f858ff4de53/Rapid_charging_points.gpkg
licence: Creative Commons Attribution (as stated in the Datastore record, version not specified)
status: observed
retrieved: 2026-09-10
size_mb: 0.15 (GeoPackage) / 0.03 (GeoParquet)
spatial_unit: point (rapid charging site)
temporal: static snapshot dated 29 August 2019 (`runtime` field); record last modified 2019-09-03, not updated since
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/london_datastore/
---

## What it is
A search of the London Datastore API (`/api/action/package_search`, queries: "electric vehicle charging",
"chargepoint", "charge point", "charging point", "rapid charging", "Source London", "lamp column charging",
"EV charging", "ULEV", "electric vehicle") found **exactly one dataset with charge point locations**:
dataset `2lzpg` "Electric Vehicle Charging Site" (GLA, created 2019-07-23), a single GeoPackage
`Rapid_charging_points.gpkg` (layer `Rapid_charging_points`, 156 points, British National Grid) listing TfL's
rapid charging network sites with borough, site name, number of rapid points and whether the site is for taxis or
public use. The Datastore description attaches it to the Low Emission Neighbourhood / Mayor's Air Quality Fund
programme; the `url` field of every record points to https://tfl.gov.uk/modes/driving/electric-vehicles-and-rapid-charging.

Other EV-related Datastore records are **not** location datasets and were not downloaded: "Low Carbon London
Electric Vehicle Load Profiles" (UK Power Networks, 2022, CC BY – charging load curves), "Mayor of London & Gnewt
Cargo Electric Vehicle Trial" (2020, OGL v3 – freight trial KPIs), "Lithium and Electric Vehicle fires" (LFB,
2026). There is no Source London, lamp-column, borough on-street or LEVI location dataset on the Datastore as of
2026-09-10; TfL's current rapid-charging map is only published as a web map.

Output: `data/interim/chargepoints/london_datastore_rapid_charging_points_2019.parquet` (GeoParquet, EPSG:4326,
156 rows). Bbox (W,S,E,N): -0.4926, 51.3042, 0.2435, 51.6718.

## Fields used
`site_id`, `site_name`, `borough` (31 labels incl. "Outside London" ×6 and "City of London"), `use_type`
("Public use" 91 / "Taxi" 65 after normalising one "Public Use"), `n_rapid_points` (1 for 140 sites, 2 for 13, up
to 7; sum 180), `url`, `snapshot_date` (2019-08-29), `easting`/`northing`, `latitude_src`/`longitude_src` (as
supplied), `lat`/`lon` (reprojected), `source = "london_datastore_tfl_rapid_2019"`, `geometry`.

## Known issues / caveats
- **Stale**: a 2019 snapshot of the then ~150-site TfL rapid network. DfT counts 2,533 public 50kW+ chargers in
  London on 1 July 2026, so this file covers a small, early fraction of today's rapid supply. Useful only as a
  historical layer / for identifying the taxi-dedicated TfL sites.
- The GeoPackage CRS is an "unnamed" Transverse Mercator (Airy 1830, OSTN02 grid) whose parameters equal British
  National Grid; the script declares it EPSG:27700 (`set_crs(allow_override=True)`) before reprojecting.
  Reprojected coordinates differ from the supplied `latitude`/`longitude` columns by < 1e-5 degrees.
- Six sites are flagged "Outside London" (Heathrow/M25 fringe) yet lie within the analysis bbox.
- Attribute columns are stored as text in the GeoPackage (numbers converted in the script); `longtitude` is
  misspelt in the source (renamed `longitude_src`).
- Licence text on the Datastore is just "Creative Commons Attribution"; no version is given.

## How to reproduce
```bash
PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_london_datastore; fetch_london_datastore()"
```
The dataset metadata (`package_show`) is saved next to the GeoPackage as `2lzpg_package_show.json`.
