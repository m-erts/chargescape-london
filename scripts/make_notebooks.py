"""Generate the analysis notebooks from code so they stay reproducible. Run then execute with
`make notebooks` (jupyter nbconvert --execute)."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB = Path(__file__).resolve().parents[1] / "notebooks"
NB.mkdir(exist_ok=True)

HEADER = """import warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from chargescape.utils.paths import PROCESSED, INTERIM, FIGURES, TABLES, DOCS
from chargescape.utils.io import read_gdf
from chargescape.viz.figures import hex_map, save, barh, boroughs
pd.set_option("display.width", 160); pd.set_option("display.max_columns", 40)
feats = read_gdf(PROCESSED / "hex_features_r8.small.parquet")
print(feats.shape)"""


import sys

FORCE = "--force" in sys.argv


def nb(cells: list[tuple[str, str]], path: Path) -> None:
    """Write the notebook unless it already exists (executed notebooks keep their outputs); use --force to regenerate."""
    if path.exists() and not FORCE:
        print("kept", path.name)
        return
    n = nbf.v4.new_notebook()
    n["cells"] = [
        nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src) for kind, src in cells
    ]
    n["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nbf.write(n, path)


# ----------------------------------------------------------------------------- 01 supply audit
nb01 = [
    (
        "md",
        """# 01 · Supply audit — where London's chargers are, and where EV owners are

**Question.** How does London's public charging supply (31k chargers, only 8 % rapid) relate to where plug-in cars are kept and to housing that lacks off-street parking?

**Data (all observed).** DfT EVCI statistics 1 July 2026 (borough totals, 50 kW+), OpenStreetMap 2026 charging stations (hub-biased sample), National Chargepoint Registry snapshot May 2021 (complete for its date), Census 2021, DfT vehicle licensing 2026 Q1 by LSOA, all moved to H3 resolution 8.""",
    ),
    ("code", HEADER),
    ("md", "## 1. Official borough picture (DfT, 1 July 2026)"),
    (
        "code",
        """dft = pd.read_parquet(INTERIM / "chargepoints" / "dft_evci_london_la.parquet")
la = dft[(dft.geography == "local_authority") & (dft.date == dft.date.max())]
tab = la.pivot_table(index="area_name", columns="measure", values="value").rename(columns={"EV chargers": "chargers", "50kW+ EV chargers": "rapid", "EV chargers per 100k": "chargers_per_100k", "50kW+ EV chargers per 100k": "rapid_per_100k"})
tab["rapid_share"] = tab["rapid"] / tab["chargers"]
print("London total chargers:", int(tab.chargers.sum()), " rapid (50kW+):", int(tab.rapid.sum()), f" rapid share {tab.rapid.sum()/tab.chargers.sum():.1%}")
fig, axes = plt.subplots(1, 2, figsize=(13, 8))
barh(tab["chargers_per_100k"], "Public chargers per 100k residents (DfT, Jul 2026)", ax=axes[0])
barh(tab["rapid_share"] * 100, "Share of chargers that are 50 kW+ (%)", ax=axes[1], color="#e4572e")
plt.tight_layout(); save(fig, "01_borough_supply.png"); plt.show()
tab.sort_values("chargers_per_100k", ascending=False).round(2).head(10)""",
    ),
    (
        "md",
        """**Reading.** Inner boroughs (Hammersmith & Fulham, Westminster) have ~1,400 chargers per 100k residents, mostly lamp-post 5–7 kW units; rapid share is highest in outer boroughs (Havering, Hillingdon ~40 %) and below 4 % in Westminster, Hackney and Kensington & Chelsea. Density of *devices* and density of *power* are different maps.""",
    ),
    ("md", "## 2. Hex view: chargers, private EVs and housing form"),
    (
        "code",
        """sites = read_gdf(PROCESSED / "charging_sites.parquet")
fig, axes = plt.subplots(2, 2, figsize=(15, 11))
hex_map(feats, "ports_slow", "Slow/fast (<50 kW) charge points per hex — NCR 2021 (complete for its date)", cmap="Blues", scheme="quantiles", k=6, ax=axes[0, 0], legend_label="ports")
hex_map(feats, "ports_rapid", "Rapid (≥50 kW) ports per hex — OSM 2026 ∪ NCR 2021", cmap="Oranges", scheme="fisher_jenks", k=5, ax=axes[0, 1], legend_label="ports", points=sites[sites.is_rapid], point_kw={"markersize": 4, "color": "black", "alpha": 0.6})
hex_map(feats, "piv_private_per_1000_hh", "Private plug-in cars per 1,000 households (DfT 2026 Q1)", cmap="viridis", scheme="quantiles", k=6, ax=axes[1, 0], legend_label="PiV / 1000 hh")
hex_map(feats, "share_flat", "Share of households living in flats (Census 2021) — proxy for no off-street parking", cmap="magma", scheme="quantiles", k=6, ax=axes[1, 1], legend_label="share")
plt.tight_layout(); save(fig, "01_hex_supply_demand.png"); plt.show()""",
    ),
    ("md", "## 3. Is the pattern clustered? Global and local spatial autocorrelation"),
    (
        "code",
        """from chargescape.features.spatial_stats import h3_weights, morans_i, local_hotspots
