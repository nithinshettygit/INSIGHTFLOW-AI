"""Insight application service (Phase 10)."""

from __future__ import annotations

import pandas as pd

from app.core.logging import get_logger
from app.engines.insight import InsightEngine, InsightEngineError
from app.schemas.insight import (
    InsightAnalyzeRequest,
    InsightAnalyzeResponse,
    InsightFinding,
    InsightRecommendation,
    InsightRootCause,
)
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

logger = get_logger(__name__)


class InsightServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InsightService:
    """Assemble evidence from dataset artifacts and run the Insight Engine."""

    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        engine: InsightEngine | None = None,
    ) -> None:
        self.dataset_service = dataset_service or get_dataset_service()
        self.engine = engine or InsightEngine()

    def analyze(self, request: InsightAnalyzeRequest) -> InsightAnalyzeResponse:
        try:
            meta = self.dataset_service.get_dataset(request.dataset_id)
        except DatasetServiceError as exc:
            raise InsightServiceError(exc.message, status_code=exc.status_code) from exc

        profile = None
        try:
            profile = self.dataset_service.get_profile(request.dataset_id)
        except DatasetServiceError as exc:
            logger.warning("Insight profile unavailable: %s", exc.message)

        frame: pd.DataFrame | None = None
        if meta.dataset_type != "pdf":
            try:
                frame, meta = self.dataset_service.load_dataframe(request.dataset_id)
            except DatasetServiceError as exc:
                raise InsightServiceError(
                    exc.message,
                    status_code=exc.status_code,
                ) from exc

        try:
            payload = self.engine.analyze(
                meta=meta,
                question=request.question,
                mode=request.mode,
                profile=profile,
                frame=frame,
                focus_metrics=request.focus_metrics,
                focus_dimensions=request.focus_dimensions,
                include_ml_context=request.include_ml_context,
            )
        except InsightEngineError as exc:
            raise InsightServiceError(exc.message, status_code=exc.status_code) from exc

        logger.info(
            "Insight service dataset_id=%s mode=%s provider=%s",
            meta.dataset_id,
            payload["mode"],
            payload["provider"],
        )
        return InsightAnalyzeResponse(
            dataset_id=meta.dataset_id,
            mode=payload["mode"],
            question=payload["question"],
            headline=payload["headline"],
            explanation=payload["explanation"],
            findings=[InsightFinding(**item) for item in payload["findings"]],
            recommendations=[
                InsightRecommendation(**item) for item in payload["recommendations"]
            ],
            root_causes=[InsightRootCause(**item) for item in payload["root_causes"]],
            evidence=payload["evidence"],
            provider=payload["provider"],
            applied=payload["applied"],
        )


def get_insight_service() -> InsightService:
    return InsightService()
