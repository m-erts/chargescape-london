---
id: sessions_leeds
title: Leeds City Council - Electric vehicle chargepoints operated by LCC (sessions, Apr 2014 - Mar 2021)
provider: Leeds City Council via Data Mill North (dataset 2lx68)
url: "https://datamillnorth.org/dataset/2lx68 (mirrored on data.gov.uk: electric-vehicle-chargepoints-operated-by-leeds-city-council)"
download_url: https://datamillnorth.org/download/2lx68/<uuid>/<year> EVCP use <Qn>.csv - 16 files, ids listed in src/chargescape/data/sessions_open.py (LEEDS_FILES)
licence: Open Government Licence v3 (Data Mill North package licence)
status: observed
retrieved: 2026-09-10
size_mb: 2.8 (raw); 0.9 (parquet)
spatial_unit: site name only (council car parks / park & rides) - NO coordinates published
temporal: per session, 2014-04-10 .. 2021-03-31 (local UK time); quarterly/half-yearly files
script: src/chargescape/data/sessions_open.py (fetch_leeds / harmonise_leeds)
raw_path: data/raw/sessions_open/leeds/
---

## What it is
Session-level usage of the charge points in Leeds City Council car parks (Woodhouse Lane multi-storey -
dominant, Elland Road and Temple Green park & rides, Wellington Place), same back-office layout as PKC:
`Charging event, User ID (anonymised "User 406"), CP ID, Connector, Start Date, Start Time, End Date,
End Time, Total kWh, Site, Model (APT 7kW Dual Outlet; one 50 kW rapid at Elland Road from Dec 2017)`.
Unlike Dundee/PKC it carries a **stable pseudonymous user id** (1,087 users) -> repeat-use / loyalty statistics.

## Fields used
As PKC; user_id = SHA-1 hash of the "User N" label; power_kw from the model string (7 / 50).
Date formats differ between files (2014 files are m/d/Y, later d/m/Y, some mixed) - `_smart_datetime()`
picks the format per file by parse success and year window; ranges per file were verified against the
filename quarter.

## Harmonised outputs (2026-09-10 run)
* `leeds_sessions.parquet`: **25,322 sessions, 23 charge points, 0% located** (site names only);
  2014 90, 2015 487, 2016 2.8k, 2017 4.4k, 2018 4.3k, 2019 7.6k, 2020 4.6k, 2021 Q1 1.0k.
* Median 9.9 kWh, median dwell **573 min** (7 kW car-park posts: commuters/residents leave cars all day or
  overnight); 8.6% sessions > 24 h (multi-day parking - genuine, not a parse artefact: verified end > start
  on same-day rows).
* Arrivals: bimodal - 07-10h 36% and 16-19h 39% (peak 16h, 16.9%); weekend 14%. The evening peak is
  Woodhouse Lane (city-centre car park next to the universities); park & rides peak 07-09h.

## Known issues / caveats
* No coordinates and no postcodes: sites are named car parks. The 5 sites can be geocoded by name
  (Nominatim / OS Open Names) or looked up on the council's parking pages - deliberately not automated
  here; do it by hand and record the source before using Leeds spatially.
* 4.3% sessions <= 0.05 kWh, 1.3% zero duration; 2019-Q3Q4 file has rows with blank end/kWh (in-progress sessions).
* Small network (5 sites) - useful for dwell distributions of *destination car-park* charging, not for spatial
  transfer.
* `EV Fleet Chargepoint use` (dataset e7ljx, council fleet) exists on the same portal - not fetched (not public charging).

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.sessions_open --only leeds
```
