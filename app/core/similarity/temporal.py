"""Temporal/era similarity functions."""

from typing import Sequence
import numpy as np


def decade_similarity(
    year1: float,
    year2: float,
    decay_years: float = 60.0
) -> float:
    """
    Compute temporal proximity between two years.

    Uses linear decay: closer years = higher similarity.

    Args:
        year1: First year (can be float for mean year)
        year2: Second year
        decay_years: Years at which similarity drops to 0. Default 60.

    Returns:
        Similarity in [0, 1], where 1 = same year, 0 = 60+ years apart
    """
    diff = abs(year1 - year2)
    return max(0.0, 1.0 - diff / decay_years)


def era_similarity_exponential(
    year1: float,
    year2: float,
    half_life: float = 15.0
) -> float:
    """
    Compute temporal proximity with exponential decay.

    More forgiving for small differences, steeper penalty for large ones.

    Args:
        year1: First year
        year2: Second year
        half_life: Years at which similarity is 0.5. Default 15.

    Returns:
        Similarity in (0, 1], where 1 = same year
    """
    diff = abs(year1 - year2)
    return float(np.exp(-diff * np.log(2) / half_life))


def decade_distribution_similarity(
    dist1: dict[str, float],
    dist2: dict[str, float]
) -> float:
    """
    Compute similarity between two decade distributions.

    Uses cosine similarity on decade probability vectors.

    Args:
        dist1: First distribution {decade: proportion}
        dist2: Second distribution {decade: proportion}

    Returns:
        Cosine similarity in [0, 1]
    """
    # Collect all decades
    all_decades = sorted(set(dist1.keys()) | set(dist2.keys()))

    if not all_decades:
        return 0.0

    vec1 = np.array([dist1.get(d, 0.0) for d in all_decades])
    vec2 = np.array([dist2.get(d, 0.0) for d in all_decades])

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def year_to_decade(year: int) -> str:
    """Convert a year to decade string (e.g., 1985 -> '1980s')."""
    return f"{(year // 10) * 10}s"


def get_era_type(
    decade_distribution: dict[str, int],
    entropy_threshold_era: float = 0.5,
    entropy_threshold_timeless: float = 1.5
) -> str:
    """
    Classify an artist's era type based on decade distribution entropy.

    Args:
        decade_distribution: {decade: count}
        entropy_threshold_era: Below this = 'era_specific'
        entropy_threshold_timeless: Above this = 'timeless'

    Returns:
        One of: 'era_specific', 'decade_focused', 'timeless'
    """
    if not decade_distribution:
        return 'unknown'

    # Calculate entropy
    counts = np.array(list(decade_distribution.values()), dtype=float)
    total = counts.sum()

    if total == 0:
        return 'unknown'

    probs = counts / total
    # Filter out zeros for log
    probs = probs[probs > 0]

    entropy = float(-np.sum(probs * np.log(probs)))

    if entropy < entropy_threshold_era:
        return 'era_specific'
    elif entropy > entropy_threshold_timeless:
        return 'timeless'
    else:
        return 'decade_focused'
