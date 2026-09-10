---
id: sessions_dundee
title: Dundee City Council - Public EV Charge Point Usage (sessions, Jul 2021 - Aug 2025) + charger locations
provider: Dundee City Council (ChargePlace Scotland back office until 2024; DCC / Urban Fox back offices after)
url: https://data.dundeecity.gov.uk/ (ArcGIS Hub - search "Public EV Charge Point Usage"; e.g. https://data.dundeecity.gov.uk/datasets/dundeecity::public-ev-charge-point-usage-dundee-city-council-2023)
download_url: https://www.arcgis.com/sharing/rest/content/items/<item_id>/data  (item ids 189b838f51e74f6bb77509d91c47d7c0 [Jul-Dec 2021], f1a6b5df441d4606821d5f1a78e92d7e [2022], 80df5f177b8c4a94b2bc692835801e8e [2023], 8b443deaf9174b7aa9d3e10eaa906422 [2024], e185a3a1cfc948a69ada76e950b9d447 [Jan-Aug 2025]); station layers: services.arcgis.com/GlZ1P6ksdiXNYhvC/.../EV_charging_points_View_/FeatureServer/0 and .../All%20public%20chargers%20one%20layer/FeatureServer/0
licence: Open Government Licence v3 - stated on the council's retired CKAN portal for the predecessor dataset ("Electric Vehicle Charging Sessions Dundee", archived 2019/2023); the current ArcGIS Hub items carry NO per-item licence text (owner replied "No licence" in the Open Data Scotland index) - treat as OGL v3 pending confirmation with DCC (ask before publication)
status: observed
retrieved: 2026-09-10
size_mb: 56 (raw CSVs 55 + two GeoJSON layers); 11.4 (sessions parquet)
spatial_unit: point (charge point; council layer coordinates, postcode centroid fallback)
temporal: per session, 2021-07-27 .. 2025-08-30 (local UK time)
script: src/chargescape/data/sessions_open.py (fetch_dundee / harmonise_dundee)
raw_path: data/raw/sessions_open/dundee/
---

## What it is
Every charging session at Dundee City Council-owned public charge points (the UK's densest rapid-hub
network: Princes Street, Lochee, Queen Street, Clepington Road hubs + car parks + a 150 kW bus charger),
one CSV per period. Columns: `SDR ID, Site, CP ID, Connector Type (ac|rapid|ultra_rapid), Consum(kWh),
Duration (HH:MM:SS), Start, End (dd/mm/yyyy HH:MM), Postcode`. No user id. The council changed back office
in July 2021, so nothing earlier is on the new portal; the legacy CKAN dataset (2017-2019: `cpdata.csv`,
`cp-data-dec-mar-2018.csv`, `cp-data-mar-may-2018.csv`, `charge-sessions-june-sept.csv`, `cp-locations.csv`)
is gone and the Wayback Machine holds only its landing page, not the files (checked 2026-09-10; the script
still tries and skips gracefully).

Station coordinates come from two council layers: `EV charging points View` (134 points,
`chargepoint_ID`, kW) and `All public chargers one layer` (211 points incl. Urban Fox on-street posts,
`Charge_Point_ID`, `Site_Name`, kW), then the ChargePlace Scotland public locations feed (see
`sessions_chargeplace_scotland.md`), then the session's own **postcode centroid** (postcodes.io, ONS/OGL),
then the centroid of same-named charge points.

## Fields used
station_id = digits of `CP ID` (`APT51593` -> `51593`); station_name = `Site`; start_ts/end_ts;
duration_min from `Duration`; energy_kwh from `Consum(kWh)`; port_type = `Connector Type`;
power_kw from the layers (7/22/50/150); postcode; session_id = `SDR ID`; lat/lon + `lat_source`
(`dcc_layer_ev_charging_points_view` 93%, `postcode_centroid_postcodes_io` 6%, `dcc_layer_all_public_chargers`
1%, `same_site_name_centroid` <0.1%).

## Harmonised outputs (2026-09-10 run)
* `dundee_sessions.parquet`: **387,843 sessions, 90 charge points, 100% located** (2021: 35.9k, 2022: 88.1k,
  2023: 119.1k, 2024: 94.7k, 2025 Jan-Aug: 50.1k).
* Median 15.9 kWh / 39 min overall; rapid (78% of sessions) 16.2 kWh / 35 min; AC 12.2 kWh / 146 min;
  ultra-rapid (bus charger + 150 kW) 38 kWh / 49 min.
* Arrivals by hour: peak 13h (7.4%); 07-10h 19%, 11-15h 36%, 16-19h 22%, 20-23h 13%, 00-06h 11%;
  weekend 29% -> a taxi/PHV-heavy rapid-hub profile with a real night tail (free charging until 2022).
* `dundee_stations.parquet`: n_sessions, first/last seen, kW, coordinates per charge point - directly usable
  as the per-charger utilisation target.

## Known issues / caveats
* The 2024 file exists twice on the Hub: a Jan-2025 upload (113,607 rows) and a Jul-2025 re-upload (94,661 rows,
  93,945 SDR IDs in common, 2,650 only in the old one). We use the re-upload only (`_2024_dup.csv` kept raw).
* 1.5% sessions have start == end (aborted plug-ins, kWh often blank); 0.2% rows share (CP, start, kWh) with
  different SDR IDs (double logging) - drop for calibration.
* 1.4% sessions > 150 kWh: almost all `Greenmarket 150kW Bus Charger` (CP 62124/62125, ultra_rapid) - a bus
  depot charger, exclude for car behaviour; one absurd 1.6 GWh row.
* Tariff regime changed (free -> paid 2022, price rises 2023/24) - visible in the yearly counts; model year effects.
* Postcode-centroid coordinates are within ~100 m in urban Dundee, fine for OSM-feature joins at 250 m+.
* Licence ambiguity above: the data is published on a council open-data portal but without explicit terms.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only cps,dundee   # cps first supplies feed coordinates
```