w = h3_weights(feats["h3"])
rows = []
for col in ["piv_private_per_1000_hh", "share_flat", "ports_slow", "ports_rapid", "vkm_total"]:
    m = morans_i(feats[col].fillna(0), w, permutations=499)
    rows.append({"variable": col, "Moran_I": m["I"], "p_sim": m["p_sim"]})
moran = pd.DataFrame(rows).round(3); print(moran.to_string(index=False))
feats["need_index"] = feats["piv_private_est"].fillna(0) * feats["share_flat"].fillna(0)
hs = local_hotspots(feats["need_index"], w, permutations=499)
feats["need_hotspot"] = hs["hotspot"].values
fig, ax = plt.subplots(figsize=(9, 7))
feats.to_crs(27700).plot(column="need_hotspot", categorical=True, cmap="RdBu_r", ax=ax, legend=True, linewidth=0, legend_kwds={"loc": "lower right", "fontsize": 8, "frameon": False})
boroughs().boundary.plot(ax=ax, color="white", linewidth=0.4); ax.set_axis_off()
ax.set_title("Getis-Ord Gi* hot spots of 'private EVs × flats' (residents who own an EV but likely lack a driveway)", loc="left")
save(fig, "01_need_hotspots.png"); plt.show()""",
    ),
    ("md", "## 4. Gap analysis: high need, far from rapid charging (network drive time)"),
    (
        "code",
        """svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet").set_index("h3")
feats["tt_nearest_rapid_min"] = feats["h3"].map(svc["tt_nearest_rapid_min"])
gap = feats[(feats["need_index"] > feats["need_index"].quantile(0.75)) & (feats["tt_nearest_rapid_min"] > 6)]
print(f"hexes in top-quartile need with no rapid site within 6 min drive: {len(gap)} ({gap['piv_private_est'].sum():,.0f} private EVs)")
fig, ax = plt.subplots(figsize=(9, 7))
hex_map(feats, "tt_nearest_rapid_min", "Drive time to nearest rapid site (min, OSM network + igraph)", cmap="YlOrRd", vmin=0, vmax=12, ax=ax, legend_label="minutes")
gap.to_crs(27700).boundary.plot(ax=ax, color="#1b4965", linewidth=0.8)
ax.set_title("Drive time to nearest rapid site — outlined: top-quartile need, > 6 min away", loc="left")
save(fig, "01_gap_rapid_access.png"); plt.show()
gap.groupby("borough").agg(hexes=("h3", "size"), private_evs=("piv_private_est", "sum"), mean_tt=("tt_nearest_rapid_min", "mean")).sort_values("private_evs", ascending=False).round(1).head(12)""",
    ),
    (
        "md",
        """## Takeaways
* Supply follows *devices*, need follows *cars without driveways*: the densest slow networks sit in inner boroughs, the largest private EV stocks in outer, house-rich boroughs — but the group that depends most on public charging (EV owners in flats) forms distinct hot spots, mostly in inner-west and inner-south London.
* Rapid access by drive time is already fairly dense: only a handful of top-quartile-need hexes (Wandsworth, Waltham Forest, Newham, Richmond) are more than six minutes from a rapid site. The binding constraint in London is therefore *capacity and queues* at existing sites rather than pure distance — which is what notebooks 03–04 model.
* Everything above is observed data; the next notebook turns it into a demand surface with explicit uncertainty.""",
    ),
]
nb(nb01, NB / "01_supply_audit.ipynb")

# ----------------------------------------------------------------------------- 02 demand
nb02 = [
    (
        "md",
        """# 02 · Demand surface with uncertainty

**Question.** How much public charging energy will each hex need, today and in 2030, and how sure are we?

