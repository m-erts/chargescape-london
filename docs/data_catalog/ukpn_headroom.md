---
id: ukpn_headroom
title: UKPN grid headroom for London - primary substation supply areas with firm capacity / demand RAG (2024-2026 snapshots) and DFES-NSHR headroom forecasts to 2050
provider: UK Power Networks data, republished by the Greater London Authority (GLAGIS, LAEP data hub) as public ArcGIS feature services; original tables on the UKPN Open Data Portal are login-only
url: https://laep-datahub-alpha-cityhall.hub.arcgis.com/ (items 8f79458dd7c04e09a534a900550f0de4, d68db93824a44ef9801806ce5b5a682c, 5ef3f8160bee40a5ac57d4c3fcee2bfb, 383199f6296742a19150dc637d6854cd, 316151597e034563a4bd7188aad1557d) ; portal originals https://ukpowernetworks.opendatasoft.com/explore/dataset/ukpn_primary_postcode_area/ , /ukpn-dfes-network-headroom-report/
download_url: https://services.arcgis.com/drifeOPKLpgnJ8Qa/arcgis/rest/services/UKPN%20Primary%20Substation%20Distribution%20Areas%20(Summer%202026)/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson (and the four sibling layers listed in ukpn.py HEADROOM_LAYERS)
licence: CC BY 4.0 (stated on every ArcGIS item; UKPN portal originals are CC BY 4.0)
status: observed (snapshots of current firm capacity / demand) + proxy (NSHR scenario headroom 2023-2050)
retrieved: 2026-09-10
size_mb: raw 6.6 (GeoJSON) ; interim 3.9 (5 GeoParquet files)
spatial_unit: primary substation supply area polygon (Voronoi-style, EPSG:4326) / primary substation point
temporal: snapshots Aug-2026 (LTDS Nov-2025 loading), Mar-2026, Dec-2024; forecast years 2023-2030 annual then 2035/40/45/50
script: src/chargescape/data/ukpn.py  (parts `headroom` and `ods`)
raw_path: data/raw/ukpn/headroom/ (+ data/raw/ukpn/catalog/ for portal metadata)
---

## What it is
Grid-side constraint layer for the siting model. On the UKPN Opendatasoft portal every
substation/headroom dataset we wanted (`ukpn_primary_postcode_area`, `ukpn_secondary_postcode_area`,
`ukpn-secondary-sites`, `ukpn-secondary-site-utilisation`, `ukpn-capacity-heatmap`,
`ukpn-primary-transformers`, `ukpn-grid-supply-points-overview`, `ukpn-dfes-network-headroom-report`,
`ukpn-low-carbon-technologies-*`) is flagged `data_visible=false`: metadata is public, the
anonymous `/records` API returns 403 and anonymous exports return header-only files. Only
38 of 138 portal datasets are open without a login. Per project rules we did **not** register;
`_ods_report.json` records each as "registration required".

The GLA's Local Area Energy Planning hub mirrors the London-relevant subset as public ArcGIS
services (CC BY 4.0). `build_headroom()` pages through them and writes GeoParquet:

| interim file | rows (LPN) | geometry | vintage | key fields |
|---|---|---|---|---|
| `headroom_primary_areas_summer2026.parquet` | 229 (108) | polygon | GLA harvest 13-Aug-2026 of `ukpn_primary_postcode_area` | `primary, primary_floc, dno, grid_site, grid_supply_point, firmcapacitywinter/summer (MVA), demand (% of firm capacity), demandrag, seasonofconstraint, generationavailablecapacity, generationfirmcapacity, generationrag, resp25` |
| `headroom_primary_areas_march2026.parquet` | 232 (107) | polygon | Mar-2026 (LTDS Nov-2025) | same core fields |
| `headroom_primary_areas_baseline_dec2024.parquet` | 158 (96) | polygon | Dec-2024 harvest | same + `local_authority, laep_region` |
| `headroom_demand_forecast_nshr2023.parquet` | 113 (19 LPN + 43 blank) | point | Arup 2023 from DFES NSHR | `sitename, sitetype, borough, local_auth, gsp, capacity_c, f2023..f2030, f2035, f2040, f2045, f2050` = demand headroom MW per year |
| `headroom_generation_forecast_nshr2023.parquet` | 113 | point | as above | generation headroom MW per year |

Also open on the portal and stored under `data/interim/ukpn/`: `lpn_operational_boundaries.parquet`
(4 LPN ops areas), `local_authorities.parquet` (133 LADs in UKPN area, 33 London, with geometry),
`standard_demand_profiles.parquet` (17,520 half-hourly normalised profiles incl. an `ev_charging`
column UKPN uses for connection studies - a useful *observed-derived* diurnal shape).

Headline (Summer-2026 layer, all 229 London-area primaries): demand RAG Green 223 / Yellow 4 /
Red 2; LPN demand at 10/50/90 % quantiles = 17 / 37 / 64 % of firm capacity. In the 2023 NSHR
forecast 13 % of listed sites go negative on demand headroom by 2030, 35 % by 2040.

## Fields used
For siting: `primary_floc` (join key across vintages), polygon geometry, `firmcapacitywinter`,
`demand` (%), `demandrag`, `seasonofconstraint`; for future stress: `f2030/f2035/f2040`.
Secondary-substation level (customer counts, utilisation bands, supply polygons) is **not**
available without login - the model will have to work at primary-area resolution, with the
Optimise Prime WS3 borough RAG (`ws3_phv_network_impact_by_borough`) as the only open
secondary-level signal.

## Known issues / caveats
- GLA clips to the London LAEP area (Greater London + buffer), so EPN/SPN primaries near the
  boundary are included and the LPN count (108) is the London core; check completeness of LPN
  primaries against `lpn_operational_boundaries` before use.
- `demand` is a percentage of firm capacity (not MVA); firm capacity in MVA; RAG thresholds at +-5 %.
- Capacity is not "available to connect": contracted-but-unbuilt demand is excluded from these
  snapshots (UKPN caveat). Treat as relative constraint, not an absolute cap.
- The NSHR forecast layer is a 2023 vintage (DFES 2022 pathways) with many blank `pn` values and
  only 19 LPN sites; the 2026 NSHR is login-only on the portal (177,240 rows).
- ArcGIS item ids are stable but the GLA may republish under new names; `HEADROOM_LAYERS` in
  `ukpn.py` is the single place to update.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.ukpn headroom   # ~20 s
PYTHONPATH=src python -m chargescape.data.ukpn ods        # open portal tables + registration-required log
```
