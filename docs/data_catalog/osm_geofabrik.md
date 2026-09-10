---
id: osm_geofabrik_greater_london
title: OpenStreetMap Greater London extract (Geofabrik PBF)
provider: Geofabrik GmbH (data © OpenStreetMap contributors)
url: https://download.geofabrik.de/europe/united-kingdom/england/greater-london.html
download_url: https://download.geofabrik.de/europe/united-kingdom/england/greater-london-latest.osm.pbf
licence: ODbL 1.0 (© OpenStreetMap contributors)
status: observed
retrieved: 2026-09-10
size_mb: 128.7
spatial_unit: raw OSM elements (nodes / ways / relations), EPSG:4326
temporal: static snapshot, OSM data timestamp 2026-09-09T20:21:20Z (file published 2026-09-10 04:57 UTC)
script: src/chargescape/data/osm.py
raw_path: data/raw/osm/
---

## What it is
Daily Geofabrik extract of the full OpenStreetMap database clipped to Greater London (with a small buffer
around the administrative boundary). It is the archived, checksum-verified raw source behind the OSM
context layers in this project; every derived OSM artefact (drive graph, POIs, landuse) can be rebuilt
from it offline with `--source pbf`.

* `data/raw/osm/greater-london-latest.osm.pbf` — 128,657,116 bytes, md5 `b7f24e87bf3f9c73577f4eac579403bc`
  (verified against the published `.md5`).
* `data/raw/osm/greater-london-latest.meta.json` — URL, size, md5, `Last-Modified` header, retrieval time,
  and the OSM replication timestamp read from the PBF header (`osmosis_replication_timestamp`).
* `data/raw/osm/overpass_cache/` — osmnx HTTP cache used only by the Overpass backend (empty today).

## Fields used
Raw OSM tags. The pipeline reads: `highway`, `area`, `access`, `motor_vehicle`, `motorcar`, `service`,
`oneway`, `maxspeed`, `lanes`, `name`, `ref`, `bridge`, `tunnel`, `junction`, `width`, `est_width`
(road network, via osmnx's `useful_tags_way`), and `amenity`, `shop`, `tourism`, `leisure`, `office`,
`building`, `landuse`, `name`, `brand`, `operator`, `parking`, `capacity` (POIs / landuse).

## Known issues / caveats
* The extract is refreshed daily; `latest` is a moving target, so the md5 changes every day. The download
  is idempotent (existing verified file is kept) — pass `--force` to refresh, and record the new md5.
* Geofabrik clips with a buffer polygon, so elements just outside Greater London are present; downstream
  layers filter to the OSM boundary relation 175342 (see `osm_drive_graph.md`, `osm_pois.md`).
* Public extracts carry no user/changeset metadata (GDPR-stripped), which is irrelevant here.
* Parsed with `pyosmium 4.3.1` (already in the environment); no `osmium` CLI is required.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.osm --only pbf            # download + md5 verify (~6 s at ~20 MB/s)
PYTHONPATH=src python -m chargescape.data.osm --only pbf --force    # refresh to today's extract
```
