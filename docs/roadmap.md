# Roadmap

## Next increments (in order of value)
1. **Revealed-preference calibration of the choice model** when a session dataset with origins exists (Optimise Prime WS3 if released; or a partner CPO).
2. **Open Charge Map with an API key** (`OCM_API_KEY`) to replace the borough-level port calibration with mapped rapid sites.
3. **Dasymetric interpolation** with OS Open Map building footprints instead of area weights.
4. **Spatio-temporal occupancy forecasting** on UrbanEV (Shenzhen) and Paris Belib' 15-min series: LightGBM → ST-GNN with conformal intervals; transfer discussion to London.
5. **Post-hoc validation notebook**: compare hexes flagged in July 2026 with DfT/Zapmap device growth and TfL utilisation releases through 2027.
6. **Second track — pedestrian-demand networks** (power-bank sharing / micro-hubs) reusing the same choice–queue–siting stack with walking-time catchments and inventory rebalancing.
7. **Category-scale predictability study**: at which H3 resolution does demand for coffee, grocery, car dealerships become forecastable from platform signals (entropy vs aggregation; Poisson noise floor).

## Engineering
* DVC or Zenodo for the interim data snapshot; Streamlit app over `data/processed/*.small.parquet`; GitHub Actions to rebuild maps.
