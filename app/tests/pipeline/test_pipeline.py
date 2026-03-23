"""Integration tests for the pipeline.

Tests the full pipeline against bootstrap data and verifies:
- Aggregation matches test file logic
- Graphs produce similar structure to bootstrap
- Embeddings compute correctly
- Caching works
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path

from app.pipeline.cache import PipelineCache, CacheKey, compute_hash, compute_file_hash
from app.pipeline.steps.aggregate import aggregate_tracks_to_artists, AggregationConfig
from app.pipeline.steps.compute_graphs import compute_graphs, GraphConfig
from app.pipeline.steps.compute_embeddings import compute_embeddings, EmbeddingConfig
from app.pipeline.steps.validate import validate_tracks, validate_artists, validate_graph
from app.pipeline.runner import PipelineRunner, PipelineConfig


# Bootstrap data path
BOOTSTRAP_DATA = Path(__file__).parent.parent.parent.parent / "runs" / "2026-02-15_212055" / "02_preprocessed"


@pytest.fixture(scope="module")
def bootstrap_tracks():
    """Load bootstrap tracks."""
    tracks_path = BOOTSTRAP_DATA / "normalized_tracks.json"
    if not tracks_path.exists():
        pytest.skip(f"Bootstrap data not found: {tracks_path}")

    with open(tracks_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def bootstrap_graph():
    """Load bootstrap graph for comparison."""
    graph_path = BOOTSTRAP_DATA / "artist_graph" / "artist_graph_balanced.json"
    if not graph_path.exists():
        pytest.skip(f"Bootstrap graph not found: {graph_path}")

    with open(graph_path, encoding="utf-8") as f:
        return json.load(f)


class TestCache:
    """Test cache functionality."""

    def test_compute_hash_consistent(self):
        """Same data should produce same hash."""
        data = {"key": "value", "list": [1, 2, 3]}
        h1 = compute_hash(data)
        h2 = compute_hash(data)
        assert h1 == h2

    def test_compute_hash_different(self):
        """Different data should produce different hash."""
        h1 = compute_hash({"a": 1})
        h2 = compute_hash({"a": 2})
        assert h1 != h2

    def test_cache_artists(self):
        """Test artist caching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(Path(tmpdir))
            cache.ensure_dirs()

            artists = [{"name": "Artist1"}, {"name": "Artist2"}]
            key = CacheKey("input123", "config456")

            # Save
            cache.save_artists(artists, key)

            # Check valid
            status = cache.check_artists("input123", "config456")
            assert status.valid
            assert status.exists

            # Load
            loaded = cache.load_artists()
            assert len(loaded) == 2
            assert loaded[0]["name"] == "Artist1"

            # Check invalid with different hash
            status = cache.check_artists("different", "config456")
            assert not status.valid

    def test_cache_graph(self):
        """Test graph caching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PipelineCache(Path(tmpdir))
            cache.ensure_dirs()

            graph = {"nodes": [{"id": "A"}], "edges": []}
            key = CacheKey("input123", "config456")

            # Save
            cache.save_graph("balanced", graph, key)

            # Check valid
            status = cache.check_graph("balanced", "input123", "config456")
            assert status.valid

            # Load
            loaded = cache.load_graph("balanced")
            assert len(loaded["nodes"]) == 1


class TestAggregation:
    """Test aggregation step."""

    def test_aggregation_basic(self):
        """Test basic aggregation."""
        tracks = [
            {"artist_name": "Artist1", "energy": 0.8, "danceability": 0.6,
             "genres": ["rock"], "album_date": "2010-01-01"},
            {"artist_name": "Artist1", "energy": 0.7, "danceability": 0.5,
             "genres": ["rock", "indie"], "album_date": "2011-01-01"},
            {"artist_name": "Artist2", "energy": 0.5, "danceability": 0.9,
             "genres": ["pop"], "album_date": "2020-01-01"},
        ]

        result = aggregate_tracks_to_artists(tracks)

        assert result.artist_count == 2
        assert result.track_count == 3

        # Find Artist1
        artist1 = next(a for a in result.artists if a["name"] == "Artist1")
        assert artist1["track_count"] == 2
        assert "rock" in artist1["genres"]
        assert "indie" in artist1["genres"]
        assert artist1["audio_profile"]["energy"] == pytest.approx(0.75, abs=0.01)

    def test_aggregation_with_bootstrap(self, bootstrap_tracks):
        """Test aggregation with real data."""
        result = aggregate_tracks_to_artists(bootstrap_tracks)

        # Should have ~2453 artists (from PROJECT_STATUS.md)
        assert result.artist_count > 2000
        assert result.artist_count < 3000

        # Check artist structure
        for artist in result.artists[:10]:
            assert "name" in artist
            assert "audio_profile" in artist
            assert "genres" in artist
            assert "mean_year" in artist


class TestGraphComputation:
    """Test graph computation step."""

    @pytest.fixture
    def sample_artists(self, bootstrap_tracks):
        """Get sample artists for testing."""
        result = aggregate_tracks_to_artists(bootstrap_tracks)
        return result.artists[:200]  # Use subset for speed

    def test_compute_single_preset(self, sample_artists):
        """Test computing a single graph preset."""
        config = GraphConfig(presets=["balanced"], k_neighbors=10)
        result = compute_graphs(sample_artists, config)

        assert "balanced" in result.graphs
        graph = result.graphs["balanced"]

        assert len(graph.nodes) == 200
        assert len(graph.edges) > 0
        assert graph.num_communities > 1

    def test_compute_all_presets(self, sample_artists):
        """Test computing all presets."""
        config = GraphConfig(k_neighbors=10)
        result = compute_graphs(sample_artists, config)

        assert result.preset_count == 5
        for preset in ["balanced", "audio_focused", "genre_focused", "era_focused", "audio_era"]:
            assert preset in result.graphs

    def test_graph_matches_bootstrap_structure(self, bootstrap_tracks, bootstrap_graph):
        """Test that computed graph has similar structure to bootstrap."""
        result = aggregate_tracks_to_artists(bootstrap_tracks)
        artists = result.artists

        config = GraphConfig(presets=["balanced"], k_neighbors=15, min_similarity=0.3)
        graph_result = compute_graphs(artists, config)
        graph = graph_result.graphs["balanced"]

        # Compare node counts
        bootstrap_nodes = len(bootstrap_graph["nodes"])
        our_nodes = len(graph.nodes)
        assert abs(our_nodes - bootstrap_nodes) < 100  # Within 100

        # Compare community counts
        bootstrap_comms = len(set(bootstrap_graph["communities"].values()))
        our_comms = graph.num_communities
        ratio = max(our_comms, bootstrap_comms) / max(min(our_comms, bootstrap_comms), 1)
        assert ratio < 3  # Within 3x


class TestEmbeddingComputation:
    """Test embedding computation step."""

    @pytest.fixture
    def sample_artists(self, bootstrap_tracks):
        """Get sample artists for testing."""
        result = aggregate_tracks_to_artists(bootstrap_tracks)
        return result.artists[:200]

    def test_compute_audio_embedding(self, sample_artists):
        """Test audio-only embedding."""
        config = EmbeddingConfig(presets=["audio_only"], n_neighbors=10)
        result = compute_embeddings(sample_artists, config)

        assert "audio_only" in result.embeddings
        embed = result.embeddings["audio_only"]

        assert len(embed.positions) == 200
        assert embed.n_clusters >= 1

        # Positions should be normalized
        for pos in embed.positions.values():
            assert -1.5 <= pos[0] <= 1.5
            assert -1.5 <= pos[1] <= 1.5

    def test_compute_combined_embedding(self, sample_artists):
        """Test combined embedding."""
        config = EmbeddingConfig(presets=["combined_balanced"], n_neighbors=10)
        result = compute_embeddings(sample_artists, config)

        assert "combined_balanced" in result.embeddings
        embed = result.embeddings["combined_balanced"]

        assert len(embed.positions) == 200
        # Combined should cluster better than audio-only
        assert embed.n_clusters >= 1


class TestValidation:
    """Test validation functions."""

    def test_validate_tracks_valid(self, bootstrap_tracks):
        """Test validation with valid tracks."""
        result = validate_tracks(bootstrap_tracks)
        assert result.valid
        assert result.stats["track_count"] > 6000

    def test_validate_tracks_invalid(self):
        """Test validation with invalid tracks."""
        # Too few tracks
        result = validate_tracks([{"artist_name": "A"}])
        assert not result.valid
        assert any("Too few tracks" in e.message for e in result.errors)

    def test_validate_artists(self, bootstrap_tracks):
        """Test artist validation."""
        agg_result = aggregate_tracks_to_artists(bootstrap_tracks)
        result = validate_artists(agg_result.artists)

        assert result.valid
        assert result.stats["artist_count"] > 2000


class TestFullPipeline:
    """Test the full pipeline runner."""

    def test_pipeline_run(self, bootstrap_tracks):
        """Test running the full pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write tracks to temp file
            tracks_path = tmpdir / "tracks.json"
            with open(tracks_path, "w", encoding="utf-8") as f:
                json.dump(bootstrap_tracks[:500], f)  # Use subset

            # Create minimal config
            config = PipelineConfig(
                cache_dir=tmpdir / "cache",
                enable_cache=True,
                graph_presets=["balanced"],
                embedding_presets=["audio_only"],
                k_neighbors=10,
            )

            runner = PipelineRunner(config, base_dir=tmpdir)
            result = runner.run(tracks_path)

            assert result.success
            assert result.artists_count > 0
            assert "balanced" in result.graphs_computed
            assert "audio_only" in result.embeddings_computed

    def test_pipeline_caching(self, bootstrap_tracks):
        """Test that caching works on second run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            tracks_path = tmpdir / "tracks.json"
            with open(tracks_path, "w", encoding="utf-8") as f:
                json.dump(bootstrap_tracks[:200], f)

            config = PipelineConfig(
                cache_dir=tmpdir / "cache",
                enable_cache=True,
                graph_presets=["balanced"],
                embedding_presets=["audio_only"],
                k_neighbors=10,
            )

            runner = PipelineRunner(config, base_dir=tmpdir)

            # First run - no cache
            result1 = runner.run(tracks_path)
            assert len(result1.cached_steps) == 0

            # Second run - should use cache
            result2 = runner.run(tracks_path)
            assert "aggregate" in result2.cached_steps
            assert "graph_balanced" in result2.cached_steps
            assert "embedding_audio_only" in result2.cached_steps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