**Method.** Structural bottom-up model (`chargescape.models.structural_demand`): EV stock × annual km × kWh/km × public-charging share (depends on off-street parking) with triangular priors and 500 Monte Carlo draws → P10/P50/P90 per hex. Destination/en-route demand is redistributed to activity cells by an attraction mix (vehicle-km, dwell POIs, rail, parking); a separate taxi & private-hire component follows LAEI taxi+PHV vehicle-km. 2030 scenarios use UKPN DFES 2026 pathways. Status of the result: **synthetic (model) on observed inputs** — and checked against observed aggregates below.""",
    ),
    ("code", HEADER),
    (
        "code",
        """from chargescape.models.structural_demand import DemandPriors
from chargescape.models.demand_pipeline import AttractionWeights, PHVPriors, COMPANY_FACTOR
pri = DemandPriors(); print("priors:", {k: v for k, v in pri.__dict__.items() if k not in ("extra",)})
print("attraction mix:", AttractionWeights().__dict__); print("PHV priors:", PHVPriors().__dict__); print("company-kept EV factor:", COMPANY_FACTOR)
dem = pd.read_parquet(PROCESSED / "demand_r8.small.parquet")
tot = dem.groupby("scenario")[[c for c in dem.columns if c.endswith(("_p10", "_p50", "_p90"))]].sum() / 1e6
tot.round(1)""",
    ),
    ("md", "## 1. Where the demand is (2026, P50) and how uncertain it is"),
    (
        "code",
        """d26 = dem[dem.scenario == "2026"].set_index("h3")
g = feats.set_index("h3").join(d26, how="left").reset_index()
g["total_mwh_p50"] = g["total_kwh_p50"] / 1e3
g["uncert_band_mwh"] = (g["total_kwh_p90"] - g["total_kwh_p10"]) / 1e3
g["phv_share"] = g["phv_kwh_p50"] / g["total_kwh_p50"].replace(0, np.nan)
fig, axes = plt.subplots(1, 3, figsize=(20, 6))
hex_map(g, "total_mwh_p50", "Public charging demand 2026, P50 (MWh/yr per hex)", cmap="viridis", scheme="quantiles", k=7, ax=axes[0], legend_label="MWh/yr")
hex_map(g, "uncert_band_mwh", "Uncertainty band: P90 − P10 (MWh/yr)", cmap="cividis", scheme="quantiles", k=7, ax=axes[1], legend_label="MWh/yr")
hex_map(g, "phv_share", "Share of demand from taxi & private hire", cmap="plasma", vmin=0, vmax=1, ax=axes[2], legend_label="share")
plt.tight_layout(); save(fig, "02_demand_p50_uncertainty.png"); plt.show()""",
    ),
    (
        "md",
        """## 2. Sanity checks against observed aggregates

