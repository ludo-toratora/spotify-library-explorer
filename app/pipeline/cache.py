"""Hash-based cache invalidation for pipeline outputs.

Determines when recomputation is needed by comparing:
- Input data hash (normalized_tracks.json content)
- Config hash (relevant config.yaml sections)
- Output existence
"""

import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheKey:
    """Cache key combining input hash and config hash."""
    input_hash: str
    config_hash: str

    @property
    def combined(self) -> str:
        """Combined hash for cache lookup."""
        return f"{self.input_hash[:8]}_{self.config_hash[:8]}"

    def to_dict(self) -> dict:
        return {
            "input_hash": self.input_hash,
            "config_hash": self.config_hash,
            "combined": self.combined,
        }


@dataclass
class CacheStatus:
    """Status of a cached item."""
    exists: bool
    valid: bool
    key: CacheKey | None
    path: Path | None
    reason: str = ""


def compute_hash(data: Any) -> str:
    """Compute SHA256 hash of data.

    Args:
        data: Any JSON-serializable data

    Returns:
        Hex digest of SHA256 hash
    """
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, default=str)
    elif isinstance(data, str):
        serialized = data
    elif isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    else:
        serialized = str(data)

    return hashlib.sha256(serialized.encode()).hexdigest()


def compute_file_hash(path: Path) -> str:
    """Compute hash of file contents.

    Args:
        path: Path to file

    Returns:
        SHA256 hash of file contents
    """
    if not path.exists():
        return ""

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_config_hash(config: dict, sections: list[str]) -> str:
    """Compute hash of specific config sections.

    Args:
        config: Full config dictionary
        sections: List of top-level keys to include

    Returns:
        Hash of selected config sections
    """
    relevant = {k: config.get(k) for k in sections if k in config}
    return compute_hash(relevant)


