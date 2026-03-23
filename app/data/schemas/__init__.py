# Pydantic models for data validation

from .track import Track, AudioFeatures
from .artist import Artist, AudioProfile, SampleTrack
from .graph import Graph, GraphNode, GraphEdge, BridgeInfo, GraphMetrics, GraphPreset
from .embedding import (
    Embedding,
    EmbeddingPoint,
    EmbeddingCluster,
    EmbeddingMetrics,
    AxisCorrelation,
    EMBEDDING_PRESETS
)

__all__ = [
    # Track
    "Track",
    "AudioFeatures",
    # Artist
    "Artist",
    "AudioProfile",
    "SampleTrack",
    # Graph
    "Graph",
    "GraphNode",
    "GraphEdge",
    "BridgeInfo",
    "GraphMetrics",
    "GraphPreset",
    # Embedding
    "Embedding",
    "EmbeddingPoint",
    "EmbeddingCluster",
    "EmbeddingMetrics",
    "AxisCorrelation",
    "EMBEDDING_PRESETS",
]
