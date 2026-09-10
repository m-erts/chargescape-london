"""OpenStreetMap context layers for Greater London (road network, POIs, landuse).

Artefacts (EPSG:4326 unless noted):
  data/raw/osm/greater-london-latest.osm.pbf         Geofabrik extract (+ .md5), archived raw snapshot
  data/raw/osm/overpass_cache/                       osmnx HTTP cache (Overpass responses)
  data/interim/osm/greater_london_boundary.parquet   Greater London admin boundary (OSM relation 175342)
  data/interim/osm/london_drive.graphml              osmnx drive network, simplified, speeds + travel times
  data/interim/osm/london_drive_nodes.parquet        graph nodes (GeoParquet)
  data/interim/osm/london_drive_edges.parquet        graph edges (GeoParquet)
  data/interim/osm/london_major_roads.parquet        edges with highway in {motorway, trunk, primary, secondary}
  data/interim/osm/pois.parquet                      POI points by category (polygons -> centroid)
  data/interim/osm/landuse.parquet                   commercial / industrial / retail polygons with area_m2
  data/interim/osm/osm_build_report.json             timings, counts, backend actually used

Two interchangeable backends produce the graph / POIs / landuse:
  * "overpass": osmnx -> public Overpass API (live OSM data, polite rate limiting, on-disk cache).
  * "pbf":      pyosmium over the archived Geofabrik extract (fully offline, reproducible snapshot).
                The drive graph is still built by osmnx (graph_from_xml on a highway-filtered XML
                extract) and post-processed exactly like graph_from_polygon does.
  "auto" (default) health-checks Overpass first and falls back to "pbf" when Overpass is down or a
  query keeps failing after retries.

Usage (from repo root):
  PYTHONPATH=src python -m chargescape.data.osm [--source auto|overpass|pbf] [--force]
                                                 [--only pbf boundary graph pois landuse]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import requests
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon, box

from chargescape.utils.http import UA, download
from chargescape.utils.paths import INTERIM, RAW

log = logging.getLogger("chargescape.data.osm")

# --------------------------------------------------------------------------------------
# Constants / paths
# --------------------------------------------------------------------------------------
PLACE = "Greater London, England, United Kingdom"
GEOFABRIK_URL = "https://download.geofabrik.de/europe/united-kingdom/england/greater-london-latest.osm.pbf"
# south, west, north, east -- only used if Nominatim is unavailable and no cached boundary exists
BBOX_FALLBACK = (51.28, -0.51, 51.70, 0.33)

RAW_OSM = RAW / "osm"
INTERIM_OSM = INTERIM / "osm"
PBF_PATH = RAW_OSM / "greater-london-latest.osm.pbf"
PBF_META_PATH = RAW_OSM / "greater-london-latest.meta.json"
OVERPASS_CACHE = RAW_OSM / "overpass_cache"
BOUNDARY_PATH = INTERIM_OSM / "greater_london_boundary.parquet"
GRAPHML_PATH = INTERIM_OSM / "london_drive.graphml"
NODES_PATH = INTERIM_OSM / "london_drive_nodes.parquet"
EDGES_PATH = INTERIM_OSM / "london_drive_edges.parquet"
MAJOR_ROADS_PATH = INTERIM_OSM / "london_major_roads.parquet"
DRIVE_XML_PATH = INTERIM_OSM / "london_drive_highways.osm.bz2"
POIS_PATH = INTERIM_OSM / "pois.parquet"
LANDUSE_PATH = INTERIM_OSM / "landuse.parquet"
REPORT_PATH = INTERIM_OSM / "osm_build_report.json"

CRS_WGS84 = "EPSG:4326"
CRS_BNG = "EPSG:27700"  # British National Grid, metres

MAJOR_HIGHWAYS = ("motorway", "trunk", "primary", "secondary")

# POI category -> ordered list of (key, allowed values | None = any value). First matching rule wins
# within a category; an element may legitimately fall into more than one category.
POI_RULES: dict[str, list[tuple[str, tuple[str, ...] | None]]] = {
    "fuel": [("amenity", ("fuel",))],
    "parking": [("amenity", ("parking",))],  # amenity=parking_entrance is *not* matched
    "supermarket": [("shop", ("supermarket",))],
    "retail": [
        ("shop", ("mall", "department_store", "convenience", "doityourself", "furniture", "electronics"))
    ],
    "food": [("amenity", ("restaurant", "cafe", "fast_food", "pub", "bar"))],
    "hotel": [("tourism", ("hotel", "hostel", "guest_house", "motel"))],
    "leisure": [
        ("leisure", ("fitness_centre", "sports_centre", "stadium")),
        ("amenity", ("cinema", "theatre")),
        ("tourism", ("attraction", "museum")),
    ],
    "health": [("amenity", ("hospital", "clinic"))],
    "education": [("amenity", ("university", "college", "school"))],
    "office": [("office", None), ("building", ("office",))],
    "car": [("shop", ("car", "car_repair")), ("amenity", ("car_wash", "car_rental", "taxi"))],
}
POI_TAG_KEYS = ("amenity", "shop", "tourism", "leisure", "office", "building")
POI_EXTRA_KEYS = ("name", "brand", "operator", "parking", "capacity")
LANDUSE_VALUES = ("commercial", "industrial", "retail")
POI_COLUMNS = [
    "osm_id",
    "element_type",
    "category",
    "subcategory",
    "name",
    "brand",
    "operator",
    "parking_type",
    "capacity",
    "source_geom",
    "geometry",
]

# osmnx "drive" network filter (osmnx 2.1, ox._overpass._get_network_filter("drive")), replicated as
# python predicates for the PBF backend. Overpass "!~" is an unanchored regex, so re.search is used.
_RE_HW_EXCLUDE = re.compile(
    "abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|escalator|footway|no|"
    "path|pedestrian|planned|platform|proposed|raceway|razed|rest_area|service|services|steps|track"
)
_RE_SERVICE_EXCLUDE = re.compile("alley|driveway|emergency_access|parking|parking_aisle|private")


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def __call__(self) -> float:
        return round(time.perf_counter() - self.t0, 1)


def _configure_osmnx() -> None:
    OVERPASS_CACHE.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OVERPASS_CACHE)
    ox.settings.log_console = False
    ox.settings.log_file = False
    ox.settings.requests_timeout = 300  # also becomes the Overpass [timeout:] server-side budget
    ox.settings.overpass_rate_limit = True  # ask /api/status for a free slot before each query
    # split big polygons into ~31 km quadrats -> a few medium Overpass requests instead of one huge one
    ox.settings.max_query_area_size = 1e9
    ox.settings.http_user_agent = UA


# --------------------------------------------------------------------------------------
# A1. Geofabrik PBF
# --------------------------------------------------------------------------------------
def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_pbf(force: bool = False) -> Path:
    """Download the Geofabrik Greater London extract (+ md5) and verify the checksum. Idempotent."""
    RAW_OSM.mkdir(parents=True, exist_ok=True)
    md5_path = PBF_PATH.with_suffix(".pbf.md5")
    if force:
        for p in (PBF_PATH, md5_path, PBF_META_PATH):
            p.unlink(missing_ok=True)
    if PBF_PATH.exists() and PBF_META_PATH.exists():
        log.info("PBF already present: %s (%.1f MB)", PBF_PATH, PBF_PATH.stat().st_size / 1e6)
        return PBF_PATH

    head = requests.head(GEOFABRIK_URL, headers={"User-Agent": UA}, timeout=60, allow_redirects=True)
    head.raise_for_status()
    size_mb = int(head.headers.get("Content-Length", 0)) / 1e6
    log.info("Geofabrik HEAD: %.1f MB, Last-Modified %s", size_mb, head.headers.get("Last-Modified"))
    if size_mb > 400:
        raise RuntimeError(f"unexpectedly large extract ({size_mb:.0f} MB) - refusing to download")

    t = Timer()
    download(GEOFABRIK_URL, PBF_PATH, timeout=600, retries=3)
    download(GEOFABRIK_URL + ".md5", md5_path, timeout=60, retries=3)
    expected = md5_path.read_text().split()[0]
    actual = _md5(PBF_PATH)
    if actual != expected:
        PBF_PATH.unlink(missing_ok=True)
        raise RuntimeError(f"md5 mismatch for {PBF_PATH}: {actual} != {expected}")
    meta = {
        "url": GEOFABRIK_URL,
        "size_bytes": PBF_PATH.stat().st_size,
        "md5": actual,
        "last_modified_header": head.headers.get("Last-Modified"),
        "retrieved_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    try:  # data timestamp from the PBF header (osmium is optional here)
        import osmium

        reader = osmium.io.Reader(str(PBF_PATH))
        meta["osm_data_timestamp"] = reader.header().get("osmosis_replication_timestamp")
        reader.close()
    except Exception as e:  # noqa: BLE001
        log.warning("could not read PBF header: %s", e)
    PBF_META_PATH.write_text(json.dumps(meta, indent=2))
    log.info("PBF downloaded + verified in %.1fs: md5 %s", t(), actual)
    return PBF_PATH


# --------------------------------------------------------------------------------------
# Boundary
# --------------------------------------------------------------------------------------
def get_boundary(force: bool = False) -> gpd.GeoDataFrame:
    """Greater London administrative boundary via Nominatim (osmnx), cached as GeoParquet."""
    INTERIM_OSM.mkdir(parents=True, exist_ok=True)
    if BOUNDARY_PATH.exists() and not force:
        return gpd.read_parquet(BOUNDARY_PATH)
    try:
        gdf = ox.geocode_to_gdf(PLACE)
        gdf = gdf[["display_name", "osm_type", "osm_id", "geometry"]].copy()
        gdf["source"] = "nominatim"
    except Exception as e:  # noqa: BLE001
        log.warning("Nominatim geocoding failed (%s); using bbox fallback %s", e, BBOX_FALLBACK)
        s, w, n, e_ = BBOX_FALLBACK
        gdf = gpd.GeoDataFrame(
            {"display_name": [PLACE], "osm_type": [None], "osm_id": [None], "source": ["bbox_fallback"]},
            geometry=[box(w, s, e_, n)],
            crs=CRS_WGS84,
        )
    gdf["area_km2"] = gdf.to_crs(CRS_BNG).area / 1e6
    gdf.to_parquet(BOUNDARY_PATH)
    log.info(
        "boundary: %s (%s/%s), %.0f km2",
        gdf.display_name.iloc[0],
        gdf.osm_type.iloc[0],
        gdf.osm_id.iloc[0],
        gdf.area_km2.iloc[0],
    )
    return gdf


# --------------------------------------------------------------------------------------
# Overpass helpers
# --------------------------------------------------------------------------------------
def overpass_healthy(attempts: int = 2) -> bool:
    """Tiny probe query against the configured Overpass endpoint."""
    url = ox.settings.overpass_url.rstrip("/") + "/interpreter"
    q = '[out:json][timeout:20];node["amenity"="fuel"](51.50,-0.14,51.52,-0.10);out 1;'
    for i in range(attempts):
        try:
            r = requests.post(url, data={"data": q}, headers={"User-Agent": UA}, timeout=(10, 40))
            if r.ok and "elements" in r.json():
                return True
            log.warning("Overpass probe %d: HTTP %s", i + 1, r.status_code)
        except Exception as e:  # noqa: BLE001
            log.warning("Overpass probe %d failed: %s", i + 1, type(e).__name__)
        time.sleep(10)
    return False


def _with_retries(fn, what: str, attempts: int = 4, base_sleep: int = 30):
    """Run an osmnx/Overpass call with exponential back-off (covers 429 / 504 / timeouts)."""
    from osmnx._errors import InsufficientResponseError

    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except InsufficientResponseError:
            log.info("%s: Overpass returned no elements (treated as empty)", what)
            return None
        except Exception as e:  # noqa: BLE001
            last = e
            wait = base_sleep * (2**i)
            log.warning(
                "%s failed (%s: %s) - retry %d/%d in %ds",
                what,
                type(e).__name__,
                str(e)[:120],
                i + 1,
                attempts,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"{what}: giving up after {attempts} attempts: {last}")


# --------------------------------------------------------------------------------------
# A2/A3. Drive graph
# --------------------------------------------------------------------------------------
def _drive_way_ok(tags) -> bool:
    """Python replica of the osmnx 'drive' Overpass filter."""
    hw = tags.get("highway")
    if not hw or _RE_HW_EXCLUDE.search(hw):
        return False
    if "yes" in (tags.get("area") or ""):
        return False
    if "private" in (tags.get("access") or ""):
        return False
    if "no" in (tags.get("motor_vehicle") or "") or "no" in (tags.get("motorcar") or ""):
        return False
    return not _RE_SERVICE_EXCLUDE.search(tags.get("service") or "")


def _pbf_to_drive_xml(pbf: Path, out: Path) -> dict[str, int]:
    """Filter the PBF to drivable highways (+ their nodes) and write OSM XML for osmnx."""
    import osmium

    n_ways = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with osmium.BackReferenceWriter(str(out), ref_src=str(pbf), overwrite=True, remove_tags=False) as writer:
        for w in osmium.FileProcessor(str(pbf), osmium.osm.WAY).with_filter(
            osmium.filter.KeyFilter("highway")
        ):
            if _drive_way_ok(w.tags):
                writer.add(w)
                n_ways += 1
    return {"drive_ways": n_ways}


def _graph_from_pbf(polygon: Polygon | MultiPolygon) -> nx.MultiDiGraph:
    """osmnx drive graph from the archived PBF, post-processed like ox.graph_from_polygon."""
    t = Timer()
    info = _pbf_to_drive_xml(PBF_PATH, DRIVE_XML_PATH)
    log.info("PBF -> %s: %d drivable ways in %.1fs", DRIVE_XML_PATH.name, info["drive_ways"], t())
    t = Timer()
    G_raw = ox.graph_from_xml(DRIVE_XML_PATH, bidirectional=False, simplify=False, retain_all=True)
    log.info(
        "graph_from_xml: %d nodes / %d edges (unsimplified) in %.1fs",
        len(G_raw),
        G_raw.number_of_edges(),
        t(),
    )
    # mirror graph_from_polygon: buffer 500 m, truncate, LCC, simplify, truncate to polygon, LCC, street_count
    poly_proj, crs_utm = ox.projection.project_geometry(polygon)
    poly_buff, _ = ox.projection.project_geometry(poly_proj.buffer(500), crs=crs_utm, to_latlong=True)
    G_buff = ox.truncate.truncate_graph_polygon(G_raw, poly_buff)
    G_buff = ox.truncate.largest_component(G_buff, strongly=False)
    G_buff = ox.simplification.simplify_graph(G_buff)
    G = ox.truncate.truncate_graph_polygon(G_buff, polygon)
    G = ox.truncate.largest_component(G, strongly=False)
    spn = ox.stats.count_streets_per_node(G_buff, nodes=G.nodes)
    nx.set_node_attributes(G, values=spn, name="street_count")
    return G


def _stringify_lists(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Parquet cannot store mixed scalar/list object columns: join lists with '|'."""
    for col in gdf.columns:
        if col == gdf.geometry.name or gdf[col].dtype != object:
            continue
        has_list = gdf[col].map(lambda v: isinstance(v, (list, tuple, set))).any()
        if has_list:
            gdf[col] = gdf[col].map(
                lambda v: "|".join(map(str, v))
                if isinstance(v, (list, tuple, set))
                else (None if v is None else str(v))
            )
    return gdf


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, (list, tuple)) and v else v


