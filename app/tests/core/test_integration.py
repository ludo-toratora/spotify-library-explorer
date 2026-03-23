"""Integration tests: normalized_tracks → graph → communities → embedding."""

import pytest
import numpy as np
from pathlib import Path

from app.data.loaders import load_normalized_tracks
from app.core.similarity import combined_similarity, WEIGHT_PRESETS
from app.core.graph import build_knn_graph, graph_to_adjacency
from app.core.clustering import louvain_communities, compute_centrality, identify_bridges


# Path to test data (bootstrap output)
BOOTSTRAP_DATA = Path(__file__).parent.parent.parent.parent / "runs" / "2026-02-15_212055" / "02_preprocessed"


def aggregate_tracks_to_artists(tracks: list[dict]) -> list[dict]:
    """
    Aggregate tracks into artist profiles.

    This mirrors the logic in batch8_artist_graph.py.
    """
    from collections import defaultdict

    AUDIO_FEATURES = ['energy', 'danceability', 'valence', 'acousticness',
                      'instrumentalness', 'speechiness', 'liveness', 'tempo']

    artist_tracks = defaultdict(list)
    for t in tracks:
        artist_tracks[t.get('artist_name', 'Unknown')].append(t)

    artists = []
    for artist_name, track_list in artist_tracks.items():
        # Audio profile (mean of all tracks)
        audio_profile = {}
        for feature in AUDIO_FEATURES:
            values = [t.get(feature) for t in track_list if t.get(feature) is not None]
            if values:
                if feature == 'tempo':
                    values = [min(v / 200.0, 1.0) for v in values]
                audio_profile[feature] = float(np.mean(values))
            else:
                audio_profile[feature] = 0.0

        # Genres
        all_genres = set()
        for t in track_list:
            all_genres.update(t.get('genres', []))

        # Parent genres
        parent_genres = set()
        for t in track_list:
            parents = t.get('parent_genres', [])
            parent_genres.update(parents)

        # Decade
        years = []
        decade_counts = defaultdict(int)
        for t in track_list:
            album_date = t.get('album_date', '')
            if album_date and len(album_date) >= 4:
                try:
                    year = int(album_date[:4])
                    years.append(year)
                    decade = f"{(year // 10) * 10}s"
                    decade_counts[decade] += 1
                except ValueError:
                    pass

        primary_decade = max(decade_counts.items(), key=lambda x: x[1])[0] if decade_counts else 'Unknown'
        mean_year = int(np.mean(years)) if years else 1990

        artists.append({
            'name': artist_name,
            'track_count': len(track_list),
            'audio_profile': audio_profile,
            'genres': list(all_genres),
            'parent_genres': list(parent_genres),
            'primary_decade': primary_decade,
            'mean_year': mean_year,
        })

    return artists


@pytest.fixture(scope="module")
def bootstrap_tracks():
    """Load bootstrap tracks if available."""
    tracks_path = BOOTSTRAP_DATA / "normalized_tracks.json"
    if not tracks_path.exists():
        pytest.skip(f"Bootstrap data not found: {tracks_path}")

    tracks = load_normalized_tracks(tracks_path)
    # Convert Pydantic models to dicts
    return [t.model_dump() for t in tracks]


@pytest.fixture(scope="module")
def artists(bootstrap_tracks):
    """Aggregate tracks to artists."""
    return aggregate_tracks_to_artists(bootstrap_tracks)


class TestTrackAggregation:
    """Test track → artist aggregation."""

    def test_aggregation_produces_artists(self, artists):
        """Should produce artist profiles."""
        assert len(artists) > 0
        # Bootstrap has ~2453 artists
        assert len(artists) > 2000

    def test_artist_has_required_fields(self, artists):
        """Each artist should have required fields."""
        for artist in artists[:10]:
            assert 'name' in artist
            assert 'audio_profile' in artist
            assert 'genres' in artist
            assert 'mean_year' in artist

    def test_audio_profiles_normalized(self, artists):
        """Audio profiles should be in [0, 1] range."""
        for artist in artists[:100]:
            profile = artist['audio_profile']
            for feature, value in profile.items():
                assert 0 <= value <= 1, f"{artist['name']}.{feature} = {value}"


class TestGraphBuilding:
    """Test artist → graph building."""

    @pytest.fixture(scope="class")
    def sample_artists(self, artists):
        """Get a sample for faster testing."""
        return artists[:200]

    def test_build_graph(self, sample_artists):
        """Should build a graph with nodes and edges."""
        graph = build_knn_graph(sample_artists, k=10, threshold=0.2)

        assert len(graph.nodes) == len(sample_artists)
        assert len(graph.edges) > 0

    def test_edge_weights_in_range(self, sample_artists):
        """Edge weights should be in [0, 1]."""
        graph = build_knn_graph(sample_artists, k=10, threshold=0.2)

        for edge in graph.edges:
            assert 0 <= edge.weight <= 1
            assert 0 <= edge.audio_sim <= 1
            assert 0 <= edge.genre_sim <= 1

    def test_adjacency_conversion(self, sample_artists):
        """Should convert to adjacency list."""
        graph = build_knn_graph(sample_artists, k=10, threshold=0.2)
        adj = graph_to_adjacency(graph)

        assert len(adj) == len(sample_artists)
        # Each node should have at least one neighbor (k=10)
        non_empty = sum(1 for neighbors in adj.values() if neighbors)
        assert non_empty > len(sample_artists) * 0.9  # Most should have neighbors


