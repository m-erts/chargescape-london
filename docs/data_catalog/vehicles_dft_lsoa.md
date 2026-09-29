---
id: vehicles_dft_lsoa
title: DfT / DVLA vehicle licensing statistics at LSOA 2021 level - VEH0145 plug-in vehicles, VEH0135 ULEVs, VEH0125 all vehicles (Greater London extract)
provider: Department for Transport (DfT) and Driver and Vehicle Licensing Agency (DVLA)
url: https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-files
download_url: https://assets.publishing.service.gov.uk/media/6a54d2ea9e9c95844ae64da1/df_VEH0145.csv ; https://assets.publishing.service.gov.uk/media/6a54d2eb2467584757371e08/df_VEH0135.csv ; https://assets.publishing.service.gov.uk/media/6a54d2f5a6586e258d371d73/df_VEH0125.csv
licence: OGL v3
status: observed
retrieved: 2026-09-10
size_mb: 364 raw (60.6 + 62.2 + 241.6, UK-wide CSV) / 7.6 interim (London)
spatial_unit: LSOA 2021 (UK; London extract = 4,994 LSOAs)
temporal: "quarterly, end of quarter; VEH0145 / VEH0135 2011 Q4 - 2026 Q1, VEH0125 2009 Q4 - 2026 Q1 (London extract keeps 2019 Q1+); release of 15 July 2026 (\"Vehicle licensing statistics: January to March 2026\")"
script: src/chargescape/data/vehicles.py
raw_path: data/raw/vehicles/
---

## What it is
DfT's small-area vehicle stock files, derived from the DVLA vehicle register: every licensed vehicle is allocated
to the LSOA of its registered keeper's postcode (keeper's address for privately kept vehicles, the company's
registered address for company-kept vehicles). The files were re-based to **LSOA 2021** boundaries (column
`LSOA21CD`), so they join directly to the census layer without a crosswalk.

| table | title | dimensions | London rows kept |
|---|---|---|---|
| **VEH0145** | Licensed plug-in vehicles (PiVs) at end of quarter by fuel type, keepership and LSOA: UK | Fuel (Battery electric, Plug-in hybrid electric (petrol / diesel), Range extended electric, Total) x Keepership (Private, Company, Total) | 2,150,002 (long) |
| **VEH0135** | Licensed ultra low emission vehicles (ULEVs, < 75 gCO2/km) by fuel type, keepership and LSOA: UK | Fuel (10 incl. petrol / diesel / hybrid ULEV models, Total) x Keepership | 2,302,020 (long) |
| **VEH0125** | Vehicles at end of quarter by licence status, body type, keepership and LSOA: UK | BodyType (Cars, Motorcycles, Other vehicles, Total) x Keepership x LicenceStatus (Licensed, SORN) | 2,922,939 (long, 2019 Q1+) |

Outputs in `data/interim/vehicles/`:

| file | content |
|---|---|
| `ev_by_lsoa_london.parquet` (1.4 MB) | VEH0145 long: `lsoa21cd`, `lsoa21nm`, `Fuel`, `Keepership`, `quarter`, `period_end`, `value`, `marker`, borough columns; all published rows, all quarters |
| `ev_by_lsoa_london_latest.parquet` (0.5 MB) | 2026 Q1 snapshot, 4,994 rows: `piv_total`, `piv_private`, `piv_company`, `bev`, `phev_petrol`, `phev_diesel`, `reev`, `bev_private` (each with `_flag` and `_est`), `bev_share_of_piv`, `private_share_of_piv`, VEH0125 denominators (`cars_licensed[_private|_company]`, `cars_sorn`, `vehicles_licensed`, `motorcycles_licensed`, `other_vehicles_licensed` with flags / estimates), `piv_share_of_licensed_cars`, `piv_private_share_of_private_cars`, census joins (`households`, `population`, `cars_est`), `piv_per_1000_hh`, `piv_private_per_1000_hh`, `piv_per_1000_pop` |
| `ulev_by_lsoa_london.parquet` (1.5 MB) | VEH0135 long |
| `vehicles_by_lsoa_london.parquet` (4.1 MB) | VEH0125 long, 2019 Q1 - 2026 Q1 |
| `vehicles_by_lsoa_london_latest.parquet` | 2026 Q1 snapshot of VEH0125 (published Total rows) |

