---
id: osm_drive_graph_london
title: Greater London drivable road network (osmnx MultiDiGraph)
provider: OpenStreetMap contributors (built with osmnx 2.1.1 from the Geofabrik extract; Overpass backend available)
url: https://osmnx.readthedocs.io/
download_url: derived — see osm_geofabrik.md (backend pbf) or https://overpass-api.de/api/interpreter (backend overpass)
licence: ODbL 1.0 (© OpenStreetMap contributors)
status: observed
retrieved: 2026-09-10
size_mb: 178 (GraphML) + 31.2 (edges parquet) + 5.8 (nodes parquet) + 5.4 (major roads parquet) + 17 (filtered OSM XML)
spatial_unit: road link (directed edge) / intersection or dead end (node), EPSG:4326, lengths in metres
temporal: static, OSM snapshot 2026-09-09T20:21:20Z
script: src/chargescape/data/osm.py (build_drive_graph)
raw_path: data/raw/osm/greater-london-latest.osm.pbf
---

## What it is
The osmnx `network_type="drive"` graph for Greater London (OSM boundary relation 175342, 1,594.7 km²,
geocoded via Nominatim and cached at `data/interim/osm/greater_london_boundary.parquet`), with simplified
topology, per-edge speeds and travel times.

| artefact | content |
|---|---|
| `data/interim/osm/london_drive.graphml` | full graph, load with `ox.load_graphml(path)` |
| `data/interim/osm/london_drive_nodes.parquet` | 130,755 nodes (GeoParquet, Point) |
| `data/interim/osm/london_drive_edges.parquet` | 304,267 directed edges (GeoParquet, LineString) |
| `data/interim/osm/london_major_roads.parquet` | 48,453 edges with highway ∈ {motorway, trunk, primary, secondary} (4,311 km directed) — for "distance to major road" features |
| `data/interim/osm/london_drive_highways.osm.bz2` | intermediate: drivable ways + nodes filtered out of the PBF (149,140 ways) |
| `data/interim/osm/osm_build_report.json` | counts, timings, backend used |

**Headline numbers (2026-09-10 build):** 130,755 nodes · 304,267 directed edges · 28,948 km directed /
15,719.7 km undirected (two-way streets are two edges) · mean edge speed 35.7 km/h · 824 vehicle-hours of
free-flow travel time summed over all directed edges. Highway classes (by `highway_primary`): residential
208,975 · primary 28,512 · tertiary 28,363 · unclassified 15,568 · secondary 10,906 · trunk 8,961 ·
trunk_link 978 · living_street 915 · primary_link 607 · tertiary_link 197 · secondary_link 118 ·
motorway_link 75 · motorway 63 · busway 17 · road 12. Build time 67 s (graph) / 90 s total on an
Apple-silicon laptop, 16 GB RAM.

**How it is built (backend `pbf`, used for this build).** pyosmium filters the PBF with a Python replica of
osmnx's *drive* Overpass filter (drops footway/cycleway/path/steps/service/track/construction…, `area=yes`,
`access=private`, `motor_vehicle=no`, `motorcar=no`, and `service=alley|driveway|parking_aisle|…`; Overpass
`!~` is an unanchored regex and is replicated as such so the two backends agree). The filtered XML is loaded
with `ox.graph_from_xml`, then post-processed exactly as `ox.graph_from_polygon` does: truncate to a 500 m
buffered boundary → largest weakly connected component → `simplify_graph` → truncate to the boundary →
largest component → `street_count` computed on the buffered graph. `ox.routing.add_edge_speeds` converts
`maxspeed` (mph → km/h) and imputes the mean speed of the same highway class where the tag is missing
(82,833 edges = 27 %); `add_edge_travel_times` adds seconds. Backend `overpass` (`--source overpass`) runs
`ox.graph_from_polygon(boundary, network_type="drive", simplify=True)` on live data with the same
post-processing; `auto` probes Overpass and falls back to the PBF.

## Fields used
Nodes: `osmid`, `x`, `y` (lon/lat), `street_count`, `highway` (e.g. traffic_signals, crossing), `junction`,
`ref`, `railway`, `geometry`.
Edges: `u`, `v`, `key`, `osmid`, `highway`, `highway_primary` (first value), `name`, `ref`, `maxspeed`
(raw tag), `speed_kph`, `travel_time` (s), `length` (m), `oneway`, `reversed`, `lanes`, `bridge`, `tunnel`,
`junction`, `service`, `access`, `width`, `est_width`, `area`, `is_major`, `geometry`. Attributes that
osmnx merged during simplification are lists in the GraphML and pipe-joined strings (`"a|b"`) in parquet.

## Known issues / caveats
* Overpass was degraded on 2026-09-10 (tiny probe queries returned 504, the graph query died with a
  ConnectionError after 12 min), so the archived PBF snapshot (< 24 h old) was used. Both backends produce
  the same schema; only data recency can differ.
* Median speed is 32 km/h (20 mph) for residential, tertiary and even secondary roads — London's 20 mph
  zones dominate the tag distribution; imputed speeds inherit that. Treat travel times as free-flow.
* Service roads are excluded by osmnx's *drive* filter; for last-100 m access modelling rebuild with
  `network_type="drive_service"` (Overpass) or extend `_drive_way_ok`.
* `london_major_roads.parquet` uses `is_major = any(highway in MAJOR)`, so 11 merged edges whose highway
  list mixes a major class with residential/tertiary are included.
* Directed kilometres double count two-way streets; use the undirected figure (15,720 km, consistent with
  TfL's ~14,800 km of London roads) for network-length statements.

## How to reproduce
```bash
PYTHONPATH=src python -m chargescape.data.osm --only boundary graph --source pbf --force   # ~2 min offline
PYTHONPATH=src python -m chargescape.data.osm --only graph --source overpass --force       # live data, needs a healthy Overpass
```
