---
id: ukpn_low_carbon_london
title: Low Carbon London - Electric Vehicle Load Profiles (residential, commercial, public trials 2012-2014)
provider: UK Power Networks (author) via Greater London Authority London Datastore
url: https://data.london.gov.uk/dataset/low-carbon-london-electric-vehicle-load-profiles/
download_url: https://data.london.gov.uk/download/2y5k8/c869f8ac-33d3-4cf9-bf28-d89c61bbc7a2/EV%20Load%20Profiles.zip
licence: Creative Commons Attribution (CC BY) per London Datastore record; data anonymised
status: observed
retrieved: 2026-09-10
size_mb: raw 121 (zip) / 729 extracted; interim 131 (residential) + 14 (commercial) + 0.5 (public)
spatial_unit: none (anonymised meters / charge points; Greater London trial, no coordinates or postcodes)
temporal: 10-minute meter readings 2013-01-01 .. 2014-06-03; public sessions 2012-07-11 .. 2014-05-31
script: src/chargescape/data/ukpn.py  (part `lcl`)
raw_path: data/raw/ukpn/low_carbon_london/
---

## What it is
The EV data release of the Ofgem LCNF *Low Carbon London* project (UKPN, 2011-2014). Not on the
UKPN Opendatasoft portal - it lives on the London Datastore as one zip with three nested zips
and a cover note. No login. Three parts:

| interim file | rows | units | content |
|---|---|---|---|
| `lcl_ev_residential_10min.parquet` | 10,787,232 | 66 meters | 10-min power-quality meter readings at the EV charger circuit of trial households (Nissan Leaf / wider LCL group) |
| `lcl_ev_commercial_10min.parquet` | 3,627,862 | 44 meters | same for commercial fleet chargers (light-duty pool/private vans, 3-phase heavy-duty freight) |
| `lcl_ev_public_sessions.parquet` | 25,432 | 1,846 users, 540 charge points | charging *sessions* from four public charge-point suppliers (Source London era) |
| `lcl_commercial_participants.parquet` | 64 | - | meter serial -> participant type, EV use (Pool/Private/Freight), duty (46 light, 18 heavy) |

## Fields used
Meter tables (columns present vary by meter model; missing = NaN): `meter_serial, reading_time,
import_kwh` (energy imported in the 10-min interval, kWh - so kW = import_kwh x 6), `export_kwh,
current_max_a, current_min_a, current_avg_a, voltage_v, active_power_w, apparent_power_va,
reactive_power_var, q1..q4_kwh`. Residential: 47 % of intervals show import > 0; 99th pct 3.65 kW,
99.9th 10 kW (3-phase units), median annual energy per meter ~2,900 kWh. Public sessions:
`supplier (1-4), event_id, user_id, chargepoint_id, start_time, end_time, duration_min, kwh, price`
(price is a flat "GBP10/yr" membership); median 2.9 kWh, 26 % of sessions deliver 0 kWh; start
hours peak 08-17h (workplace/destination pattern).

## Known issues / caveats
- **No locations at all** (no postcode, LSOA or coordinates) - usable only for *temporal* shape of
  home / fleet / public charging, not for spatial demand.
- 2013-14 vehicles (24 kWh Leaf, 3.3-3.7 kW chargers): kWh per session and power are ~half of
  today's; use for diurnal timing, not magnitudes.
- Header layouts differ between meter models (single-phase vs three-phase); a few files contain
  only `SerialNo, ReadingDate`. Residential `ReadingDate` sometimes lacks the time part
  (= midnight). Three residential meters have `import_kwh` ~ 0 throughout (dead meters).
- Public sessions: durations up to 339 days (never-unplugged / faulty end events); filter
  `duration_min < 1440` for analysis. Supplier_4 has 0-kWh median (mostly failed connections).
- Survey workbooks (`Survey data/*.xls`) are legacy .xls and were left unparsed (no xlrd).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.ukpn lcl
```
Downloads the 121 MB zip once, extracts nested zips, writes parquet + `_schema_report.json`
under `data/interim/ukpn/low_carbon_london/`.
