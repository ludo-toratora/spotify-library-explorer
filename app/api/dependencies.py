"""Dependency injection for FastAPI routes.

Provides lazy-loaded singletons for:
- Config (from config.yaml)
- PipelineCache
- Tracks index (artist → track_ids mapping)
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.pipeline.cache import PipelineCache


def get_app_dir() -> Path:
    """Get the app directory (where config.yaml lives)."""
    return Path(__file__).parent.parent


@lru_cache
def get_config() -> dict[str, Any]:
    """Load and cache config.yaml."""
    config_path = get_app_dir() / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_config_path() -> Path:
    """Get path to config.yaml."""
    return get_app_dir() / "config.yaml"


def save_config(config: dict[str, Any]) -> None:
    """Save config to config.yaml and clear cache."""
    config_path = get_app_dir() / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    # Clear the cached config
    get_config.cache_clear()


@lru_cache
def get_cache() -> PipelineCache:
    """Get or create PipelineCache instance."""
    config = get_config()
    cache_dir = get_app_dir() / config.get("paths", {}).get("cache_dir", "cache")
    return PipelineCache(cache_dir)


def get_uploads_dir() -> Path:
    """Get uploads directory."""
    config = get_config()
    upload_dir = get_app_dir() / config.get("paths", {}).get("upload_dir", "uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_graph_presets() -> list[str]:
    """Get list of graph preset names."""
    config = get_config()
    return list(config.get("similarity_presets", {}).keys())


def get_embedding_presets() -> list[str]:
    """Get list of embedding preset names."""
    config = get_config()
    presets = config.get("embedding_presets", [])
    return [p.get("name") for p in presets if isinstance(p, dict)]


class TracksIndex:
    """Lazy-loaded index for track lookups."""

    def __init__(self):
        self._tracks: list[dict] | None = None
        self._by_id: dict[str, dict] | None = None
        self._by_artist: dict[str, list[str]] | None = None

    def _ensure_loaded(self) -> None:
        """Load tracks from cache if not already loaded."""
        if self._tracks is not None:
            return

        cache = get_cache()
        artists_path = cache.artists_dir / "artists.json"

        if not artists_path.exists():
            self._tracks = []
            self._by_id = {}
            self._by_artist = {}
            return

        # Load artists (which contain aggregated track info)
        with open(artists_path, encoding="utf-8") as f:
            self._tracks = json.load(f)

        self._by_id = {}
        self._by_artist = {}

        for artist in self._tracks:
            artist_name = artist.get("name", "")
            track_ids = artist.get("track_ids", [])
            self._by_artist[artist_name] = track_ids

            # Build id index for artist lookup by ID
            artist_id = artist.get("id", artist.get("name", ""))
            self._by_id[artist_id] = artist

    @property
    def artists(self) -> list[dict]:
        """Get all artists."""
        self._ensure_loaded()
        return self._tracks or []

    def get_artist(self, artist_id: str) -> dict | None:
        """Get artist by ID."""
        self._ensure_loaded()
        return self._by_id.get(artist_id) if self._by_id else None

    def get_track_ids_for_artist(self, artist_name: str) -> list[str]:
        """Get track IDs for an artist."""
        self._ensure_loaded()
        return self._by_artist.get(artist_name, []) if self._by_artist else []

    def clear_cache(self) -> None:
        """Clear cached data (call after recompute)."""
        self._tracks = None
        self._by_id = None
        self._by_artist = None


# Singleton instance
_tracks_index: TracksIndex | None = None


def get_tracks_index() -> TracksIndex:
    """Get the tracks index singleton."""
    global _tracks_index
    if _tracks_index is None:
        _tracks_index = TracksIndex()
    return _tracks_index


class NormalizedTracksIndex:
    """Lazy-loaded index for normalized track lookups from normalized_tracks.json."""

    def __init__(self):
        self._tracks: list[dict] | None = None
        self._by_id: dict[str, dict] | None = None
        self._by_artist: dict[str, list[dict]] | None = None

    def _ensure_loaded(self) -> None:
        """Load normalized tracks from uploads directory if not already loaded."""
        if self._tracks is not None:
            return

        uploads_dir = get_uploads_dir()
        tracks_path = uploads_dir / "normalized_tracks.json"

        if not tracks_path.exists():
            self._tracks = []
            self._by_id = {}
            self._by_artist = {}
            return

        with open(tracks_path, encoding="utf-8") as f:
            self._tracks = json.load(f)

        self._by_id = {}
        self._by_artist = {}

        for track in self._tracks:
            track_id = track.get("track_id", "")
            if track_id:
                self._by_id[track_id] = track

            artist_name = track.get("artist_name", "")
            if artist_name:
                if artist_name not in self._by_artist:
                    self._by_artist[artist_name] = []
                self._by_artist[artist_name].append(track)

    def get_by_ids(self, track_ids: list[str]) -> list[dict]:
        """Get tracks by a list of track IDs."""
        self._ensure_loaded()
        if not self._by_id:
            return []
        return [self._by_id[tid] for tid in track_ids if tid in self._by_id]

    def get_by_artist(self, artist_name: str) -> list[dict]:
        """Get all tracks for an artist by name."""
        self._ensure_loaded()
        if not self._by_artist:
            return []
        return self._by_artist.get(artist_name, [])

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search tracks by track_name and artist_name (case-insensitive)."""
        self._ensure_loaded()
        if not self._tracks:
            return []
        q_lower = query.lower()
        results = []
        for track in self._tracks:
            track_name = track.get("track_name", "") or ""
            artist_name = track.get("artist_name", "") or ""
            if q_lower in track_name.lower() or q_lower in artist_name.lower():
                results.append(track)
                if len(results) >= limit:
                    break
        return results

    def clear_cache(self) -> None:
        """Reset all internal dicts to None."""
        self._tracks = None
        self._by_id = None
        self._by_artist = None


# Singleton instance for normalized tracks
_normalized_index: NormalizedTracksIndex | None = None


def get_normalized_tracks_index() -> NormalizedTracksIndex:
    """Get the normalized tracks index singleton."""
    global _normalized_index
    if _normalized_index is None:
        _normalized_index = NormalizedTracksIndex()
    return _normalized_index


def clear_all_caches() -> None:
    """Clear all cached data (after recompute or upload)."""
    global _tracks_index, _normalized_index
    get_config.cache_clear()
    get_cache.cache_clear()
    if _tracks_index:
        _tracks_index.clear_cache()
    _tracks_index = None
    if _normalized_index:
        _normalized_index.clear_cache()
    _normalized_index = None
