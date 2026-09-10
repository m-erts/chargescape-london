---
id: sessions_perth_kinross
title: Perth & Kinross Council - EV Charge Station Use (sessions, Sep 2016 - Aug 2019) + charging points layer
provider: Perth & Kinross Council (ChargePlace Scotland back-office export)
url: https://data.pkc.gov.uk/ (ArcGIS Hub): datasets perth-kinross::ev-chargestation-use-sept-2016-to-aug-2017, ...-sept-2017-to-aug-2018, ...ev-charge-station-use-sept-2018-to-aug-2019, perth-kinross::electric-vehicle-charging-points
download_url: https://www.arcgis.com/sharing/rest/content/items/<id>/data with ids 79cec80b01764d9db32961c3476c9346 (2016-17), 93748dde99cd45468a5e9c08f61c1953 (2017-18), ca6cae3df2624832a2eaf678f2eabee8 (2018-19); stations https://services-eu1.arcgis.com/WD0cvOmDKf7CA0Xy/arcgis/rest/services/Electric_Vehicle_Charging_Points/FeatureServer/10 (or data.pkc.gov.uk/api/download/v1/items/5b33371b1bca49808614a7d2452ac418/csv?layers=10)
licence: Open Government Licence v3 (per-item licenseInfo: "Open Government Licence. An acknowledgement of the source is required" - Perth and Kinross Council; station layer also contains OS OpenData, (c) Crown copyright)
status: observed
retrieved: 2026-09-10
size_mb: 8.5 (raw); 2.1 (parquet)
spatial_unit: point (charge point; 45 council charging points with coordinates)
temporal: per session, 2016-09-01 .. 2019-08-31 (local UK time); no later periods published
script: src/chargescape/data/sessions_open.py (fetch_pkc / harmonise_pkc)
raw_path: data/raw/sessions_open/perth_kinross/
---

## What it is
Three annual back-office exports (Sep-Aug) of every session at PKC's ChargePlace Scotland chargers
(Perth park & rides, town car parks in Kinross, Dunkeld, Aberfeldy, Auchterarder, Blairgowrie, Crieff ...):
`_id, CP ID, Connector, Start Date, Start Time, End Date, End Time, Total kWh, Site, Model`. Anonymous
(no user id). The `Electric Vehicle Charging Points` layer gives `Id` (= CP ID), site, address, town,
speed class, connector types, kW (OUTPUT1/2), free/charged, public/staff, max stay.

## Fields used
station_id = `CP ID`; station_name = `Site`; start/end from date + time; energy_kwh = `Total kWh`;
connector = `Connector` (1/2); port_type = `Model` (e.g. `APT Triple Rapid Charger`, `APT 22kW Raption`,
`Siemens Triple Rapid Charger`); power_kw parsed from the model string (rapid -> 50) or from the layer;
lat/lon from the layer (`pkc_layer_electric_vehicle_charging_points`, 98% of rows) or the CPS feed (2%).

## Data fix applied (important)
The `Start Date`/`End Date` columns are ISO strings produced upstream from d/m/Y dates through a m/d/Y parser:
every date with day <= 12 had day and month swapped (17-18% of rows fell outside each file's Sep-Aug
window; e.g. 5 Nov 2016 was exported as 2016-05-11, 9 Mar 2017 as 2017-09-03, while 25 Nov 2016 stayed correct).
`_unswap_daymonth()` swaps them back for day <= 12; afterwards each
(time-sorted) file is strictly monotone and 99.5-99.7% of rows are inside the nominal window (rest = files
overlapping a few days). Do not re-parse the raw CSVs without this.

## Harmonised outputs (2026-09-10 run)
* `pkc_sessions.parquet`: **66,664 sessions, 36 charge points, 100% located**; 2016 (Sep-Dec) 4.0k, 2017 15.9k,
  2018 24.0k, 2019 (Jan-Aug) 22.7k.
* Median 8.7 kWh / 31 min; by power: 50 kW rapid (77% of sessions) 9.0 kWh / 26 min; 22 kW 7.6 kWh / 106 min;
  7 kW 8.3 kWh / 209 min. Free-to-use network in this period (short, top-up rapid sessions).
* Arrivals: peak 12h (9.0%); 07-10h 22%, 11-15h 42%, 16-19h 27%, 20-23h 6%, 00-06h 2%; weekend 26% ->
  daytime, en-route/town-centre profile (rural/small-town Scotland).
* `pkc_stations.parquet`: 36 rows (35 located; `50244 Broxden Park & Ride` (15 sessions, 2017) is not in the
  2023 layer or feed).

## Known issues / caveats
* 3.1% sessions <= 0.05 kWh and 1.8% with zero duration (failed starts) - drop for calibration.
* `_id` restarts per file -> session_id is `<file>#<_id>`.
* Only 2016-2019; PKC has not published later years (checked Hub + Open Data Scotland index 2026-09-10).
* The layer is the 2023 network (45 points); a few 2016-19 chargers were replaced (matched via CPS feed where
  the id survived).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only cps,pkc
```
