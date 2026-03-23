"""Pipeline runner - orchestrates all preprocessing steps.

Reads config.yaml and runs:
1. Load tracks
2. Validate input
3. Aggregate to artists
4. Compute graphs (all presets)
5. Compute embeddings (all presets)
6. Validate outputs

Uses caching to skip steps when inputs haven't changed.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

from app.pipeline.cache import PipelineCache, CacheKey, compute_hash, compute_file_hash
from app.pipeline.steps.aggregate import aggregate_tracks_to_artists, AggregationConfig
from app.pipeline.steps.compute_graphs import compute_graphs, GraphConfig, graph_result_to_json
from app.pipeline.steps.compute_embeddings import compute_embeddings, EmbeddingConfig, embedding_result_to_json
from app.pipeline.steps.compute_genre_graph import compute_genre_graph, GenreGraphConfig, genre_graph_result_to_json
from app.pipeline.steps.validate import (
    validate_tracks, validate_artists, validate_graph, validate_embedding,
    validation_result_to_json
)


logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Pipeline configuration loaded from config.yaml."""
    cache_dir: Path
    enable_cache: bool = True

    # Aggregation
    min_tracks_per_artist: int = 1

    # Graph
    graph_presets: list[str] = field(default_factory=lambda: [
        'balanced', 'audio_focused', 'genre_focused', 'era_focused', 'audio_era'
    ])
    k_neighbors: int = 15
    min_similarity: float = 0.3

    # Embedding
    embedding_presets: list[str] = field(default_factory=lambda: [
        'audio_default', 'audio_local', 'audio_global',
        'audio_spread', 'audio_euclidean',
        'genre', 'era',
        'combined_balanced', 'combined_audio', 'combined_genre',
        'combined_era', 'combined_equal',
    ])
    umap_n_neighbors: int = 15
    umap_min_dist: float = 0.1
    umap_random_state: int = 42

    @classmethod
    def from_yaml(cls, config_path: Path) -> "PipelineConfig":
        """Load config from YAML file."""
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        paths = config.get("paths", {})
        pipeline = config.get("pipeline", {})
        graph = config.get("graph", {})
        umap = config.get("umap", {})
        similarity_presets = config.get("similarity_presets", {})

        return cls(
            cache_dir=Path(paths.get("cache_dir", "cache")),
            enable_cache=pipeline.get("enable_cache", True),
            min_tracks_per_artist=pipeline.get("min_artists", 1),
            graph_presets=list(similarity_presets.keys()),
            k_neighbors=pipeline.get("k_neighbors", 15),
            min_similarity=graph.get("min_similarity", 0.3),
            embedding_presets=[
                'audio_default', 'audio_local', 'audio_global',
                'audio_spread', 'audio_euclidean',
                'genre', 'era',
                'combined_balanced', 'combined_audio', 'combined_genre',
                'combined_era', 'combined_equal',
            ],
            umap_n_neighbors=umap.get("n_neighbors", 15),
            umap_min_dist=umap.get("min_dist", 0.1),
            umap_random_state=umap.get("random_state", 42),
        )


@dataclass
class PipelineResult:
    """Result of pipeline run."""
    success: bool
    artists_count: int
    graphs_computed: list[str]
    embeddings_computed: list[str]
    cached_steps: list[str]
    validation: dict
    errors: list[str]


