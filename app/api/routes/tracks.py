"""Track/Artist endpoints.

GET /api/tracks - List all artists (paginated)
GET /api/tracks/{artist_id} - Get single artist
GET /api/tracks/by-ids - Batch lookup by IDs
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import get_tracks_index, get_normalized_tracks_index
from app.api.models import ArtistSummary, ArtistDetail, ArtistListResponse

router = APIRouter()


@router.get("/tracks", response_model=ArtistListResponse)
async def list_artists(
    limit: int = Query(100, ge=1, le=10000, description="Max artists to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    artist: Optional[str] = Query(None, description="Filter by artist name (partial match)"),
    genre: Optional[str] = Query(None, description="Filter by genre (partial match)"),
) -> ArtistListResponse:
    """Get paginated list of artists.

    Note: Named 'tracks' for API consistency but returns artist data
    (artists are aggregated from tracks).
    """
    tracks_index = get_tracks_index()
    all_artists = tracks_index.artists

    # Filter by artist name if provided
    if artist:
        artist_lower = artist.lower()
        all_artists = [
            a for a in all_artists
            if artist_lower in a.get("name", "").lower()
        ]

    # Filter by genre if provided
    if genre:
        genre_lower = genre.lower()
        all_artists = [
            a for a in all_artists
            if any(genre_lower in g.lower() for g in a.get("genres", []))
        ]

    total = len(all_artists)

    # Paginate
    paginated = all_artists[offset:offset + limit]

    # Convert to summaries
    summaries = []
    for a in paginated:
        parent_genres = a.get("parent_genres") or []
        summaries.append(ArtistSummary(
            id=a.get("id", a.get("name", "")),
            name=a.get("name", ""),
            track_count=a.get("track_count", len(a.get("track_ids", []))),
            genres=a.get("genres", [])[:5],
            audio_profile=a.get("audio_profile", {}),
            avg_year=a.get("mean_year"),
            parent_genre=parent_genres[0] if parent_genres else None,
        ))

    return ArtistListResponse(
        artists=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tracks/by-ids")
async def get_artists_by_ids(
    ids: str = Query(..., description="Comma-separated artist IDs"),
) -> dict:
    """Get multiple artists by their IDs.

    Args:
        ids: Comma-separated list of artist IDs

    Returns:
        Dict mapping ID to artist data (or null if not found)
    """
    tracks_index = get_tracks_index()

    id_list = [id.strip() for id in ids.split(",") if id.strip()]

    results = {}
    for artist_id in id_list:
        artist = tracks_index.get_artist(artist_id)
        if artist:
            results[artist_id] = ArtistDetail(
                id=artist.get("id", artist.get("name", "")),
                name=artist.get("name", ""),
                track_count=artist.get("track_count", len(artist.get("track_ids", []))),
                track_ids=artist.get("track_ids", []),
                genres=artist.get("genres", []),
                audio_profile=artist.get("audio_profile", {}),
                decades=artist.get("decades", {}),
            ).model_dump()
        else:
            results[artist_id] = None

    return {"artists": results}


@router.get("/tracks/bulk-tracks")
async def get_bulk_tracks(
    ids: str = Query(..., description="Comma-separated track IDs"),
) -> dict:
    """Get track details by track IDs (used for CSV export).

    Args:
        ids: Comma-separated list of track IDs

    Returns:
        List of track dicts with name, artist, album, isrc, and audio features
    """
    track_ids = [i.strip() for i in ids.split(",") if i.strip()]
    normalized_index = get_normalized_tracks_index()
    raw_tracks = normalized_index.get_by_ids(track_ids)

    results = []
    for t in raw_tracks:
        audio = t.get("audio_features") or {}
        album_date = t.get("album_date") or ""
        results.append({
            "track_id": t.get("track_id", ""),
            "track_name": t.get("track_name", ""),
            "artist_name": t.get("artist_name", ""),
            "album_name": t.get("album_name", ""),
            "isrc": t.get("isrc", ""),
            "genres": t.get("genres", []),
            "year": str(album_date)[:4] if album_date else "",
            "energy": audio.get("energy"),
            "danceability": audio.get("danceability"),
            "valence": audio.get("valence"),
            "tempo": audio.get("tempo"),
        })

    return {"tracks": results, "count": len(results)}


@router.get("/tracks/{artist_id}/tracks")
async def get_artist_tracks(artist_id: str) -> dict:
    """Get individual tracks for an artist.

    Args:
        artist_id: Artist ID or name

    Returns:
        Dict with artist info and list of simplified track dicts
    """
    tracks_index = get_tracks_index()
    artist = tracks_index.get_artist(artist_id)

    if not artist:
        raise HTTPException(status_code=404, detail=f"Artist not found: {artist_id}")

    track_ids = artist.get("track_ids", [])
    normalized_index = get_normalized_tracks_index()

    if track_ids:
        raw_tracks = normalized_index.get_by_ids(track_ids)
    else:
        raw_tracks = normalized_index.get_by_artist(artist.get("name", ""))

    # Sort by album_date descending (handle None/empty)
    def sort_key(t):
        date = t.get("album_date") or ""
        return date

    raw_tracks = sorted(raw_tracks, key=sort_key, reverse=True)

    # Build simplified track dicts
    tracks = []
    for t in raw_tracks:
        audio = t.get("audio_features") or {}
        tracks.append({
            "track_id": t.get("track_id", ""),
            "track_name": t.get("track_name", ""),
            "album_name": t.get("album_name", ""),
            "album_date": t.get("album_date", ""),
            "duration_ms": t.get("duration_ms"),
            "energy": audio.get("energy"),
            "danceability": audio.get("danceability"),
            "valence": audio.get("valence"),
            "tempo": audio.get("tempo"),
            "added_at": t.get("added_at", ""),
        })

    return {
        "artist_id": artist_id,
        "artist_name": artist.get("name"),
        "tracks": tracks,
    }


@router.get("/search")
async def search_library(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(30, ge=1, le=200, description="Max results"),
) -> dict:
    """Search artists and tracks by name.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results

    Returns:
        Dict with matching artists and tracks
    """
    tracks_index = get_tracks_index()
    normalized_index = get_normalized_tracks_index()

    q_lower = q.lower()

    # Search artists by name
    matching_artists = [
        a for a in tracks_index.artists
        if q_lower in a.get("name", "").lower()
    ][:10]

    artist_results = []
    for a in matching_artists:
        parent_genres = a.get("parent_genres") or []
        artist_results.append({
            "id": a.get("id", a.get("name", "")),
            "name": a.get("name", ""),
            "track_count": a.get("track_count", len(a.get("track_ids", []))),
            "genres": a.get("genres", [])[:5],
            "parent_genre": parent_genres[0] if parent_genres else None,
            "avg_year": a.get("mean_year"),
        })

    # Search tracks
    raw_tracks = normalized_index.search(q, limit=20)
    track_results = []
    for t in raw_tracks:
        audio = t.get("audio_features") or {}
        track_results.append({
            "track_id": t.get("track_id", ""),
            "track_name": t.get("track_name", ""),
            "artist_name": t.get("artist_name", ""),
            "album_name": t.get("album_name", ""),
            "album_date": t.get("album_date", ""),
            "energy": audio.get("energy"),
            "danceability": audio.get("danceability"),
        })

    return {"artists": artist_results, "tracks": track_results}


@router.get("/tracks/{artist_id}", response_model=ArtistDetail)
async def get_artist(artist_id: str) -> ArtistDetail:
    """Get detailed info for a single artist.

    Args:
        artist_id: Artist ID or name
    """
    tracks_index = get_tracks_index()
    artist = tracks_index.get_artist(artist_id)

    if not artist:
        raise HTTPException(status_code=404, detail=f"Artist not found: {artist_id}")

    return ArtistDetail(
        id=artist.get("id", artist.get("name", "")),
        name=artist.get("name", ""),
        track_count=artist.get("track_count", len(artist.get("track_ids", []))),
        track_ids=artist.get("track_ids", []),
        genres=artist.get("genres", []),
        audio_profile=artist.get("audio_profile", {}),
        decades=artist.get("decades", {}),
    )