class PipelineCache:
    """Manages pipeline cache with hash-based invalidation."""

    def __init__(self, cache_dir: Path):
        """Initialize cache manager.

        Args:
            cache_dir: Base cache directory
        """
        self.cache_dir = Path(cache_dir)
        self.graphs_dir = self.cache_dir / "graphs"
        self.embeddings_dir = self.cache_dir / "embeddings"
        self.artists_dir = self.cache_dir / "artists"
        self.validation_dir = self.cache_dir / "validation"
        self.genre_graph_dir = self.cache_dir / "genre_graph"

    def ensure_dirs(self) -> None:
        """Create cache directories if they don't exist."""
        for d in [self.graphs_dir, self.embeddings_dir,
                  self.artists_dir, self.validation_dir, self.genre_graph_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _read_manifest(self, manifest_path: Path) -> dict | None:
        """Read cache manifest file."""
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _write_manifest(self, manifest_path: Path, data: dict) -> None:
        """Write cache manifest file."""
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def check_artists(self, input_hash: str, config_hash: str) -> CacheStatus:
        """Check if aggregated artists cache is valid.

        Args:
            input_hash: Hash of input tracks
            config_hash: Hash of relevant config

        Returns:
            CacheStatus indicating validity
        """
        key = CacheKey(input_hash, config_hash)
        manifest_path = self.artists_dir / "manifest.json"
        data_path = self.artists_dir / "artists.json"

        manifest = self._read_manifest(manifest_path)

        if manifest is None:
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="No manifest found"
            )

        if not data_path.exists():
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="Data file missing"
            )

        if manifest.get("input_hash") != input_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Input hash mismatch"
            )

        if manifest.get("config_hash") != config_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Config hash mismatch"
            )

        return CacheStatus(
            exists=True, valid=True, key=key, path=data_path,
            reason="Cache valid"
        )

    def save_artists(self, artists: list[dict], key: CacheKey) -> Path:
        """Save aggregated artists to cache.

        Args:
            artists: List of artist dictionaries
            key: Cache key

        Returns:
            Path to saved data
        """
        self.ensure_dirs()
        data_path = self.artists_dir / "artists.json"
        manifest_path = self.artists_dir / "manifest.json"

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(artists, f)

        self._write_manifest(manifest_path, {
            "input_hash": key.input_hash,
            "config_hash": key.config_hash,
            "artist_count": len(artists),
        })

        return data_path

    def load_artists(self) -> list[dict]:
        """Load cached artists."""
        data_path = self.artists_dir / "artists.json"
        with open(data_path, encoding="utf-8") as f:
            return json.load(f)

    def check_graph(self, preset: str, input_hash: str, config_hash: str) -> CacheStatus:
        """Check if graph cache is valid for a preset.

        Args:
            preset: Preset name (e.g., "balanced")
            input_hash: Hash of input artists
            config_hash: Hash of graph config

        Returns:
            CacheStatus indicating validity
        """
        key = CacheKey(input_hash, config_hash)
        preset_dir = self.graphs_dir / preset
        manifest_path = preset_dir / "manifest.json"
        data_path = preset_dir / "graph.json"

        manifest = self._read_manifest(manifest_path)

        if manifest is None:
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="No manifest found"
            )

        if not data_path.exists():
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="Data file missing"
            )

        if manifest.get("input_hash") != input_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Input hash mismatch"
            )

        if manifest.get("config_hash") != config_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Config hash mismatch"
            )

        return CacheStatus(
            exists=True, valid=True, key=key, path=data_path,
            reason="Cache valid"
        )

    def save_graph(self, preset: str, graph_data: dict, key: CacheKey) -> Path:
        """Save graph data to cache.

        Args:
            preset: Preset name
            graph_data: Graph dictionary (nodes, edges, communities, etc.)
            key: Cache key

        Returns:
            Path to saved data
        """
        self.ensure_dirs()
        preset_dir = self.graphs_dir / preset
        preset_dir.mkdir(parents=True, exist_ok=True)

        data_path = preset_dir / "graph.json"
        manifest_path = preset_dir / "manifest.json"

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f)

        self._write_manifest(manifest_path, {
            "input_hash": key.input_hash,
            "config_hash": key.config_hash,
            "preset": preset,
            "node_count": len(graph_data.get("nodes", [])),
            "edge_count": len(graph_data.get("edges", [])),
        })

        return data_path

    def load_graph(self, preset: str) -> dict:
        """Load cached graph for a preset."""
        data_path = self.graphs_dir / preset / "graph.json"
        with open(data_path, encoding="utf-8") as f:
            return json.load(f)

    def check_embedding(self, preset: str, input_hash: str, config_hash: str) -> CacheStatus:
        """Check if embedding cache is valid.

        Args:
            preset: Embedding preset name
            input_hash: Hash of input artists
            config_hash: Hash of UMAP config

        Returns:
            CacheStatus indicating validity
        """
        key = CacheKey(input_hash, config_hash)
        preset_dir = self.embeddings_dir / preset
        manifest_path = preset_dir / "manifest.json"
        data_path = preset_dir / "embedding.json"

        manifest = self._read_manifest(manifest_path)

        if manifest is None:
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="No manifest found"
            )

        if not data_path.exists():
            return CacheStatus(
                exists=False, valid=False, key=key, path=data_path,
                reason="Data file missing"
            )

        if manifest.get("input_hash") != input_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Input hash mismatch"
            )

        if manifest.get("config_hash") != config_hash:
            return CacheStatus(
                exists=True, valid=False, key=key, path=data_path,
                reason="Config hash mismatch"
            )

        return CacheStatus(
            exists=True, valid=True, key=key, path=data_path,
            reason="Cache valid"
        )

    def save_embedding(self, preset: str, embedding_data: dict, key: CacheKey) -> Path:
        """Save embedding data to cache.

        Args:
            preset: Embedding preset name
            embedding_data: Embedding dictionary (positions, clusters, etc.)
            key: Cache key

        Returns:
            Path to saved data
        """
        self.ensure_dirs()
        preset_dir = self.embeddings_dir / preset
        preset_dir.mkdir(parents=True, exist_ok=True)

        data_path = preset_dir / "embedding.json"
        manifest_path = preset_dir / "manifest.json"

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(embedding_data, f)

        self._write_manifest(manifest_path, {
            "input_hash": key.input_hash,
            "config_hash": key.config_hash,
            "preset": preset,
            "point_count": len(embedding_data.get("positions", {})),
        })

        return data_path

    def load_embedding(self, preset: str) -> dict:
        """Load cached embedding for a preset."""
        data_path = self.embeddings_dir / preset / "embedding.json"
        with open(data_path, encoding="utf-8") as f:
            return json.load(f)

    # --- Genre Graph Cache ---

    def check_genre_graph(self, input_hash: str, config_hash: str) -> CacheStatus:
        """Check if genre graph cache is valid."""
        key = CacheKey(input_hash, config_hash)
        data_path = self.genre_graph_dir / "genre_graph.json"
        manifest_path = self.genre_graph_dir / "manifest.json"

        manifest = self._read_manifest(manifest_path)
        if manifest is None:
            return CacheStatus(exists=False, valid=False, key=key, path=data_path, reason="No manifest")
        if not data_path.exists():
            return CacheStatus(exists=False, valid=False, key=key, path=data_path, reason="Data file missing")
        if manifest.get("input_hash") != input_hash:
            return CacheStatus(exists=True, valid=False, key=key, path=data_path, reason="Input hash mismatch")
        if manifest.get("config_hash") != config_hash:
            return CacheStatus(exists=True, valid=False, key=key, path=data_path, reason="Config hash mismatch")
        return CacheStatus(exists=True, valid=True, key=key, path=data_path, reason="Cache valid")

    def save_genre_graph(self, data: dict, key: CacheKey) -> Path:
        """Save genre graph data to cache."""
        self.ensure_dirs()
        data_path = self.genre_graph_dir / "genre_graph.json"
        manifest_path = self.genre_graph_dir / "manifest.json"
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self._write_manifest(manifest_path, {
            "input_hash": key.input_hash,
            "config_hash": key.config_hash,
            "node_count": len(data.get("nodes", [])),
            "edge_count": len(data.get("edges", [])),
        })
        return data_path

    def load_genre_graph(self) -> dict:
        """Load cached genre graph."""
        data_path = self.genre_graph_dir / "genre_graph.json"
        with open(data_path, encoding="utf-8") as f:
            return json.load(f)

    def clear_all(self) -> None:
        """Clear all cached data."""
        import shutil
        for d in [self.graphs_dir, self.embeddings_dir,
                  self.artists_dir, self.validation_dir]:
            if d.exists():
                shutil.rmtree(d)
        self.ensure_dirs()

    def clear_preset(self, category: str, preset: str) -> None:
        """Clear cache for a specific preset.

        Args:
            category: "graphs" or "embeddings"
            preset: Preset name
        """
        import shutil
        if category == "graphs":
            preset_dir = self.graphs_dir / preset
        elif category == "embeddings":
            preset_dir = self.embeddings_dir / preset
        else:
            raise ValueError(f"Unknown category: {category}")

        if preset_dir.exists():
            shutil.rmtree(preset_dir)
