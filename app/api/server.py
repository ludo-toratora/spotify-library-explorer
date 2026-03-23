"""FastAPI application server.

Creates the app with:
- Lifespan manager (load config/cache on startup)
- CORS middleware
- All API routes
- Health endpoint
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_config, get_cache, get_tracks_index
from app.api.models import HealthResponse
from app.api.routes import register_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager - runs on startup and shutdown."""
    # Startup
    logger.info("Starting LibraryExplorer API server...")

    # Load config and initialize cache
    config = get_config()
    cache = get_cache()
    cache.ensure_dirs()

    # Store in app state
    app.state.config = config
    app.state.cache = cache
    app.state.jobs = {}  # Background job tracking

    # Pre-load tracks index
    tracks_index = get_tracks_index()

    logger.info(f"Server ready. Cache dir: {cache.cache_dir}")
    logger.info(f"Available artists: {len(tracks_index.artists)}")

    yield

    # Shutdown
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="LibraryExplorer API",
        description="API for Spotify library analysis and playlist building",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS - allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prevent browser caching of UI HTML/JS files
    @app.middleware("http")
    async def no_cache_ui(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/ui/") and path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    # Register all routes
    register_routes(app)

    # Serve favicon to suppress 404s
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        from fastapi.responses import Response
        return Response(content=b"", media_type="image/x-icon")

    # Mount static files for UI
    ui_dir = Path(__file__).parent.parent / "ui"
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")

    # Health endpoint at root
    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        """Check server health and cache status."""
        cache = get_cache()
        tracks_index = get_tracks_index()

        # Check which graphs and embeddings are available
        graphs_available = []
        embeddings_available = []

        if cache.graphs_dir.exists():
            for preset_dir in cache.graphs_dir.iterdir():
                if preset_dir.is_dir() and (preset_dir / "graph.json").exists():
                    graphs_available.append(preset_dir.name)

        if cache.embeddings_dir.exists():
            for preset_dir in cache.embeddings_dir.iterdir():
                if preset_dir.is_dir() and (preset_dir / "embedding.json").exists():
                    embeddings_available.append(preset_dir.name)

        return HealthResponse(
            status="ok",
            cache_available=cache.cache_dir.exists(),
            artists_count=len(tracks_index.artists),
            graphs_available=sorted(graphs_available),
            embeddings_available=sorted(embeddings_available),
        )

    return app


# Create app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    server_config = config.get("server", {})

    uvicorn.run(
        "app.api.server:app",
        host=server_config.get("host", "127.0.0.1"),
        port=server_config.get("port", 8000),
        reload=server_config.get("debug", True),
    )