London, end of March 2026 (2026 Q1): **300,180 licensed plug-in vehicles** (published LSOA totals; 1 LSOA
suppressed), of which ~177,600 privately kept and ~122,200 company kept; ~190,400 battery electric (63%),
~98,600 petrol PHEV, ~4,300 range-extended, ~350 diesel PHEV. Licensed cars (VEH0125): 2,639,182, of which
2,390,055 private. PiVs (all body types) / licensed cars = 11.4%.

## Fields used
`LSOA21CD`, `LSOA21NM`, `Fuel`, `Keepership`, `BodyType`, `LicenceStatus`, one column per quarter (`YYYY Qn`,
newest first). `period_end` is derived (Q1 = 31 Mar, Q2 = 30 Jun, Q3 = 30 Sep, Q4 = 31 Dec).

## Known issues / caveats
- **Disclosure control (observed, not documented on the DfT notes page):** counts of 1-4 are shown as `[c]` (the
  smallest visible non-zero value in every file is 5) and, in addition, many small fuel x keepership rows are
  simply **omitted** - the files are not a full cross-product. Only 6% of London LSOAs have component rows that
  sum to the published `Total`/`Total` row. The snapshot therefore uses the published Total rows as
  authoritative (`*_flag = ok | c | missing`) and derives `piv_company_est = piv_total_est - piv_private_est`
  (the company row is absent for 1,533 London LSOAs). `[c]` cells are estimated at 2.5 (`SUPPRESSED_EST`);
  omitted fuel rows are filled from the residual to the total only when it is identifiable, otherwise left NaN
  (`bev_est` NaN for 23 LSOAs; `phev_diesel_est` / `reev_est` NaN for ~3,200 LSOAs where the residual of 1-4
  vehicles cannot be split). `piv_total_est` and `piv_private_est` are complete for all 4,994 LSOAs.
- **Company-kept vehicles are counted at the company's registered address**, not where they are parked.
  Westminster alone holds 52,547 PiVs (554 per 1,000 households, 59% of its licensed cars) and one Westminster
  LSOA has 35,000 PiVs per 1,000 households - lease / fleet registrations, not resident demand. Use
  `piv_private_*` for residential demand and treat `piv_company_*` as a fleet / workplace signal.
- VEH0145 has no body-type split: PiV totals include vans, motorcycles and buses, while the natural denominator
  (VEH0125 `Cars`, Licensed) is cars only; the ratio `piv_share_of_licensed_cars` is therefore a slight
  over-statement. Borough-level cars-only PiV figures are available in VEH0142 (see `vehicles_dft_la_timeseries.md`).
- The London LSOA sum (300,180) is 197 below the VEH0142 London region total (300,377): vehicles with a
  postcode that cannot be matched to an LSOA are only in the higher-level tables.
- VEH0135 fuels include petrol, diesel and non-plug-in hybrid rows - these are ULEV-qualifying conventional
  models, not EVs; filter on fuel before using it as an EV measure (VEH0145 is the cleaner PiV source).
- Keepership `Disposal` exists in the UK files but has zero London vehicles in 2026 Q1; `Total` = Private + Company.
- The census join uses Census-day 2021 households against March-2026 vehicle counts; household growth since 2021
  (new-build LSOAs) inflates per-household rates slightly.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.census     # first, for the London LSOA list and census denominators
PYTHONPATH=src python -m chargescape.data.vehicles   # ~370 MB download on first run, then ~20 s from cache
```
Set `fetch_vehicle_stats(include_veh0125=False)` to skip the 242 MB VEH0125 file (loses the car-stock denominators).
