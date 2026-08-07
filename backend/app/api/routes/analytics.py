"""Analytics Engine API endpoints (Phase 5)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.analytics import AnalyticsQueryRequest, AnalyticsQueryResponse
from app.services.analytics_service import (
    AnalyticsService,
    AnalyticsServiceError,
    get_analytics_service,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = get_logger(__name__)


@router.post("/query", response_model=AnalyticsQueryResponse)
def run_analytics_query(
    request: AnalyticsQueryRequest,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsQueryResponse:
    """Run aggregation / filter / sort / KPI analytics on a tabular dataset."""
    try:
        return service.query(request)
    except AnalyticsServiceError as exc:
        logger.warning("Analytics query rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
