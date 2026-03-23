"""API endpoint tests using FastAPI TestClient.

Tests cover:
- Health endpoint
- Graph endpoints (list, get by preset, enrichment)
- Embedding endpoints (list, get by preset)
- Tracks/Artists endpoints (pagination, filters, batch lookup)
- Validation endpoint
- Config endpoints (get, update)
- Upload endpoint
- Recompute endpoints (trigger, status)
"""

import json
import pytest


class TestHealthEndpoint:
    """Test /api/health endpoint."""

    def test_health_check(self, client):
        """Health endpoint returns status."""
        response = client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "cache_available" in data
        assert "artists_count" in data
        assert "graphs_available" in data
        assert "embeddings_available" in data


class TestGraphEndpoints:
    """Test /api/graphs/* endpoints."""

    def test_list_graphs(self, client):
        """List available graph presets."""
        response = client.get("/api/graphs")
        assert response.status_code == 200

        data = response.json()
        assert "presets" in data
        assert "available" in data
        assert "balanced" in data["presets"]
        assert "balanced" in data["available"]

    def test_get_graph_valid_preset(self, client):
        """Get graph for valid preset."""
        response = client.get("/api/graphs/balanced")
        assert response.status_code == 200

        data = response.json()
        assert data["preset"] == "balanced"
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) == 2
        assert "communities" in data
        assert "bridges" in data

    def test_get_graph_invalid_preset(self, client):
        """Invalid preset returns 400."""
        response = client.get("/api/graphs/invalid_preset")
        assert response.status_code == 400
        assert "Invalid preset" in response.json()["detail"]

    def test_get_graph_missing_preset(self, client):
        """Missing preset returns 404."""
        response = client.get("/api/graphs/audio_focused")
        assert response.status_code == 404

    def test_get_graph_with_enrichment(self, client):
        """Enrichment adds track_ids and is_bridge."""
        response = client.get("/api/graphs/balanced?enrich=true")
        assert response.status_code == 200

        data = response.json()
        # Check enrichment fields on all nodes
        for node in data["nodes"]:
            assert "track_ids" in node
            assert "is_bridge" in node

        # Verify bridge detection
        bridge_nodes = [n for n in data["nodes"] if n["is_bridge"]]
        assert len(bridge_nodes) >= 1


class TestEmbeddingEndpoints:
    """Test /api/embedding/* endpoints."""

    def test_list_embedding_presets(self, client):
        """List available embedding presets."""
        response = client.get("/api/embedding/presets")
        assert response.status_code == 200

        data = response.json()
        assert "presets" in data
        assert "available" in data
        assert "combined_balanced" in data["available"]

    def test_get_embedding_default(self, client):
        """Get embedding with default preset."""
        response = client.get("/api/embedding")
        assert response.status_code == 200

        data = response.json()
        assert data["preset"] == "combined_balanced"
        assert "positions" in data
        assert len(data["positions"]) == 3

    def test_get_embedding_with_clusters(self, client):
        """Get embedding includes clusters by default."""
        response = client.get("/api/embedding")
        assert response.status_code == 200

        data = response.json()
        assert "clusters" in data
        assert len(data["clusters"]) == 3

    def test_get_embedding_without_clusters(self, client):
        """Can exclude clusters."""
        response = client.get("/api/embedding?include_clusters=false")
        assert response.status_code == 200

        data = response.json()
        assert data["clusters"] == {}

    def test_get_embedding_invalid_preset(self, client):
        """Invalid preset returns 400."""
        response = client.get("/api/embedding?preset=invalid")
        assert response.status_code == 400


