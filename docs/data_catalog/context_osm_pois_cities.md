---
id: context_osm_pois_cities
title: OpenStreetMap context around charging stations - POIs, major roads and railway stations (Dundee, Perth & Kinross, Palo Alto, Boulder; same features for London)
provider: OpenStreetMap contributors, via the Overpass API (overpass-api.de; mirrors overpass.private.coffee / overpass.kumi.systems as fallback). London re-uses the Geofabrik-derived tables built by chargescape.data.osm and the TfL/NaPTAN station list built by chargescape.data.transit
url: https://wiki.openstreetmap.org/wiki/Overpass_API
download_url: https://overpass-api.de/api/interpreter - every query text is stored next to its cached response in data/raw/context/<city>/<name>.meta.json
licence: ODbL 1.0 (Open Database License) - attribution "(c) OpenStreetMap contributors" required; the derived feature table is a "produced work"
status: observed
retrieved: 2026-09-10
size_mb: 26.8 (raw Overpass JSON, four cities; 0.3 MB of it are the superseded per-group Dundee files of the first attempt)
spatial_unit: point (charge point / London site); counts within 300 m and 800 m buffers, distances in metres, in a local metric CRS (EPSG:27700 UK, 26910 Palo Alto, 26913 Boulder)
temporal: snapshot of the live OSM database on 2026-09-10 (Overpass `timestamp_osm_base` 19:31-19:36 UTC, per .meta.json); London POIs / roads from the Geofabrik extract with OSM timestamp 2026-09-09, TfL stations retrieved 2026-09-10
script: src/chargescape/features/station_context.py
raw_path: "data/raw/context/{dundee,pkc,palo_alto,boulder}/  (London: data/interim/osm/pois.parquet, london_major_roads.parquet, data/interim/transit/tfl_stations.parquet)"
---

## What it is
The OSM part of the station-level feature table `data/processed/station_features.small.parquet` (7,108 rows: one per
charge point with >= 60 active days in Dundee (90), Perth & Kinross / pkc (35), Palo Alto (34), Boulder (45), plus one
per London site of `data/processed/charging_sites.parquet` (6,904)). Every city gets the *same* features from the *same*
tag lists, so a model fitted on the four cities with session logs can be applied to London.

For the four session cities the script sends **two Overpass queries per city** (bbox = metric bounding box of the
city's stations, padded): `pois` - one union of five `nwr` selectors (one per OSM key, regex also matching
multi-valued tags such as `cafe;bar`) covering all nine POI groups, 2 km padding, `out center` (ways/relations reduced
to their centroid, like the London table); `roads_rail` - `highway=motorway|trunk|primary|secondary` ways with
`out geom` in a 15 km-padded box, followed by `railway=station|halt` (all station types) with `out center` in a
40 km-padded box (Boulder has no passenger rail; rural Perth & Kinross sites are far from a station). Group
membership is assigned client-side from the tags, so one element can sit in several groups (as in the London table).

Overpass etiquette (the first attempt of this task was rate-limited): before every live query the client polls
`/api/status` and sleeps until this IP has a free slot plus 3 s (handles "N slots available now",
"Slot available after ..., in N seconds" and the all-slots-running case); a lock keeps exactly one query in flight;
`[timeout:180]`; on HTTP 429/502/503/504 or an Overpass "runtime error" remark it backs off 30/60/120 s, then moves to
the next mirror; every response is cached as `data/raw/context/<city>/<name>.json` (+ `.meta.json` with query, bbox,
endpoint, OSM base timestamp, size, duration) and never re-fetched. The 2026-09-10 run needed 8 live queries
(1.9-14 s each, 0.9-11 MB), none was rejected.

For London nothing is fetched: POIs come from `data/interim/osm/pois.parquet`, roads from
`data/interim/osm/london_major_roads.parquet` (edges of the osmnx drive graph, `highway` may be `a|b`) and rail from
`data/interim/transit/tfl_stations.parquet` (740 tube / DLR / Overground / Elizabeth line / tram / National Rail
stations, incl. some outside Greater London).

Tag groups (identical for all cities; `POI_GROUPS` in the script):

| group | OSM tags | London source categories |
|---|---|---|
| food | amenity = restaurant, cafe, fast_food, pub, bar | food |
| retail | shop = supermarket, mall, department_store, convenience, doityourself, furniture, electronics | retail + supermarket |
| hotel | tourism = hotel, hostel, guest_house, motel | hotel |
| leisure | leisure = fitness_centre, sports_centre, stadium; amenity = cinema, theatre; tourism = attraction, museum | leisure |
| parking | amenity = parking (+ the `capacity` tag, summed) | parking |
| fuel | amenity = fuel | fuel |
| office | office = * (any value) | office minus `building_office` |
| health_edu | amenity = hospital, clinic, university, college, school | health + education |
| car | shop = car, car_repair; amenity = car_wash, car_rental | car minus `taxi` |
| roads | highway = motorway, trunk -> `dist_motorway_m`; highway = primary, secondary -> `dist_primary_m` | london_major_roads |
| rail | railway = station, halt (all `station=*` types) -> `dist_rail_m` | tfl_stations |

