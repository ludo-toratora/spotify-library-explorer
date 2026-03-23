"""Compute UMAP embeddings for artists.

Input: List of artist dictionaries
Output: 2D positions, cluster assignments, axis correlations

Uses core modules:
- core.embedding.compute_umap
- core.embedding.cluster_positions
- core.embedding.compute_axis_correlations
"""

from dataclasses import dataclass, field
import numpy as np
from typing import Any

from app.core.embedding import (
    compute_umap, UMAPSettings,
    cluster_positions, compute_axis_correlations
)
from app.pipeline.steps.aggregate import artists_to_feature_matrix


# All supported embedding presets
DEFAULT_EMBEDDING_PRESETS = [
    # Audio-only variants (different UMAP settings / metrics)
    'audio_default',      # standard audio features, default UMAP
    'audio_local',        # n_neighbors=5 → captures local/fine-grained structure
    'audio_global',       # n_neighbors=50 → global/macro structure
    'audio_spread',       # min_dist=0.5 → more spread-out layout
    'audio_euclidean',    # euclidean metric instead of cosine
    # Genre-only
    'genre',              # parent genre one-hot vectors only
    # Era-only
    'era',                # decade buckets only
    # Combined feature sets
    'combined_balanced',  # audio=0.4 genre=0.4 era=0.2 (default)
    'combined_audio',     # audio=0.7 genre=0.2 era=0.1
    'combined_genre',     # audio=0.2 genre=0.6 era=0.2
    'combined_era',       # audio=0.2 genre=0.2 era=0.6
    'combined_equal',     # audio=0.33 genre=0.33 era=0.33
]


@dataclass
class EmbeddingConfig:
    """Configuration for embedding computation."""
    presets: list[str] = field(default_factory=lambda: DEFAULT_EMBEDDING_PRESETS.copy())
    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "cosine"
    random_state: int = 42
    cluster_method: str = "auto"  # "auto", "dbscan", or "kmeans"


@dataclass
class EmbeddingResult:
    """Result for a single embedding preset."""
    preset: str
    positions: dict[str, tuple[float, float]]
    clusters: dict[str, int]
    n_clusters: int
    axis_correlations: dict | None
    silhouette: float | None


@dataclass
class ComputeEmbeddingsResult:
    """Result of computing all embeddings."""
    embeddings: dict[str, EmbeddingResult]
    preset_count: int
    artist_count: int


def compute_embeddings(
    artists: list[dict],
    config: EmbeddingConfig | None = None
) -> ComputeEmbeddingsResult:
    """Compute UMAP embeddings for all configured presets.

    Args:
        artists: List of artist dictionaries with audio_profile
        config: Embedding computation configuration

    Returns:
        ComputeEmbeddingsResult with all embedding data
    """
    if config is None:
        config = EmbeddingConfig()

    embeddings = {}

    for preset in config.presets:
        result = compute_single_embedding(artists, preset, config)
        embeddings[preset] = result

    return ComputeEmbeddingsResult(
        embeddings=embeddings,
        preset_count=len(embeddings),
        artist_count=len(artists),
    )


def compute_single_embedding(
    artists: list[dict],
    preset: str,
    config: EmbeddingConfig
) -> EmbeddingResult:
    """Compute UMAP embedding for a single preset.

    Args:
        artists: List of artist dictionaries
        preset: Embedding preset name
        config: Embedding configuration

    Returns:
        EmbeddingResult with positions, clusters, correlations
    """
    # Extract features based on preset
    features, feature_names = _extract_features_for_preset(artists, preset)
    ids = [a['name'] for a in artists]

    # Compute UMAP — some presets override the default settings
    umap_settings = _get_umap_settings(preset, config)

    umap_result = compute_umap(features, ids, umap_settings, normalize_output=True)

    # Cluster positions
    clustering = cluster_positions(umap_result.positions, method=config.cluster_method)

    # Compute axis correlations
    axis_corr = None
    if feature_names:
        axis_corr_result = compute_axis_correlations(
            umap_result.positions, features, ids, feature_names
        )
        axis_corr = {
            'x_axis': axis_corr_result.x,
            'y_axis': axis_corr_result.y,
        }

    return EmbeddingResult(
        preset=preset,
        positions=umap_result.positions,
        clusters=clustering.labels,
        n_clusters=clustering.n_clusters,
        axis_correlations=axis_corr,
        silhouette=clustering.silhouette,
    )


def _get_umap_settings(preset: str, config: 'EmbeddingConfig') -> 'UMAPSettings':
    """Return UMAP settings for a given preset.
    Most presets use the base config; audio_* variants override specific params.
    """
    base = dict(
        n_neighbors=config.n_neighbors,
        min_dist=config.min_dist,
        metric=config.metric,
        random_state=config.random_state,
    )
    overrides = {
        'audio_local':     {'n_neighbors': 5},
        'audio_global':    {'n_neighbors': 50},
        'audio_spread':    {'min_dist': 0.5},
        'audio_euclidean': {'metric': 'euclidean'},
    }
    base.update(overrides.get(preset, {}))
    return UMAPSettings(**base)


