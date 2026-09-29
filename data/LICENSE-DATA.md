# Data licences

The code in this repository is MIT-licensed (see `LICENSE`). The data files committed under `data/processed/`, `docs/maps/data/` and the figures derived from them combine several open sources and are distributed under the terms below.

Because the tables contain information derived from OpenStreetMap, the combined processed database is made available under the **Open Database License (ODbL) 1.0**. Individual contents keep their original licences:

| Source | Licence | Attribution |
|---|---|---|
| OpenStreetMap (charging stations, POIs, road network) | ODbL 1.0 | © OpenStreetMap contributors |
| Open Charge Map | CC BY 4.0 | Open Charge Map (openchargemap.org) |
| DfT EV charging infrastructure statistics, vehicle licensing statistics, road traffic counts | OGL v3 | Department for Transport |
| National Chargepoint Registry (May 2021 snapshot) | OGL v3 | Office for Zero Emission Vehicles |
| ONS Census 2021, geographies and lookups | OGL v3 | Office for National Statistics |
| English Indices of Deprivation 2025 | OGL v3 | Ministry of Housing, Communities and Local Government |
| London Atmospheric Emissions Inventory 2022 | OGL v3 (London Datastore) | Greater London Authority / TfL |
| TfL Unified API, NaPTAN | OGL v3 | Powered by TfL Open Data; Department for Transport |
| UK Power Networks DFES 2026, primary-substation headroom (GLA LAEP mirror) | CC BY 4.0 | UK Power Networks |
| Dundee City Council and Perth & Kinross Council charging sessions | OGL v3 | Dundee City Council; Perth & Kinross Council |
| City of Palo Alto EV charging station usage | ODC-PDDL | City of Palo Alto |
| City of Boulder EV charging station data | CC0 | City of Boulder |
| WorldPop 2020 population | CC BY 4.0 | WorldPop, University of Southampton |
| Open-Meteo historical weather (not committed) | CC BY 4.0 | Open-Meteo.com |
| Basemap tiles in the web maps | CARTO basemaps terms | © CARTO © OpenStreetMap contributors |

Raw downloads are not redistributed; `make data` fetches them from the original publishers. Per-source details, including known issues, are in `docs/data_catalog/`.
