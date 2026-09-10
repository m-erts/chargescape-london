---
id: census_2021_tables
title: Census 2021 (England & Wales) topic summaries for London LSOA 2021 via the nomis API - TS001, TS003, TS007A, TS044, TS045 (+TS045A), TS054, TS061, TS062
provider: Office for National Statistics, served by Nomis (Durham University)
url: https://www.nomisweb.co.uk/sources/census_2021_ts
download_url: https://www.nomisweb.co.uk/api/v01/dataset/NM_2063_1.data.csv?geography=2013265927TYPE151&c2021_cars_5=0,1,2,3,4&measures=20100 (pattern; dataset ids below)
licence: OGL v3 (Crown copyright, ONS)
status: observed
retrieved: 2026-09-10
size_mb: 40 raw CSV / 2.0 tidy parquet + 2.7 feature table
spatial_unit: LSOA 2021 (4,994 London LSOAs); MSOA 2021 (1,002) for the car-stock calibration only
temporal: Census day, 21 March 2021 (static)
script: src/chargescape/data/census.py
raw_path: data/raw/census/nomis/
---

## What it is
Census 2021 topic-summary (TS) tables for every London LSOA, fetched from the nomis REST API (no key; hard cap of
25,000 cells per call, so categories are requested in groups of <=5 x 4,994 LSOAs = 24,970 cells and the
`RECORD_COUNT` field is asserted against the rows received). Geography is nomis's region London
(`2013265927`) with type `TYPE151` (2021 LSOAs). One tidy parquet per table
(`data/interim/census/<table>_lsoa21_london.parquet`: `geography_code`, `geography_name`, `table`,
`category_code`, `category`, `value`, `obs_status`) plus the joined wide table
`data/interim/census/lsoa21_london_features.parquet` (4,994 rows x 99 columns, no missing values).

| table | nomis id | dimension | categories fetched | population base |
|---|---|---|---|---|
| TS001 usual residents by residence type | NM_2021_1 | c2021_restype_3 | all 3 | usual residents |
| TS003 household composition | NM_2023_1 | c2021_hhcomp_15 | total only | households |
| TS007A age, five-year bands | NM_2020_1 | c2021_age_19 | all 19 | usual residents |
| TS044 accommodation type | NM_2062_1 | c2021_acctype_9 | all 9 | households |
| TS045 car or van availability | NM_2063_1 | c2021_cars_5 | all 5 | households |
| TS045A number of cars or vans in the area | NM_2324_1 | c2021_cars_total | total, **MSOA level only** | cars |
| TS054 tenure | NM_2072_1 | c2021_tenure_9 | all 15 (incl. aggregates 1001-1004) | households |
| TS061 method used to travel to work | NM_2078_1 | c2021_ttwmeth_12 | all 12 | residents 16+ in employment |
| TS062 NS-SeC | NM_2079_1 | c2021_nssec_10 | all 10 | residents 16+ |

Verified totals for London (sum of the 4,994 LSOAs): population 8,799,776; households 3,423,845 (TS045; TS003
gives 3,423,999 and TS044 3,423,841 - the small differences are ONS's record-swapping / rounding disclosure
control); estimated cars 2,775,461 (cars per household 0.811).

## Fields used
Wide feature table, by source:
- geography: `lsoa21cd`, `lsoa21nm`, `msoa21cd`, `msoa21nm`, `lad22cd`, `lad22nm`, `inner_london`, `area_km2`,
  `pwc_x`, `pwc_y`, `pwc_lon`, `pwc_lat`, `pop_density_km2`, `hh_density_km2`
- TS001: `population`, `population_in_households`, `population_communal`
- TS003: `households_ts003`
- TS045: `households`, `hh_no_car`, `hh_1_car`, `hh_2_cars`, `hh_3plus_cars`, `cars_est`, `cars_per_household`,
  `share_no_car`, `share_1_car`, `share_2plus_cars`
- TS044: `n_detached`, `n_semi_detached`, `n_terraced`, `n_flat_purpose_built`, `n_flat_converted`
  (converted/shared house + other converted building), `n_flat_commercial`, `n_caravan_temporary`,
  `share_detached`, `share_semi_detached`, `share_terraced`, `share_detached_semi`, `share_house`
  (detached + semi + terraced: off-street-parking / home-charging proxy), `share_flat` (all flat types),
  `share_flat_purpose_built`
- TS054: `share_owner_occupied` (owned outright + mortgage), `share_owned_outright`, `share_shared_ownership`,
  `share_social_rented`, `share_private_rented`, `share_rent_free`
- TS061: `workers_16plus`, `share_wfh`, `share_drive_to_work`, `share_drive_to_work_excl_wfh` (denominator
  excludes home-workers), `share_car_passenger`, `share_public_transport` (underground/metro + train + bus),
  `share_active_travel` (bicycle + on foot)
- TS062: `residents_16plus`, `share_nssec_higher_managerial` (L1-L3), `share_nssec_managerial_professional`
  (L1-L6), `share_nssec_intermediate`, `share_nssec_small_employers`, `share_nssec_routine_semiroutine`
  (L12-L13), `share_nssec_never_worked_ltu`, `share_nssec_students`
- TS007A: `share_age_under_20`, `share_age_20_39`, `share_age_40_64`, `share_age_65plus`
- IoD2025 columns: see `census_imd.md`

## Known issues / caveats
- **TS045A is not published at LSOA level** (nomis returns `OBS_STATUS = Q`, "figures are missing"), only at MSOA
  and above. The LSOA car stock is therefore estimated as `hh_1_car + 2*hh_2_cars + k3*hh_3plus_cars`, with the
  London-wide `k3` (mean cars in "3 or more" households) calibrated so the estimate reproduces the published
  MSOA total exactly (k3 = 3.372; a naive k3 = 3 under-counts London's cars by ~51,000). The value is printed
  in the run log (`cars_3plus_multiplier`). Within-LSOA error is small but non-zero.
- Census 2021 was taken during a COVID-19 lockdown: TS061 travel-to-work shares (41% "work mainly from home"
  London-wide) and TS066/TS062 economic activity are not representative of normal commuting; use
  `share_drive_to_work_excl_wfh` or treat TS061 as a relative, not absolute, indicator.
- ONS applies targeted record swapping and cell perturbation; sub-table totals differ by a few households
  (see the three household totals above) and tiny categories in small LSOAs are noisy.
- Nomis category codes 1001-1007 / 9996-9997 are ONS aggregate rows (e.g. TS054 `1001 = Owned`); they are kept
  in the tidy files, so do not sum all rows of a table.
- Column names in the tidy files keep nomis's `geography_code` naming; the feature table uses `lsoa21cd`.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.census        # fetch_census_tables() -> build_lsoa_features()
```
Raw CSV responses are cached in `data/raw/census/nomis/` (one file per table x category chunk; delete to refetch).
Runtime ~1-2 minutes for the 20 nomis calls; be polite (the module sleeps 0.5 s between calls).
