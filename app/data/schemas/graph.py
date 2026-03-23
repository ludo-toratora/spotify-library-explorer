"""Graph schemas - artist and genre graph structures."""

from typing import Optional, Any
from pydantic import BaseModel, Field

from .artist import Artist, AudioProfile, SampleTrack


class GraphNode(BaseModel):
    """A node in the similarity graph (artist or genre)."""

    id: str = Field(..., description="Node identifier")
    label: Optional[str] = Field(None, description="Display label")
    track_count: int = Field(1, ge=0, description="Associated track count")

    # For artist nodes
    genres: list[str] = Field(default_factory=list)
    parent_genres: list[str] = Field(default_factory=list)
    primary_decade: Optional[str] = Field(None)
    mean_year: Optional[int] = Field(None)
    audio_profile: Optional[AudioProfile] = Field(None)
    sample_tracks: list[SampleTrack] = Field(default_factory=list)

    # For genre nodes
    parent: Optional[str] = Field(None, description="Parent genre")
    is_parent: bool = Field(False, description="Is this a parent genre")

    # Community assignment
    community: Optional[int] = Field(None, description="Community/cluster ID")


class GraphEdge(BaseModel):
    """An edge connecting two nodes with similarity weight."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    weight: float = Field(..., ge=0, le=1, description="Similarity score")


class BridgeInfo(BaseModel):
    """Information about bridge nodes (high betweenness centrality)."""

    top_by_betweenness: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top nodes by betweenness centrality"
    )
    cross_cluster: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Nodes connecting multiple clusters"
    )


class GraphMetrics(BaseModel):
    """Graph-level metrics."""

    modularity: float = Field(..., description="Louvain modularity score")
    num_communities: int = Field(..., ge=0, description="Number of communities")
    num_nodes: Optional[int] = Field(None, ge=0)
    num_edges: Optional[int] = Field(None, ge=0)


class Graph(BaseModel):
    """Complete graph with nodes, edges, communities, and metrics."""

    nodes: list[GraphNode] = Field(..., description="All graph nodes")
    edges: list[GraphEdge] = Field(..., description="All edges")
    communities: dict[str, int] = Field(
        default_factory=dict,
        description="Node ID to community mapping"
    )
    bridges: Optional[BridgeInfo] = Field(None, description="Bridge node analysis")
    metrics: Optional[GraphMetrics] = Field(None, description="Graph-level metrics")

    # For genre graphs
    hierarchy: Optional[dict[str, list[str]]] = Field(
        None,
        description="Parent genre to children mapping"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {"id": "Artist A", "track_count": 5, "community": 0},
                    {"id": "Artist B", "track_count": 3, "community": 0}
                ],
                "edges": [
                    {"source": "Artist A", "target": "Artist B", "weight": 0.85}
                ],
                "communities": {"Artist A": 0, "Artist B": 0},
                "metrics": {"modularity": 0.65, "num_communities": 12}
            }
        }


# Type alias for preset names
GraphPreset = str  # "balanced", "audio_focused", "genre_focused", "era_focused", "audio_era"
