"""Intent detection API endpoints (Phase 4)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.intent import (
    IntentCatalogResponse,
    IntentDetectRequest,
    IntentDetectResponse,
)
from app.services.intent_service import IntentService, IntentServiceError, get_intent_service

router = APIRouter(prefix="/intent", tags=["intent"])
logger = get_logger(__name__)


@router.post("/detect", response_model=IntentDetectResponse)
def detect_intent(
    request: IntentDetectRequest,
    service: IntentService = Depends(get_intent_service),
) -> IntentDetectResponse:
    """Classify a user query via LangGraph + Groq (rules fallback)."""
    try:
        return service.detect(request)
    except IntentServiceError as exc:
        logger.warning("Intent detection rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/catalog", response_model=IntentCatalogResponse)
def intent_catalog(
    service: IntentService = Depends(get_intent_service),
) -> IntentCatalogResponse:
    """List supported intents and example queries."""
    return service.catalog()
