"""ML Engine API endpoints (Phase 9)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.ml import MlRunRequest, MlRunResponse
from app.services.ml_service import MlService, MlServiceError, get_ml_service

router = APIRouter(prefix="/ml", tags=["ml"])
logger = get_logger(__name__)


@router.post("/run", response_model=MlRunResponse)
def run_ml(
    request: MlRunRequest,
    service: MlService = Depends(get_ml_service),
) -> MlRunResponse:
    """Run forecast, segmentation, or anomaly detection on a tabular dataset."""
    try:
        return service.run(request)
    except MlServiceError as exc:
        logger.warning("ML run rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
