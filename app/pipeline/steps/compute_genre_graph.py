"""Compute genre co-occurrence graph.

Input: List of artist dicts (from aggregate step) — each has genres: list[str]
Output: Genre graph with nodes, edges, Louvain communities, bridges

Algorithm mirrors scripts/preprocessing/genre_graph/batch9_genre_graph.py.
"""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import networkx as nx

# python-louvain exposes community module
try:
    import community as community_louvain  # python-louvain
except ImportError:
    community_louvain = None


@dataclass
class GenreGraphConfig:
    """Configuration for genre graph computation."""
    min_track_count: int = 3       # minimum tracks for a genre node
    min_cooccurrence: int = 2      # minimum co-occurrence to create edge
    jaccard_threshold: float = 0.03  # minimum edge weight to keep
    top_bridges: int = 20


@dataclass
class GenreGraphResult:
    """Result of genre graph computation."""
    nodes: list[dict]
    edges: list[dict]
    communities: dict[str, int]    # genre → community_id
    bridges: list[str]
    stats: dict[str, Any]


def compute_genre_graph(
    artists: list[dict],
    config: GenreGraphConfig | None = None,
) -> GenreGraphResult:
    """Compute genre co-occurrence graph from aggregated artists.

    Args:
        artists: List of artist dicts with 'genres' and 'parent_genres' lists.
        config: Genre graph configuration.

    Returns:
        GenreGraphResult with nodes, edges, communities, bridges, stats.
    """
    if config is None:
        config = GenreGraphConfig()

    # --- Build genre profiles ---
    genre_tracks: dict[str, int] = defaultdict(int)
    genre_parents: dict[str, set] = defaultdict(set)
    genre_artists: dict[str, list] = defaultdict(list)

    for artist in artists:
        genres = artist.get("genres") or []
        parent_genres = artist.get("parent_genres") or []
        track_count = artist.get("track_count", 1)
        artist_name = artist.get("name") or artist.get("id", "")

        for g in genres:
            if not g:
                continue
            genre_tracks[g] += track_count
            for pg in parent_genres:
                if pg:
                    genre_parents[g].add(pg)
            genre_artists[g].append({"name": artist_name, "tracks": track_count})

    # Filter to genres with enough tracks
    valid_genres = {g for g, cnt in genre_tracks.items() if cnt >= config.min_track_count}

    # --- Co-occurrence from artists ---
    cooccur: dict[tuple, int] = defaultdict(int)
    for artist in artists:
        genres = [g for g in (artist.get("genres") or []) if g in valid_genres]
        for g1, g2 in combinations(sorted(set(genres)), 2):
            cooccur[(g1, g2)] += 1

    # Filter edges by minimum co-occurrence
    cooccur = {k: v for k, v in cooccur.items() if v >= config.min_cooccurrence}

    # --- Build weighted edges (Jaccard similarity) ---
    edges = []
    for (g1, g2), count in cooccur.items():
        union = genre_tracks[g1] + genre_tracks[g2] - count
        jaccard = count / union if union > 0 else 0.0
        if jaccard >= config.jaccard_threshold:
            edges.append({
                "source": g1,
                "target": g2,
                "weight": round(jaccard, 4),
                "cooccurrence": count,
            })

    # Nodes that appear in at least one edge
    connected_genres = set()
    for e in edges:
        connected_genres.add(e["source"])
        connected_genres.add(e["target"])

    # Fall back to all valid genres if very sparse
    graph_genres = connected_genres if connected_genres else valid_genres

    # --- NetworkX graph for community detection ---
    G = nx.Graph()
    for g in graph_genres:
        G.add_node(g)
    for e in edges:
        if e["source"] in graph_genres and e["target"] in graph_genres:
            G.add_edge(e["source"], e["target"], weight=e["weight"])

    # --- Louvain communities ---
    communities: dict[str, int] = {}
    if community_louvain and len(G.nodes) > 0:
        try:
            partition = community_louvain.best_partition(G, weight="weight", random_state=42)
            communities = partition
        except Exception:
            # Fallback: assign all to community 0
            communities = {g: 0 for g in G.nodes}
    else:
        # Fallback using networkx greedy modularity
        try:
            comp = nx.algorithms.community.greedy_modularity_communities(G, weight="weight")
            for comm_id, members in enumerate(comp):
                for m in members:
                    communities[m] = comm_id
        except Exception:
            communities = {g: 0 for g in G.nodes}

    # --- Betweenness centrality (sampled for speed) ---
    centrality: dict[str, float] = {}
    if len(G.nodes) > 0:
        try:
            k = min(100, len(G.nodes))
            centrality = nx.betweenness_centrality(G, k=k, weight="weight", normalized=True)
        except Exception:
            centrality = {g: 0.0 for g in G.nodes}

    # --- Bridge genres ---
    bridge_genres: list[str] = []
    if communities and centrality:
        # Genres connecting different communities with high betweenness
        sorted_by_centrality = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        seen_comms: set = set()
        for genre, score in sorted_by_centrality:
            if len(bridge_genres) >= config.top_bridges:
                break
            bridge_genres.append(genre)

    # --- Build node list ---
    nodes = []
    for g in graph_genres:
        parents = sorted(genre_parents.get(g, set()))
        sample = sorted(genre_artists.get(g, []), key=lambda x: x["tracks"], reverse=True)[:3]
        nodes.append({
            "id": g,
            "label": g,
            "track_count": genre_tracks.get(g, 0),
            "parent_genres": parents,
            "community": communities.get(g, 0),
            "is_bridge": g in set(bridge_genres[:config.top_bridges]),
            "centrality": round(centrality.get(g, 0.0), 4),
            "sample_artists": [s["name"] for s in sample],
        })

    num_communities = len(set(communities.values())) if communities else 0

    stats = {
        "total_genres_in_library": len(genre_tracks),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "num_communities": num_communities,
    }

    return GenreGraphResult(
        nodes=nodes,
        edges=edges,
        communities=communities,
        bridges=bridge_genres,
        stats=stats,
    )


def genre_graph_result_to_json(result: GenreGraphResult) -> dict:
    """Convert GenreGraphResult to JSON-serializable dict."""
    return {
        "nodes": result.nodes,
        "edges": result.edges,
        "communities": result.communities,
        "bridges": result.bridges,
        "stats": result.stats,
    }
