"""Network travel-time accessibility on an OSM drive graph using igraph (fast Dijkstra).

Why igraph and not OSRM: the project must be reproducible on a laptop without Docker.
igraph's C core computes many-to-many shortest paths on the ~300k-node London graph in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

import igraph as ig
import networkx as nx
import numpy as np
import osmnx as ox


@dataclass
class RoadGraph:
    g: ig.Graph
    node_ids: np.ndarray  # osmid per igraph vertex index
    index_of: dict[int, int]
    nx_graph: nx.MultiDiGraph

    @classmethod
    def from_networkx(cls, G: nx.MultiDiGraph, weight: str = "travel_time") -> RoadGraph:
        nodes = np.array(list(G.nodes))
        index_of = {n: i for i, n in enumerate(nodes)}
        edges, weights = [], []
        for u, v, data in G.edges(data=True):
            edges.append((index_of[u], index_of[v]))
            weights.append(float(data.get(weight, np.nan)))
        g = ig.Graph(n=len(nodes), edges=edges, directed=True)
        w = np.array(weights)
        if np.isnan(w).any():  # fall back to length/ (30 km/h) if travel_time missing
            lengths = np.array([float(d.get("length", 100.0)) for _, _, d in G.edges(data=True)])
            w = np.where(np.isnan(w), lengths / (30 / 3.6), w)
        g.es["weight"] = w.tolist()
        return cls(g=g, node_ids=nodes, index_of=index_of, nx_graph=G)

    def nearest_vertices(self, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
        osmids = ox.distance.nearest_nodes(self.nx_graph, X=np.asarray(lons), Y=np.asarray(lats))
        return np.array([self.index_of[o] for o in np.atleast_1d(osmids)])

    def travel_time_matrix(self, sources: np.ndarray, targets: np.ndarray, chunk: int = 2000) -> np.ndarray:
        """Seconds from each source vertex to each target vertex (directed). Shape (S, T)."""
        out = np.empty((len(sources), len(targets)), dtype=np.float32)
        for i in range(0, len(sources), chunk):
            block = self.g.distances(
                source=sources[i : i + chunk].tolist(), target=targets.tolist(), weights="weight", mode="out"
            )
            out[i : i + chunk] = np.array(block, dtype=np.float32)
        return out


def accessibility_features(
    tt: np.ndarray, thresholds_min: tuple[int, ...] = (2, 5, 10), target_weights: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    """Row-wise accessibility summaries from a travel-time matrix in seconds.

    Returns nearest travel time (minutes) and counts (or weighted sums) of targets reachable
    within each threshold — the 2/5/10-minute logic used by practitioners.
    """
    tt_min = tt / 60.0
    feats = {"tt_nearest_min": np.nanmin(np.where(np.isfinite(tt_min), tt_min, np.nan), axis=1)}
    w = np.ones(tt.shape[1]) if target_weights is None else np.asarray(target_weights, dtype=float)
    for th in thresholds_min:
        feats[f"n_within_{th}min"] = ((tt_min <= th) * w).sum(axis=1)
    return feats


def gravity_access(tt: np.ndarray, target_weights: np.ndarray, beta: float = 0.25) -> np.ndarray:
    """Hansen-type gravity accessibility: sum_j w_j * exp(-beta * t_ij[min])."""
    tt_min = np.where(np.isfinite(tt), tt / 60.0, np.inf)
    return (np.asarray(target_weights) * np.exp(-beta * tt_min)).sum(axis=1)