The model was not fitted to London usage data (none is open), so we check its total against quantities that *are* observed:
1. the supply side — DfT counts of chargers × TfL-reported occupancy by charger type (slow chargers occupied 46–49 % of the time, ultra-rapid ~34 %, March 2025);
2. per-charger throughput in Dundee's open session log (median 16 kWh per rapid session, ~3 sessions per charger per day in a small city).""",
    ),
    (
        "code",
        """dft = pd.read_parquet(INTERIM / "chargepoints" / "dft_evci_london_la.parquet")
la = dft[(dft.geography == "local_authority") & (dft.date == dft.date.max())].pivot_table(index="area_name", columns="measure", values="value")
n_rapid = la["50kW+ EV chargers"].sum(); n_slow = la["EV chargers"].sum() - n_rapid
# occupancy != charging: assume charging happens during ~45% of occupied time on slow units (long dwell) and ~85% on rapid
supply_kwh = {
    "slow (7 kW, occupied 47%, charging 45% of that)": n_slow * 7 * 24 * 365 * 0.47 * 0.45,
    "rapid (avg 60 kW delivered, occupied 34%, charging 85% of that)": n_rapid * 60 * 24 * 365 * 0.34 * 0.85,
}
imp = pd.Series(supply_kwh) / 1e6
print(f"DfT chargers: {n_slow:,.0f} slow, {n_rapid:,.0f} rapid")
print("Supply-implied energy, GWh/yr:\\n", imp.round(0), "\\n total ≈", round(imp.sum()), "GWh/yr")
m = tot.loc["2026"]
print(f"\\nModel 2026: near-home {m['res_kwh_p50']:.0f} GWh (P10–P90 {m['res_kwh_p10']:.0f}–{m['res_kwh_p90']:.0f}); rapid-type (destination+PHV) {m['dest_kwh_p50']+m['phv_kwh_p50']:.0f} GWh; total {m['total_kwh_p50']:.0f} GWh (P10–P90 {m['total_kwh_p10']:.0f}–{m['total_kwh_p90']:.0f})")
rapid_sessions_day = (m['dest_kwh_p50'] + m['phv_kwh_p50']) * 1e6 / 17 / 365
print(f"→ implied rapid sessions per charger per day: {rapid_sessions_day / n_rapid:.1f}  (TfL occupancy 34% with 38-min sessions ⇒ ~{0.34*24*60/38:.0f}/day; Dundee observed ≈3/day)")""",
    ),
    (
        "md",
        """**A note on the uncertainty map.** The P90−P10 band scales with the level of demand because the priors are global; the *relative* band is nearly constant (P90/P10 ≈ 1.7) and only shifts with the local mix of near-home, destination and PHV demand. Spatially varying uncertainty would need local calibration data — which is precisely what the post-hoc validation plan collects.

**Reading.** The model's rapid-type demand lands at the order of magnitude implied by TfL's observed occupancy of London's rapid network, while the near-home component sits below the energy that 28k slow chargers *could* be delivering — consistent with the known low charging-time share of long-dwell on-street sessions. The wide P10–P90 band is the honest statement: the biggest levers are the public-charging share of drivers without a driveway and the size of the electric PHV fleet.""",
    ),
    ("md", "## 3. 2030 scenarios (UKPN DFES 2026 pathways) — where growth concentrates"),
    (
        "code",
        """d30 = dem[dem.scenario == "2030_mid"].set_index("h3")
g["growth_2030_mid"] = g["h3"].map(d30["total_kwh_p50"]) / g["total_kwh_p50"].replace(0, np.nan)
g["total_2030_mid_mwh"] = g["h3"].map(d30["total_kwh_p50"]) / 1e3
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
hex_map(g, "total_2030_mid_mwh", "Demand 2030, DFES 'Holistic Transition' (P50, MWh/yr)", cmap="viridis", scheme="quantiles", k=7, ax=axes[0], legend_label="MWh/yr")
hex_map(g, "growth_2030_mid", "Growth factor 2030 / 2026 (P50)", cmap="RdYlGn", vmin=2, vmax=8, ax=axes[1], legend_label="×")
plt.tight_layout(); save(fig, "02_demand_2030.png"); plt.show()
print(tot[["total_kwh_p10", "total_kwh_p50", "total_kwh_p90"]].round(0))
bor = g.groupby("borough")[["total_kwh_p50"]].sum().join(g.groupby("borough")["total_2030_mid_mwh"].sum() * 1e3)
(bor / 1e6).rename(columns={"total_kwh_p50": "GWh_2026", "total_2030_mid_mwh": "GWh_2030_mid"}).sort_values("GWh_2030_mid", ascending=False).round(1).head(10)""",
    ),
]
nb(nb02, NB / "02_demand_surface.ipynb")

