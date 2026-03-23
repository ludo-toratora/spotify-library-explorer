"""Audio feature similarity functions."""

import numpy as np
from typing import Sequence


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector (must be same length as vec1)

    Returns:
        Cosine similarity in [-1, 1], or 0.0 if either vector is zero
    """
    v1 = np.asarray(vec1, dtype=float)
    v2 = np.asarray(vec2, dtype=float)

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(v1, v2) / (norm1 * norm2))


# Default audio features used for similarity
DEFAULT_AUDIO_FEATURES = [
    'energy', 'danceability', 'valence', 'acousticness',
    'instrumentalness', 'speechiness', 'liveness', 'tempo'
]


def audio_similarity(
    profile1: dict[str, float],
    profile2: dict[str, float],
    features: Sequence[str] | None = None
) -> float:
    """
    Compute cosine similarity between two audio profiles.

    Args:
        profile1: First audio profile {feature_name: value}
        profile2: Second audio profile {feature_name: value}
        features: List of feature names to use. Defaults to DEFAULT_AUDIO_FEATURES.

    Returns:
        Cosine similarity in [0, 1]

    Note:
        Tempo should be pre-normalized to [0, 1] range (e.g., tempo / 200)
    """
    if features is None:
        features = DEFAULT_AUDIO_FEATURES

    vec1 = [profile1.get(f, 0.0) for f in features]
    vec2 = [profile2.get(f, 0.0) for f in features]

    return cosine_similarity(vec1, vec2)


def audio_distance(
    profile1: dict[str, float],
    profile2: dict[str, float],
    features: Sequence[str] | None = None
) -> float:
    """
    Compute distance between two audio profiles (1 - cosine_similarity).

    Returns:
        Distance in [0, 2], where 0 = identical, 2 = opposite
    """
    return 1.0 - audio_similarity(profile1, profile2, features)
