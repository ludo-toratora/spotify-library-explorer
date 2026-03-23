"""Genre graph endpoint.

GET /api/genre-graph - Get genre co-occurrence graph
"""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_cache

router = APIRouter()


@router.get("/genre-graph")
async def get_genre_graph() -> dict:
    """Get genre co-occurrence graph.

    Returns:
        Genre graph with nodes, edges, communities, bridges, and stats.
        404 if pipeline hasn't been run yet.
    """
    cache = get_cache()

    try:
        data = cache.load_genre_graph()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Genre graph not found. Run pipeline first."
        )

    return data