# ----------------------------------------------------------------------------- 03 allocation
nb03 = [
    (
        "md",
        """# 03 · Station choice, network load and queues

**Question.** If drivers choose among today's rapid sites by travel time, price, power and size, where does the demand land, and where do queues form at the peak hour?

**Method.** Multinomial logit allocation (`chargescape.models.choice`, literature-informed parameters) of rapid-type demand (destination + PHV, P50) from every hex to rapid sites within 20 minutes on the OSM drive network; Erlang-C M/M/c queue per site with 38-minute service (Dundee median). Supply is calibrated so that each borough's rapid ports match DfT's official 50 kW+ counts (OSM alone sees only ~15 % of them).""",
    ),
    ("code", HEADER),
    (
        "code",
        """from chargescape.models.choice import ChoiceParams
print(ChoiceParams().__dict__)
sites = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet")
print(f"{len(sites)} rapid sites, {sites.ports.sum():,} ports after calibration (known ports {sites.ports_known.sum():,.0f}, median scale ×{sites.port_scale.median():.1f})")
sites[["sessions_day", "kwh_day", "utilisation_24h", "utilisation_peak", "p_wait", "mean_wait_min"]].describe().round(2).T""",
    ),
    ("md", "## 1. Where load concentrates and where queues form"),
    (
        "code",
        """s = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(sites.lon, sites.lat), crs=4326).to_crs(27700)
fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
boroughs().boundary.plot(ax=axes[0], color="#bbbbbb", linewidth=0.4)
s.plot(ax=axes[0], markersize=np.sqrt(s.sessions_day) * 2, column="utilisation_24h", cmap="viridis", vmin=0, vmax=0.6, alpha=0.85, legend=True, legend_kwds={"label": "24h utilisation", "shrink": 0.6})
axes[0].set_axis_off(); axes[0].set_title("Rapid sites: size = expected sessions/day, colour = utilisation", loc="left")
boroughs().boundary.plot(ax=axes[1], color="#bbbbbb", linewidth=0.4)
s.plot(ax=axes[1], markersize=14, column="p_wait", cmap="Reds", vmin=0, vmax=1, legend=True, legend_kwds={"label": "P(wait) at peak hour", "shrink": 0.6})
axes[1].set_axis_off(); axes[1].set_title("Probability of waiting at the peak hour (Erlang C)", loc="left")
plt.tight_layout(); save(fig, "03_site_load_queues.png"); plt.show()
print(f"sites with P(wait) > 0.5 at peak: {(sites.p_wait > 0.5).sum()} of {len(sites)}; median expected wait {sites.mean_wait_min.replace(np.inf, np.nan).median():.1f} min")
sites.sort_values("sessions_day", ascending=False)[["borough", "operator", "power_kw", "ports", "sessions_day", "utilisation_24h", "p_wait", "mean_wait_min"]].head(10).round(2)""",
    ),
    ("md", "## 2. What drivers experience, by hex"),
    (
        "code",
        """g = feats.merge(svc, on="h3", how="left")
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
hex_map(g, "expected_wait_min", "Expected wait faced by a hex's drivers at the peak hour (min)", cmap="YlOrRd", vmin=0, vmax=30, ax=axes[0], legend_label="min")
hex_map(g, "n_rapid_within_10min", "Rapid sites reachable within 10 min drive", cmap="Blues", scheme="quantiles", k=6, ax=axes[1], legend_label="sites")
plt.tight_layout(); save(fig, "03_hex_experience.png"); plt.show()""",
    ),
    ("md", "## 3. Incremental demand vs cannibalisation for a candidate hub"),
    (
        "code",
        """from chargescape.models.choice import utilities, incremental_demand, choice_probabilities
from chargescape.features.travel_time import travel_time_minutes
from chargescape.models.allocation_pipeline import rapid_sites, KWH_PER_RAPID_SESSION
rs = rapid_sites()
tt, method = travel_time_minutes(feats, rs, name="hex_r8_to_rapid")
tt = np.where(np.isfinite(tt), tt, 1e6)
d26 = pd.read_parquet(PROCESSED / "demand_r8.small.parquet"); d26 = d26[d26.scenario == "2026"].set_index("h3").reindex(feats.h3)
demand = (d26.dest_kwh_p50.fillna(0) + d26.phv_kwh_p50.fillna(0)).to_numpy() / KWH_PER_RAPID_SESSION / 365
p = ChoiceParams(outside_utility=0.0)
v = utilities(tt, rs.price.to_numpy(), rs.power_kw.to_numpy(), rs.ports.to_numpy(), None, p)
# candidate: the hex with the largest unserved demand
svc_i = svc.set_index("h3").reindex(feats.h3)
cand_idx = int(np.argmax(svc_i.unserved_sessions_day.fillna(0).to_numpy() + demand * np.clip(svc_i.expected_wait_min.fillna(0).to_numpy() / 30, 0, 1)))
cand = feats.iloc[[cand_idx]][["h3", "lat", "lon", "borough"]]
ttc, _ = travel_time_minutes(feats, cand, name="hex_r8_to_democand", cache=False)
ttc = np.where(np.isfinite(ttc), ttc, 1e6)
rows = []
for kw, ports in [(50, 2), (150, 4), (150, 8), (300, 8)]:
    vc = utilities(ttc, np.array([79.0]), np.array([float(kw)]), np.array([float(ports)]), None, p)[:, 0]
    r = incremental_demand(demand, v, vc, outside_utility=0.0); r.update({"power_kw": kw, "ports": ports}); rows.append(r)
print("candidate hub in", cand.borough.iloc[0], cand.h3.iloc[0])
pd.DataFrame(rows)[["power_kw", "ports", "captured", "new", "cannibalised", "cannibalisation_share"]].round(1)""",
    ),
    (
        "md",
        """**Reading.** Even at the hex with the largest unmet demand, a new hub takes a substantial share of its sessions from existing sites; bigger and faster hubs capture more in total but also cannibalise more. This is the number an investor or partner needs next to the headline "expected sessions", and it is exactly what a pure gap map cannot show. Parameters are literature-informed; the sensitivity of siting to them is reported in notebook 04.""",
    ),
]
nb(nb03, NB / "03_choice_and_queues.ipynb")