def _extract_features_for_preset(
    artists: list[dict],
    preset: str
) -> tuple[np.ndarray, list[str]]:
    """Extract feature matrix based on preset.

    Args:
        artists: List of artist dictionaries
        preset: Embedding preset name

    Returns:
        Tuple of (feature matrix, feature names)
    """
    AUDIO_FEATURES = ['energy', 'danceability', 'valence',
                      'acousticness', 'instrumentalness', 'tempo']

    # Audio-only variants (all use same features; UMAP settings differ per preset)
    if preset in ('audio_only', 'audio_default', 'audio_local',
                  'audio_global', 'audio_spread', 'audio_euclidean'):
        matrix, _ = artists_to_feature_matrix(artists, AUDIO_FEATURES)
        return matrix, AUDIO_FEATURES

    # Genre-only: parent genre one-hot
    elif preset == 'genre':
        return _build_genre_only_features(artists)

    # Era-only: decade buckets
    elif preset == 'era':
        return _build_era_features(artists)

    # Combined feature sets
    elif preset == 'combined_balanced':
        return _build_combined_features(artists, audio_weight=0.4,
                                        genre_weight=0.4, era_weight=0.2)
    elif preset == 'combined_audio':
        return _build_combined_features(artists, audio_weight=0.7,
                                        genre_weight=0.2, era_weight=0.1)
    elif preset == 'combined_genre':
        return _build_combined_features(artists, audio_weight=0.2,
                                        genre_weight=0.6, era_weight=0.2)
    elif preset == 'combined_era':
        return _build_combined_features(artists, audio_weight=0.2,
                                        genre_weight=0.2, era_weight=0.6)
    elif preset == 'combined_equal':
        return _build_combined_features(artists, audio_weight=1/3,
                                        genre_weight=1/3, era_weight=1/3)

    else:
        # Unknown preset — fall back to standard audio
        matrix, _ = artists_to_feature_matrix(artists, AUDIO_FEATURES)
        return matrix, AUDIO_FEATURES


def _build_genre_only_features(artists: list[dict]) -> tuple[np.ndarray, list[str]]:
    """Parent genre one-hot matrix."""
    all_parent_genres = set()
    for a in artists:
        all_parent_genres.update(a.get('parent_genres', []))
    genre_list = sorted(all_parent_genres)

    matrix = np.zeros((len(artists), len(genre_list)))
    for i, a in enumerate(artists):
        for pg in a.get('parent_genres', []):
            if pg in genre_list:
                matrix[i, genre_list.index(pg)] = 1.0

    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    matrix = matrix / row_sums
    return matrix, genre_list


def _build_combined_features(
    artists: list[dict],
    audio_weight: float,
    genre_weight: float,
    era_weight: float
) -> tuple[np.ndarray, list[str]]:
    """Build combined feature matrix with audio, genre, and era.

    Args:
        artists: List of artist dictionaries
        audio_weight: Weight for audio features
        genre_weight: Weight for genre features
        era_weight: Weight for era features

    Returns:
        Tuple of (combined feature matrix, feature names)
    """
    # Audio features (6 dimensions)
    audio_features = ['energy', 'danceability', 'valence',
                      'acousticness', 'instrumentalness', 'tempo']
    audio_matrix, _ = artists_to_feature_matrix(artists, audio_features)

    # Genre features (one-hot for parent genres)
    all_parent_genres = set()
    for a in artists:
        all_parent_genres.update(a.get('parent_genres', []))
    parent_genre_list = sorted(all_parent_genres)

    genre_matrix = np.zeros((len(artists), len(parent_genre_list)))
    for i, a in enumerate(artists):
        for pg in a.get('parent_genres', []):
            if pg in parent_genre_list:
                j = parent_genre_list.index(pg)
                genre_matrix[i, j] = 1.0

    # Normalize genre matrix
    row_sums = genre_matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1  # Avoid division by zero
    genre_matrix = genre_matrix / row_sums

    # Era features (normalized year)
    era_matrix = np.zeros((len(artists), 1))
    for i, a in enumerate(artists):
        year = a.get('mean_year', 1990)
        # Normalize to roughly 0-1 (1950-2030 range)
        era_matrix[i, 0] = (year - 1950) / 80.0

    # Combine with weights (scale dimensions to have equal influence)
    n_audio = audio_matrix.shape[1]
    n_genre = genre_matrix.shape[1] if genre_matrix.shape[1] > 0 else 1
    n_era = era_matrix.shape[1]

    # Scale each matrix
    audio_scaled = audio_matrix * audio_weight * np.sqrt(n_genre / n_audio)
    genre_scaled = genre_matrix * genre_weight
    era_scaled = era_matrix * era_weight * np.sqrt(n_genre / n_era)

    combined = np.hstack([audio_scaled, genre_scaled, era_scaled])

    feature_names = (
        [f"audio_{f}" for f in audio_features] +
        [f"genre_{g}" for g in parent_genre_list] +
        ["era_year"]
    )

    return combined, feature_names


def _build_era_features(artists: list[dict]) -> tuple[np.ndarray, list[str]]:
    """Build era/decade feature matrix.

    Args:
        artists: List of artist dictionaries

    Returns:
        Tuple of (era feature matrix, feature names)
    """
    # Define decade buckets
    decades = ['1960s', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s']

    matrix = np.zeros((len(artists), len(decades)))
    for i, a in enumerate(artists):
        primary_decade = a.get('primary_decade', 'Unknown')
        if primary_decade in decades:
            j = decades.index(primary_decade)
            matrix[i, j] = 1.0
        else:
            # Fallback: use mean_year
            year = a.get('mean_year', 1990)
            decade = f"{(year // 10) * 10}s"
            if decade in decades:
                j = decades.index(decade)
                matrix[i, j] = 1.0

    return matrix, decades


def embedding_result_to_json(result: EmbeddingResult) -> dict:
    """Convert EmbeddingResult to JSON-serializable dict."""
    return {
        'preset': result.preset,
        'positions': {k: list(v) for k, v in result.positions.items()},
        'clusters': result.clusters,
        'metrics': {
            'n_clusters': result.n_clusters,
            'silhouette': result.silhouette,
            'point_count': len(result.positions),
        },
        'axis_correlations': result.axis_correlations,
    }
