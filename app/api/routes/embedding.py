"""Embedding endpoints.

GET /api/embedding - Get UMAP embedding with optional clustering
"""

import json
from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import get_cache
from app.api.models import EmbeddingResponse
from app.pipeline.steps.compute_embeddings import DEFAULT_EMBEDDING_PRESETS

router = APIRouter()


@router.get("/embedding/presets")
async def list_embedding_presets() -> dict:
    """List available embedding presets and their status."""
    cache = get_cache()
    available = []
    missing = []

    for preset in DEFAULT_EMBEDDING_PRESETS:
        embed_path = cache.embeddings_dir / preset / "embedding.json"
        if embed_path.exists():
            available.append(preset)
        else:
            missing.append(preset)

    return {
        "presets": DEFAULT_EMBEDDING_PRESETS,
        "available": available,
        "missing": missing,
    }


@router.get("/embedding", response_model=EmbeddingResponse)
async def get_embedding(
    preset: str = Query("combined_balanced", description="Embedding preset to use"),
    include_clusters: bool = Query(True, description="Include cluster assignments"),
) -> EmbeddingResponse:
    """Get UMAP embedding positions.

    Args:
        preset: Embedding preset (audio_only, genre, era, combined_balanced, combined_genre)
        include_clusters: Whether to include cluster assignments

    Returns:
        Embedding with positions, optional clusters, and metrics
    """
    if preset not in DEFAULT_EMBEDDING_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset '{preset}'. Valid presets: {', '.join(DEFAULT_EMBEDDING_PRESETS)}"
        )

    cache = get_cache()

    try:
        embed_data = cache.load_embedding(preset)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Embedding '{preset}' not computed yet. Run pipeline first."
        )

    raw_positions = embed_data.get("positions", {})
    clusters = embed_data.get("clusters", {}) if include_clusters else {}
    metrics = embed_data.get("metrics", {})

    # Transform axis_correlations keys: x_axis/y_axis → x/y
    raw_axis = embed_data.get("axis_correlations") or {}
    axis_correlations = None
    if raw_axis:
        axis_correlations = {
            "x": raw_axis.get("x_axis") or raw_axis.get("x"),
            "y": raw_axis.get("y_axis") or raw_axis.get("y"),
        }

    # Load artists metadata for enrichment
    cache_dir = cache.cache_dir
    artists_cache_path = cache_dir / "artists" / "artists.json"
    artists_lookup = {}
    if artists_cache_path.exists():
        with open(artists_cache_path) as f:
            artists_data = json.load(f)
            # Handle both list and dict formats
            if isinstance(artists_data, list):
                artists_list = artists_data
            else:
                artists_list = artists_data.get("artists", [])
            for artist in artists_list:
                artist_id = artist.get("id") or artist.get("name")
                if artist_id:
                    artists_lookup[artist_id] = artist

    # Transform positions: pipeline saves {artist: [x, y]}
    # API expects {artist: {x: float, y: float, ...metadata}}
    positions: dict[str, dict[str, float]] = {}
    for artist, pos in raw_positions.items():
        if isinstance(pos, list) and len(pos) >= 2:
            positions[artist] = {"x": float(pos[0]), "y": float(pos[1])}
        elif isinstance(pos, dict) and "x" in pos and "y" in pos:
            positions[artist] = {"x": pos["x"], "y": pos["y"]}
        else:
            # Skip invalid positions
            continue

        # Enrich with artist metadata for coloring
        if artist in artists_lookup:
            artist_data = artists_lookup[artist]
            parent_genres = artist_data.get("parent_genres") or artist_data.get("parent_genre") or []
            positions[artist]["parent_genre"] = parent_genres[0] if parent_genres else None
            positions[artist]["genres"] = artist_data.get("genres", [])
            positions[artist]["primary_decade"] = artist_data.get("primary_decade")
            audio_profile = artist_data.get("audio_profile") or {}
            positions[artist]["avg_energy"] = audio_profile.get("energy")
            positions[artist]["avg_tempo"] = audio_profile.get("tempo")
            positions[artist]["avg_danceability"] = audio_profile.get("danceability")
            positions[artist]["avg_valence"] = audio_profile.get("valence")
            positions[artist]["avg_acousticness"] = audio_profile.get("acousticness")
            positions[artist]["avg_instrumentalness"] = audio_profile.get("instrumentalness")
            positions[artist]["track_count"] = artist_data.get("track_count")

        # Add cluster assignment to position
        if artist in clusters:
            positions[artist]["cluster"] = clusters[artist]

    return EmbeddingResponse(
        preset=preset,
        positions=positions,
        clusters=clusters,
        metrics=metrics,
        axis_correlations=axis_correlations,
    )
