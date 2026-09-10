---
id: vehicles_dft_la_timeseries
title: DfT VEH0142 - licensed plug-in vehicles by body type, fuel type, keepership and local authority; London boroughs time series 2009 Q4 - 2026 Q1
provider: Department for Transport (DfT) and Driver and Vehicle Licensing Agency (DVLA)
url: https://www.gov.uk/government/statistical-data-sets/vehicle-licensing-statistics-data-tables
download_url: https://assets.publishing.service.gov.uk/media/6a56140b2cbe5d1c179a6454/veh0142.ods
licence: OGL v3
status: observed
retrieved: 2026-09-10
size_mb: 7.3 raw ODS (UK, 25,996 rows) / 0.2 interim (London subset, long)
spatial_unit: local authority district (33 London boroughs) + London region, England, UK context rows
temporal: quarterly, end of quarter, 2009 Q4 - 2026 Q1 (Great Britain to 2014 Q2, United Kingdom from 2014 Q3); release 15 July 2026
script: src/chargescape/data/vehicles.py
raw_path: data/raw/vehicles/veh0142.ods
---

## What it is
The local-authority companion to VEH0145: licensed plug-in vehicles at the end of each quarter by body type
(Cars, Light goods vehicles, Heavy goods vehicles, Buses and coaches, Motorcycles, Other vehicles, Total), fuel
(Battery electric, Plug-in hybrid electric petrol / diesel, Range extended electric, Total) and keepership
(Private, Company, Total), for every UK upper- and lower-tier local authority. The workbook is an accessible ODS
(cover, contents, notes and one data sheet `VEH0142`); it is parsed with a small stdlib reader
(`read_ods_sheet`, no odfpy dependency) and filtered to ONS codes `E09*` plus `E12000007` (London),
`E92000001` (England) and `K02000001` (United Kingdom).

Output: `data/interim/vehicles/ev_by_la_london_timeseries.parquet` - 152,196 rows, long format:
`table`, `BodyType`, `Fuel`, `Keepership`, `ons_code`, `area_name`, `quarter`, `period_end`, `value`, `marker`.

Headline series (London region, all keepers): all PiVs 39,562 (2020 Q1) -> 60,875 -> 99,402 -> 139,080 ->
192,411 -> 242,002 -> **300,377 (2026 Q1)**; PiV cars 34,706 (2020 Q1) -> 276,825 (2026 Q1), i.e. x8.0 in six
years. Borough growth 2020 Q1 -> 2026 Q1 ranges from x3.4 (Kensington and Chelsea) to x19.4 (Westminster,
fleet registrations).

## Fields used
`BodyType`, `Fuel`, `Keepership`, `ONS Code` -> `ons_code`, `ONS Geography` -> `area_name`, quarter columns
(`YYYY Qn`) -> `quarter`, `period_end`, `value`. `Units` and `ONS Sort` are dropped.

## Known issues / caveats
- Company-kept vehicles are allocated to the company's registered address; Westminster's series (2,712 ->
  52,539 PiVs) is dominated by leasing / fleet registrations. Use `Keepership = Private` for resident uptake.
- `[z]` (not applicable) cells - e.g. UK rows before 2014 Q3 - are NaN with `marker = z`; there is no small-count
  suppression at LA level in this table.
- Numeric cells are read from the ODS `office:value` attribute (exact integers); text cells are only markers.
- Local authority codes are as published by DfT for the release (London boroughs unchanged since 1965, so the
  series is consistent over time).
- Body-type "Total" rows include buses, HGVs and motorcycles; use `BodyType = Cars` for a like-for-like comparison
  with car-stock denominators.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.vehicles     # downloads veh0142.ods once (cached) and rebuilds the parquet
```
