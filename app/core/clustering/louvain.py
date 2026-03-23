"""Louvain community detection and centrality metrics."""

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any


@dataclass
class CommunityResult:
    """Result of community detection."""
    communities: dict[str, int]  # {node_id: community_id}
    num_communities: int
    modularity: float | None = None


@dataclass
class CentralityMetrics:
    """Centrality metrics for a single node."""
    degree: int = 0
    weighted_degree: float = 0.0
    betweenness: float = 0.0
    pagerank: float = 0.0
    eigenvector: float = 0.0
    clustering_coef: float = 0.0


@dataclass
class BridgeInfo:
    """Information about bridge nodes connecting communities."""
    top_by_betweenness: list[dict[str, Any]] = field(default_factory=list)
    cross_cluster: list[dict[str, Any]] = field(default_factory=list)


def louvain_communities(
    nodes: list[dict],
    edges: list[dict],
    max_iterations: int = 10
) -> CommunityResult:
    """
    Louvain community detection algorithm.

    A greedy modularity optimization algorithm that iteratively
    moves nodes between communities to maximize modularity.

    Args:
        nodes: List of node dicts with 'id' field
        edges: List of edge dicts with 'source', 'target', 'weight' fields
        max_iterations: Maximum optimization iterations

    Returns:
        CommunityResult with community assignments
    """
    # Build node index
    node_ids = {n['id']: i for i, n in enumerate(nodes)}
    n = len(nodes)

    if n == 0:
        return CommunityResult(communities={}, num_communities=0)

    # Build adjacency with weights
    adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)

    for edge in edges:
        src_idx = node_ids.get(edge.get('source'))
        tgt_idx = node_ids.get(edge.get('target'))
        weight = edge.get('weight', 1.0)

        if src_idx is not None and tgt_idx is not None:
            adjacency[src_idx].append((tgt_idx, weight))
            adjacency[tgt_idx].append((src_idx, weight))

    # Total edge weight (sum of all weights, each edge counted twice)
    total_weight = sum(edge.get('weight', 1.0) for edge in edges)

    if total_weight == 0:
        return CommunityResult(
            communities={nodes[i]['id']: 0 for i in range(n)},
            num_communities=1
        )

    # Node strengths (sum of incident edge weights)
    strength = {
        i: sum(w for _, w in adjacency.get(i, []))
        for i in range(n)
    }

    # Initialize: each node in its own community
    communities = {i: i for i in range(n)}

    # Iterate
    for _ in range(max_iterations):
        improved = False

        for node_idx in range(n):
            current_comm = communities[node_idx]

            # Sum weights to each neighboring community
            neighbor_comm_weights: dict[int, float] = defaultdict(float)
            for neighbor, weight in adjacency.get(node_idx, []):
                neighbor_comm_weights[communities[neighbor]] += weight

            # Find best community to move to
            best_comm = current_comm
            best_gain = 0.0

            for target_comm, edge_weight in neighbor_comm_weights.items():
                if target_comm == current_comm:
                    continue

                # Sum of strengths in target community
                comm_strength = sum(
                    strength[i] for i in range(n)
                    if communities[i] == target_comm
                )

                # Modularity gain approximation
                gain = edge_weight - (strength[node_idx] * comm_strength) / (2 * total_weight)

                if gain > best_gain:
                    best_gain = gain
                    best_comm = target_comm

            if best_comm != current_comm:
                communities[node_idx] = best_comm
                improved = True

        if not improved:
            break

    # Renumber communities to be contiguous 0, 1, 2, ...
    unique_comms = sorted(set(communities.values()))
    mapping = {c: i for i, c in enumerate(unique_comms)}
    communities = {i: mapping[c] for i, c in communities.items()}

    # Convert to node IDs
    result = {nodes[i]['id']: communities[i] for i in range(n)}

    return CommunityResult(
        communities=result,
        num_communities=len(unique_comms)
    )


