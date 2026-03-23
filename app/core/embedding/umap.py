"""UMAP embedding computation and analysis."""

from dataclasses import dataclass, field
from typing import Sequence, Literal
import numpy as np


@dataclass
class UMAPSettings:
    """UMAP hyperparameters."""
    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "cosine"
    random_state: int = 42


@dataclass
class AxisCorrelation:
    """Correlation of UMAP axes with original features."""
    x: dict[str, float] = field(default_factory=dict)
    y: dict[str, float] = field(default_factory=dict)


@dataclass
class EmbeddingCluster:
    """A cluster in the 2D embedding space."""
    id: int
    size: int
    centroid: tuple[float, float]
    sample_ids: list[str]


@dataclass
class ClusteringResult:
    """Result of clustering 2D positions."""
    labels: dict[str, int]  # {id: cluster_label}
    n_clusters: int
    n_noise: int
    silhouette: float | None
    method: str
    clusters: dict[int, EmbeddingCluster]


@dataclass
class EmbeddingResult:
    """Complete UMAP embedding result."""
    positions: dict[str, tuple[float, float]]  # {id: (x, y)}
    settings: UMAPSettings
    axis_correlations: AxisCorrelation | None = None
    clustering: ClusteringResult | None = None


# Standard UMAP presets
UMAP_PRESETS = {
    "default": UMAPSettings(n_neighbors=15, min_dist=0.1, metric="cosine"),
    "local": UMAPSettings(n_neighbors=5, min_dist=0.05, metric="cosine"),
    "global": UMAPSettings(n_neighbors=50, min_dist=0.1, metric="cosine"),
    "spread": UMAPSettings(n_neighbors=15, min_dist=0.5, metric="cosine"),
    "euclidean": UMAPSettings(n_neighbors=15, min_dist=0.1, metric="euclidean"),
}


def compute_umap(
    features: np.ndarray,
    ids: list[str],
    settings: UMAPSettings | None = None,
    normalize_output: bool = True
) -> EmbeddingResult:
    """
    Compute 2D UMAP embedding from feature matrix.

    Args:
        features: NxD feature matrix (N samples, D dimensions)
        ids: List of IDs corresponding to each row
        settings: UMAP hyperparameters
        normalize_output: If True, normalize positions to [-1, 1]

    Returns:
        EmbeddingResult with 2D positions
    """
    try:
        import umap as umap_lib
    except ImportError:
        raise ImportError("umap-learn not installed. Run: pip install umap-learn")

    if settings is None:
        settings = UMAP_PRESETS["default"]

    # Compute UMAP
    reducer = umap_lib.UMAP(
        n_neighbors=settings.n_neighbors,
        min_dist=settings.min_dist,
        metric=settings.metric,
        random_state=settings.random_state,
        n_components=2,
    )

    positions = reducer.fit_transform(features)

    # Normalize to [-1, 1] for consistent visualization
    if normalize_output:
        positions = positions - positions.mean(axis=0)
        max_abs = np.abs(positions).max()
        if max_abs > 0:
            positions = positions / max_abs

    # Convert to dict
    position_dict = {
        ids[i]: (float(positions[i, 0]), float(positions[i, 1]))
        for i in range(len(ids))
    }

    return EmbeddingResult(
        positions=position_dict,
        settings=settings
    )


def compute_axis_correlations(
    positions: dict[str, tuple[float, float]],
    features: np.ndarray,
    ids: list[str],
    feature_names: list[str]
) -> AxisCorrelation:
    """
    Compute Pearson correlation between UMAP axes and original features.

    Helps interpret what each axis represents.

    Args:
        positions: {id: (x, y)}
        features: NxD feature matrix
        ids: IDs corresponding to feature rows
        feature_names: Names for each feature column

    Returns:
        AxisCorrelation with {feature: correlation} for each axis
    """
    from scipy.stats import pearsonr

    # Extract position arrays in same order as ids
    x_vals = np.array([positions[id][0] for id in ids])
    y_vals = np.array([positions[id][1] for id in ids])

    correlations = AxisCorrelation(x={}, y={})

    for i, name in enumerate(feature_names):
        feat_vals = features[:, i]

        corr_x, _ = pearsonr(x_vals, feat_vals)
        corr_y, _ = pearsonr(y_vals, feat_vals)

        correlations.x[name] = round(float(corr_x), 3)
        correlations.y[name] = round(float(corr_y), 3)

    return correlations


