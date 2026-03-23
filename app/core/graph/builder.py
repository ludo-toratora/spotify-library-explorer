"""Graph building functions for artist similarity networks."""

from dataclasses import dataclass, field
from typing import Sequence
import numpy as np

from ..similarity import (
    combined_similarity,
    SimilarityWeights,
    WEIGHT_PRESETS,
)


@dataclass
class GraphNode:
    """A node in the similarity graph."""
    id: str
    track_count: int = 0
    genres: list[str] = field(default_factory=list)
    parent_genres: list[str] = field(default_factory=list)
    primary_decade: str = ""
    mean_year: int = 1990
    audio_profile: dict[str, float] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in the similarity graph."""
    source: str
    target: str
    weight: float
    audio_sim: float = 0.0
    genre_sim: float = 0.0
    era_sim: float = 0.0


@dataclass
class SimilarityGraph:
    """Complete similarity graph with nodes and edges."""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    preset: str = "balanced"
    k: int = 15
    threshold: float = 0.3


def build_knn_graph(
    artists: list[dict],
    k: int = 15,
    weights: SimilarityWeights | None = None,
    threshold: float = 0.3,
    preset_name: str | None = None
) -> SimilarityGraph:
    """
    Build a k-nearest-neighbor similarity graph from artist data.

    For each artist, connects to its k most similar neighbors.
    Edges below the threshold are excluded.

    Args:
        artists: List of artist dicts with keys:
            - name: str
            - track_count: int
            - audio_profile: dict
            - genres: list[str]
            - parent_genres: list[str]
            - primary_decade: str
            - mean_year: int
        k: Number of nearest neighbors per artist
        weights: Similarity weights. Uses preset_name or defaults to balanced.
        threshold: Minimum similarity to create edge
        preset_name: Name of weight preset (alternative to weights)

    Returns:
        SimilarityGraph with nodes and edges
    """
    # Resolve weights
    if weights is None:
        preset_name = preset_name or "balanced"
        weights = WEIGHT_PRESETS.get(preset_name, WEIGHT_PRESETS["balanced"])

    n = len(artists)

    # Compute pairwise similarity matrix
    similarity_matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(i + 1, n):
            result = combined_similarity(artists[i], artists[j], weights=weights)
            similarity_matrix[i, j] = result.combined
            similarity_matrix[j, i] = result.combined

    # Build k-NN edges
    edges: list[GraphEdge] = []
    edge_set: set[tuple[int, int]] = set()

    for i in range(n):
        # Get similarities for this artist
        sims = similarity_matrix[i].copy()
        sims[i] = -1  # Exclude self

        # Get top k neighbors
        top_k_indices = np.argsort(sims)[-k:]

        for j in top_k_indices:
            if sims[j] < threshold:
                continue

            # Avoid duplicate edges
            edge_key = tuple(sorted([i, j]))
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)

            # Compute component similarities for edge metadata
            result = combined_similarity(artists[i], artists[j], weights=weights)

            edges.append(GraphEdge(
                source=artists[i].get('name', str(i)),
                target=artists[j].get('name', str(j)),
                weight=round(result.combined, 4),
                audio_sim=round(result.audio, 4),
                genre_sim=round(result.genre, 4),
                era_sim=round(result.era, 4)
            ))

    # Build nodes
    nodes = [
        GraphNode(
            id=a.get('name', str(i)),
            track_count=a.get('track_count', 0),
            genres=a.get('genres', [])[:10],
            parent_genres=a.get('parent_genres', []),
            primary_decade=a.get('primary_decade', ''),
            mean_year=a.get('mean_year', 1990),
            audio_profile=a.get('audio_profile', {})
        )
        for i, a in enumerate(artists)
    ]

    return SimilarityGraph(
        nodes=nodes,
        edges=edges,
        preset=preset_name or "balanced",
        k=k,
        threshold=threshold
    )


def graph_to_adjacency(graph: SimilarityGraph) -> dict[str, list[tuple[str, float]]]:
    """
    Convert graph to adjacency list representation.

    Returns:
        {node_id: [(neighbor_id, weight), ...]}
    """
    adj: dict[str, list[tuple[str, float]]] = {node.id: [] for node in graph.nodes}

    for edge in graph.edges:
        adj[edge.source].append((edge.target, edge.weight))
        adj[edge.target].append((edge.source, edge.weight))

    return adj


def get_node_degree(graph: SimilarityGraph) -> dict[str, int]:
    """Get degree (number of connections) for each node."""
    degree: dict[str, int] = {node.id: 0 for node in graph.nodes}

    for edge in graph.edges:
        degree[edge.source] += 1
        degree[edge.target] += 1

    return degree


def get_weighted_degree(graph: SimilarityGraph) -> dict[str, float]:
    """Get weighted degree (sum of edge weights) for each node."""
    w_degree: dict[str, float] = {node.id: 0.0 for node in graph.nodes}

    for edge in graph.edges:
        w_degree[edge.source] += edge.weight
        w_degree[edge.target] += edge.weight

    return w_degree