def compute_centrality(
    nodes: list[dict],
    edges: list[dict]
) -> dict[str, CentralityMetrics]:
    """
    Compute centrality metrics for all nodes using NetworkX.

    Metrics computed:
        - degree: number of connections
        - weighted_degree: sum of edge weights
        - betweenness: fraction of shortest paths through node
        - pagerank: iterative importance
        - eigenvector: connectivity to well-connected nodes
        - clustering_coef: how connected neighbors are to each other

    Args:
        nodes: List of node dicts with 'id' field
        edges: List of edge dicts with 'source', 'target', 'weight' fields

    Returns:
        {node_id: CentralityMetrics}
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("networkx required for centrality. Run: pip install networkx")

    # Build NetworkX graph
    G = nx.Graph()

    for node in nodes:
        G.add_node(node['id'])

    for edge in edges:
        G.add_edge(
            edge['source'],
            edge['target'],
            weight=edge.get('weight', 1.0)
        )

    # Compute metrics
    betweenness = nx.betweenness_centrality(G, weight='weight')
    pagerank = nx.pagerank(G, weight='weight')

    try:
        eigenvector = nx.eigenvector_centrality(G, weight='weight', max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        # Fallback to normalized degree
        eigenvector = {
            node: G.degree(node) / (len(G) - 1) if len(G) > 1 else 0
            for node in G.nodes()
        }

    clustering = nx.clustering(G, weight='weight')

    # Compile results
    metrics = {}
    for node in nodes:
        node_id = node['id']
        degree = G.degree(node_id)
        weighted_deg = sum(
            G[node_id][neighbor]['weight']
            for neighbor in G.neighbors(node_id)
        )

        metrics[node_id] = CentralityMetrics(
            degree=degree,
            weighted_degree=round(weighted_deg, 4),
            betweenness=round(betweenness.get(node_id, 0), 6),
            pagerank=round(pagerank.get(node_id, 0), 6),
            eigenvector=round(eigenvector.get(node_id, 0), 6),
            clustering_coef=round(clustering.get(node_id, 0), 4)
        )

    return metrics


def identify_bridges(
    nodes: list[dict],
    edges: list[dict],
    communities: dict[str, int],
    centrality: dict[str, CentralityMetrics],
    top_n: int = 20
) -> BridgeInfo:
    """
    Identify bridge nodes that connect different communities.

    Args:
        nodes: Graph nodes
        edges: Graph edges
        communities: {node_id: community_id}
        centrality: {node_id: CentralityMetrics}
        top_n: Number of top bridges to return

    Returns:
        BridgeInfo with top bridges by betweenness and cross-cluster connectors
    """
    # Top by betweenness
    bridges_by_betweenness = sorted(
        [(node_id, metrics.betweenness) for node_id, metrics in centrality.items()],
        key=lambda x: -x[1]
    )[:top_n]

    # Build adjacency for cross-cluster analysis
    neighbors: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        neighbors[edge['source']].add(edge['target'])
        neighbors[edge['target']].add(edge['source'])

    # Find cross-cluster connectors
    cross_cluster = []
    for node in nodes:
        node_id = node['id']
        node_comm = communities.get(node_id, -1)

        # Communities of neighbors
        neighbor_comms = {
            communities.get(n, -1)
            for n in neighbors.get(node_id, [])
        }
        neighbor_comms.discard(-1)

        if len(neighbor_comms) > 2:
            cross_cluster.append({
                'artist': node_id,
                'communities_connected': len(neighbor_comms),
                'betweenness': centrality.get(node_id, CentralityMetrics()).betweenness
            })

    cross_cluster.sort(key=lambda x: (-x['communities_connected'], -x['betweenness']))

    return BridgeInfo(
        top_by_betweenness=[
            {'artist': b[0], 'betweenness': round(b[1], 6)}
            for b in bridges_by_betweenness
        ],
        cross_cluster=cross_cluster[:top_n]
    )


def community_summary(
    nodes: list[dict],
    communities: dict[str, int]
) -> dict[int, dict]:
    """
    Generate summary statistics for each community.

    Args:
        nodes: Graph nodes with 'id', 'genres', etc.
        communities: {node_id: community_id}

    Returns:
        {community_id: {size, top_genres, ...}}
    """
    # Group nodes by community
    comm_nodes: dict[int, list[dict]] = defaultdict(list)
    for node in nodes:
        comm_id = communities.get(node['id'], 0)
        comm_nodes[comm_id].append(node)

    summaries = {}
    for comm_id, members in comm_nodes.items():
        # Genre counts
        genre_counts: dict[str, int] = defaultdict(int)
        for node in members:
            for g in node.get('genres', []):
                genre_counts[g] += 1

        top_genres = sorted(genre_counts.items(), key=lambda x: -x[1])[:5]

        # Decade distribution
        decade_counts: dict[str, int] = defaultdict(int)
        for node in members:
            decade = node.get('primary_decade', 'Unknown')
            if decade:
                decade_counts[decade] += 1

        summaries[comm_id] = {
            'size': len(members),
            'top_genres': [g for g, _ in top_genres],
            'decade_distribution': dict(decade_counts),
            'sample_artists': [n['id'] for n in members[:5]]
        }

    return summaries
