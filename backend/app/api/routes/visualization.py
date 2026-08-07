"""Visualization Engine API endpoints (Phase 6)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.visualization import VisualizationRequest, VisualizationResponse
from app.services.visualization_service import (
    VisualizationService,
    VisualizationServiceError,
    get_visualization_service,
)

router = APIRouter(prefix="/visualization", tags=["visualization"])
logger = get_logger(__name__)


@router.post("/chart", response_model=VisualizationResponse)
def create_chart(
    request: VisualizationRequest,
    service: VisualizationService = Depends(get_visualization_service),
) -> VisualizationResponse:
    """Build a Plotly bar/line/pie/scatter chart from a tabular dataset."""
    try:
        return service.create_chart(request)
    except VisualizationServiceError as exc:
        logger.warning("Visualization rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
