"""Insight Engine API endpoints (Phase 10)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.insight import InsightAnalyzeRequest, InsightAnalyzeResponse
from app.services.insight_service import (
    InsightService,
    InsightServiceError,
    get_insight_service,
)

router = APIRouter(prefix="/insight", tags=["insight"])
logger = get_logger(__name__)


@router.post("/analyze", response_model=InsightAnalyzeResponse)
def analyze_insight(
    request: InsightAnalyzeRequest,
    service: InsightService = Depends(get_insight_service),
) -> InsightAnalyzeResponse:
    """Explain, recommend, or root-cause using LLM reasoning over processed evidence."""
    try:
        return service.analyze(request)
    except InsightServiceError as exc:
        logger.warning("Insight analyze rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
