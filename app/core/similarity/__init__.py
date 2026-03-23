# Similarity functions: audio, genre, temporal, composite

from .audio import (
    cosine_similarity,
    audio_similarity,
    audio_distance,
    DEFAULT_AUDIO_FEATURES,
)

from .genre import (
    jaccard_similarity,
    genre_overlap,
    weighted_genre_overlap,
    dice_coefficient,
)

from .temporal import (
    decade_similarity,
    era_similarity_exponential,
    decade_distribution_similarity,
    year_to_decade,
    get_era_type,
)

from .composite import (
    SimilarityWeights,
    SimilarityResult,
    WEIGHT_PRESETS,
    combined_similarity,
    similarity_matrix,
    get_preset,
)

__all__ = [
    # Audio
    "cosine_similarity",
    "audio_similarity",
    "audio_distance",
    "DEFAULT_AUDIO_FEATURES",
    # Genre
    "jaccard_similarity",
    "genre_overlap",
    "weighted_genre_overlap",
    "dice_coefficient",
    # Temporal
    "decade_similarity",
    "era_similarity_exponential",
    "decade_distribution_similarity",
    "year_to_decade",
    "get_era_type",
    # Composite
    "SimilarityWeights",
    "SimilarityResult",
    "WEIGHT_PRESETS",
    "combined_similarity",
    "similarity_matrix",
    "get_preset",
]
