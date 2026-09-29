# Roadmap

## Next increments (in order of value)
1. **Revealed-preference calibration of the choice model** when a session dataset with origins exists (Optimise Prime WS3 if released; or a partner CPO).
2. **Dasymetric interpolation** with OS Open Map building footprints instead of area weights.
3. **Spatio-temporal occupancy forecasting** on UrbanEV (Shenzhen) and Paris Belib' 15-min series: LightGBM → ST-GNN with conformal intervals; transfer discussion to London.
4. **Post-hoc validation notebook**: compare hexes flagged in July 2026 with DfT/Zapmap device growth and TfL utilisation releases through 2027.
5. **Second track — pedestrian-demand networks** (power-bank sharing / micro-hubs) reusing the same choice–queue–siting stack with walking-time catchments and inventory rebalancing.
6. **Category-scale predictability study**: at which H3 resolution does demand for coffee, grocery, car dealerships become forecastable from platform signals (entropy vs aggregation; Poisson noise floor).

7. **Discrete-event queue simulation** with empirical service-time distributions (Dundee rapid sessions) instead of Erlang C's exponential assumption.

## Done in v1.0
* Open Charge Map integrated (12.5k points) alongside OSM and the 2021 registry.
* MapLibre GL maps with embedded data and an offline fallback; HTML slides in English and Russian.
* Siting sensitivity analysis and recorded MIP gaps.
* Runs from a clean clone on committed processed tables.

## Engineering
* Zenodo snapshot of the interim data with a DOI; scheduled GitHub Action that re-checks DfT/Zapmap releases for the post-hoc test.
