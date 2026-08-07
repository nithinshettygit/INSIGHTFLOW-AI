"""Visualization application service (Phase 6)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.engines.visualization import VisualizationEngine, VisualizationEngineError
from app.schemas.visualization import VisualizationRequest, VisualizationResponse
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

logger = get_logger(__name__)


class VisualizationServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class VisualizationService:
    """Load datasets and build Plotly chart payloads."""

    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        engine: VisualizationEngine | None = None,
    ) -> None:
        self.dataset_service = dataset_service or get_dataset_service()
        self.engine = engine or VisualizationEngine()

    def create_chart(self, request: VisualizationRequest) -> VisualizationResponse:
        try:
            frame, meta = self.dataset_service.load_dataframe(request.dataset_id)
        except DatasetServiceError as exc:
            raise VisualizationServiceError(
                exc.message,
                status_code=exc.status_code,
            ) from exc

        try:
            payload = self.engine.execute(frame, request)
        except VisualizationEngineError as exc:
            raise VisualizationServiceError(
                exc.message,
                status_code=exc.status_code,
            ) from exc

        logger.info(
            "Visualization created dataset_id=%s chart_type=%s",
            meta.dataset_id,
            request.chart_type,
        )
        return VisualizationResponse(
            dataset_id=meta.dataset_id,
            chart_type=request.chart_type,
            title=payload["title"],
            applied=payload["applied"],
            data_preview=payload["data_preview"],
            plotly_figure=payload["plotly_figure"],
        )


def get_visualization_service() -> VisualizationService:
    return VisualizationService()
