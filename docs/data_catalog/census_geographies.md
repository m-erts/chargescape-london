---
id: census_geographies
title: ONS Open Geography Portal - LSOA 2021 / LAD 2024 boundaries, lookups and population-weighted centroids (Greater London)
provider: Office for National Statistics (Open Geography Portal)
url: https://geoportal.statistics.gov.uk/
download_url: https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/<service>/FeatureServer/0/query (services listed below)
licence: OGL v3 (Source: Office for National Statistics licensed under the Open Government Licence v3.0; contains OS data (c) Crown copyright and database right 2025)
status: observed
retrieved: 2026-09-10
size_mb: 13.4 raw (cached JSON pages) / 6.6 interim (GeoParquet)
spatial_unit: LSOA 2021 polygon, LAD 2024 polygon, LSOA21 / OA21 population-weighted centroid points
temporal: static (Census 2021 statistical geography; LAD boundaries as at December 2024)
script: src/chargescape/data/census.py
raw_path: data/raw/census/geoportal/
---

## What it is
Reference geography for the demand-side layers, pulled directly from the ONS Open Geography Portal ArcGIS
FeatureServer (no key, paginated 2,000 / 1,000 records per request; POST queries with `LSOA21CD IN (...)`
chunks so no non-London area slips in). Five services are used:

| purpose | service (FeatureServer/0) | rows for London |
|---|---|---|
| LSOA 2021 boundaries, BGC (generalised 20 m, clipped to coastline), V5 | `Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5` | 4,994 |
| OA21 -> LSOA21 -> MSOA21 -> LAD22 exact-fit lookup (table), v3 | `OA_LSOA_MSOA_EW_DEC_2021_LU_v3` | 26,369 OA / 4,994 LSOA / 1,002 MSOA / 33 LAD |
| LAD December 2024 boundaries, UK BGC | `Local_Authority_Districts_December_2024_Boundaries_UK_BGC` | 33 (E09000001-E09000033) |
| LSOA 2021 population-weighted centroids, V4 | `LSOA_PopCentroids_EW_2021_V4` | 4,994 |
| OA 2021 population-weighted centroids, V4 | `OA_December_2021_EW_PWC_V4` | 26,369 |

Outputs in `data/interim/census/`:

| file | content | CRS |
|---|---|---|
| `lsoa21_london.parquet` (1.9 MB) | 4,994 LSOA21 polygons + `msoa21cd/nm`, `lad22cd/nm`, `inner_london`, `area_km2`, BNG/lat-long centroid attributes | EPSG:27700 |
| `lsoa21_london_wgs84.parquet` (2.4 MB) | same, reprojected | EPSG:4326 |
| `lad24_london.parquet` | 33 borough polygons (`lad24cd`, `lad24nm`, `inner_london`, `area_km2`) | EPSG:27700 |
| `greater_london.parquet` | dissolve of the 33 boroughs (MultiPolygon, 1,573.3 km2) | EPSG:27700 |
| `lsoa21_lookup_london.parquet` | LSOA21 -> MSOA21 -> LAD22 (+ `inner_london`) - the canonical London LSOA list used by every other module | - |
| `oa21_lsoa21_lookup_london.parquet` | OA21 -> LSOA21 -> MSOA21 -> LAD22 | - |
| `lsoa21_pwc_london.parquet` | LSOA21 PWC points + `pwc_x`, `pwc_y` (BNG) and `pwc_lon`, `pwc_lat` | EPSG:27700 |
| `oa21_pwc_london.parquet` | OA21 PWC points with LSOA/MSOA/LAD codes (for later H3 / dasymetric work) | EPSG:27700 |

## Fields used
`LSOA21CD`, `LSOA21NM`, `MSOA21CD`, `MSOA21NM`, `LAD22CD`, `LAD22NM`, `OA21CD`, `LAD24CD`, `LAD24NM`, `BNG_E`, `BNG_N`,
`LAT`, `LONG`, geometry. Derived: `inner_london` (ONS statistical Inner London = City of London, Camden, Hackney,
Hammersmith and Fulham, Haringey, Islington, Kensington and Chelsea, Lambeth, Lewisham, Newham, Southwark,
Tower Hamlets, Wandsworth, Westminster - 1,966 LSOAs; the remaining 19 boroughs / 3,028 LSOAs are Outer London),
`area_km2` (from the generalised BGC geometry).

## Known issues / caveats
- BGC is generalised (20 m) and clipped to the coastline / Thames; areas differ slightly from the full-extent BFE
  product (London total 1,573.3 km2 vs the commonly quoted 1,572 km2). Fine for density and mapping; use BFE if
  exact areas or riverside geometry matter.
- The lookup carries LAD **2022** codes; for London these are identical to LAD 2024 codes (verified against the
  IoD2025 file's `lad24cd` for all 4,994 LSOAs), so `lad22cd` joins directly to `lad24_london.parquet`.
- The nomis "within London" LSOA list (region 2013265927, TYPE151) contains exactly the same 4,994 codes.
- The FeatureServer occasionally returns `exceededTransferLimit` on the last page; the helper paginates on that
  flag and caches concatenated pages, so a partial download is never persisted silently.
- Population-weighted centroids are ONS's 2021 PWCs (not geometric centroids); a few lie outside their own
  polygon by construction.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.census   # fetch_geographies() runs first; cached under data/raw/census/geoportal/
```
Delete `data/raw/census/geoportal/*.json` to force a fresh pull.
