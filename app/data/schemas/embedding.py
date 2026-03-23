"""Embedding schemas - UMAP 2D positions and clustering."""

from typing import Optional, Any
from pydantic import BaseModel, Field


class EmbeddingPoint(BaseModel):
    """A single point in the 2D embedding space."""

    id: str = Field(..., description="Artist/item identifier")
    x: float = Field(..., description="UMAP X coordinate")
    y: float = Field(..., description="UMAP Y coordinate")
    cluster: Optional[int] = Field(None, description="DBSCAN/k-means cluster ID")


class AxisCorrelation(BaseModel):
    """Feature correlation with an embedding axis."""

    feature: str = Field(..., description="Feature name")
    correlation: float = Field(..., ge=-1, le=1, description="Pearson correlation")


class EmbeddingCluster(BaseModel):
    """Cluster information from DBSCAN/k-means on embedding."""

    cluster_id: int = Field(..., description="Cluster identifier")
    size: int = Field(..., ge=0, description="Number of points in cluster")
    centroid_x: float = Field(..., description="Cluster centroid X")
    centroid_y: float = Field(..., description="Cluster centroid Y")
    members: list[str] = Field(default_factory=list, description="Artist IDs in cluster")


class EmbeddingMetrics(BaseModel):
    """Quality metrics for the embedding."""

    silhouette_score: Optional[float] = Field(
        None, ge=-1, le=1,
        description="Clustering quality (-1 to 1, higher is better)"
    )
    num_clusters: int = Field(..., ge=0, description="Number of clusters")
    noise_count: Optional[int] = Field(
        None, ge=0,
        description="DBSCAN noise points count"
    )


class Embedding(BaseModel):
    """Complete UMAP embedding with positions, clusters, and metadata."""

    preset: str = Field(..., description="Embedding preset name")
    points: list[EmbeddingPoint] = Field(..., description="All 2D positions")

    # Clustering results
    clusters: list[EmbeddingCluster] = Field(
        default_factory=list,
        description="Cluster information"
    )
    metrics: Optional[EmbeddingMetrics] = Field(None, description="Quality metrics")

    # Axis interpretation
    x_axis: list[AxisCorrelation] = Field(
        default_factory=list,
        description="Features correlating with X axis"
    )
    y_axis: list[AxisCorrelation] = Field(
        default_factory=list,
        description="Features correlating with Y axis"
    )

    # UMAP parameters used
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="UMAP parameters (n_neighbors, min_dist, metric)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "preset": "combined_balanced",
                "points": [
                    {"id": "Artist A", "x": 1.23, "y": -0.45, "cluster": 0},
                    {"id": "Artist B", "x": 1.15, "y": -0.52, "cluster": 0}
                ],
                "metrics": {"silhouette_score": 0.51, "num_clusters": 18},
                "params": {"n_neighbors": 15, "min_dist": 0.1, "metric": "cosine"}
            }
        }


# Available embedding presets
EMBEDDING_PRESETS = [
    "audio_only",
    "genre",
    "era",
    "combined_balanced",
    "combined_genre"
]
