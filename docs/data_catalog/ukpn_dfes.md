---
id: ukpn_dfes
title: UK Power Networks Distribution Future Energy Scenarios 2026 - EV uptake by LSOA (cars, vans, PHV, taxi, HGV, bus, coach, minibus) and domestic connection counts
provider: UK Power Networks DSO (prepared by Environmental Resources Management, ERM)
url: https://dso.ukpowernetworks.co.uk/distribution-future-energy-scenarios
download_url: https://d1lf1oz5vvdb9r.cloudfront.net/app/uploads/2026/03/UKPN-electric-car-van-scenarios-LSOA-UPDATED.xlsx (35.9 MB) ; UKPN-electric-taxi-phv-scenarios-LSOA-UPDATED.xlsx (16.7 MB) ; UKPN-electric-HGV-Bus-Coach-Minibus-scenarios-LSOA-UPDATED.xlsx (26.7 MB) ; UKPN-domestic-connection-count-scenarios-LSOA-UPDATED.xlsx (7.0 MB)
licence: CC BY 4.0 ("UK Power Networks Distribution Future Energy Scenarios (C) 2024 by UK Power Networks is licenced under Attribution 4.0 International" - workbook cover sheet)
status: proxy (scenario forecasts, not observations)
retrieved: 2026-09-10
size_mb: raw 86 (4 xlsx) + 1.2 (LSOA/GSP mapping JSON); interim 6.6 (London LSOA) + 0.9 (LAD) + 0.1 (lookup)
spatial_unit: LSOA 2021 (4,555 London LSOAs of 11,023 in the UKPN area); aggregated to LAD 2022
temporal: annual regulatory years 2024..2050 (2024 = actuals / baseline), 4 NESO-aligned pathways
script: src/chargescape/data/ukpn.py  (part `dfes`)
raw_path: data/raw/ukpn/dfes/
---

## What it is
The 2026 DFES (issued 23 Mar 2026, "with tRESP and LAEP alignment") disaggregated to LSOA for
the whole UKPN footprint. The Opendatasoft copies (`ukpn-dfes-by-local-authorities`,
`ukpn-dfes-network-headroom-report`) are **login-only** (`data_visible=false`); the DSO site
publishes the same 2026 vintage as open Excel workbooks, which is what we ingest.

Outputs (`data/interim/ukpn/`):
- `dfes2026_lsoa_london_ev.parquet` - 177,645 rows: London LSOAs x pathway x parameter, wide by
  year (`y2024..y2050`). Technologies: `cars` (BEV Cars, PHEV Cars), `vans` (BEV/PHEV Vans),
  `phv`, `taxi`, `hgv`, `bus`, `coach`, `minibus`, `domestic_connection_counts`.
- `dfes2026_lad_ukpn_ev.parquet` - same, summed to LAD for all 121 UKPN local authorities
  (`is_london` flag) - use for sanity checks against DfT VEH0142 licensed-vehicle stats.
- `dfes2026_lsoa_licence_area.parquet` - LSOA21CD -> LPN/EPN/SPN (UKPN's own mapping, from the
  DFES-visualisation GitHub repo; also cached `gsp2lsoa.json` = LSOA -> GSP shares).
- `_dfes_report.json` - row counts, value lists, headline totals.

Pathways (`pathway` = NESO "Scenario World"): ElectricEngagement, HolisticTransition,
HydrogenEvolution, FallingBehind; `scenario` = the driver trajectory used (ZEV Mandate / Reduced
Demand / Limited Uptake). Headline, London BEV cars, ElectricEngagement: 2024 **127,861** ->
2026 370k -> 2030 **1.05 M** -> 2035 1.90 M -> 2050 2.97 M.

## Fields used
`lsoa21cd, lsoa21nm, msoa21cd, lad22cd, lad22nm, share_epn/share_lpn/share_spn` (customer-count
share of the LSOA in each licence area), `licence_area` (majority), `pathway, scenario,
parameter, unit, technology, y2024..y2050`. Values are integer vehicle counts (rounded
disaggregation - LSOA sums differ from network totals by <0.1 %).

## Known issues / caveats
- **Forecast, not observation**: use as the spatial prior for EV stock/demand growth; calibrate
  the 2024 column against DfT VEH0142 (licensed ULEVs by LSOA) before trusting the level.
- LSOA counts are *vehicles kept in the LSOA* (registered keeper), not where they charge - PHV
  and taxi stock is concentrated in outer-London LSOAs while charging happens centrally.
- 2024 column is identical across pathways (baseline); divergence starts 2025.
- Regulatory years (Apr-Mar). ONS 2021 LSOA codes - 2011-based lookups need the ONS best-fit table.
- HGV/Bus/Coach/Minibus sheets have no `unit` column (counts) and a trailing "Rounded" note column (dropped).
- The DSO page states no licence; the licence line is taken from each workbook's cover sheet.

## How to reproduce
```
PYTHONPATH=src python -m chargescape.data.ukpn dfes
```
~45 s (Excel parsing dominates). Other DFES 2026 workbooks (heat pumps, PV, batteries, I&C
connection counts, GSP-level generation/storage) are at the same URL pattern if needed.
