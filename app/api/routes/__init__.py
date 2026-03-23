"""API route registration."""

from fastapi import FastAPI

from app.api.routes.graphs import router as graphs_router
from app.api.routes.embedding import router as embedding_router
from app.api.routes.tracks import router as tracks_router
from app.api.routes.validation import router as validation_router
from app.api.routes.config import router as config_router
from app.api.routes.upload import router as upload_router
from app.api.routes.recompute import router as recompute_router
from app.api.routes.genre_graph import router as genre_graph_router


def register_routes(app: FastAPI) -> None:
    """Register all API routes with /api prefix."""
    app.include_router(graphs_router, prefix="/api", tags=["graphs"])
    app.include_router(embedding_router, prefix="/api", tags=["embedding"])
    app.include_router(tracks_router, prefix="/api", tags=["tracks"])
    app.include_router(validation_router, prefix="/api", tags=["validation"])
    app.include_router(config_router, prefix="/api", tags=["config"])
    app.include_router(upload_router, prefix="/api", tags=["upload"])
    app.include_router(recompute_router, prefix="/api", tags=["recompute"])
    app.include_router(genre_graph_router, prefix="/api", tags=["genre_graph"])
