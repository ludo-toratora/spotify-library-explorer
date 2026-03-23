"""Config endpoints.

GET /api/config - Get safe config subset
POST /api/config - Update config (deep merge)
POST /api/config/restore - Restore to defaults
"""

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.dependencies import get_config, save_config
from app.api.models import ConfigResponse, ConfigUpdateRequest, ConfigUpdateResponse

router = APIRouter()

# Default config values (used for restore)
DEFAULT_CONFIG = {
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
    },
    "paths": {
        "cache_dir": "cache",
        "upload_dir": "uploads",
    },
    "similarity_presets": {
        "balanced": {
            "audio_weight": 0.4,
            "genre_weight": 0.4,
            "era_weight": 0.2,
        },
        "audio_focused": {
            "audio_weight": 0.7,
            "genre_weight": 0.2,
            "era_weight": 0.1,
        },
        "genre_focused": {
            "audio_weight": 0.2,
            "genre_weight": 0.6,
            "era_weight": 0.2,
        },
        "era_focused": {
            "audio_weight": 0.2,
            "genre_weight": 0.2,
            "era_weight": 0.6,
        },
        "audio_era": {
            "audio_weight": 0.5,
            "genre_weight": 0.0,
            "era_weight": 0.5,
        },
    },
    "embedding_presets": [
        {"name": "audio_only", "features": ["energy", "danceability", "valence", "acousticness", "instrumentalness", "tempo"]},
        {"name": "combined_balanced", "features": ["audio", "genre", "era"]},
    ],
    "umap": {
        "n_neighbors": 15,
        "min_dist": 0.1,
        "metric": "cosine",
    },
    "graph": {
        "min_similarity": 0.3,
        "k_neighbors": 15,
    },
    "default_preset": "balanced",
    "default_embedding": "combined_balanced",
}


def extract_safe_config(config: dict[str, Any]) -> ConfigResponse:
    """Extract frontend-safe config subset (omit server/paths)."""
    return ConfigResponse(
        similarity_presets=config.get("similarity_presets", {}),
        embedding_presets=config.get("embedding_presets", []),
        umap=config.get("umap", {}),
        graph=config.get("graph", {}),
        default_preset=config.get("default_preset", "balanced"),
        default_embedding=config.get("default_embedding", "combined_balanced"),
    )


def deep_merge(base: dict, updates: dict) -> dict:
    """Deep merge updates into base dict."""
    result = base.copy()
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def detect_recompute_needed(old_config: dict, new_config: dict) -> tuple[bool, list[str]]:
    """Check if config changes require recomputation.

    Returns:
        Tuple of (needs_recompute, list of changed sections)
    """
    recompute_sections = ["similarity_presets", "umap", "graph"]
    changed = []

    for section in recompute_sections:
        if old_config.get(section) != new_config.get(section):
            changed.append(section)

    return len(changed) > 0, changed


@router.post("/config/restore", response_model=ConfigResponse)
async def restore_config() -> ConfigResponse:
    """Restore config to default values.

    Resets all settings to their factory defaults.
    Note: This will require a pipeline recompute to take effect.
    """
    save_config(DEFAULT_CONFIG.copy())
    return extract_safe_config(DEFAULT_CONFIG)


@router.get("/config/defaults", response_model=ConfigResponse)
async def get_defaults() -> ConfigResponse:
    """Get default config values (without applying them).

    Useful for UI to show what defaults would be.
    """
    return extract_safe_config(DEFAULT_CONFIG)


@router.get("/config", response_model=ConfigResponse)
async def get_config_endpoint() -> ConfigResponse:
    """Get safe config subset for frontend.

    Returns similarity presets, UMAP settings, graph settings,
    and defaults. Omits server/paths for security.
    """
    config = get_config()
    return extract_safe_config(config)


@router.post("/config", response_model=ConfigUpdateResponse)
async def update_config(request: ConfigUpdateRequest) -> ConfigUpdateResponse:
    """Update config with partial values (deep merge).

    Only updates provided fields. Changes to similarity_presets,
    umap, or graph will set needs_recompute=true.

    Args:
        request: Partial config update

    Returns:
        Updated config with recompute flag
    """
    current_config = get_config()

    # Build updates dict from request (only non-None fields)
    updates = {}
    if request.similarity_presets is not None:
        updates["similarity_presets"] = request.similarity_presets
    if request.umap is not None:
        updates["umap"] = request.umap
    if request.graph is not None:
        updates["graph"] = request.graph
    if request.default_preset is not None:
        updates["default_preset"] = request.default_preset
    if request.default_embedding is not None:
        updates["default_embedding"] = request.default_embedding

    if not updates:
        # No changes
        return ConfigUpdateResponse(
            config=extract_safe_config(current_config),
            needs_recompute=False,
            changed_sections=[],
        )

    # Detect what changed
    needs_recompute, changed_sections = detect_recompute_needed(current_config, updates)

    # Deep merge
    new_config = deep_merge(current_config, updates)

    # Validate preset references
    if new_config.get("default_preset") not in new_config.get("similarity_presets", {}):
        raise HTTPException(
            status_code=400,
            detail=f"default_preset '{new_config['default_preset']}' not in similarity_presets"
        )

    embedding_names = [p.get("name") for p in new_config.get("embedding_presets", [])]
    if new_config.get("default_embedding") not in embedding_names:
        raise HTTPException(
            status_code=400,
            detail=f"default_embedding '{new_config['default_embedding']}' not in embedding_presets"
        )

    # Save
    save_config(new_config)

    return ConfigUpdateResponse(
        config=extract_safe_config(new_config),
        needs_recompute=needs_recompute,
        changed_sections=changed_sections,
    )
