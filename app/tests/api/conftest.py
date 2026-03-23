"""Shared fixtures for API tests."""

import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from app.pipeline.cache import PipelineCache


@pytest.fixture
def mock_cache_dir(tmp_path):
    """Create mock cache directory with sample data."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Create graphs directory with sample data
    graphs_dir = cache_dir / "graphs"
    balanced_dir = graphs_dir / "balanced"
    balanced_dir.mkdir(parents=True)

    sample_graph = {
        "nodes": [
            {"id": "artist1", "name": "Artist One", "community": 0, "degree": 5},
            {"id": "artist2", "name": "Artist Two", "community": 0, "degree": 3},
            {"id": "artist3", "name": "Artist Three", "community": 1, "degree": 4},
        ],
        "edges": [
            {"source": "artist1", "target": "artist2", "weight": 0.8},
            {"source": "artist1", "target": "artist3", "weight": 0.6},
        ],
        "communities": {
            "0": ["artist1", "artist2"],
            "1": ["artist3"],
        },
        "bridges": ["artist1"],
        "metrics": {"node_count": 3, "edge_count": 2},
    }

    with open(balanced_dir / "graph.json", "w") as f:
        json.dump(sample_graph, f)

    # Create embeddings directory
    embeddings_dir = cache_dir / "embeddings"
    combined_dir = embeddings_dir / "combined_balanced"
    combined_dir.mkdir(parents=True)

    sample_embedding = {
        "positions": {
            "artist1": {"x": 0.1, "y": 0.2},
            "artist2": {"x": 0.3, "y": 0.4},
            "artist3": {"x": -0.5, "y": 0.6},
        },
        "clusters": {
            "artist1": 0,
            "artist2": 0,
            "artist3": 1,
        },
        "metrics": {"silhouette": 0.75},
    }

    with open(combined_dir / "embedding.json", "w") as f:
        json.dump(sample_embedding, f)

    # Create artists cache
    artists_dir = cache_dir / "artists"
    artists_dir.mkdir()

    sample_artists = [
        {
            "id": "artist1",
            "name": "Artist One",
            "track_count": 10,
            "track_ids": ["t1", "t2", "t3"],
            "genres": ["rock", "indie"],
            "audio_profile": {"energy": 0.7, "danceability": 0.5},
            "decades": {"2010s": 8, "2020s": 2},
        },
        {
            "id": "artist2",
            "name": "Artist Two",
            "track_count": 5,
            "track_ids": ["t4", "t5"],
            "genres": ["electronic"],
            "audio_profile": {"energy": 0.8, "danceability": 0.9},
            "decades": {"2020s": 5},
        },
        {
            "id": "artist3",
            "name": "Artist Three",
            "track_count": 3,
            "track_ids": ["t6"],
            "genres": ["jazz"],
            "audio_profile": {"energy": 0.3, "danceability": 0.4},
            "decades": {"2000s": 3},
        },
    ]

    with open(artists_dir / "artists.json", "w") as f:
        json.dump(sample_artists, f)

    # Create validation directory
    validation_dir = cache_dir / "validation"
    validation_dir.mkdir()

    return cache_dir


@pytest.fixture
def mock_config():
    """Return mock config."""
    return {
        "server": {"host": "127.0.0.1", "port": 8000},
        "paths": {"cache_dir": "cache", "upload_dir": "uploads"},
        "similarity_presets": {
            "balanced": {"audio_weight": 0.4, "genre_weight": 0.4, "era_weight": 0.2},
            "audio_focused": {"audio_weight": 0.7, "genre_weight": 0.2, "era_weight": 0.1},
        },
        "embedding_presets": [
            {"name": "audio_only", "features": ["energy", "danceability"]},
            {"name": "combined_balanced", "features": ["audio", "genre", "era"]},
        ],
        "umap": {"n_neighbors": 15, "min_dist": 0.1},
        "graph": {"min_similarity": 0.3},
        "default_preset": "balanced",
        "default_embedding": "combined_balanced",
    }


@pytest.fixture
def uploads_dir(tmp_path):
    """Create uploads directory."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    return uploads


@pytest.fixture
def client(mock_cache_dir, mock_config, uploads_dir, monkeypatch):
    """Create test client with mocked dependencies."""
    # Import dependencies module
    from app.api import dependencies

    # Create cache instance pointing to mock directory
    cache = PipelineCache(mock_cache_dir)

    # Clear all caches FIRST
    dependencies.get_config.cache_clear()
    dependencies.get_cache.cache_clear()
    dependencies._tracks_index = None

    # Monkeypatch BEFORE importing server
    # We need to patch the module-level functions
    monkeypatch.setattr("app.api.dependencies.get_config", lambda: mock_config)
    monkeypatch.setattr("app.api.dependencies.get_cache", lambda: cache)
    monkeypatch.setattr("app.api.dependencies.get_uploads_dir", lambda: uploads_dir)

    # Also patch in the routes modules that import these
    monkeypatch.setattr("app.api.routes.graphs.get_cache", lambda: cache)
    monkeypatch.setattr("app.api.routes.graphs.get_tracks_index", lambda: dependencies.TracksIndex())
    monkeypatch.setattr("app.api.routes.embedding.get_cache", lambda: cache)
    monkeypatch.setattr("app.api.routes.tracks.get_tracks_index", lambda: dependencies.TracksIndex())
    monkeypatch.setattr("app.api.routes.validation.get_cache", lambda: cache)
    monkeypatch.setattr("app.api.routes.config.get_config", lambda: mock_config)
    monkeypatch.setattr("app.api.routes.config.save_config", lambda config: None)  # No-op for tests
    monkeypatch.setattr("app.api.routes.upload.get_uploads_dir", lambda: uploads_dir)

    # Reinitialize tracks index so it loads from mock cache
    mock_tracks_index = dependencies.TracksIndex()
    monkeypatch.setattr("app.api.dependencies._tracks_index", mock_tracks_index)

    # Now import and create app after all patches are applied
    from app.api.server import create_app
    app = create_app()

    return TestClient(app)
