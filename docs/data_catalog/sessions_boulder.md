---
id: sessions_boulder
title: City of Boulder, CO - Electric Vehicle Charging Station Data (transactions, Jan 2018 - Nov 2023)
provider: City of Boulder (Facilities & Fleet / Community Vitality), Colorado, USA - ChargePoint export
url: https://open-data.bouldercolorado.gov/datasets/95992b3938be4622b07f0b05eba95d4c_0
download_url: https://open-data.bouldercolorado.gov/api/download/v1/items/95992b3938be4622b07f0b05eba95d4c/csv?layers=0 (redirects to a signed CDN file); FeatureServer https://services.arcgis.com/ePKBjXrBZ2vEEgWd/arcgis/rest/services/Electric_Vehicle_Charging_Station_Data/FeatureServer/0 (table, maxRecordCount 1000 - script falls back to paging)
licence: CC0 1.0 ("CC0 License" in the Hub item licenseInfo, verified 2026-09-10)
status: observed
retrieved: 2026-09-10
size_mb: 23 (raw CSV); 3.3 (parquet)
spatial_unit: street address (no coordinates in source) -> geocoded to points with Nominatim (flagged)
temporal: per transaction, 2018-01-01 .. 2023-11-30 (local Mountain time); dataset last modified 2023-12-06, not updated since
script: src/chargescape/data/sessions_open.py (fetch_boulder / harmonise_boulder)
raw_path: data/raw/sessions_open/boulder/
---

## What it is
ChargePoint transactions at all city-owned public EV chargers (recreation centres, downtown garages, civic
buildings, airport, reservoir; mostly Level 2): `Station_Name, Address, City, State, Zip, Start_Date___Time,
Start_Time_Zone, End_Date___Time, End_Time_Zone, Total_Duration (hh:mm:ss), Charging_Time (hh:mm:ss),
Energy (kWh), GHG_Savings, Gasoline_Savings, Port_Type, ObjectID, ObjectId2`. Data dictionary:
https://webappsprod.bouldercolorado.gov/opendata/ev_datadictionary.csv. No user id.

## Fields used
station_id/name = `Station_Name` (50 names at 24 distinct addresses); start/end (mixed `m/d/Y H:M` and, from
June 2023, ISO `Y-m-d H:M:S` - both parsed); duration_min = total plugged-in time, charging_min = actual
charging; energy_kwh; port_type (Level 2 / Level 1 / DC Fast); postcode = ZIP; session_id = ObjectID.
**Coordinates**: the 27 distinct addresses were geocoded once with Nominatim (structured query, 1 req/s,
cached in `data/raw/sessions_open/boulder/geocode_nominatim.json` with the matched `display_name`), all 24
resulting points fall inside the city extent; `lat_source = nominatim_geocode`.

## Harmonised outputs (2026-09-10 run)
* Source table holds **two overlapping loads**: 148,136 rows but only 77,942 distinct ObjectIDs and 56,046
  exact duplicate rows -> de-duplicated on all content columns to **92,090 transactions, 50 stations, 100%
  located**; per year 7.4k (2018), 11.8k, 5.6k (2020), 12.0k, 20.6k, 34.8k (2023 to Nov).
* Median 5.7 kWh; median dwell 87 min, median charging 77 min. 18% of transactions deliver <= 0.05 kWh
  (failed/aborted plug-ins; share stable 14-20%/year) - filter before calibration.
* Arrivals: peak 17h (8.4%) but broad daytime plateau - 07-10h 27%, 11-15h 38%, 16-19h 27%, 20-23h 4%,
  00-06h 5%; weekend 29% (rec-centre / downtown-garage destination profile).
* 7.2% rows still share (station, start, kWh): pairs with identical timestamps and 0 kWh (port retries) -
  harmless once zero-kWh rows are dropped.

## Known issues / caveats
* Geocoded, not surveyed, coordinates: two station names at the same address (ST1/ST2, or the garage renamed
  `COMM VITALITY` -> `MUNICIPAL SC`) collapse to one point; treat the *address* as the site.
* `Start_Time_Zone` mixes MST/MDT - timestamps are local wall-clock, kept naive with tz=America/Denver.
* No power rating per port; Level 2 in Boulder is 6.2-7.2 kW typical (not imputed).
* Series ends Nov 2023 (Hub item not refreshed).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only boulder          # add --no-geocode to skip Nominatim
```