def cluster_positions(
    positions: dict[str, tuple[float, float]],
    method: Literal["auto", "dbscan", "kmeans"] = "auto"
) -> ClusteringResult:
    """
    Cluster 2D UMAP positions.

    Args:
        positions: {id: (x, y)}
        method: "auto" tries DBSCAN first, falls back to k-means

    Returns:
        ClusteringResult with cluster assignments
    """
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics import silhouette_score

    ids = list(positions.keys())
    pos_array = np.array([positions[id] for id in ids])

    n_clusters = 0
    n_noise = 0
    labels = None
    used_method = method

    # Try DBSCAN first
    if method in ("dbscan", "auto"):
        for eps in [0.08, 0.12, 0.18, 0.25]:
            clusterer = DBSCAN(eps=eps, min_samples=5)
            trial_labels = clusterer.fit_predict(pos_array)
            trial_n_clusters = len(set(trial_labels)) - (1 if -1 in trial_labels else 0)

            if trial_n_clusters >= 3:
                labels = trial_labels
                n_clusters = trial_n_clusters
                n_noise = int((labels == -1).sum())
                used_method = "dbscan"
                break

    # Fall back to k-means
    if (labels is None or n_clusters < 2) and method in ("kmeans", "auto"):
        best_k = 10
        best_sil = -1
        best_labels = None

        for k in range(5, min(25, len(pos_array))):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            trial_labels = km.fit_predict(pos_array)
            sil = silhouette_score(pos_array, trial_labels)

            if sil > best_sil:
                best_sil = sil
                best_k = k
                best_labels = trial_labels

        if best_labels is not None:
            labels = best_labels
            n_clusters = best_k
            n_noise = 0
            used_method = "kmeans"

    # Fallback: all in one cluster
    if labels is None:
        labels = np.zeros(len(pos_array), dtype=int)
        n_clusters = 1
        n_noise = 0

    # Compute silhouette
    silhouette = None
    if n_clusters >= 2:
        valid_mask = labels >= 0
        if valid_mask.sum() >= 2:
            silhouette = float(silhouette_score(pos_array[valid_mask], labels[valid_mask]))
            silhouette = round(silhouette, 4)

    # Build cluster info
    clusters = {}
    for c in set(labels):
        if c == -1:
            continue
        mask = labels == c
        cluster_pos = pos_array[mask]
        cluster_ids = [ids[i] for i in range(len(ids)) if labels[i] == c]

        clusters[int(c)] = EmbeddingCluster(
            id=int(c),
            size=int(mask.sum()),
            centroid=(
                float(cluster_pos[:, 0].mean()),
                float(cluster_pos[:, 1].mean())
            ),
            sample_ids=cluster_ids[:10]
        )

    return ClusteringResult(
        labels={ids[i]: int(labels[i]) for i in range(len(ids))},
        n_clusters=n_clusters,
        n_noise=n_noise,
        silhouette=silhouette,
        method=used_method,
        clusters=clusters
    )


def compare_to_communities(
    positions: dict[str, tuple[float, float]],
    communities: dict[str, int]
) -> dict:
    """
    Compute how well UMAP embedding matches Louvain communities.

    Uses silhouette score to measure if same-community members
    are closer in embedding space.

    Args:
        positions: {id: (x, y)}
        communities: {id: community_id}

    Returns:
        {"silhouette": float, "interpretation": str, ...}
    """
    from sklearn.metrics import silhouette_score

    # Filter to IDs present in both
    common_ids = [id for id in positions if id in communities]

    if len(common_ids) < 10:
        return {"silhouette": None, "note": "Not enough common IDs"}

    pos_array = np.array([positions[id] for id in common_ids])
    labels = np.array([communities[id] for id in common_ids])

    # Need at least 2 communities
    unique_labels = set(labels)
    if len(unique_labels) < 2:
        return {"silhouette": None, "note": "Only one community"}

    score = silhouette_score(pos_array, labels)

    interpretation = "good" if score > 0.3 else "moderate" if score > 0.1 else "poor"

    return {
        "silhouette": round(float(score), 4),
        "interpretation": interpretation,
        "num_artists": len(common_ids),
        "num_communities": len(unique_labels)
    }