Elements per city after group assignment (2026-09-10 run; a multi-tagged element counts in each of its groups):

| city | food | retail | hotel | leisure | parking | fuel | office | health_edu | car | motorway/trunk ways | primary/secondary ways | rail stations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dundee | 467 | 172 | 35 | 122 | 2,043 | 15 | 165 | 76 | 85 | 315 | 1,148 | 31 |
| pkc | 472 | 152 | 177 | 116 | 1,218 | 32 | 171 | 110 | 111 | 943 | 4,367 | 192 |
| palo_alto | 391 | 72 | 37 | 87 | 1,572 | 23 | 310 | 101 | 51 | 1,777 | 12,619 | 217 |
| boulder | 413 | 67 | 86 | 101 | 1,261 | 30 | 267 | 77 | 75 | 1,577 | 5,967 | 76 |
| london | 26,570 | 8,298 | 1,693 | 2,969 | 17,715 | 526 | 7,922 | 4,374 | 1,690 | 9,027 edges | 39,429 edges | 740 |

(Road counts for the four cities are OSM ways inside the 15 km-padded box; the rail count is inside the 40 km box, so
it includes e.g. Glasgow for pkc and the BART / VTA network for Palo Alto.)

## Fields used
`poi_<group>_300`, `poi_<group>_800` (integer counts of centroids inside the radius), `parking_capacity_300/800` (sum
of the parsed `capacity` of the counted car parks; untagged car parks contribute 0), `dist_motorway_m`,
`dist_primary_m`, `dist_rail_m` (Euclidean distance to the nearest way / station point in the metric CRS),
`poi_edge_flag` (London only: the 800 m buffer leaves the Greater London boundary the POI table is clipped to; 358
sites, their counts are lower bounds). Per-city build metadata: `data/interim/context/<city>_build_info.json`.

## Known issues / caveats
* **Definition choices, resolved in favour of cross-city consistency**: `shop=clothes` is *not* counted anywhere
  (the London POI table does not carry it); `building=office` (London subcategory `building_office`, 1,766 rows)
  and `amenity=taxi` (266 rows) are dropped from the London `office` / `car` groups because the four-city query
  uses `office=*` and `shop=car|car_repair` + `amenity=car_wash|car_rental` only.
* Ways/relations count as one point at their centroid, so a 300 m circle can miss a large car park or campus whose
  centroid lies just outside it; centroids of London polygons were computed in EPSG:27700 by data/osm.py,
  Overpass `out center` uses the bbox centre of the way - equivalent at this scale.
* `capacity` is tagged on a minority of car parks (London 16.6 %), so `parking_capacity_*` is "tagged capacity",
  not capacity; it is 0 for 72% of all rows at 300 m.
* Distances are computed inside the padded boxes, so a value above the padding is an upper bound: one pkc station
  has `dist_motorway_m` = 19.3 km (> 15 km pad); all `dist_rail_m` values are below the 40 km pad (Boulder
  21.9-29.9 km to the Denver-area RTD stations - effectively a city constant). London roads come from the drive
  graph clipped to Greater London, so the M25 (just outside) is absent and `dist_motorway_m` reaches 10.8 km for
  outer sites; London POIs are clipped to the boundary (see `poi_edge_flag`).
* OSM completeness differs by place: Dundee has 2,043 mapped car parks in an 8 x 7 km box (median 116 within
  800 m of a charger vs 28 in London), Palo Alto / Boulder retail tagging is sparse. Counts are comparable in
  kind, not necessarily in level - a city fixed effect or per-city scaling is advisable.
* Station coordinates in Dundee are partly postcode centroids (~100 m error) and Boulder's are Nominatim address
  geocodes - fine for 800 m, noisy for 300 m counts.
* `data/raw/context/dundee/poi_food.json` and `poi_retail.json` are the per-group responses of the interrupted
  first attempt (same bbox, OSM base 15:16 UTC); they are superseded by `pois.json` and not read by the script.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.features.station_context                 # all five cities, uses caches
PYTHONPATH=src python -m chargescape.features.station_context --cities dundee --force   # rebuild one city
```
Outputs: `data/interim/context/<city>_station_features.parquet`, `<city>_build_info.json`,
`context_build_report.json`, and the merged `data/processed/station_features.small.parquet` (0.7 MB).
Deleting a `data/raw/context/<city>/*.json` file triggers exactly one new Overpass query for that layer.
