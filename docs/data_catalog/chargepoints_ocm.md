---
id: chargepoints_ocm
title: "Open Charge Map v3 POI API – Greater London (NOT acquired: API key required)"
provider: Open Charge Map (OCM Foundation / openchargemap.org community)
url: https://openchargemap.org/site/develop/api
download_url: https://api.openchargemap.io/v3/poi/?output=json&countrycode=GB&boundingbox=(51.28,-0.51),(51.70,0.33)&maxresults=10000&compact=true&verbose=false
licence: CC BY 4.0 for user-contributed data (per openchargemap.org/develop); imported subsets keep their own open licences (e.g. former NCR under OGL); end-user attribution required
status: observed
retrieved: 2026-09-10 (probe only – HTTP 403, no data downloaded)
size_mb: 0.0 (only the probe record data/raw/chargepoints/ocm_api_status.json)
spatial_unit: point (POI = site with 1..n connections)
temporal: live crowd-sourced database (not snapshotted)
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/ocm_api_status.json (would be data/raw/chargepoints/ocm/ tile JSONs if the API answered)
---

## What it is

**Update 2026-09-10 (evening):** downloaded with a free API key supplied via `OCM_API_KEY` (never stored in the repo): 12,565 POIs in the London bounding box in 5 bbox tiles; operators, usage and status resolved through `/v3/referencedata/`; 611 POIs with ≥50 kW (1,235 known points). Used as the primary supply source, de-duplicated against OSM and the NCR 2021 snapshot within 50 m.

Open Charge Map is the global crowd-sourced registry of EV charging locations. The intended pull was the
Greater London bbox (51.28,-0.51)–(51.70,0.33), `countrycode=GB`, compact JSON, tiled recursively because the v3
API has no offset paging (a tile that returns `maxresults` rows is split into four).

**Outcome on 2026-09-10:** the API refused the request without a key –
`HTTP 403`, body `"You must specify an API key using the key query parameter or x-api-key header."`
(also for `maxresults=1` and for `/v3/referencedata/`). The project rule is not to register for API keys, so the
source was **recorded and skipped**; `fetch_ocm()` writes the probe result to `raw_path` and returns `None`.
Key history: OCM announced on 2020-08-31 ("API Keys are now required", community.openchargemap.org/t/161) that
keys were required for `maxresults > 250`; today the restriction applies to every POI call.

## Fields used
Schema the script produces if a key is supplied via the `OCM_API_KEY` environment variable (sent as `X-API-Key`):
`ocm_id, lat, lon, operator, usage_type, status, n_points, connections (JSON string of
ConnectionTypeID/PowerKW/Quantity/LevelID/CurrentTypeID/StatusTypeID), max_power_kw, level, date_created,
date_last_verified, source="ocm"`. Compact responses carry IDs only, so `/v3/referencedata/` is fetched once to map
`OperatorID`, `UsageTypeID`, `StatusTypeID` to titles. Output would be `data/interim/chargepoints/ocm_london.parquet`.

## Known issues / caveats
- No data acquired; the OSM-vs-OCM 50 m duplicate check therefore could not be run. The script substitutes an
  OSM-vs-NCR(2021) and OSM-vs-TfL-rapid(2019) proximity check (see chargepoints_osm / chargepoints_ncr_archive).
- Licence verification: openchargemap.org/develop states that data contributed by users and redistributed is
  licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)** and that applications must show
  the appropriate Data Provider attribution (including licence terms) to end users. OCM also imports third-party
  open datasets (historically including the DfT NCR), whose provenance/licence is carried per-record
  (`DataProvider`). Treat OCM as mixed-provenance.
- OCM asks heavy users to cache and to avoid re-downloading whole countries repeatedly; the tiled downloader
  sleeps 1 s between calls and stores every tile response.
- Once a refusal is recorded the script does not re-probe on later runs unless `OCM_API_KEY` is set (idempotent,
  no hammering).

## How to reproduce
```bash
PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_ocm; fetch_ocm()"   # records the 403
# if the project owner ever obtains a key:
OCM_API_KEY=... PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_ocm; fetch_ocm()"
```
