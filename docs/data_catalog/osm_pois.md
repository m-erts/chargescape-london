---
id: osm_pois_london
title: OpenStreetMap points of interest and commercial/industrial/retail landuse, Greater London
provider: OpenStreetMap contributors (extracted with pyosmium from the Geofabrik PBF; osmnx/Overpass backend available)
url: https://wiki.openstreetmap.org/wiki/Map_features
download_url: derived — see osm_geofabrik.md (backend pbf) or https://overpass-api.de/api/interpreter (backend overpass)
licence: ODbL 1.0 (© OpenStreetMap contributors)
status: observed
retrieved: 2026-09-10
size_mb: 2.8 (pois.parquet) + 2.6 (landuse.parquet)
spatial_unit: point (POI; polygons reduced to centroid) / polygon (landuse), EPSG:4326
temporal: static, OSM snapshot 2026-09-09T20:21:20Z
script: src/chargescape/data/osm.py (fetch_pois, fetch_landuse)
raw_path: data/raw/osm/greater-london-latest.osm.pbf
---

## What it is
Activity-generator and land-use context for charging demand features. Every OSM node, way (open ways as
lines, closed ways and multipolygon relations as assembled areas) carrying one of the tag rules below is
matched against the category table; polygons/lines are reduced to their centroid (computed in EPSG:27700,
stored in EPSG:4326) and only features whose point falls inside the Greater London boundary are kept.
`amenity=charging_station` is deliberately **not** included (covered by the chargers module).

`data/interim/osm/pois.parquet` — 73,789 rows (41,926 from polygons, 31,844 from nodes, 19 from lines;
104 OSM elements legitimately appear in two categories, e.g. a pub that is also `tourism=attraction`).

| category | tag rule | rows | main subcategories |
|---|---|---:|---|
| food | amenity ∈ restaurant, cafe, fast_food, pub, bar | 26,570 | restaurant 9,088 · cafe 6,828 · fast_food 6,247 · pub 3,165 · bar 1,242 |
| parking | amenity=parking (parking_entrance excluded) | 17,715 | `parking_type`: surface 6,005 · street_side 2,846 · lane 617 · underground 291 · multi-storey 213 · untagged 7,674; `capacity` on 2,948 (median 6, sum 86,343 spaces) |
| office | office=* (any) or building=office | 9,688 | estate_agent 2,318 · building_office 1,766 · company 1,077 · yes 846 · lawyer 586 · accountant 431 · diplomatic 260 · government 198 · ngo 178 · charity 167 · coworking 142 (+ long tail of free-text values) |
| retail | shop ∈ mall, department_store, convenience, doityourself, furniture, electronics | 7,028 | convenience 5,524 · furniture 579 · doityourself 402 · electronics 301 · department_store 135 · mall 87 |
| education | amenity ∈ university, college, school | 3,679 | school 3,264 · college 227 · university 188 |
| leisure | leisure ∈ fitness_centre, sports_centre, stadium; amenity ∈ cinema, theatre; tourism ∈ attraction, museum | 2,969 | fitness_centre 996 · sports_centre 929 · attraction 372 · theatre 274 · museum 219 · cinema 135 · stadium 44 |
| car | shop ∈ car, car_repair; amenity ∈ car_wash, car_rental, taxi | 1,956 | car_repair 917 · car 382 · taxi 266 · car_wash 258 · car_rental 133 |
| hotel | tourism ∈ hotel, hostel, guest_house, motel | 1,693 | hotel 1,492 · hostel 118 · guest_house 78 · motel 5 |
| supermarket | shop=supermarket | 1,270 | brands: Lidl 120 · Co-op Food 97 · Sainsbury's 94 · Waitrose 58 · Aldi 55 · Tesco 38 |
| health | amenity ∈ hospital, clinic | 695 | clinic 498 · hospital 197 |
| fuel | amenity=fuel | 526 | brands: Esso 124 · Shell 123 · BP 88 · Texaco 38 |

`data/interim/osm/landuse.parquet` — 9,017 polygons with `landuse ∈ {commercial, industrial, retail}` that
intersect Greater London (not clipped): retail 5,284 (30.2 km²), commercial 1,906 (15.6 km²), industrial
1,827 (49.3 km²); `area_m2` computed in EPSG:27700. Median polygon 2,586 m², largest 1.57 km².

## Fields used
POIs: `osm_id` (`node/123`, `way/456`, `relation/789`), `element_type`, `category`, `subcategory` (matched
tag value; `building_office` for building=office; raw `office=*` value for offices), `name`, `brand`,
`operator`, `parking_type` (`parking=*`, parking only), `capacity` (numeric, parking only), `source_geom`
(point / polygon / line), `geometry` (Point). Landuse: `osm_id`, `element_type`, `landuse`, `name`,
`area_m2`, `geometry` (MultiPolygon).

## Known issues / caveats
* OSM completeness and tagging are uneven: 95 % of parking features have no name and 83 % no `capacity`;
  `office=*` values are free text (normalise before using as a factor — `estate_agent`, `company`, `yes`,
  `lawyer`, `accountant` cover ~55 %). Convenience stores (5,524) dominate "retail".
* Multi-valued tags (`amenity=cafe;restaurant`) match on any value; the first matching value becomes the
  subcategory. Only the exact values listed are matched (e.g. `shop=car_parts` is not "car").
* Centroids of large polygons (universities, hospitals, parks-with-stadiums) can sit away from entrances;
  use the landuse polygons or the original geometry when a footprint matters.
* Backend `overpass` issues one `ox.features_from_polygon` query per category (plus one for landuse) with
  5 s pauses, osmnx's rate-limit check, a 300 s server budget and retries on 429/504; on 2026-09-10 Overpass
  was degraded so the PBF backend (single pyosmium pass, ~19 s) produced this build. Schema is identical.
* Two OSM areas failed geometry assembly at the extract edge and were skipped (`geom_errors: 2`).

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.osm --only pois landuse --source pbf --force        # ~40 s offline
PYTHONPATH=src python -m chargescape.data.osm --only pois landuse --source overpass --force   # live Overpass
```
