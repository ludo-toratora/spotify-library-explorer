"""Compute similarity graphs for all presets.

Input: List of artist dictionaries (from aggregate step)
Output: Graph data per preset (nodes, edges, communities, bridges)

Uses core modules:
- core.graph.build_knn_graph
- core.clustering.louvain_communities
- core.clustering.compute_centrality
- core.clustering.identify_bridges
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.graph import build_knn_graph, SimilarityGraph
from app.core.clustering import louvain_communities, compute_centrality, identify_bridges
from app.core.similarity import SimilarityWeights, WEIGHT_PRESETS


@dataclass
class GraphConfig:
    """Configuration for graph computation."""
    presets: list[str] = field(default_factory=lambda: list(WEIGHT_PRESETS.keys()))
    k_neighbors: int = 15
    min_similarity: float = 0.3
    compute_bridges: bool = True
    top_bridges: int = 20


@dataclass
class GraphResult:
    """Result for a single graph preset."""
    preset: str
    nodes: list[dict]
    edges: list[dict]
    communities: dict[str, int]
    num_communities: int
    modularity: float
    bridges: dict | None
    centrality: dict[str, dict] | None


@dataclass
class ComputeGraphsResult:
    """Result of computing all graphs."""
    graphs: dict[str, GraphResult]
    preset_count: int
    total_nodes: int
    total_edges: int


def compute_graphs(
    artists: list[dict],
    config: GraphConfig | None = None
) -> ComputeGraphsResult:
    """Compute similarity graphs for all configured presets.

    Args:
        artists: List of artist dictionaries with audio_profile, genres, mean_year
        config: Graph computation configuration

    Returns:
        ComputeGraphsResult with all graph data
    """
    if config is None:
        config = GraphConfig()

    graphs = {}
    total_edges = 0

    for preset in config.presets:
        result = compute_single_graph(artists, preset, config)
        graphs[preset] = result
        total_edges += len(result.edges)

    return ComputeGraphsResult(
        graphs=graphs,
        preset_count=len(graphs),
        total_nodes=len(artists),
        total_edges=total_edges,
    )


def compute_single_graph(
    artists: list[dict],
    preset: str,
    config: GraphConfig
) -> GraphResult:
    """Compute graph for a single preset.

    Args:
        artists: List of artist dictionaries
        preset: Preset name (e.g., "balanced")
        config: Graph configuration

    Returns:
        GraphResult with nodes, edges, communities, bridges
    """
    # Build k-NN graph using core module
    graph = build_knn_graph(
        artists,
        k=config.k_neighbors,
        preset_name=preset,
        threshold=config.min_similarity,
    )

    # Convert to dicts for community detection
    nodes = [_node_to_dict(n) for n in graph.nodes]
    edges = [_edge_to_dict(e) for e in graph.edges]

    # Detect communities
    community_result = louvain_communities(nodes, edges)

    # Compute centrality and bridges
    centrality_data = None
    bridges_data = None

    if config.compute_bridges:
        centrality = compute_centrality(nodes, edges)
        centrality_data = {
            node_id: {
                'degree': m.degree,
                'betweenness': m.betweenness,
                'pagerank': m.pagerank,
            }
            for node_id, m in centrality.items()
        }

        bridges = identify_bridges(
            nodes, edges,
            community_result.communities,
            centrality,
            top_n=config.top_bridges
        )
        bridges_data = {
            'top_by_betweenness': bridges.top_by_betweenness,
            'cross_cluster': bridges.cross_cluster,
        }

    return GraphResult(
        preset=preset,
        nodes=nodes,
        edges=edges,
        communities=community_result.communities,
        num_communities=community_result.num_communities,
        modularity=community_result.modularity,
        bridges=bridges_data,
        centrality=centrality_data,
    )


def _node_to_dict(node) -> dict:
    """Convert GraphNode to dictionary."""
    return {
        'id': node.id,
        'track_count': node.track_count,
        'genres': node.genres,
        'parent_genres': node.parent_genres,
        'primary_decade': node.primary_decade,
        'mean_year': node.mean_year,
    }


def _edge_to_dict(edge) -> dict:
    """Convert GraphEdge to dictionary."""
    return {
        'source': edge.source,
        'target': edge.target,
        'weight': edge.weight,
        'audio_sim': edge.audio_sim,
        'genre_sim': edge.genre_sim,
        'era_sim': edge.era_sim,
    }


def graph_result_to_json(result: GraphResult) -> dict:
    """Convert GraphResult to JSON-serializable dict.

    This matches the bootstrap output format for API compatibility.
    """
    return {
        'preset': result.preset,
        'nodes': result.nodes,
        'edges': result.edges,
        'communities': result.communities,
        'metrics': {
            'num_communities': result.num_communities,
            'modularity': result.modularity,
            'node_count': len(result.nodes),
            'edge_count': len(result.edges),
        },
        'bridges': result.bridges,
        'centrality': result.centrality,
    }
