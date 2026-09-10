---
id: chargepoints_osm
title: OpenStreetMap charging stations, Greater London (Overpass extract)
provider: OpenStreetMap contributors (queried via overpass-api.de)
url: https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dcharging_station
download_url: https://overpass-api.de/api/interpreter (query embedded in the script as OVERPASS_QUERY)
licence: ODbL 1.0 (Open Database License) – attribution "© OpenStreetMap contributors" required
status: observed
retrieved: 2026-09-10
size_mb: 0.31 (raw Overpass JSON) / 0.13 (GeoParquet)
spatial_unit: point (OSM nodes; centroid of ways/relations via `out center`)
temporal: snapshot of the live OSM database, 2026-09-10 (exact base timestamp in column `osm_data_timestamp`)
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/osm_charging_stations_overpass.json
---

## What it is
All OSM features tagged `amenity=charging_station` inside the Greater London administrative area
(OSM relation 175342, `boundary=administrative`, `admin_level=5`; Overpass area id 3600175342).
One Overpass query (`[out:json][timeout:180]`, nodes + ways + relations, `out center tags`) returned
**1,303 elements: 1,238 nodes, 65 ways, 0 relations** (Overpass base timestamp 2026-09-10T14:40:51Z).
A feature is whatever the mapper chose: usually one physical charging post or lamp-column socket, sometimes a
whole hub/car-park (the 65 ways; their centroid is used). Output:
`data/interim/chargepoints/osm_charging_stations.parquet` (GeoParquet, EPSG:4326, 1,303 rows, 44 columns,
`source = "osm"`). Bbox (W,S,E,N): -0.4927, 51.3190, 0.1916, 51.6699.

## Fields used
- `osm_type`, `osm_id`, `lat`, `lon`, `geometry` (WGS84 point)
- plain tags copied to columns (":" -> "_"): `name`, `operator`, `brand`, `network`, `ref`, `capacity`,
  `charging_station_output`, `maxpower`, `fee`, `access`, `opening_hours`, `motorcar`, `bicycle`, `check_date`,
  `authentication_app`, `authentication_membership_card`, `authentication_none`, `payment_contactless`, `payment_app`
- every `socket:<type>` count present in the data becomes `socket_<type>` (int) and every `socket:<type>:output`
  becomes `socket_<type>_output_kw` (float kW). Types seen: `type2`, `type2_cable`, `type2_combo`, `chademo`,
  `tesla_supercharger`, `tesla_supercharger_ccs`, `type1`, `type1_cable`, `bs1363` (features carrying the tag:
  type2 115, type2_combo 41, chademo 22, type1 15, tesla_supercharger 9, tesla_supercharger_ccs 9, type1_cable 3, bs1363 2).
- derived: `max_power_kw` = max of `charging_station:output`, `maxpower`, all `socket:*:output` (parsed from strings
  such as "22 kW", "7.4kW", "50000 W", "2x22kW"); `n_sockets` = sum of `socket:*` counts; `capacity_int`
- `tags_json` = full tag dictionary (JSON string) so nothing is lost
- `source` = "osm", `osm_data_timestamp`

## Known issues / caveats
- **Power is rarely tagged**: only 7.8 % of features have any power information (`max_power_kw`); of those 102,
  42 are <8 kW, 5 are 8–22 kW, 20 are 22–50 kW, 9 are 50–150 kW and 26 are ≥150 kW (35 features ≥50 kW in total). Do not compute rapid shares
  from OSM alone – use the DfT tables (chargepoints_dft_evci) for that.
- Operator coverage is decent but incomplete: 67.9 % have `operator`, 73.5 % have operator|brand|network.
  Top values: Source London 225, Believ 93, ubitricity 76, Zest 62, Pod Point 52, BP Pulse 39, char.gy 37,
  TotalEnergies 32, Shell Recharge 27, Allego 27, Tesla 19, eVolt 19.
- `capacity` is present on 64.4 % (sum 3,242 sockets over 879 features, median 2); `socket:*` counts on only 11.4 %.
  `fee` on 24.6 % (yes 313 / no 8); `access` on 14.7 % (yes 100, customers 33, private 28, residents 22, no 4,
  permissive 3) – roughly 4 % of features are explicitly not public and should be filtered; `check_date` on 9 %.
- **Massive under-coverage of on-street lamp-post chargers**: lamp-post style operators (ubitricity, char.gy,
  Connected Kerb, Shell Recharge, Trojan, SureCharge, Siemens, City EV) are 14.3 % of OSM features versus 42 % of
  devices in the 2021 NCR snapshot – and London has c. 31k public chargers per DfT (July 2026) versus 1.3k OSM
  features. OSM is therefore a partial, hub-biased sample, not a census. Only 47 % of OSM points have an NCR-2021
  device within 50 m (and 13 % of NCR devices have an OSM feature nearby).
- Unit of record is inconsistent (single socket vs post vs site); ways are represented by centroids.
- No exact duplicate coordinates within the extract. The area filter already clips to Greater London; the bbox
  filter in the script is a no-op safety net.
- Overpass etiquette: a single query, `timeout:180`, custom User-Agent; the raw response is cached in `raw_path`, so
  reruns never hit the API unless the raw file is deleted.

## How to reproduce
```bash
PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_osm; fetch_osm()"
# or the whole supply-side pipeline:
PYTHONPATH=src python -m chargescape.data.chargepoints
```
Delete `data/raw/chargepoints/osm_charging_stations_overpass.json` (and the parquet) to force a fresh Overpass query.