class TestTracksEndpoints:
    """Test /api/tracks/* endpoints."""

    def test_list_artists(self, client):
        """List artists with pagination."""
        response = client.get("/api/tracks")
        assert response.status_code == 200

        data = response.json()
        assert "artists" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert len(data["artists"]) == 3
        assert data["total"] == 3

    def test_list_artists_with_pagination(self, client):
        """Pagination works correctly."""
        response = client.get("/api/tracks?limit=2&offset=1")
        assert response.status_code == 200

        data = response.json()
        assert len(data["artists"]) == 2
        assert data["offset"] == 1

    def test_list_artists_with_filter(self, client):
        """Filter by artist name."""
        response = client.get("/api/tracks?artist=One")
        assert response.status_code == 200

        data = response.json()
        assert len(data["artists"]) == 1
        assert "One" in data["artists"][0]["name"]

    def test_get_single_artist(self, client):
        """Get single artist by ID."""
        response = client.get("/api/tracks/artist1")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "artist1"
        assert data["name"] == "Artist One"
        assert "track_ids" in data
        assert "audio_profile" in data

    def test_get_artist_not_found(self, client):
        """Non-existent artist returns 404."""
        response = client.get("/api/tracks/nonexistent")
        assert response.status_code == 404

    def test_batch_lookup(self, client):
        """Batch lookup by IDs."""
        response = client.get("/api/tracks/by-ids?ids=artist1,artist2,nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert "artists" in data
        assert data["artists"]["artist1"] is not None
        assert data["artists"]["artist2"] is not None
        assert data["artists"]["nonexistent"] is None


class TestValidationEndpoint:
    """Test /api/validation endpoint."""

    def test_validation_with_artists(self, client):
        """Validation returns counts when artists exist."""
        response = client.get("/api/validation")
        assert response.status_code == 200

        data = response.json()
        assert data["valid"] is True
        assert data["artist_count"] == 3


class TestConfigEndpoints:
    """Test /api/config endpoints."""

    def test_get_config(self, client):
        """Get safe config subset."""
        response = client.get("/api/config")
        assert response.status_code == 200

        data = response.json()
        assert "similarity_presets" in data
        assert "embedding_presets" in data
        assert "umap" in data
        assert "default_preset" in data
        # Server/paths should not be exposed
        assert "server" not in data
        assert "paths" not in data

    def test_update_config(self, client):
        """Update config with partial values."""
        # save_config is already mocked in conftest to no-op
        response = client.post("/api/config", json={
            "default_preset": "balanced",
        })

        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "needs_recompute" in data


class TestUploadEndpoint:
    """Test /api/upload endpoint."""

    def test_upload_valid_json(self, client):
        """Upload valid tracks JSON."""
        tracks = [
            {
                "track_id": "t1",
                "track_name": "Test Track",
                "artist_name": "Test Artist",
                "tempo": 120,
                "energy": 0.7,
                "danceability": 0.8,
                "valence": 0.6,
                "acousticness": 0.3,
                "instrumentalness": 0.1,
                "genres": ["rock"],
            }
        ]

        files = {"tracks_file": ("test.json", json.dumps(tracks), "application/json")}
        response = client.post("/api/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["track_count"] == 1

    def test_upload_invalid_json(self, client):
        """Invalid JSON returns error."""
        files = {"tracks_file": ("test.json", "not valid json", "application/json")}
        response = client.post("/api/upload", files=files)

        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    def test_upload_missing_fields(self, client):
        """Missing required fields returns validation error."""
        tracks = [{"some_field": "value"}]

        files = {"tracks_file": ("test.json", json.dumps(tracks), "application/json")}
        response = client.post("/api/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["validation"]["valid"] is False


class TestRecomputeEndpoints:
    """Test /api/recompute endpoints."""

    def test_list_jobs_empty(self, client):
        """List jobs when none exist."""
        response = client.get("/api/recompute")
        assert response.status_code == 200

        data = response.json()
        assert data["jobs"] == []

    def test_get_job_not_found(self, client):
        """Non-existent job returns 404."""
        response = client.get("/api/recompute/nonexistent")
        assert response.status_code == 404


class TestOpenAPISpec:
    """Test that OpenAPI spec is generated correctly."""

    def test_openapi_spec(self, client):
        """OpenAPI spec is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        spec = response.json()
        assert spec["info"]["title"] == "LibraryExplorer API"
        assert "/api/health" in spec["paths"]
        assert "/api/graphs/{preset}" in spec["paths"]
        assert "/api/embedding" in spec["paths"]
