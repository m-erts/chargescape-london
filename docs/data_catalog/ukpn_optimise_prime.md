---
id: ukpn_optimise_prime
title: Project Optimise Prime - Commercial Electric Vehicles Trial (WS1 home, WS2 depot, WS3 PHV)
provider: UK Power Networks (with Hitachi, Centrica/British Gas, Royal Mail, Uber, SSEN)
url: https://ukpowernetworks.opendatasoft.com/explore/dataset/ukpn-optimise-prime/information/
download_url: Azure Blob container https://ukpnoppublicdata001.blob.core.windows.net/optimiseprime (public read/list SAS token published in the dataset description; current token valid to 2027-08-20) - 1,027 CSV files, 164.2 GB
licence: CC BY 4.0
status: observed (trial telemetry Aug-2018..Sep-2022; core trial period 2021-07-01..2022-06-30)
retrieved: 2026-09-10
size_mb: raw 1,490 downloaded (116 of 1,027 files: every table <100 MB in full + one partition of each large table); interim ~300
spatial_unit: none for sessions (WS1 charger ids only); outward postcode district for WS1 trips; depot name (9 Royal Mail depots, London/Kent) for WS2; London borough for WS3
temporal: WS1 charging 2020-06..2022-07 (plus 20 stray 2014 rows); WS1 trips 2018-08..2022-09 monthly files; WS2 2020-07..2022-09; WS3 static (5 time windows)
script: src/chargescape/data/ukpn.py  (part `op`)
raw_path: data/raw/ukpn/optimise_prime/
---

## What it is
The full data release (Deliverable D6, Feb 2023) of UKPN's NIC project on commercial EV charging.
On the Opendatasoft portal the dataset has **0 records** - it is a landing page whose description
contains the Azure Blob account URL and a read+list SAS token. `ukpn.py` parses that token at run
time, lists the container (`_blob_listing.json`), and downloads a curated subset (below).
No registration is involved; the token is published openly and the guidance PDF/FAQ are attached
to the portal record (`docs/202302_OP_Deliverables_D6_Dataset_Guidance_V4.pdf`, `docs/OP_Deliverables_D6_FAQ.docx`).

Container layout (28 tables, sizes are totals in the container):

| WS | table | files | size | downloaded | interim |
|---|---|---|---|---|---|
| WS1 | 06 bg-fleet-charging (home CP sessions) | 8 | 25 MB | **all** | `ws1_bg_home_charging_sessions` |
| WS1 | 07 bg-trips (telematics trips, outward postcode) | 50 monthly | 10.9 GB | 1 month (2021-10) | `ws1_bg_trips_sample` |
| WS1 | 8 aggregated shift telematics (ICE + EV) | 1 | 77 MB | all | `ws1_bg_shift_telematics` |
| WS2 | 10-14 depots / cptypes / chargepoints / evtypes / evehicles (Kafka change logs) | 43 | <3 MB | all | `assets_*`, `assets_log_*` |
| WS2 | 15 brand-a charging / consumption / poslog | 75 | 8.4 GB | 1 month charging+consumption; poslog skipped (no coordinates) | `ws2_telematics_brand_a_*_sample` |
| WS2 | 16-17 brand-b measures | 22 | 3.7 GB | 1 month | `ws2_telematics_brand_b_measures_sample` |
| WS2 | 18 brand-c ev | 7 | 0.3 GB | 1 file (2021-11) | `ws2_telematics_brand_c_sample` |
| WS2 | 19 building-load-measures (1-min site load) | 25 | 5.0 GB | 1 month | `ws2_building_load_1min_sample` |
| WS2 | 20 building-catalog | 2 | - | all | `ws2_building_catalog` |
| WS2 | 21-22 nortech-ihost-measurements (OCPP CP telemetry) | 733 daily | **133.5 GB** | 1 day (2021-10-13) | `ws2_chargepoint_measurements_sample` |
| WS2 | 23 profiled-connections | 12 | 2.1 GB | 6 small config files | `trial_config_profiled-connections` |
| WS2 | 24-26 ToU throttling / planned flex events / flex dispatches | 29 | 20 MB | all | `trial_config_*` |
| WS2 | 27 depot_load (1-min EV load + headroom per depot) | 1 | 74 MB | all | `ws2_depot_load` |
| WS2 | 28-31 EV details by site, CP counts, enacted flex A/B | 4 | 2 MB | all | `ws2_ev_details_by_site`, `ws2_cp_counts`, `ws2_enacted_flex_product_a/b` |
| WS2 | 32 load_profiles_dataset (hourly depot EV load + trial flags) | 1 | 4.5 MB | all | `ws2_depot_hourly_load_profiles` |
| WS3 | 33 network_impact_by_borough | 1 | <1 MB | all | `ws3_phv_network_impact_by_borough` |

Full machine-readable profile (dtypes, time spans, cardinalities, numeric quantiles, READMEs):
`data/interim/ukpn/optimise_prime/_schema_report.json`.

## Schema findings - what decides the demand-model design

**1. WS1 home charging sessions (`ws1_bg_home_charging_sessions`, 173,920 rows, complete)**
- One row per charging *transaction* at a British Gas engineer's **home** charge point:
  `charger_id` (1,076 distinct, 'BGS_xxxx'), `transaction_id`, `start_date_time`, `end_date_time`,
  `charge_duration_minutes`, `total_kwh`, `plug_duration_minutes` (+ `is_valid` flag we add).
- Timestamps yes; energy yes (median 23.9 kWh, p95 55 kWh, 9 % zero-kWh sessions); plug-in
  duration yes (median 11.6 h); **no SoC**, **no location, no postcode, no LSOA** and, by design,
  **no join key to the trips table** (FAQ Q16).
