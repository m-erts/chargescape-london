# Model card — ChargeScape London demand & siting system

## Intended use
Decision support for planning public rapid-charging hubs in Greater London: ranking candidate
locations under a budget, with explicit uncertainty and queue-aware capacity. Not a substitute
for site surveys, grid connection studies or commercial due diligence.

## Components and their status

| Component | Type | Trained on | Status label |
|---|---|---|---|
| Hex features (Census, EV licensing, POI, traffic, transit, headroom) | data engineering | — | observed / proxy (see `docs/data_catalog/`) |
| Structural demand (`structural_demand.py`) | bottom-up model with triangular priors, 500 MC draws | not fitted; priors from UK NTS, EV Database, ICCT, TfL | synthetic on observed inputs |
| Attraction mix (`demand_pipeline.py`) | weighted normalised signals | weights set by judgement (0.45 traffic, 0.35 dwell POIs, 0.10 rail, 0.10 parking) | proxy |
| PHV component | structural, priors on fleet size / km / public share | TfL licensing orders of magnitude | synthetic |
| Supply calibration | ports of known rapid sites scaled to DfT borough 50 kW+ counts | DfT EVCI 1 July 2026 | observed totals, proxy geometry |
| Station choice (`choice.py`) | multinomial logit | literature-informed parameters, not estimated | synthetic |
| Queues (`queueing.py`) | Erlang C (M/M/c), 38-min service from Dundee median | observed service-time | analytic |
| Siting (`facility.py`) | capacitated MCLP + robust two-stage MILP (HiGHS) | — | optimisation |
| Utilisation transfer (`ml.py`, notebook 05) | LightGBM with leave-city-out CV | Dundee, Perth & Kinross, Palo Alto, Boulder observed sessions | observed target, out-of-London |

## Key assumptions and their sensitivity
* Public-charging share for drivers without off-street parking (prior 0.55–0.95): the single largest driver of near-home demand.
* Electric taxi/PHV fleet size (prior 14–26k in 2026) and its public share (0.70–0.95): dominates rapid-type demand in inner London.
* Choice parameters (travel-time coefficient −0.25/min, power +0.6/log kW): change *which* sites absorb demand more than *how much* there is.
* Coverage radius 8 min and hub capacity from P(wait) ≤ 15 %: tighter service levels reduce the number of hexes any hub can serve.

## Validation performed
* Consistency of modelled city totals with DfT charger counts × TfL observed occupancy (notebook 02).
* Implied rapid sessions per charger per day compared with TfL occupancy and Dundee observations.
* Spatial autocorrelation diagnostics (Moran's I) on inputs; spatial (leave-city / leave-borough) cross-validation for any fitted model.

## Validation still to do (the post-hoc plan)
The recommendation for each hex is falsifiable: DfT/Zapmap publish quarterly device counts by borough and TfL publishes utilisation by type. Sites opened after July 2026 in hexes flagged here as high unmet demand should show above-median utilisation within 12 months; a systematic miss would indicate the priors on PHV demand or the choice radius are wrong.

## Known limitations
* No open London session data at charger level; behavioural parameters come from other UK cities and fleet trials.
* OSM holds ~15 % of London's rapid devices; the borough-level calibration preserves totals but not exact positions of unmapped chargers.
* Area-weighted interpolation from LSOA assumes uniform density; hexes whose centroid falls outside the boundary are dropped (≈1.4 % of population).
* Grid constraints use primary-substation headroom only; secondary-substation data require UKPN registration.
