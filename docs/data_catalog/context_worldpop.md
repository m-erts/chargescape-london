---
id: context_worldpop
title: WorldPop 2020 population counts, 1 km unconstrained (GBR, USA) - population within 1 km of each charging station
provider: WorldPop, School of Geography and Environmental Science, University of Southampton (with CIESIN, Columbia University; Universite de Namur; University of Louisville) - "Global High Resolution Population Denominators Project"
url: https://hub.worldpop.org/project/categories?id=3 (Population Counts -> Unconstrained individual countries 2000-2020, 1 km)
download_url: https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/GBR/gbr_ppp_2020_1km_Aggregated.tif and https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/USA/usa_ppp_2020_1km_Aggregated.tif
licence: CC BY 4.0 - cite WorldPop and CIESIN (2018), Global High Resolution Population Denominators Project, funded by the Bill and Melinda Gates Foundation (OPP1134076), https://dx.doi.org/10.5258/SOTON/WP00647
status: observed (top-down modelled population estimates, not a census count)
retrieved: 2026-09-10
size_mb: 2.6 (GBR) + 52.7 (USA) GeoTIFF (server Last-Modified 2020-06-22)
spatial_unit: raster, 30 arc-second (~1 km) cells, EPSG:4326 -> one value per station (1 km buffer, area-weighted pixel sum)
temporal: 2020 estimate (single year used for all cities and all session years)
script: src/chargescape/features/station_context.py (worldpop_raster, population_within, buildings_within)
raw_path: data/raw/context/worldpop/
---

## What it is
WorldPop's unconstrained top-down estimates of people per grid cell for 2020, aggregated from the 100 m product to
1 km cells (`ppp_2020_1km_Aggregated`: persons per pixel, float32, nodata -99999). National totals match WorldPop's
own country estimates (the `_UNadj` variant is *not* used). Two country rasters cover all five study areas:
GBR (Dundee, Perth & Kinross, London) and USA (Palo Alto, Boulder).

`pop_1km` in `data/processed/station_features.small.parquet`: the station's 1 km buffer is built in the local metric
CRS (EPSG:27700 / 26910 / 26913), re-projected to EPSG:4326 and passed to `rasterio.mask` (`all_touched=True`,
`crop=True`); every touched pixel then contributes *value x (area of the pixel inside the buffer / pixel area)*
and the products are summed. The plain pixel-centre sum (`all_touched=False`) was rejected because a 1 km radius over
1 km pixels covers only 6-8 pixel centres and the result jumps as a station moves by 100 m: on the 90 Dundee stations
the pixel-centre sum is between 0.59x and 1.30x the area-weighted value (median 1.01x). Area fractions are computed in
degrees, which is exact enough because numerator and denominator share the same local distortion.

Result by city (persons within 1 km, 2026-09-10 run):

| city | n | min | median | mean | max |
|---|---:|---:|---:|---:|---:|
| dundee | 90 | 3,675 | 9,986 | 10,203 | 18,465 |
| pkc | 35 | 954 | 4,445 | 5,505 | 10,549 |
| palo_alto | 34 | 6,797 | 8,231 | 8,427 | 10,065 |
| boulder | 45 | 83 | 7,430 | 6,571 | 12,005 |
| london | 6,904 | 180 | 32,202 | 32,199 | 71,159 |

## Fields used
Single band -> feature column `pop_1km` (persons, float) plus `pop_source` (`worldpop_ppp_2020_1km` for every row
of this build). If a raster cannot be downloaded the script falls back to the number of OSM `building=*` features
(centroids) within 1 km, fetched with one extra Overpass query per session city (`data/raw/context/<city>/buildings.json`),
and sets `pop_source = osm_buildings_1km`; London has no offline building layer, so it would get NaN and
`pop_source = none`. The two quantities are not on the same scale - always split or filter on `pop_source`.
The raster file name is recorded in `data/interim/context/<city>_build_info.json`.

## Known issues / caveats
* **Resolution**: 1 km radius over ~1 km pixels (9-16 touched pixels). Area-weighting removes the pixel-centre
  lumpiness but cannot resolve within-pixel structure; the constrained 100 m products would be sharper (GBR 34 MB
  but USA ~500 MB), so the 1 km product is used for *both* countries to keep the feature comparable.
* **Unconstrained** estimates spread some population into unbuilt cells (parks, fields, foothills); the Perth &
  Kinross park-and-ride sites and Boulder's edge stations (minimum 83 persons) are the most affected.
* One reference year (2020) for sessions observed 2011-2025 (Palo Alto 2011-2020, Perth & Kinross 2016-2019,
  Boulder 2018-2023, Dundee 2021-2025); population change over that span is small relative to between-station
  differences. Pixel size in km varies with latitude (~0.5 km east-west at 56 N, ~0.6 km at 51.5 N), which the area weights absorb.
* Nodata / negative pixels are treated as 0; a buffer entirely outside the raster would yield NaN (did not occur).
* Values are modelled (random-forest dasymetric redistribution of census totals, https://www.worldpop.org/methods/),
  not a substitute for the Census 2021 LSOA counts used for London elsewhere in the project (`census_2021_tables.md`);
  WorldPop is used here only because the same variable must exist for the US cities.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.features.station_context          # downloads the two rasters on first run
```
The rasters are cached in `data/raw/context/worldpop/` (`utils.http.download` skips existing files). Check sizes
before downloading with `curl -sI <download_url>` (Content-Length 2,569,196 and 52,715,668 bytes on 2026-09-10).
