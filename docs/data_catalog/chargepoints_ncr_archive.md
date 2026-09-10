---
id: chargepoints_ncr_archive
title: National Chargepoint Registry (NCR) – archived full CSV snapshot, 25 May 2021 (Internet Archive)
provider: Office for Zero Emission Vehicles / Department for Transport (registry, decommissioned); snapshot served by the Internet Archive Wayback Machine
url: https://www.gov.uk/guidance/find-and-use-data-on-public-electric-vehicle-chargepoints
download_url: https://web.archive.org/web/20210525024631id_/https://chargepoints.dft.gov.uk/api/retrieve/registry/format/csv
licence: Open Government Licence v3.0 (data.gov.uk record "national-charge-point-registry", licence uk-ogl)
status: observed
retrieved: 2026-09-10
size_mb: 12.1 (CSV, whole UK) / 0.62 (GeoParquet, London bbox)
spatial_unit: point (charge device with 1–8 connectors)
temporal: static snapshot captured 2021-05-25 02:46 UTC; registry closed 2024-11-28
script: src/chargescape/data/chargepoints.py
raw_path: data/raw/chargepoints/ncr_archive/
---

## What it is
The NCR was DfT/OZEV's open, voluntary registry of public chargepoints (2011–2024), downloadable as CSV/JSON/XML
without registration. **It is closed.** Evidence gathered on 2026-09-10:
- GOV.UK guidance "Find and use data on public electric vehicle chargepoints" carries a withdrawal notice dated
  2024-12-02: "The National Chargepoint Registry (NCR) was decommissioned on 28 November 2024 … The archived NCR data
  will be available on request to users and researchers" (contact consumerofferconsult@ozev.gov.uk). Operators must
  now publish open data under the Public Charge Point Regulations 2023.
- data.gov.uk dataset `national-charge-point-registry` still exists but has **0 resources**.
- UK Power Networks' Open Data Portal mirror `ozev-ukpn-national-chargepoint-register` now holds **0 records**
  (notice dated 5 December 2024).
- Wayback Machine captures of the full registry download: CSV on 2012-04-05, 2012-06-10, 2012-10-04 and
  **2021-05-25** (HTTP 200, text/csv, 1.13 MB compressed); JSON on 2021-05-07; a 2022-08-28 JSON capture returned
  HTTP 500. No 2022–2024 full-registry captures exist, so the last usable snapshot is May 2021.

The 2021-05-25 CSV (17,705 UK devices parsed, 158 columns) was downloaded via the Wayback `id_` raw endpoint; the
Greater London bbox subset (**6,654 devices**) is saved to `data/interim/chargepoints/ncr_archive_london_2021.parquet`
(GeoParquet, EPSG:4326, 30 columns). Bbox (W,S,E,N): -0.5065, 51.2834, 0.3285, 51.6957.

## Fields used
Original NCR names kept: `chargeDeviceID`, `reference`, `name`, `latitude`, `longitude`, `town`, `county`,
`postcode`, `uprn`, `deviceOwnerName`, `deviceControllerName`, `deviceNetworks`, `chargeDeviceStatus`
(In service 6,558 / Out of service 96), `publishStatus`, `dateCreated`, `dateUpdated`, `attribution`,
`paymentRequired`, `subscriptionRequired`, `onStreetFlag`, `locationType`, `access24Hours`,
`accessRestrictionFlag`. Derived from the `connector1..8*` columns: `n_connectors`, `max_rated_kw`,
`connector_types` (JSON list), `connectors_json` (type / rated_kw / status / charge_method per connector);
plus `snapshot_date` (2021-05-25) and `source = "ncr_wayback_2021"`.

## Known issues / caveats
- Historical (2021) and voluntary: operators uploaded what they chose; coverage of some networks was partial and
  status fields were not reliably maintained. Use for structure/comparison, not as current supply.
- Two malformed rows (unquoted newlines) are skipped by the python CSV engine (17,705 of 17,707 rows parsed).
  Some `dateCreated` values are "0000-00-00".
- The bbox subset is a rectangle, not the Greater London boundary: it includes fringe devices in Hertfordshire,
  Surrey, Kent and Essex (e.g. 70 rows with county "Hertfordshire"). Clip to the borough polygons before
  computing London totals.
- `locationType` is the usable siting field (On-street 4,388 = 66 %, Other 658, Public car park 625, Retail car
  park 263, Workplace car park 165, Leisure centre 108); `onStreetFlag` is null for 97 % of rows. `paymentRequired`
  is 1 for 3,055 / 0 for 3,418 devices, `subscriptionRequired` 1 for 3,223 / 0 for 3,431.
- Rated power is populated for 100 % of London rows, but the registry recorded nominal connector ratings
  (3.7 kW lamp-post sockets dominate: 84 % of London devices ≤ 7.4 kW, 6.6 % ≥ 50 kW).
- The Wayback `id_` endpoint returns the archived bytes unmodified, but the capture reflects whatever the registry
  served at 02:46 UTC on 25 May 2021; it is not an official DfT archive release (that is "available on request").

## How to reproduce
```bash
PYTHONPATH=src python -c "from chargescape.data.chargepoints import fetch_ncr_archive; fetch_ncr_archive()"
```
