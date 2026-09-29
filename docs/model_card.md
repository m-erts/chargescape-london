# Model card: ChargeScape London demand and siting system

## Intended use
Decision support for planning public rapid-charging hubs in Greater London: ranking candidate
locations under a budget, with explicit uncertainty and queue-aware capacity. Not a substitute
for site surveys, grid connection studies or commercial due diligence.

## Components and their status

| Component | Type | Trained on | Status label |
|---|---|---|---|
| Hex features (Census, EV licensing, POI, traffic, transit, headroom) | data engineering | n/a | observed / proxy (see `docs/data_catalog/`) |
| Structural demand (`structural_demand.py`) | bottom-up model with triangular priors, 500 MC draws | not fitted; priors from UK NTS, EV Database, ICCT, TfL | synthetic on observed inputs |
| Attraction mix (`demand_pipeline.py`) | weighted normalised signals | weights set by judgement (0.45 traffic, 0.35 dwell POIs, 0.10 rail, 0.10 parking) | proxy |
| PHV component | structural, priors on fleet size / km / public share | TfL licensing orders of magnitude | synthetic |
| Supply | Open Charge Map ∪ OSM ∪ NCR 2021, de-duplicated within 50 m; ports of mapped rapid sites scaled per borough to DfT 50 kW+ counts (median ×1.6) | DfT EVCI 1 July 2026 | observed positions, observed totals, proxy port counts |
| Station choice (`choice.py`) | multinomial logit | literature-informed parameters, not estimated | synthetic |
| Queues (`queueing.py`) | Erlang C (M/M/c), 38-min service from Dundee median | observed service-time | analytic |
| Siting (`facility.py`) | capacitated MCLP (SciPy / HiGHS) with MIP gap recorded per solve; a plan per demand scenario cross-evaluated with an exact fixed-plan LP (regret, robust core) | n/a | optimisation |
| Sensitivity (`sensitivity.py`) | re-solve at £20M under 9 changed assumptions on a fixed candidate set | n/a | analysis |
| Utilisation transfer (`ml.py`, notebook 05) | LightGBM with leave-city-out CV | Dundee, Perth & Kinross, Palo Alto, Boulder observed sessions | observed target, out-of-London |

## Key assumptions and their sensitivity
* Public-charging share for drivers without off-street parking (prior 0.55 to 0.95): the single largest driver of near-home demand.
* Electric taxi/PHV fleet size (prior 14k to 26k in 2026) and its public share (0.70 to 0.95): dominates rapid-type demand in inner London.
* Choice parameters (travel-time coefficient −0.25/min, power +0.6 per log kW) and the choice-set radius: they change how much demand the existing network absorbs and therefore the unmet total (notebook 04, sensitivity table), and they reshuffle exact hub hexes more than corridors.
* Service level (P(wait) ≤ 15% at the peak hour ⇒ ≈33 sessions/day per 4 × 150 kW hub) and coverage radius (8 min): the service level is a business choice with the largest effect on how much demand a budget covers.

## Validation performed
* Consistency of modelled city totals with DfT charger counts × TfL observed occupancy (notebook 02).
* Implied rapid sessions per charger per day compared with TfL occupancy and Dundee observations.
* Spatial autocorrelation diagnostics (Moran's I) on inputs; leave-city-out cross-validation for the utilisation model (notebook 05: it does not transfer, reported as a negative result).
* Plans for P10/P50/P90 demand cross-evaluated exactly (regret of the P50 plan, robust core); siting sensitivity to 9 changed assumptions (notebook 04); MIP optimality gaps recorded for every solve.
* The two-stage robust MILP (`robust_capacitated_mclp`) does not close its gap within 5 minutes on this instance; its incumbent is not reported.

## Validation still to do (the post-hoc plan)
The recommendation for each hex is falsifiable: DfT/Zapmap publish quarterly device counts by borough and TfL publishes utilisation by type. Sites opened after July 2026 in hexes flagged here as high unmet demand should show above-median utilisation within 12 months; a systematic miss would indicate the priors on PHV demand or the choice radius are wrong.

## Known limitations
* No open London session data at charger level; behavioural parameters come from other UK cities and fleet trials.
* Open Charge Map, OSM and the 2021 registry together still miss some ports; the borough-level calibration preserves totals but not exact positions of unmapped chargers.
* Area-weighted interpolation from LSOA assumes uniform density; hexes whose centroid falls outside the boundary are dropped (≈1.4% of population).
* Grid constraints use primary-substation headroom only; secondary-substation data require UKPN registration.