class TestCommunityDetection:
    """Test graph → communities."""

    @pytest.fixture(scope="class")
    def graph_data(self, artists):
        """Build a graph for community detection."""
        sample = artists[:300]
        graph = build_knn_graph(sample, k=10, threshold=0.2)

        nodes = [{'id': n.id, 'genres': n.genres, 'primary_decade': n.primary_decade}
                 for n in graph.nodes]
        edges = [{'source': e.source, 'target': e.target, 'weight': e.weight}
                 for e in graph.edges]

        return nodes, edges

    def test_louvain_finds_communities(self, graph_data):
        """Louvain should find multiple communities."""
        nodes, edges = graph_data
        result = louvain_communities(nodes, edges)

        assert result.num_communities > 1
        assert len(result.communities) == len(nodes)

    def test_community_assignments_valid(self, graph_data):
        """Each node should be assigned to exactly one community."""
        nodes, edges = graph_data
        result = louvain_communities(nodes, edges)

        for node in nodes:
            assert node['id'] in result.communities
            comm_id = result.communities[node['id']]
            assert 0 <= comm_id < result.num_communities

    def test_centrality_computation(self, graph_data):
        """Should compute centrality metrics for all nodes."""
        nodes, edges = graph_data
        centrality = compute_centrality(nodes, edges)

        assert len(centrality) == len(nodes)

        for node_id, metrics in centrality.items():
            assert metrics.degree >= 0
            assert 0 <= metrics.betweenness <= 1
            assert metrics.pagerank >= 0

    def test_bridge_identification(self, graph_data):
        """Should identify bridge nodes."""
        nodes, edges = graph_data
        result = louvain_communities(nodes, edges)
        centrality = compute_centrality(nodes, edges)

        bridges = identify_bridges(nodes, edges, result.communities, centrality)

        assert len(bridges.top_by_betweenness) > 0
        # Cross-cluster bridges may or may not exist depending on graph structure


class TestFullPipeline:
    """Test complete pipeline with real data."""

    def test_full_pipeline_balanced(self, artists):
        """Test complete pipeline with balanced preset."""
        # Sample for speed
        sample = artists[:500]

        # Build graph
        graph = build_knn_graph(sample, k=15, preset_name='balanced', threshold=0.3)

        # Convert for community detection
        nodes = [{'id': n.id, 'genres': n.genres, 'primary_decade': n.primary_decade}
                 for n in graph.nodes]
        edges = [{'source': e.source, 'target': e.target, 'weight': e.weight}
                 for e in graph.edges]

        # Detect communities
        result = louvain_communities(nodes, edges)

        # Assertions
        assert len(graph.nodes) == 500
        assert len(graph.edges) > 100
        assert result.num_communities >= 5  # Should find multiple communities
        assert result.num_communities <= 100  # But not too many

    def test_different_presets_produce_different_results(self, artists):
        """Different presets should produce different community structures."""
        sample = artists[:200]

        results = {}
        for preset in ['audio_focused', 'genre_focused']:
            graph = build_knn_graph(sample, k=10, preset_name=preset, threshold=0.2)
            nodes = [{'id': n.id} for n in graph.nodes]
            edges = [{'source': e.source, 'target': e.target, 'weight': e.weight}
                     for e in graph.edges]
            result = louvain_communities(nodes, edges)
            results[preset] = result.communities

        # Check that at least some artists are in different communities
        different_count = 0
        for artist_id in results['audio_focused']:
            if results['audio_focused'][artist_id] != results['genre_focused'].get(artist_id, -1):
                different_count += 1

        # At least 10% should differ
        assert different_count > len(sample) * 0.1


class TestUMAPEmbedding:
    """Test embedding computation (if umap-learn is installed)."""

    def test_umap_computation(self, artists):
        """Test UMAP embedding on artist features."""
        try:
            from app.core.embedding import compute_umap, UMAPSettings, cluster_positions
        except ImportError:
            pytest.skip("umap-learn not installed")

        sample = artists[:200]

        # Extract features
        features = []
        ids = []
        for a in sample:
            profile = a['audio_profile']
            vec = [profile.get(f, 0) for f in
                   ['energy', 'danceability', 'valence', 'acousticness', 'instrumentalness', 'tempo']]
            features.append(vec)
            ids.append(a['name'])

        features = np.array(features)

        # Compute UMAP
        settings = UMAPSettings(n_neighbors=10, min_dist=0.1)
        result = compute_umap(features, ids, settings)

        assert len(result.positions) == len(sample)

        # All positions should be in [-1, 1] range
        for pos in result.positions.values():
            assert -1.5 <= pos[0] <= 1.5  # Allow slight buffer
            assert -1.5 <= pos[1] <= 1.5

    def test_clustering_positions(self, artists):
        """Test clustering of UMAP positions."""
        try:
            from app.core.embedding import compute_umap, cluster_positions
        except ImportError:
            pytest.skip("umap-learn not installed")

        sample = artists[:200]

        # Extract and embed
        features = np.array([
            [a['audio_profile'].get(f, 0) for f in
             ['energy', 'danceability', 'valence', 'acousticness', 'instrumentalness', 'tempo']]
            for a in sample
        ])
        ids = [a['name'] for a in sample]

        result = compute_umap(features, ids)

        # Cluster
        clustering = cluster_positions(result.positions)

        assert clustering.n_clusters >= 1
        assert len(clustering.labels) == len(sample)
