"""Composite similarity functions combining audio, genre, and temporal."""

from dataclasses import dataclass
from typing import Sequence

from .audio import audio_similarity, DEFAULT_AUDIO_FEATURES
from .genre import genre_overlap
from .temporal import decade_similarity


@dataclass
class SimilarityWeights:
    """Weights for combined similarity computation."""
    audio: float = 0.33
    genre: float = 0.33
    era: float = 0.34

    def normalized(self) -> "SimilarityWeights":
        """Return normalized weights that sum to 1.0."""
        total = self.audio + self.genre + self.era
        if total == 0:
            return SimilarityWeights(1/3, 1/3, 1/3)
        return SimilarityWeights(
            audio=self.audio / total,
            genre=self.genre / total,
            era=self.era / total
        )


# Standard weight presets
WEIGHT_PRESETS = {
    'balanced': SimilarityWeights(audio=0.33, genre=0.33, era=0.34),
    'audio_focused': SimilarityWeights(audio=0.6, genre=0.3, era=0.1),
    'genre_focused': SimilarityWeights(audio=0.3, genre=0.6, era=0.1),
    'era_focused': SimilarityWeights(audio=0.2, genre=0.3, era=0.5),
    'audio_era': SimilarityWeights(audio=0.5, genre=0.2, era=0.3),
}


@dataclass
class SimilarityResult:
    """Result of composite similarity computation."""
    combined: float
    audio: float
    genre: float
    era: float
    weights: SimilarityWeights


def combined_similarity(
    artist1: dict,
    artist2: dict,
    weights: SimilarityWeights | None = None,
    audio_features: Sequence[str] | None = None,
    era_decay_years: float = 60.0
) -> SimilarityResult:
    """
    Compute weighted composite similarity between two artists.

    Args:
        artist1: First artist dict with keys:
            - audio_profile: {feature: value}
            - genres: list[str]
            - mean_year: float
        artist2: Second artist dict (same structure)
        weights: Similarity weights. Defaults to balanced.
        audio_features: Audio features to use. Defaults to DEFAULT_AUDIO_FEATURES.
        era_decay_years: Years for era similarity decay. Default 60.

    Returns:
        SimilarityResult with combined score and components
    """
    if weights is None:
        weights = WEIGHT_PRESETS['balanced']

    # Normalize weights
    w = weights.normalized()

    # Audio similarity
    audio_sim = audio_similarity(
        artist1.get('audio_profile', {}),
        artist2.get('audio_profile', {}),
        features=audio_features
    )

    # Genre similarity
    genre_sim = genre_overlap(
        artist1.get('genres', []),
        artist2.get('genres', [])
    )

    # Era similarity
    era_sim = decade_similarity(
        artist1.get('mean_year', 1990),
        artist2.get('mean_year', 1990),
        decay_years=era_decay_years
    )

    # Weighted combination
    combined = (
        audio_sim * w.audio +
        genre_sim * w.genre +
        era_sim * w.era
    )

    return SimilarityResult(
        combined=combined,
        audio=audio_sim,
        genre=genre_sim,
        era=era_sim,
        weights=w
    )


def similarity_matrix(
    artists: list[dict],
    weights: SimilarityWeights | None = None,
    audio_features: Sequence[str] | None = None
) -> list[list[float]]:
    """
    Compute pairwise similarity matrix for a list of artists.

    Args:
        artists: List of artist dicts
        weights: Similarity weights
        audio_features: Audio features to use

    Returns:
        NxN similarity matrix where matrix[i][j] = similarity(artists[i], artists[j])
    """
    n = len(artists)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        matrix[i][i] = 1.0  # Self-similarity
        for j in range(i + 1, n):
            result = combined_similarity(
                artists[i], artists[j],
                weights=weights,
                audio_features=audio_features
            )
            matrix[i][j] = result.combined
            matrix[j][i] = result.combined

    return matrix


def get_preset(name: str) -> SimilarityWeights:
    """Get a weight preset by name."""
    if name not in WEIGHT_PRESETS:
        valid = ', '.join(WEIGHT_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Valid presets: {valid}")
    return WEIGHT_PRESETS[name]
