"""Genre set similarity functions."""

from typing import Sequence, Set


def jaccard_similarity(set1: Set, set2: Set) -> float:
    """
    Compute Jaccard similarity between two sets.

    J(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        set1: First set
        set2: Second set

    Returns:
        Jaccard index in [0, 1], where 1 = identical sets
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def genre_overlap(
    genres1: Sequence[str],
    genres2: Sequence[str]
) -> float:
    """
    Compute Jaccard similarity between two genre lists.

    Args:
        genres1: First list of genres
        genres2: Second list of genres

    Returns:
        Jaccard index in [0, 1]
    """
    return jaccard_similarity(set(genres1), set(genres2))


def weighted_genre_overlap(
    genres1: Sequence[str],
    genres2: Sequence[str],
    weights: dict[str, float] | None = None
) -> float:
    """
    Compute weighted overlap between two genre lists.

    If weights are provided, shared genres are weighted by their importance.

    Args:
        genres1: First list of genres
        genres2: Second list of genres
        weights: Optional {genre: weight} mapping

    Returns:
        Weighted overlap score in [0, 1]
    """
    set1 = set(genres1)
    set2 = set(genres2)

    if not set1 or not set2:
        return 0.0

    if weights is None:
        return jaccard_similarity(set1, set2)

    # Weighted intersection / weighted union
    intersection = set1 & set2
    union = set1 | set2

    weighted_inter = sum(weights.get(g, 1.0) for g in intersection)
    weighted_union = sum(weights.get(g, 1.0) for g in union)

    return weighted_inter / weighted_union if weighted_union > 0 else 0.0


def dice_coefficient(set1: Set, set2: Set) -> float:
    """
    Compute Sørensen-Dice coefficient between two sets.

    D(A, B) = 2|A ∩ B| / (|A| + |B|)

    Alternative to Jaccard, less sensitive to set size differences.

    Args:
        set1: First set
        set2: Second set

    Returns:
        Dice coefficient in [0, 1]
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    total = len(set1) + len(set2)

    return (2 * intersection) / total if total > 0 else 0.0
