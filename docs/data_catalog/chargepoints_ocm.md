---
id: chargepoints_ocm
title: "Open Charge Map v3 POI API, Greater London"
provider: Open Charge Map (OCM Foundation / openchargemap.org community)
url: https://openchargemap.org/site/develop/api
download_url: "https://api.openchargemap.io/v3/poi/?output=json&countrycode=GB&boundingbox=(51.28,-0.51),(51.70,0.33)&maxresults=10000&compact=true&verbose=false"
licence: "CC BY 4.0 for user-contributed data (per openchargemap.org/develop); imported subsets keep their own open licences (e.g. former NCR under OGL); end-user attribution required"
status: observed
retrieved: "2026-09-10"
size_mb: "0.45 (GeoParquet, 12,565 POIs); raw tile JSON kept locally, not committed"
spatial_unit: "point (POI = site with 1..n connections)"
temporal: "live crowd-sourced database, snapshot of 2026-09-10; latest verification date in the snapshot 2026-08-13"
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/ocm/
---

## What it is

Open Charge Map is the global crowd-sourced registry of EV charging locations. It is the primary supply
source of this project: 12,565 POIs in the Greater London bounding box, of which 611 have a connection of
50 kW or more. After de-duplication within 50 m against OpenStreetMap and the 2021 National Chargepoint
Registry snapshot, Open Charge Map contributes 12,519 of the 13,174 charging sites.

## How it was acquired

The v3 API requires a key for every POI call. A free key is read from the environment variable
`OCM_API_KEY` and sent as the `X-API-Key` header. The key is never written to the repository, to logs or to
the cached responses.

The API has no offset paging, so the bounding box (51.28,-0.51) to (51.70,0.33) is tiled recursively: a tile
that returns `maxresults` rows is split into four. Compact responses carry identifiers only, so
`/v3/referencedata/` is fetched once to resolve `OperatorID`, `UsageTypeID` and `StatusTypeID` to titles.

Without a key `fetch_ocm()` records the refusal (HTTP 403) in `data/raw/chargepoints/ocm_api_status.json`
and returns `None`. The supply build then falls back to OpenStreetMap and the registry snapshot, with a
larger borough calibration against DfT totals.

## Fields used

`ocm_id, lat, lon, operator, usage_type, status, n_points, connections (JSON string of
ConnectionTypeID/PowerKW/Quantity/LevelID/CurrentTypeID/StatusTypeID), max_power_kw, level, date_created,
date_last_verified, source="ocm"`. Output: `data/interim/chargepoints/ocm_london.parquet`.

## Known issues / caveats

- Coverage of sites is good, coverage of ports is not: `Quantity` is often missing, so port counts are
  scaled per borough to the DfT totals of 1 July 2026 (median factor 1.6 for rapid sites).
- Mixed provenance. Data contributed by users is CC BY 4.0 and applications must show the data provider
  attribution to end users. OCM also imports third-party open datasets (historically including the DfT
  registry), whose licence is carried per record (`DataProvider`).
- Crowd-sourced status. `status` and `date_last_verified` are kept so that stale records can be filtered.
  Records marked removed, not operational or planned are excluded from the supply layer.
- OCM asks heavy users to cache and not to download whole countries repeatedly. The downloader sleeps 1 s
  between calls and stores every tile response, so a rerun makes no network calls.

## How to reproduce

```bash
OCM_API_KEY=... PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_ocm; fetch_ocm()"
```
