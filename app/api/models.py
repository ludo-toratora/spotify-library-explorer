"""Request and response models for API endpoints."""

from typing import Any, Optional
from pydantic import BaseModel, Field


# Graph responses
class GraphNodeResponse(BaseModel):
    """Graph node in API response."""
    id: str
    name: str
    community: int = 0
    degree: int = 0
    is_bridge: bool = False
    track_ids: list[str] = Field(default_factory=list)
    position: Optional[dict[str, float]] = None


class GraphEdgeResponse(BaseModel):
    """Graph edge in API response."""
    source: str
    target: str
    weight: float


class GraphResponse(BaseModel):
    """Full graph response."""
    preset: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    communities: dict[str, list[str]] = Field(default_factory=dict)
    bridges: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


# Embedding responses
class EmbeddingPointResponse(BaseModel):
    """Single point in embedding space."""
    id: str
    x: float
    y: float
    cluster: int = -1


class EmbeddingResponse(BaseModel):
    """Full embedding response."""
    preset: str
    positions: dict[str, dict[str, Any]]  # x, y coordinates + optional metadata
    clusters: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    axis_correlations: Optional[dict[str, Any]] = None


# Track/Artist responses
class ArtistSummary(BaseModel):
    """Simplified artist for list responses."""
    id: str
    name: str
    track_count: int
    genres: list[str] = Field(default_factory=list)
    audio_profile: dict[str, float] = Field(default_factory=dict)
    avg_year: Optional[float] = None
    parent_genre: Optional[str] = None


class ArtistDetail(BaseModel):
    """Full artist details."""
    id: str
    name: str
    track_count: int
    track_ids: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    audio_profile: dict[str, float] = Field(default_factory=dict)
    decades: dict[str, int] = Field(default_factory=dict)


class ArtistListResponse(BaseModel):
    """Paginated artist list."""
    artists: list[ArtistSummary]
    total: int
    limit: int
    offset: int


# Validation responses
class ValidationIssue(BaseModel):
    """Single validation issue."""
    level: str  # "error" or "warning"
    code: str
    message: str
    count: int = 1


class ValidationResponse(BaseModel):
    """Validation report response."""
    valid: bool
    track_count: int = 0
    artist_count: int = 0
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


# Upload request/response
class UploadResponse(BaseModel):
    """Response after file upload."""
    status: str  # "success" or "error"
    message: str
    track_count: int = 0
    artist_count: int = 0
    file_path: str = ""
    validation: Optional[ValidationResponse] = None


# Recompute request/response
class RecomputeRequest(BaseModel):
    """Request to trigger recomputation."""
    presets: list[str] = Field(default_factory=list, description="Graph presets to compute")
    embedding_presets: list[str] = Field(default_factory=list, description="Embedding presets")
    force: bool = Field(False, description="Force recompute even if cache is valid")
    config_overrides: dict[str, Any] = Field(default_factory=dict, description="Temp config changes")


class JobStatus(BaseModel):
    """Background job status."""
    job_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: float = 0.0  # 0.0 to 1.0
    steps_completed: list[str] = Field(default_factory=list)
    current_step: str = ""
    errors: list[str] = Field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    log: list[dict[str, Any]] = Field(default_factory=list)
    tracks_file: str = ""


class RecomputeResponse(BaseModel):
    """Response when starting recompute job."""
    job_id: str
    status: str


# Config request/response
class ConfigResponse(BaseModel):
    """Safe config subset for frontend."""
    similarity_presets: dict[str, dict[str, Any]]
    embedding_presets: list[dict[str, Any]]
    umap: dict[str, Any]
    graph: dict[str, Any]
    default_preset: str
    default_embedding: str


class ConfigUpdateRequest(BaseModel):
    """Partial config update."""
    similarity_presets: Optional[dict[str, dict[str, Any]]] = None
    umap: Optional[dict[str, Any]] = None
    graph: Optional[dict[str, Any]] = None
    default_preset: Optional[str] = None
    default_embedding: Optional[str] = None


class ConfigUpdateResponse(BaseModel):
    """Response after config update."""
    config: ConfigResponse
    needs_recompute: bool
    changed_sections: list[str]


# Health check
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    cache_available: bool
    artists_count: int
    graphs_available: list[str]
    embeddings_available: list[str]