# ----------------------------------------------------------------------------- 04 siting
nb04 = [
    (
        "md",
        """# 04 · Siting new rapid hubs under budget, capacity, grid and demand uncertainty

**Question.** With a given budget, where should the next 4 × 150 kW hubs go so that the most currently unmet or queue-constrained rapid demand is served within 8 minutes' drive — and which choices stay good if demand is 30 % lower or higher?

**Method.** Candidates = plausible hexes (parking / fuel / retail present or heavy traffic, primary substation not RED), pre-filtered to the 500 with most local unmet demand. Capacitated maximal covering MILP (HiGHS via scipy) with per-hub capacity from Erlang C (P(wait) ≤ 15 % at peak) and a budget; robust two-stage version over P10/P50/P90 scenarios; greedy uncapacitated baseline for contrast.""",
    ),
    ("code", HEADER),
    (
        "code",
        """meta = json.loads((TABLES / "siting_meta_2026.json").read_text()); print(meta)
sweep = pd.read_csv(TABLES / "siting_budget_sweep_2026.csv")
cap = meta["hub_capacity_sessions_day"]
sweep["capacity_bound_share"] = sweep["covered_p50"] / (sweep["n_hubs"] * cap)  # 1.0 = every hub is full
sweep["hubs_needed_for_all_unmet"] = np.ceil(sweep["total_unmet_p50"] / cap).astype(int)
sweep.round(3)""",
    ),
    (
        "code",
        """fig, ax = plt.subplots(figsize=(7, 4.5))
ax.plot(sweep.budget_m, sweep.covered_p50, "o-", label="capacitated MCLP (exact)")
ax.plot(sweep.budget_m, sweep.greedy_uncapacitated_covered, "s--", label="greedy, uncapacitated (optimistic)")
ax.set_xlabel("budget, £M"); ax.set_ylabel("unmet rapid sessions/day served"); ax.set_title("Budget → served unmet demand (2026, P50)", loc="left"); ax.legend(frameon=False); ax.grid(alpha=0.3)
save(fig, "04_budget_curve.png"); plt.show()""",
    ),
    ("md", "## Selected hubs (P50 vs robust) at £20M"),
    (
        "code",
        """sel = pd.read_parquet(PROCESSED / "siting_selected_2026.small.parquet")
b = 20.0 if (sel.budget_m == 20.0).any() else sel.budget_m.max()
s20 = sel[sel.budget_m == b]
both = set(s20[s20.model == "p50"].h3) & set(s20[s20.model == "robust"].h3)
print(f"budget £{b:.0f}M: {len(s20[s20.model=='p50'])} hubs (P50), {len(s20[s20.model=='robust'])} hubs (robust), {len(both)} in both")
svc = pd.read_parquet(PROCESSED / "hex_service_2026.small.parquet")
g = feats.merge(svc, on="h3", how="left")
g["unmet"] = g["unserved_sessions_day"].fillna(0) + g["rapid_sessions_day"].fillna(0) * g["served_share"].fillna(0) * np.clip(g["expected_wait_min"].fillna(0) / 30, 0, 1)
fig, ax = plt.subplots(figsize=(10, 8))
hex_map(g, "unmet", "Unmet / queue-constrained rapid demand 2026 (sessions/day) with selected hubs", cmap="Greys", scheme="quantiles", k=6, ax=ax, legend_label="sessions/day")
hexes = feats.set_index("h3")
for model, color, marker in [("p50", "#e4572e", "o"), ("robust", "#1b4965", "^")]:
    pts = hexes.loc[s20[s20.model == model].h3]
    gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat), crs=4326).to_crs(27700).plot(ax=ax, color=color, marker=marker, markersize=60, label=f"{model} ({len(pts)})", edgecolor="white")
ax.legend(loc="lower right", frameon=False); save(fig, "04_selected_hubs.png"); plt.show()
s20.groupby(["model", "borough"]).size().unstack(0).fillna(0).astype(int).sort_values("p50", ascending=False).head(15)""",
    ),
    (
        "md",
        """## Reading
* **The regime is capacity-bound, not location-bound.** With a 15 % peak-wait service level a 4 × 150 kW hub absorbs about 33 sessions/day, so covered demand rises almost linearly with budget (`capacity_bound_share` ≈ 1) until the ~90 hubs needed to absorb today's unmet demand. The exact model therefore serves a fraction of what the greedy uncapacitated estimate claims — that gap is demand a hub physically cannot take at an acceptable wait, which naïve coverage models hand out for free.
* **Low overlap between the P50 and robust solutions is degeneracy, not fragility.** When every hub fills up, many candidate sets are near-equivalent; the robust model simply picks another equivalent set. The operationally useful reading is the *set of hexes that appear in either* solution — the demand-dense corridors where hubs pay back under any scenario — and the phasing question becomes "how many hubs per corridor", which the queue model answers.
* Every selected hex carries its primary-substation headroom label, so a RED site never enters the candidate set and loaded primaries pay a connection uplift.
* Relaxing the service level (e.g. P(wait) ≤ 30 %) or larger hubs (8 ports) raise per-hub capacity and shift the regime back towards location choice — a one-line change in `siting_pipeline.py` to explore.""",
    ),
]
nb(nb04, NB / "04_siting.ipynb")

