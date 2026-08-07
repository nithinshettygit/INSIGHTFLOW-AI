"""ML application service (Phase 9)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.engines.ml import MlEngine, MlEngineError
from app.schemas.ml import MlRunRequest, MlRunResponse
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

logger = get_logger(__name__)


class MlServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class MlService:
    """Load tabular datasets and run classical ML tasks."""

    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        engine: MlEngine | None = None,
    ) -> None:
        self.dataset_service = dataset_service or get_dataset_service()
        self.engine = engine or MlEngine()

    def run(self, request: MlRunRequest) -> MlRunResponse:
        try:
            frame, meta = self.dataset_service.load_dataframe(request.dataset_id)
        except DatasetServiceError as exc:
            raise MlServiceError(exc.message, status_code=exc.status_code) from exc

        try:
            payload = self.engine.execute(frame, request)
        except MlEngineError as exc:
            raise MlServiceError(exc.message, status_code=exc.status_code) from exc

        logger.info(
            "ML run dataset_id=%s task=%s model=%s",
            meta.dataset_id,
            payload["task"],
            payload["model"],
        )
        return MlRunResponse(
            dataset_id=meta.dataset_id,
            task=payload["task"],
            model=payload["model"],
            summary=payload.get("summary") or {},
            results=payload.get("results") or [],
            result_count=int(payload.get("result_count") or 0),
            applied=payload.get("applied") or {},
            plotly_figure=payload.get("plotly_figure"),
        )


def get_ml_service() -> MlService:
    return MlService()