def build_drive_graph(source: str = "auto", force: bool = False) -> dict[str, Any]:
    """Build (or load) the Greater London drive network; save GraphML + node/edge GeoParquet + major roads."""
    INTERIM_OSM.mkdir(parents=True, exist_ok=True)
    _configure_osmnx()
    if (
        GRAPHML_PATH.exists()
        and NODES_PATH.exists()
        and EDGES_PATH.exists()
        and MAJOR_ROADS_PATH.exists()
        and not force
    ):
        nodes = pd.read_parquet(NODES_PATH, columns=["osmid"])
        edges = pd.read_parquet(EDGES_PATH, columns=["length"])
        stats = {
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "edge_km_directed": round(edges.length.sum() / 1000, 1),
            "skipped": True,
        }
        log.info("drive graph already built: %s", stats)
        return stats

    boundary = get_boundary()
    polygon = boundary.geometry.iloc[0]
    backend = source
    if backend == "auto":
        backend = "overpass" if overpass_healthy() else "pbf"
        log.info("auto backend -> %s", backend)

    t_total = Timer()
    G: nx.MultiDiGraph | None = None
    if backend == "overpass":
        try:
            G = _with_retries(
                lambda: ox.graph_from_polygon(polygon, network_type="drive", simplify=True),
                "graph_from_polygon(drive)",
                attempts=3,
                base_sleep=60,
            )
        except Exception as e:  # noqa: BLE001
            if source != "auto":
                raise
            log.error("Overpass graph build failed (%s); falling back to PBF backend", e)
            backend = "pbf"
    if G is None:
        if not PBF_PATH.exists():
            fetch_pbf()
        G = _graph_from_pbf(polygon)
    t_build = t_total()
    log.info(
        "graph built via %s: %d nodes / %d edges in %.1fs", backend, len(G), G.number_of_edges(), t_build
    )

    t = Timer()
    G = ox.routing.add_edge_speeds(G)  # km/h from maxspeed, imputed per highway type where missing
    G = ox.routing.add_edge_travel_times(G)  # seconds
    G.graph["backend"] = backend
    G.graph["built_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    ox.io.save_graphml(G, GRAPHML_PATH)
    log.info("speeds/travel times + GraphML saved in %.1fs", t())

    t = Timer()
    nodes, edges = ox.convert.graph_to_gdfs(
        G, nodes=True, edges=True, node_geometry=True, fill_edge_geometry=True
    )
    nodes = nodes.reset_index()
    edges = edges.reset_index()
    edges["highway_primary"] = edges["highway"].map(_first)
    edges["is_major"] = edges["highway"].map(
        lambda v: any(h in MAJOR_HIGHWAYS for h in (v if isinstance(v, list) else [v]))
    )
    nodes = _stringify_lists(nodes)
    edges = _stringify_lists(edges)
    nodes.to_parquet(NODES_PATH, index=False)
    edges.to_parquet(EDGES_PATH, index=False)
    keep = [
        c
        for c in (
            "u",
            "v",
            "key",
            "osmid",
            "highway",
            "highway_primary",
            "name",
            "ref",
            "oneway",
            "lanes",
            "maxspeed",
            "speed_kph",
            "length",
            "geometry",
        )
        if c in edges.columns
    ]
    major = edges.loc[edges.is_major, keep].copy()
    major.to_parquet(MAJOR_ROADS_PATH, index=False)
    log.info("nodes/edges/major-roads parquet written in %.1fs", t())

    Gu = ox.convert.to_undirected(G)
    hw_counts = edges.highway_primary.value_counts().to_dict()
    stats = {
        "backend": backend,
        "n_nodes": int(len(nodes)),
        "n_edges": int(len(edges)),
        "edge_km_directed": round(float(edges.length.sum()) / 1000, 1),
        "edge_km_undirected": round(sum(d["length"] for _, _, d in Gu.edges(data=True)) / 1000, 1),
        "n_major_edges": int(len(major)),
        "major_km_directed": round(float(major.length.sum()) / 1000, 1),
        "highway_counts": {str(k): int(v) for k, v in hw_counts.items()},
        "speed_kph_missing_before_impute": int(edges["maxspeed"].isna().sum())
        if "maxspeed" in edges
        else None,
        "seconds_build": t_build,
        "seconds_total": t_total(),
        "graphml_mb": round(GRAPHML_PATH.stat().st_size / 1e6, 1),
    }
    log.info("drive graph stats: %s", {k: v for k, v in stats.items() if k != "highway_counts"})
    return stats


# --------------------------------------------------------------------------------------
# B. POIs and landuse
# --------------------------------------------------------------------------------------
def match_categories(tags: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return [(category, subcategory), ...] for an OSM tag mapping (handles 'a;b' multi-values)."""
    out: list[tuple[str, str]] = []
    for cat, rules in POI_RULES.items():
        for key, allowed in rules:
            raw = tags.get(key)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == "":
                continue
            vals = [v.strip() for v in str(raw).split(";") if v.strip()]
            if not vals:
                continue
            if allowed is None:
                hit = vals[0]
            else:
                hit = next((v for v in vals if v in allowed), None)
            if hit is None:
                continue
            sub = "building_office" if key == "building" else hit
            out.append((cat, sub))
            break
    return out


def _to_capacity(v: Any) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return float("nan")
    m = re.search(r"\d+", str(v).replace(",", ""))
    return float(m.group()) if m else float("nan")


def _finalise_pois(rows: list[dict], geoms: list, boundary_poly) -> gpd.GeoDataFrame:
    """rows: dicts with everything but geometry; geoms: shapely geometries (any type) in EPSG:4326."""
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=CRS_WGS84)
    if gdf.empty:
        return gpd.GeoDataFrame(columns=POI_COLUMNS, geometry="geometry", crs=CRS_WGS84)
    gdf["source_geom"] = gdf.geometry.geom_type.map(
        lambda g: "point" if g == "Point" else ("polygon" if g in ("Polygon", "MultiPolygon") else "line")
    )
    not_point = gdf.source_geom != "point"
    if not_point.any():
        cent = gdf.loc[not_point].to_crs(CRS_BNG).geometry.centroid.to_crs(CRS_WGS84)
        gdf.loc[not_point, "geometry"] = cent
    gdf["capacity"] = gdf["capacity"].map(_to_capacity)
    inside = shapely.contains(boundary_poly, gdf.geometry.values)
    gdf = gdf[inside].drop_duplicates(["category", "osm_id"])
    gdf = gdf[POI_COLUMNS].sort_values(["category", "osm_id"]).reset_index(drop=True)
    return gdf


def _finalise_landuse(rows: list[dict], geoms: list, boundary_poly) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=CRS_WGS84)
    if gdf.empty:
        return gdf
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf = gdf[shapely.intersects(boundary_poly, gdf.geometry.values)]
    gdf["area_m2"] = gdf.to_crs(CRS_BNG).area.round(1)
    gdf = gdf.drop_duplicates("osm_id")
    cols = ["osm_id", "element_type", "landuse", "name", "area_m2", "geometry"]
    return gdf[cols].sort_values(["landuse", "osm_id"]).reset_index(drop=True)


# ---- Overpass backend ------------------------------------------------------------------
def _rules_to_osmnx_tags(rules) -> dict[str, bool | list[str]]:
    tags: dict[str, bool | list[str]] = {}
    for key, allowed in rules:
        if allowed is None:
            tags[key] = True
        elif tags.get(key) is not True:
            tags[key] = sorted(set(list(tags.get(key, [])) + list(allowed)))
    return tags


def _features_to_rows(gdf: gpd.GeoDataFrame, category: str | None) -> tuple[list[dict], list]:
    """Normalise an osmnx features GeoDataFrame into POI rows (category=None -> landuse rows)."""
    gdf = gdf.reset_index()
    el_col = "element" if "element" in gdf.columns else "element_type"
    id_col = "id" if "id" in gdf.columns else "osmid"
    keys = [k for k in (*POI_TAG_KEYS, *POI_EXTRA_KEYS, "landuse") if k in gdf.columns]
    tag_df = gdf[keys].astype(object).where(gdf[keys].notna(), None)
    rows, geoms = [], []
    for (_, tags), el, oid, geom in zip(
        tag_df.iterrows(), gdf[el_col], gdf[id_col], gdf.geometry, strict=True
    ):
        tags = tags.to_dict()
        base = {
            "osm_id": f"{el}/{oid}",
            "element_type": str(el),
            "name": tags.get("name"),
            "brand": tags.get("brand"),
            "operator": tags.get("operator"),
        }
        if category is None:
            lu = tags.get("landuse")
            if lu in LANDUSE_VALUES:
                rows.append({**base, "landuse": lu})
                geoms.append(geom)
            continue
        for cat, sub in match_categories(tags):
            if cat != category:
                continue
            rows.append(
                {
                    **base,
                    "category": cat,
                    "subcategory": sub,
                    "parking_type": tags.get("parking") if cat == "parking" else None,
                    "capacity": tags.get("capacity") if cat == "parking" else None,
                }
            )
            geoms.append(geom)
    return rows, geoms


def _pois_from_overpass(
    polygon, categories: Iterable[str], pause: float = 5.0
) -> dict[str, tuple[list[dict], list]]:
    """One osmnx features_from_polygon query per category (plus landuse), with etiquette pauses."""
    out: dict[str, tuple[list[dict], list]] = {}
    for cat in categories:
        tags = {"landuse": list(LANDUSE_VALUES)} if cat == "landuse" else _rules_to_osmnx_tags(POI_RULES[cat])
        t = Timer()
        gdf = _with_retries(lambda: ox.features_from_polygon(polygon, tags), f"features[{cat}]")
        if gdf is None or gdf.empty:
            out[cat] = ([], [])
        else:
            out[cat] = _features_to_rows(gdf, None if cat == "landuse" else cat)
        log.info(
            "overpass %-12s %6d features -> %6d rows in %.1fs",
            cat,
            0 if gdf is None else len(gdf),
            len(out[cat][0]),
            t(),
        )
        time.sleep(pause)
    return out


# ---- PBF backend -----------------------------------------------------------------------
def _pois_from_pbf(pbf: Path) -> tuple[list[dict], list, list[dict], list]:
    """Single pyosmium pass (nodes, open ways, assembled areas) -> POI rows + landuse rows."""
    import osmium

    fab = osmium.geom.WKBFactory()
    keys = (*POI_TAG_KEYS, "landuse")
    poi_rows: list[dict] = []
    poi_geoms: list = []
    lu_rows: list[dict] = []
    lu_geoms: list = []
    stats = {"nodes": 0, "open_ways": 0, "areas": 0, "geom_errors": 0}

    def handle(tags, osm_id: str, el: str, geom) -> None:
        name, brand, operator = tags.get("name"), tags.get("brand"), tags.get("operator")
        for cat, sub in match_categories(tags):
            poi_rows.append(
                {
                    "osm_id": osm_id,
                    "element_type": el,
                    "category": cat,
                    "subcategory": sub,
                    "name": name,
                    "brand": brand,
                    "operator": operator,
                    "parking_type": tags.get("parking") if cat == "parking" else None,
                    "capacity": tags.get("capacity") if cat == "parking" else None,
                }
            )
            poi_geoms.append(geom)
        lu = tags.get("landuse")
        if lu in LANDUSE_VALUES and geom.geom_type in ("Polygon", "MultiPolygon"):
            lu_rows.append({"osm_id": osm_id, "element_type": el, "landuse": lu, "name": name})
            lu_geoms.append(geom)

    fp = (
        osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY | osmium.osm.AREA)
        .with_locations()
        .with_areas()
        .with_filter(osmium.filter.KeyFilter(*keys))
    )
    for o in fp:
        tl = o.tags
        if not any(tl.get(k) for k in keys):  # KeyFilter already ensures this; cheap guard
            continue
        try:
            if o.is_node():
                if not o.location.valid():
                    continue
                stats["nodes"] += 1
                tags = {k: tl.get(k) for k in (*keys, *POI_EXTRA_KEYS)}
                handle(tags, f"node/{o.id}", "node", Point(o.location.lon, o.location.lat))
            elif o.is_way():
                if o.is_closed():
                    continue  # closed ways arrive as areas
                stats["open_ways"] += 1
                tags = {k: tl.get(k) for k in (*keys, *POI_EXTRA_KEYS)}
                handle(tags, f"way/{o.id}", "way", shapely.from_wkb(bytes.fromhex(fab.create_linestring(o))))
            elif o.is_area():
                stats["areas"] += 1
                el = "way" if o.from_way() else "relation"
                tags = {k: tl.get(k) for k in (*keys, *POI_EXTRA_KEYS)}
                handle(
                    tags,
                    f"{el}/{o.orig_id()}",
                    el,
                    shapely.from_wkb(bytes.fromhex(fab.create_multipolygon(o))),
                )
        except Exception:  # noqa: BLE001  (invalid / incomplete geometry at the extract edge)
            stats["geom_errors"] += 1
    log.info("PBF scan: %s", stats)
    return poi_rows, poi_geoms, lu_rows, lu_geoms


def fetch_pois(source: str = "auto", force: bool = False) -> dict[str, Any]:
    """POIs by category -> data/interim/osm/pois.parquet (also writes landuse.parquet when using the PBF)."""
    INTERIM_OSM.mkdir(parents=True, exist_ok=True)
    _configure_osmnx()
    if POIS_PATH.exists() and not force:
        gdf = gpd.read_parquet(POIS_PATH)
        log.info("pois already built (%d rows)", len(gdf))
        return {"skipped": True, "n_pois": len(gdf), "by_category": gdf.category.value_counts().to_dict()}

    boundary = get_boundary()
    polygon = boundary.geometry.iloc[0]
    backend = source
    if backend == "auto":
        backend = "overpass" if overpass_healthy() else "pbf"
        log.info("auto backend -> %s", backend)
    t = Timer()
    pois = landuse = None
    if backend == "overpass":
        try:
            res = _pois_from_overpass(polygon, list(POI_RULES))
            rows = [r for cat in POI_RULES for r in res[cat][0]]
            geoms = [g for cat in POI_RULES for g in res[cat][1]]
            pois = _finalise_pois(rows, geoms, polygon)
        except Exception as e:  # noqa: BLE001
            if source != "auto":
                raise
            log.error("Overpass POI queries failed (%s); falling back to PBF backend", e)
            backend = "pbf"
    if pois is None:
        if not PBF_PATH.exists():
            fetch_pbf()
        prow, pgeom, lrow, lgeom = _pois_from_pbf(PBF_PATH)
        pois = _finalise_pois(prow, pgeom, polygon)
        landuse = _finalise_landuse(lrow, lgeom, polygon)
        if landuse is not None and (force or not LANDUSE_PATH.exists()):
            landuse.to_parquet(LANDUSE_PATH, index=False)
            log.info("landuse.parquet written from PBF pass (%d polygons)", len(landuse))
    pois.to_parquet(POIS_PATH, index=False)
    by_cat = pois.category.value_counts().to_dict()
    by_sub = pois.groupby(["category", "subcategory"]).size().sort_values(ascending=False).head(60).to_dict()
    log.info("pois via %s: %d rows in %.1fs; by category: %s", backend, len(pois), t(), by_cat)
    return {
        "backend": backend,
        "n_pois": int(len(pois)),
        "by_category": {k: int(v) for k, v in by_cat.items()},
        "by_subcategory_top": {f"{k[0]}/{k[1]}": int(v) for k, v in by_sub.items()},
        "by_source_geom": pois.source_geom.value_counts().to_dict(),
        "seconds": t(),
    }


def fetch_landuse(source: str = "auto", force: bool = False) -> dict[str, Any]:
    """commercial/industrial/retail landuse polygons -> data/interim/osm/landuse.parquet."""
    INTERIM_OSM.mkdir(parents=True, exist_ok=True)
    _configure_osmnx()
    if LANDUSE_PATH.exists() and not force:
        gdf = gpd.read_parquet(LANDUSE_PATH)
        log.info("landuse already built (%d polygons)", len(gdf))
        return {"skipped": True, "n_polygons": len(gdf), "by_landuse": gdf.landuse.value_counts().to_dict()}
    boundary = get_boundary()
    polygon = boundary.geometry.iloc[0]
    backend = source
    if backend == "auto":
        backend = "overpass" if overpass_healthy() else "pbf"
    t = Timer()
    gdf = None
    if backend == "overpass":
        try:
            rows, geoms = _pois_from_overpass(polygon, ["landuse"])["landuse"]
            gdf = _finalise_landuse(rows, geoms, polygon)
        except Exception as e:  # noqa: BLE001
            if source != "auto":
                raise
            log.error("Overpass landuse query failed (%s); falling back to PBF backend", e)
            backend = "pbf"
    if gdf is None:
        if not PBF_PATH.exists():
            fetch_pbf()
        _, _, lrow, lgeom = _pois_from_pbf(PBF_PATH)
        gdf = _finalise_landuse(lrow, lgeom, polygon)
    gdf.to_parquet(LANDUSE_PATH, index=False)
    by_lu = gdf.landuse.value_counts().to_dict()
    area_km2 = gdf.groupby("landuse").area_m2.sum().div(1e6).round(2).to_dict()
    log.info("landuse via %s: %d polygons in %.1fs; %s; km2 %s", backend, len(gdf), t(), by_lu, area_km2)
    return {
        "backend": backend,
        "n_polygons": int(len(gdf)),
        "by_landuse": {k: int(v) for k, v in by_lu.items()},
        "area_km2_by_landuse": area_km2,
        "seconds": t(),
    }


# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["auto", "overpass", "pbf"], default="auto")
    ap.add_argument("--force", action="store_true", help="rebuild even if outputs exist")
    ap.add_argument(
        "--only", nargs="+", choices=["pbf", "boundary", "graph", "pois", "landuse"], default=None
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    steps = args.only or ["pbf", "boundary", "graph", "pois", "landuse"]

    report: dict[str, Any] = {
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_arg": args.source,
    }
    if REPORT_PATH.exists():
        try:
            report = {**json.loads(REPORT_PATH.read_text()), **report}
        except Exception:  # noqa: BLE001
            pass
    t_all = Timer()
    if "pbf" in steps:
        p = fetch_pbf(force=args.force)
        report["pbf"] = json.loads(PBF_META_PATH.read_text()) if PBF_META_PATH.exists() else {"path": str(p)}
    if "boundary" in steps:
        b = get_boundary(force=args.force)
        report["boundary"] = {
            "osm_type": b.osm_type.iloc[0],
            "osm_id": None if pd.isna(b.osm_id.iloc[0]) else int(b.osm_id.iloc[0]),
            "area_km2": round(float(b.area_km2.iloc[0]), 1),
            "source": b.source.iloc[0],
        }
    for step, fn in (("graph", build_drive_graph), ("pois", fetch_pois), ("landuse", fetch_landuse)):
        if step in steps:
            try:
                res = fn(source=args.source, force=args.force)
                prev = report.get(step)
                if (
                    res.get("skipped")
                    and isinstance(prev, dict)
                    and "error" not in prev
                    and "backend" in prev
                ):
                    report[step] = {**prev, "skipped_rerun": True}  # keep the rich stats from the real build
                else:
                    report[step] = res
            except Exception as e:  # noqa: BLE001
                log.exception("step %s failed", step)
                report[step] = {"error": f"{type(e).__name__}: {e}"}
    report["seconds_total"] = t_all()
    report["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    log.info("report -> %s (%.0fs total)", REPORT_PATH, report["seconds_total"])
    return report


if __name__ == "__main__":
    main()