class PipelineRunner:
    """Orchestrates the preprocessing pipeline."""

    def __init__(self, config: PipelineConfig, base_dir: Path | None = None):
        """Initialize pipeline runner.

        Args:
            config: Pipeline configuration
            base_dir: Base directory for relative paths (defaults to app/)
        """
        self.config = config
        self.base_dir = base_dir or Path(__file__).parent.parent

        cache_dir = self.base_dir / config.cache_dir
        self.cache = PipelineCache(cache_dir)

    def run(self, tracks_path: Path, progress_callback=None, force: bool = False) -> PipelineResult:
        """Run the full pipeline.

        Args:
            tracks_path: Path to normalized_tracks.json
            progress_callback: Optional callable(step_id, message, pct) for progress updates
            force: If True, skip cache reads (overwrite existing cache) without deleting files first

        Returns:
            PipelineResult with stats and any errors
        """
        if force:
            self.config.enable_cache = False
        errors = []
        cached_steps = []
        graphs_computed = []
        embeddings_computed = []

        def _report(step_id: str, message: str, pct: float):
            logger.info(f"[{step_id}] {message} ({pct:.0%})")
            if progress_callback:
                progress_callback(step_id, message, pct)

        logger.info(f"Starting pipeline with {tracks_path}")

        # Step 1: Load tracks
        _report("load_tracks", "Loading tracks...", 0.05)
        try:
            tracks = self._load_tracks(tracks_path)
            logger.info(f"Loaded {len(tracks)} tracks")
            _report("load_tracks", "done", 0.10)
        except Exception as e:
            errors.append(f"Failed to load tracks: {e}")
            return PipelineResult(
                success=False, artists_count=0,
                graphs_computed=[], embeddings_computed=[],
                cached_steps=[], validation={}, errors=errors
            )

        # Step 2: Validate input
        _report("validate", "Validating tracks...", 0.12)
        track_validation = validate_tracks(tracks)
        if not track_validation.valid:
            errors.extend([i.message for i in track_validation.errors])
            return PipelineResult(
                success=False, artists_count=0,
                graphs_computed=[], embeddings_computed=[],
                cached_steps=[], validation=validation_result_to_json(track_validation),
                errors=errors
            )
        _report("validate", "done", 0.14)

        # Compute input hash for caching
        input_hash = compute_file_hash(tracks_path)
        config_hash = compute_hash({
            "graph": {
                "k": self.config.k_neighbors,
                "threshold": self.config.min_similarity,
            },
            "umap": {
                "n_neighbors": self.config.umap_n_neighbors,
                "min_dist": self.config.umap_min_dist,
            },
        })

        # Step 3: Aggregate to artists
        _report("aggregate", "Aggregating artists...", 0.15)
        artists, from_cache = self._get_or_compute_artists(
            tracks, input_hash, config_hash
        )
        if from_cache:
            cached_steps.append("aggregate")
            _report("aggregate", "cached", 0.22)
        else:
            _report("aggregate", "done", 0.22)
        logger.info(f"Have {len(artists)} artists")

        # Step 4: Validate artists
        artist_validation = validate_artists(artists)
        if not artist_validation.valid:
            errors.extend([i.message for i in artist_validation.errors])

        # Compute artist hash for downstream caching
        artist_hash = compute_hash([a['name'] for a in artists])

        # Step 5: Compute graphs
        n_graphs = len(self.config.graph_presets)
        for i, preset in enumerate(self.config.graph_presets):
            pct_start = 0.25 + (i / n_graphs) * 0.35
            pct_end   = 0.25 + ((i + 1) / n_graphs) * 0.35
            _report(f"graph_{preset}", f"Building {preset} graph...", pct_start)

            graph_config_hash = compute_hash({
                "preset": preset,
                "k": self.config.k_neighbors,
                "threshold": self.config.min_similarity,
            })

            computed, from_cache = self._get_or_compute_graph(
                artists, preset, artist_hash, graph_config_hash
            )
            if from_cache:
                cached_steps.append(f"graph_{preset}")
                _report(f"graph_{preset}", "cached", pct_end)
            else:
                _report(f"graph_{preset}", "done", pct_end)
            graphs_computed.append(preset)

        # Step 6: Compute embeddings
        n_embeddings = len(self.config.embedding_presets)
        for i, preset in enumerate(self.config.embedding_presets):
            pct_start = 0.62 + (i / n_embeddings) * 0.38
            pct_end   = 0.62 + ((i + 1) / n_embeddings) * 0.38
            _report(f"embedding_{preset}", f"Computing {preset} embedding...", pct_start)

            embed_config_hash = compute_hash({
                "preset": preset,
                "n_neighbors": self.config.umap_n_neighbors,
                "min_dist": self.config.umap_min_dist,
            })

            computed, from_cache = self._get_or_compute_embedding(
                artists, preset, artist_hash, embed_config_hash
            )
            if from_cache:
                cached_steps.append(f"embedding_{preset}")
                _report(f"embedding_{preset}", "cached", pct_end)
            else:
                _report(f"embedding_{preset}", "done", pct_end)
            embeddings_computed.append(preset)

        # Step 7: Compute genre graph
        _report("genre_graph", "Computing genre graph...", 0.90)
        genre_config_hash = compute_hash({"min_track_count": 3, "min_cooccurrence": 2, "jaccard_threshold": 0.03})
        genre_graph_computed, genre_from_cache = self._get_or_compute_genre_graph(
            artists, artist_hash, genre_config_hash
        )
        if genre_from_cache:
            cached_steps.append("genre_graph")
            _report("genre_graph", "cached", 0.95)
        else:
            _report("genre_graph", "done", 0.95)

        _report("complete", "Pipeline complete", 1.0)
        logger.info(f"Pipeline complete. Cached steps: {cached_steps}")

        return PipelineResult(
            success=len(errors) == 0,
            artists_count=len(artists),
            graphs_computed=graphs_computed,
            embeddings_computed=embeddings_computed,
            cached_steps=cached_steps,
            validation={
                "tracks": validation_result_to_json(track_validation),
                "artists": validation_result_to_json(artist_validation),
            },
            errors=errors,
        )

    def _load_tracks(self, path: Path) -> list[dict]:
        """Load tracks from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle both list and dict formats
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "tracks" in data:
            return data["tracks"]
        else:
            raise ValueError("Invalid tracks file format")

    def _get_or_compute_artists(
        self, tracks: list[dict], input_hash: str, config_hash: str
    ) -> tuple[list[dict], bool]:
        """Get artists from cache or compute.

        Returns:
            Tuple of (artists, from_cache)
        """
        if self.config.enable_cache:
            status = self.cache.check_artists(input_hash, config_hash)
            if status.valid:
                logger.info("Using cached artists")
                return self.cache.load_artists(), True

        # Compute
        logger.info("Computing artist aggregation...")
        agg_config = AggregationConfig(min_tracks=self.config.min_tracks_per_artist)
        result = aggregate_tracks_to_artists(tracks, agg_config)

        # Cache
        key = CacheKey(input_hash, config_hash)
        self.cache.save_artists(result.artists, key)

        return result.artists, False

    def _get_or_compute_graph(
        self, artists: list[dict], preset: str,
        input_hash: str, config_hash: str
    ) -> tuple[dict, bool]:
        """Get graph from cache or compute.

        Returns:
            Tuple of (graph_data, from_cache)
        """
        if self.config.enable_cache:
            status = self.cache.check_graph(preset, input_hash, config_hash)
            if status.valid:
                logger.info(f"Using cached graph for {preset}")
                return self.cache.load_graph(preset), True

        # Compute
        logger.info(f"Computing graph for {preset}...")
        graph_config = GraphConfig(
            presets=[preset],
            k_neighbors=self.config.k_neighbors,
            min_similarity=self.config.min_similarity,
        )
        result = compute_graphs(artists, graph_config)
        graph_result = result.graphs[preset]
        graph_data = graph_result_to_json(graph_result)

        # Validate
        validation = validate_graph(graph_data)
        if validation.warnings:
            for w in validation.warnings:
                logger.warning(f"Graph {preset}: {w.message}")

        # Cache
        key = CacheKey(input_hash, config_hash)
        self.cache.save_graph(preset, graph_data, key)

        return graph_data, False

    def _get_or_compute_embedding(
        self, artists: list[dict], preset: str,
        input_hash: str, config_hash: str
    ) -> tuple[dict, bool]:
        """Get embedding from cache or compute.

        Returns:
            Tuple of (embedding_data, from_cache)
        """
        if self.config.enable_cache:
            status = self.cache.check_embedding(preset, input_hash, config_hash)
            if status.valid:
                logger.info(f"Using cached embedding for {preset}")
                return self.cache.load_embedding(preset), True

        # Compute
        logger.info(f"Computing embedding for {preset}...")
        embed_config = EmbeddingConfig(
            presets=[preset],
            n_neighbors=self.config.umap_n_neighbors,
            min_dist=self.config.umap_min_dist,
            random_state=self.config.umap_random_state,
        )
        result = compute_embeddings(artists, embed_config)
        embed_result = result.embeddings[preset]
        embed_data = embedding_result_to_json(embed_result)

        # Validate
        validation = validate_embedding(embed_data)
        if validation.warnings:
            for w in validation.warnings:
                logger.warning(f"Embedding {preset}: {w.message}")

        # Cache
        key = CacheKey(input_hash, config_hash)
        self.cache.save_embedding(preset, embed_data, key)

        return embed_data, False


    def _get_or_compute_genre_graph(
        self, artists: list[dict], input_hash: str, config_hash: str
    ) -> tuple[dict, bool]:
        """Get genre graph from cache or compute."""
        if self.config.enable_cache:
            status = self.cache.check_genre_graph(input_hash, config_hash)
            if status.valid:
                logger.info("Using cached genre graph")
                return self.cache.load_genre_graph(), True

        logger.info("Computing genre graph...")
        genre_config = GenreGraphConfig()
        result = compute_genre_graph(artists, genre_config)
        data = genre_graph_result_to_json(result)

        key = CacheKey(input_hash, config_hash)
        self.cache.save_genre_graph(data, key)

        return data, False


def run_pipeline(tracks_path: str | Path, config_path: str | Path | None = None) -> PipelineResult:
    """Convenience function to run pipeline.

    Args:
        tracks_path: Path to normalized_tracks.json
        config_path: Path to config.yaml (defaults to app/config.yaml)

    Returns:
        PipelineResult
    """
    tracks_path = Path(tracks_path)

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    config = PipelineConfig.from_yaml(config_path)
    runner = PipelineRunner(config)

    return runner.run(tracks_path)
