"""FastAPI application entrypoint for InsightFlow AI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    settings = get_settings()
    logger = get_logger(__name__)
    logger.info(
        "Starting %s (env=%s, debug=%s)",
        settings.app_name,
        settings.app_env,
        settings.debug,
    )
    # Ensure data directories exist early so later phases can write safely.
    for path in (
        settings.upload_path,
        settings.processed_path,
        settings.model_path,
        settings.rag_path,
    ):
        path.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory exists: %s", path)

    yield

    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.10.0",
        description=(
            "InsightFlow AI — modular AI Business Intelligence Platform. "
            "Phase 10: Business Insight Engine (explanation, recommendations, root cause)."
        ),
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Permissive local CORS for the future React client (Phase 7).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["root"])
    def root() -> dict:
        return {
            "message": f"Welcome to {settings.app_name}",
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
            "datasets_upload": f"{settings.api_prefix}/datasets/upload",
            "dataset_profile": f"{settings.api_prefix}/datasets/{{dataset_id}}/profile",
            "intent_detect": f"{settings.api_prefix}/intent/detect",
            "analytics_query": f"{settings.api_prefix}/analytics/query",
            "visualization_chart": f"{settings.api_prefix}/visualization/chart",
            "rag_query": f"{settings.api_prefix}/rag/query",
            "rag_index": f"{settings.api_prefix}/rag/index",
            "ml_run": f"{settings.api_prefix}/ml/run",
            "insight_analyze": f"{settings.api_prefix}/insight/analyze",
        }

    return app


app = create_app()