- Vehicles are all Vauxhall Vivaro-e vans on 7.4 kW single-socket home CPs; drivers are spread
  across the UK (not London-specific). Active chargers ramp from 5 (Jul-2020) to 735 (Jun-2022);
  ~10-16k sessions/month in the core period. Start-hour profile peaks 15-18h (return-to-home),
  1 % of sessions start 00-05h.
- => It is an excellent **observed home/return-to-home session generator** (arrival time, energy,
  dwell) but **not** public charging and not spatially resolvable.

**2. WS1 trips (`ws1_bg_trips_sample`, 1.31 M trips in Oct-2021 alone; 50 months, 10.9 GB total)**
- `device_screen_name` (vehicle; 7,192 in the sample), UTC start/end, `distance_trip_miles`
  (median 1.2 mi, p90 11.4), `start_post_code` / `end_post_code` = **outward district only**
  (e.g. "SE15"), 9.6 % UNKNOWN. Covers the whole GB BG fleet (mostly ICE): only ~17 % of trips
  start in London-area postcode districts. Usable for OD/dwell patterns at postcode-district
  level (map districts to LSOAs by area weighting) but not for charging events.

**3. WS1 shift telematics (`ws1_bg_shift_telematics`, 1,048,575 rows = Excel row cap, so the
source file is truncated)**: per vehicle-shift start/end, miles, `is_ev_bool` (13 % EV),
`home_loc_definition` (Urban/Suburban/Rural), `schedule_profile`. EV shifts average 51 mi/day
(ICE 41) - good for daily energy need distributions.

**4. WS2 depot trial (Royal Mail, 9 depots: Mount Pleasant, Whitechapel, Islington, Camden,
Victoria, Premier Park (Park Royal), Bexleyheath, Orpington, Dartford)**
- Assets: 703 EVs (Mercedes e-Vito 4.6 kW / Peugeot Partner & Expert 3.6 kW; battery types 22.5-52.5 kWh),
  130 charge-point sockets (Alfen twin/single, Swarco twin; 3.6-7.3 kW), depot connection
  capacities 40-2,800 kVA. Locations are depot *names* only (geocodable to ~9 points).
- Observed charging: `ws2_depot_hourly_load_profiles` (49,056 depot-hours, 2021-06..2022-06,
  `ev_load_kw` mean 10.9, max 339 kW) with flags for unmanaged / ToU / profiled connection /
  flexibility days - a clean **observed depot load curve** dataset. `ws2_depot_load` gives the same
  at 1-minute resolution (1.1 M rows) with `capacity_kva` and `final_headroom`.
- CP-level OCPP telemetry (`nortech`, 133.5 GB): per socket `realpower`, `totalenergy`,
  `currentlimit`, OCPP status booleans, `tag_id` (=EV `ChargingTagId`) - session reconstruction
  possible but only for these depots; we hold one day (2.7 M rows).
- Telematics: brand A (`energy_level` = **SoC %**, `autonomy` = range km, plug/charging flags,
  charging power) and brand B (`HighVoltageBattery.StateOfCharge`, `Charging.Power`, odometer)
  -> **SoC is available for depot vans** (125 EVs in the Oct-2021 sample); GPS position logs exist
  (`poslog`) but carry speed/reason only, **no coordinates**.

**5. WS3 Uber/PHV (`ws3_phv_network_impact_by_borough`, 164 rows)**: the only PHV output
released - per London borough x 5 time windows, the RAG status and % of LSOAs red/amber/green
of *secondary-substation headroom after Uber EV charging demand* (worst-case, static). **No
Uber trips, no PHV sessions, no LSOA table** were released (commercially confidential / GDPR).

**Bottom line for ChargeScape:** Optimise Prime gives observed *behavioural* distributions
(home-charging arrival/energy/dwell; depot load curves with SoC) and a borough-level PHV
stress screen, but **no public-charging sessions with London locations**. The spatial demand
model must be built on proxies (DFES LSOA EV forecasts, LAEI PHV/taxi flows, DfT counts, POI /
census) and calibrated in shape (not location) against OP/LCL sessions.

## Fields used
See table above and `_schema_report.json`; principal modelling inputs are
`ws1_bg_home_charging_sessions[start_date_time, end_date_time, total_kwh, plug_duration_minutes, is_valid]`,
`ws2_depot_hourly_load_profiles[depot_name, timestamp, ev_load_kw, unmanaged_charging, ...]`,
`ws1_bg_shift_telematics[shift_distance_miles, is_ev_bool, home_loc_definition]`,
`ws3_phv_network_impact_by_borough[borough_name, time_window, borough_avg_RAG_status, pct_lsoas_*]`.

## Known issues / caveats
- SAS token rotates (yearly so far); the module re-reads it from the portal description.
- Kafka-style tables (10-14, 23-26) are change logs; `assets_*` = latest non-deleted state,
  `assets_log_*` = full history (11 depot records incl. 2 test/deleted depots).
- WS1 sessions contain 20 rows dated 2014, negative plug durations and a 1,487 kWh row -
  `is_valid` (>= 2020-06-01, 0-100 kWh, plug <= 7 d) keeps 99.5 %.
- Table 8 is truncated at 1,048,575 rows (source exported through Excel).
- Large tables are sampled (one partition each); re-run with more file names in
  `OP_SAMPLE_FILES` to extend. Timestamps in telematics are UTC; depot load profiles are local.
- 2021-22 energy prices / COVID recovery period; Royal Mail depots are LPN + SPN (Dartford).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.ukpn op
```
~2 min on first run (1.5 GB); afterwards ~35 s (parquet rebuild only).
