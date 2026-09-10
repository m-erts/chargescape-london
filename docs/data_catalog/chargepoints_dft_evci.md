---
id: chargepoints_dft_evci
title: DfT Electric vehicle charging infrastructure statistics – data tables (EVCI), 1 July 2026
provider: Department for Transport (official statistics; charger data supplied by Zapmap and chargepoint operators, population by ONS)
url: https://www.gov.uk/government/statistics/electric-vehicle-charging-infrastructure-statistics-1-july-2026
download_url: https://www.gov.uk/government/statistical-data-sets/electric-vehicle-charging-infrastructure-statistics-data-tables-evci
licence: Open Government Licence v3.0
status: observed
retrieved: 2026-09-10
size_mb: 1.05 (four ODS workbooks) / 0.04 (two parquet extracts)
spatial_unit: local authority (33 London boroughs incl. City of London, E09*), region (London E12000007), country (England, UK)
temporal: quarterly snapshots 1 January / 1 April / 1 July 2026 (new "EV chargers" series) plus historic quarterly "charging devices" series Oct-2019 .. Jul-2026
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/dft_evci/
---

## What it is
The latest DfT release (published **27 August 2026**, data as at **1 July 2026**, next release November 2026) of the
"Electric vehicle charging infrastructure statistics" series. The data-tables page lists 24 ODS attachments; four
were downloaded (exact GOV.UK titles and asset URLs):

| Table | Title on GOV.UK | File (assets.publishing.service.gov.uk/media/…) |
|---|---|---|
| EVCI0101 | Public EV chargers by country and region: United Kingdom, 1 July 2026 | `6a8ed778df4246cf45e4654d/evci0101_2026-07_EV_chargers_by_region_and_country_UK.ods` (27.6 kB) |
| EVCI0102 | Public EV chargers by local authority: United Kingdom, 1 July 2026 | `6a8ed78af5b35599aec18df8/evci0102_2026-07_EV_chargers_by_local_authority_UK.ods` (203.7 kB) |
| EVCI0201 | Public EV chargers by power band: United Kingdom, 1 July 2026 | `6a8ed7e53b22fb169dc18e1d/evci0201_2026-07_EV_chargers_by_power_band_UK.ods` (7.6 kB) |
| EVCI9001 | Public EV charging devices: United Kingdom, 1 July 2026 (historic tables) | `6a8c0284a8f84a582b84280a/evci9001_2026-07_EV_charging_devices_UK.ods` (808.2 kB) |

Sheets used: `EVCI0101e` and `EVCI0102e` (tidy long versions of the a–d sheets: Date, Notes, area code, area name,
Key, Value with the four keys *EV chargers*, *50kW+ EV chargers*, *EV chargers per 100k*, *50kW+ EV chargers per
100k*), `EVCI0201b` (UK totals by power band: Standard / Standard plus / Rapid / Ultra-rapid) and EVCI9001 sheets
`1a` (devices, all speeds), `1b` (rapid+ devices), `2a`/`2b` (the same per 100,000 population) – local authority ×
quarter, Oct-19 … Jul-26.

Outputs:
- `data/interim/chargepoints/dft_evci_london_la.parquet` – 4,512 rows, 36 areas (33 boroughs + London + England
  + UK), columns `area_code, area_name, geography, date, period_label, measure, value, notes, source_table,
  source_file`.
- `data/interim/chargepoints/dft_evci_uk_power_band.parquet` – 12 rows (3 quarters × 4 bands, UK only).

## Fields used
`area_code` (ONS GSS code), `area_name`, `geography` (local_authority | region | country), `date` (snapshot date),
`period_label` (label as printed, e.g. "1 July 2026" or "Oct-24 [Note 14]"), `measure` (the DfT Key or the EVCI9001
series name), `value` (float; suppressed "[x]" cells become NaN), `notes` (e.g. "[note 5]"), `source_table`
(EVCI0101e, EVCI0102e, EVCI9001_1a/1b/2a/2b), `source_file`.

## Known issues / caveats
- **Two definitions coexist.** The 2026 "EV chargers" tables (EVCI01xx/02xx) count chargers as reported by CPOs
  through Zapmap; the historic EVCI9001 tables count "charging devices". They do not reconcile: London on 1 July
  2026 is 31,371 chargers (EVCI0102e sum of boroughs = EVCI0101e region figure) but 28,767 devices (EVCI9001 1a).
  Use one series per analysis; EVCI9001 is the only source of a long time series (London 4,360 devices Oct-19 →
  28,767 Jul-26).
- **No power-band split by local authority.** LA level offers only total and 50kW+ ("rapid and ultra-rapid").
  The four-band split (Standard <8 kW, Standard plus 8–49 kW, Rapid 50–149 kW, Ultra-rapid ≥150 kW) exists at
  UK level only (EVCI0201: 59,587 / 32,697 / 14,891 / 13,996 on 1 July 2026, total 121,171).
- EVCI9001 1b/2b use a 25 kW+ threshold before Oct-23 and 50 kW+ after (labels kept in `period_label`).
- The 1 July 2026 columns carry "[note 5]": in June 2026 one CPO removed c. 1,270 chargers from its open data feed
  because they were private-access chargers wrongly reported as public; DfT warns April→July comparisons may be
  affected. Hammersmith and Fulham (−170 chargers Jan→Jul 2026) and City of London (−49) look like this correction,
  not decommissioning. EVCI0201 note 3 flags a similar feed error that reclassified "standard plus" chargers as
  "standard" between January and April 2026.
- Granularity is deliberately limited: the regional "EV chargers" series starts January 2025 and the local-authority
  series only January 2026, because DfT trusts granular data only after the Public Charge Point Regulations 2023
  open-data duty was enforced (November 2024) – EVCI0101 note 4. The whole series is labelled "official statistics
  in development".
- Per-100k figures in the 2026 tables use ONS Mid-Year Estimates 2024; older EVCI9001 quarters used 2022, 2019 and
  2018 estimates (EVCI9001 notes 5 and 16), so per-capita history is not strictly comparable. City of London's tiny
  resident population inflates its rate.
- The ODS files were parsed with a stdlib reader (`read_ods`, zipfile + XML) because `odfpy` is not installed; only
  the cell values/text are read (no formulas, no formatting).
- Figures are compiled from CPO returns; they are counts of publicly available devices/chargers, not of sockets or
  sites, and are not geocoded – join to boroughs by `area_code`.

## How to reproduce
```bash
PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_dft_evci; fetch_dft_evci()"
```
Re-running is a no-op while the parquet exists; the ODS files are only downloaded when missing.