# ----------------------------------------------------------------------------- 05 utilisation transfer
nb05 = [
    (
        "md",
        """# 05 · Can context features explain observed charger utilisation? A transfer test

**Question.** In cities that publish session logs (Dundee, Perth & Kinross, Palo Alto, Boulder), how much of the variation in sessions per charger per day is explained by OpenStreetMap context, population and charger power — and does a model trained in some cities transfer to another? This is the honest counterpart to any "AI site-selection" claim: the target here is **observed** usage, not "where chargers already are".

**Method.** LightGBM on station features (`chargescape.features.station_context`), log target, three CV schemes: random 5-fold (optimistic), leave-city-out (the realistic transfer setting), and within-Dundee leave-cluster-out. Quantile models for P10/P90. Then the fitted model scores London's rapid sites and is compared with the structural allocation from notebook 03.""",
    ),
    ("code", HEADER),
    (
        "code",
        """from chargescape.models.ml import cross_validate, fit_lgbm, fit_quantiles, interval_coverage, pinball_loss
sf = pd.read_parquet(PROCESSED / "station_features.small.parquet")
train = sf[sf.city != "london"].dropna(subset=["sessions_per_day"]).copy()
train = train[train.active_days >= 60]
print(train.groupby("city").agg(n=("station_id", "size"), spd_median=("sessions_per_day", "median"), kwh_day=("kwh_per_day", "median"), rapid_share=("is_rapid", "mean")).round(2))
feat_cols = [c for c in sf.columns if c.startswith(("poi_", "parking_capacity", "dist_", "pop_")) and pd.api.types.is_numeric_dtype(sf[c])] + ["power_kw_f", "is_rapid_f"]
for d in (sf, train):
    d["power_kw_f"] = d["power_kw"].fillna(d.groupby("city")["power_kw"].transform("median")).fillna(7.0)
    d["is_rapid_f"] = (d["power_kw_f"] >= 50).astype(int)
X = train[feat_cols].astype(float); y = train["sessions_per_day"].to_numpy()
groups_city = train["city"].to_numpy()""",
    ),
    ("md", "## 1. Random vs leave-city-out cross-validation"),
    (
        "code",
        """rows = []
r_rand = cross_validate(X, y, None, n_splits=5, num_rounds=300, log_target=True); rows.append({"scheme": "random 5-fold", "MAE": r_rand.mae, "R2": r_rand.r2})
r_city = cross_validate(X, y, groups_city, n_splits=4, num_rounds=300, log_target=True); rows.append({"scheme": "leave-city-out", "MAE": r_city.mae, "R2": r_city.r2})
Xd = X[train.city == "dundee"]; yd = y[train.city.to_numpy() == "dundee"]
import h3 as _h3
gd = np.array([_h3.latlng_to_cell(a, b, 6) for a, b in zip(train.loc[train.city == "dundee", "lat"], train.loc[train.city == "dundee", "lon"])])
r_dund = cross_validate(Xd, yd, gd, n_splits=min(5, len(set(gd))), num_rounds=300, log_target=True); rows.append({"scheme": "Dundee only, leave-H3(6)-cluster-out", "MAE": r_dund.mae, "R2": r_dund.r2})
cv = pd.DataFrame(rows).round(3); print(cv.to_string(index=False))
from sklearn.metrics import mean_absolute_error, r2_score
from scipy.stats import spearmanr
oof = r_city.oof
per_city = pd.DataFrame([{"city": c, "n": int((groups_city == c).sum()), "MAE": mean_absolute_error(y[groups_city == c], oof[groups_city == c]), "R2": r2_score(y[groups_city == c], oof[groups_city == c]), "Spearman": spearmanr(y[groups_city == c], oof[groups_city == c]).correlation} for c in sorted(pd.unique(groups_city))]).round(2)
print(); print("per-city scores when trained on the other three cities (level vs ranking):"); print(per_city.to_string(index=False))
# level-free variant: predict each station's usage relative to its city's median (removes the city level shift)
y_rel = np.log1p(y) - pd.Series(np.log1p(y)).groupby(groups_city).transform("median").to_numpy()
r_rel = cross_validate(X, y_rel, groups_city, n_splits=4, num_rounds=300, log_target=False)
rel_city = pd.DataFrame([{"city": c, "Spearman_within_city": spearmanr(y_rel[groups_city == c], r_rel.oof[groups_city == c]).correlation} for c in sorted(pd.unique(groups_city))]).round(2)
print(); print(f"level-free target (log usage relative to city median), leave-city-out R2 = {r_rel.r2:.2f}"); print(rel_city.to_string(index=False))""",
    ),
    (
        "md",
        """**Reading — the result is negative, and that is the point.** Random 5-fold reports a respectable R² because charger power and the city's overall level leak across folds. Leave-city-out R² is below zero: a model trained on three cities does not predict the fourth's usage level, and it does not reliably predict the *ranking* within the held-out city either (Spearman from −0.3 to +0.6 depending on the city). Removing the city level (relative target) helps only marginally. With ~200 chargers and OpenStreetMap context, "where the amenities are" explains little of where people actually charge — power, operator, pricing and network effects dominate. This is exactly the kind of evidence a hiring manager should ask for before trusting any geo-embedding site model: the validation must be out-of-city and against observed usage.""",
    ),
    ("md", "## 2. What the model uses"),
    (
        "code",
        """m = fit_lgbm(X, np.log1p(y), num_rounds=300)
imp = pd.Series(m.feature_importance("gain"), index=feat_cols).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(7, 5)); barh(imp.head(15), "LightGBM gain importance (pooled 4 cities)", ax=ax); save(fig, "05_importance.png"); plt.show()
try:
    import shap
    ex = shap.TreeExplainer(m); sv = ex.shap_values(X)
    fig = plt.figure(figsize=(7, 5)); shap.summary_plot(sv, X, max_display=12, show=False); save(fig, "05_shap.png"); plt.show()
except Exception as e:
    print("shap skipped:", e)""",
    ),
    (
        "md",
        "## 3. Scoring London's rapid sites — does the transferred ranking agree with the structural allocation?",
    ),
    (
        "code",
        """lon = sf[(sf.city == "london")].copy()
lon = lon[lon["is_rapid_f"] == 1]
qm = fit_quantiles(X, np.log1p(y), quantiles=(0.1, 0.5, 0.9), num_rounds=300)
for q, mod in qm.items():
    lon[f"pred_spd_p{int(q*100)}"] = np.expm1(mod.predict(lon[feat_cols].astype(float)))
lon["pred_spd_p50"] = lon["pred_spd_p50"].clip(lower=0)
alloc = pd.read_parquet(PROCESSED / "rapid_sites_load_2026.small.parquet")
j = lon.merge(alloc[["site_id", "sessions_day", "ports", "borough"]], left_on="station_id", right_on="site_id", how="inner")
j["alloc_per_port"] = j["sessions_day"] / j["ports"].clip(lower=1)
from scipy.stats import spearmanr
rho = spearmanr(j["pred_spd_p50"], j["alloc_per_port"]).correlation
print(f"London rapid sites scored: {len(j)}; Spearman(transfer model, structural allocation per port) = {rho:.2f}")
fig, ax = plt.subplots(figsize=(6, 5)); ax.scatter(j["alloc_per_port"], j["pred_spd_p50"], s=10, alpha=0.5)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("structural allocation, sessions/day per port (nb 03)"); ax.set_ylabel("transfer model, sessions/day per charger (P50)")
ax.set_title(f"Two independent views of London rapid-site demand (ρ = {rho:.2f})", loc="left"); save(fig, "05_transfer_vs_structural.png"); plt.show()
j.groupby("borough")[["pred_spd_p50", "alloc_per_port"]].median().sort_values("pred_spd_p50", ascending=False).round(2).head(10)""",
    ),
    (
        "md",
        """## Reading
Two models that share no parameters — a structural demand model driven by EV stock, housing and traffic, and a transfer model trained on observed sessions elsewhere — produce **essentially uncorrelated** rankings of London's rapid sites (ρ reported above). Given the transfer model's out-of-city failure, the disagreement says more about the transfer model than about London. The structural model at least reproduces observed aggregates (notebook 02); the transfer model reproduces nothing outside its training cities. Both are weaker than one season of the network's own data — which is why the README sets out what to measure once hubs open, and why the choice model's parameters are flagged as the first thing to estimate from revealed preferences.""",
    ),
]
nb(nb05, NB / "05_utilisation_transfer.ipynb")

print("notebooks written:", sorted(p.name for p in NB.glob("*.ipynb")))
