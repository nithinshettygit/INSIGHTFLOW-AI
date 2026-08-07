"""Health and readiness endpoints."""

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
def health_check() -> dict:
    """Liveness probe — confirms the API process is running."""
    settings = get_settings()
    logger.debug("Health check requested")
    return {
        "status": "ok",
        "service": "insightflow-ai",
        "version": __version__,
        "environment": settings.app_env,
    }
