"""Graph endpoints.

GET /api/graphs - List available presets
GET /api/graphs/{preset} - Get graph for preset with optional enrichment
"""

import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import get_cache, get_graph_presets, get_tracks_index
from app.api.models import GraphResponse

router = APIRouter()


VALID_PRESETS = ["balanced", "audio_focused", "genre_focused", "era_focused", "audio_era"]


@router.get("/graphs")
async def list_graphs() -> dict:
    """List available graph presets and their status."""
    cache = get_cache()
    available = []
    missing = []

    for preset in VALID_PRESETS:
        graph_path = cache.graphs_dir / preset / "graph.json"
        if graph_path.exists():
            available.append(preset)
        else:
            missing.append(preset)

    return {
        "presets": VALID_PRESETS,
        "available": available,
        "missing": missing,
    }


@router.get("/graphs/{preset}", response_model=GraphResponse)
async def get_graph(
    preset: str,
    enrich: bool = Query(False, description="Add track_ids and positions to nodes"),
) -> GraphResponse:
    """Get graph data for a specific preset.

    Args:
        preset: One of balanced, audio_focused, genre_focused, era_focused, audio_era
        enrich: If true, adds track_ids list and positions to each node

    Returns:
        Graph with nodes, edges, communities, and bridges
    """
    if preset not in VALID_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset: {preset}. Must be one of: {', '.join(VALID_PRESETS)}"
        )

    cache = get_cache()

    try:
        graph_data = cache.load_graph(preset)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Graph for preset '{preset}' not found. Run pipeline first."
        )

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    raw_communities = graph_data.get("communities", {})
    raw_bridges = graph_data.get("bridges", [])
    metrics = graph_data.get("metrics", {})

    # Transform communities: pipeline saves {artist: community_id}
    # API expects {community_id: [artists]}
    communities: dict[str, list[str]] = {}
    if raw_communities:
        # Check format - if values are ints, it's artist->community mapping
        sample_value = next(iter(raw_communities.values()), None)
        if isinstance(sample_value, int):
            # Convert {artist: community_id} to {community_id: [artists]}
            for artist, comm_id in raw_communities.items():
                comm_key = str(comm_id)
                if comm_key not in communities:
                    communities[comm_key] = []
                communities[comm_key].append(artist)
        elif isinstance(sample_value, list):
            # Already in correct format
            communities = raw_communities
        else:
            communities = {}

    # Transform bridges: pipeline saves {'top_by_betweenness': [...], 'cross_cluster': [...]}
    # API expects list of artist names
    bridges: list[str] = []
    if isinstance(raw_bridges, list):
        bridges = raw_bridges
    elif isinstance(raw_bridges, dict):
        # Extract artist names from bridge dict
        seen = set()
        for key in ['top_by_betweenness', 'cross_cluster', 'top_bridges']:
            for bridge in raw_bridges.get(key, []):
                artist = bridge.get('artist') or bridge.get('name') or bridge.get('id', '')
                if artist and artist not in seen:
                    bridges.append(artist)
                    seen.add(artist)

    # Build community lookup: node_id -> community_id
    community_lookup = {}
    for comm_id, members in communities.items():
        for member in members:
            community_lookup[member] = int(comm_id) if comm_id.isdigit() else comm_id

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

    # Enrich all nodes with community and metadata
    bridge_set = set(bridges)
    enriched_nodes = []
    for node in nodes:
        node_id = node.get("id", node.get("name", ""))

        enriched_node = {**node}

        # Add community assignment
        if node_id in community_lookup:
            enriched_node["community"] = community_lookup[node_id]

        # Add artist metadata for coloring
        if node_id in artists_lookup:
            artist = artists_lookup[node_id]
            parent_genres = artist.get("parent_genres") or artist.get("parent_genre") or []
            enriched_node.setdefault("parent_genre", parent_genres[0] if parent_genres else None)
            enriched_node.setdefault("genres", artist.get("genres", []))
            enriched_node.setdefault("primary_decade", artist.get("primary_decade"))
            audio_profile = artist.get("audio_profile") or {}
            enriched_node.setdefault("avg_energy", audio_profile.get("energy"))
            enriched_node.setdefault("avg_tempo", audio_profile.get("tempo"))
            enriched_node.setdefault("avg_danceability", audio_profile.get("danceability"))
            enriched_node.setdefault("avg_valence", audio_profile.get("valence"))
            enriched_node.setdefault("track_count", artist.get("track_count"))

        # Add bridge flag
        enriched_node["is_bridge"] = node_id in bridge_set

        enriched_nodes.append(enriched_node)

    nodes = enriched_nodes

    # Additional enrichment with track_ids if requested
    if enrich:
        tracks_index = get_tracks_index()

        final_nodes = []
        for node in nodes:
            node_id = node.get("id", node.get("name", ""))
            track_ids = tracks_index.get_track_ids_for_artist(node_id)

            enriched_node = {
                **node,
                "track_ids": track_ids,
            }
            final_nodes.append(enriched_node)

        nodes = final_nodes

    return GraphResponse(
        preset=preset,
        nodes=nodes,
        edges=edges,
        communities=communities,
        bridges=bridges,
        metrics=metrics,
    )
