"""Analytics application service (Phase 5)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.engines.analytics import AnalyticsEngine, AnalyticsEngineError
from app.schemas.analytics import AnalyticsQueryRequest, AnalyticsQueryResponse
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

logger = get_logger(__name__)


class AnalyticsServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AnalyticsService:
    """Load datasets and execute deterministic analytics queries."""

    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        engine: AnalyticsEngine | None = None,
    ) -> None:
        self.dataset_service = dataset_service or get_dataset_service()
        self.engine = engine or AnalyticsEngine()

    def query(self, request: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
        try:
            frame, meta = self.dataset_service.load_dataframe(request.dataset_id)
        except DatasetServiceError as exc:
            raise AnalyticsServiceError(exc.message, status_code=exc.status_code) from exc

        try:
            payload = self.engine.execute(frame, request)
        except AnalyticsEngineError as exc:
            raise AnalyticsServiceError(exc.message, status_code=exc.status_code) from exc

        logger.info(
            "Analytics query dataset_id=%s type=%s results=%s",
            meta.dataset_id,
            meta.dataset_type,
            payload["result_count"],
        )
        return AnalyticsQueryResponse(
            dataset_id=meta.dataset_id,
            row_count_before=payload["row_count_before"],
            row_count_after_filter=payload["row_count_after_filter"],
            applied=payload["applied"],
            kpis=payload["kpis"],
            results=payload["results"],
            result_count=payload["result_count"],
        )


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()
