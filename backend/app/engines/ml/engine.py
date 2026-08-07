"""ML Engine — forecast, segmentation, anomaly detection (Phase 9)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.ml.anomaly import run_anomaly
from app.engines.ml.forecast import run_forecast
from app.engines.ml.helpers import MlEngineError, build_column_lookup
from app.engines.ml.segmentation import run_segmentation
from app.schemas.ml import MlRunRequest, MlTask
from app.utils.files import ensure_directory

logger = get_logger(__name__)

_TASK_PATTERNS: list[tuple[MlTask, tuple[str, ...]]] = [
    (
        "segmentation",
        (
            "segment",
            "segmentation",
            "cluster",
            "clustering",
            "customer group",
            "customer groups",
        ),
    ),
    (
        "anomaly",
        ("anomal", "outlier", "outliers", "unusual", "fraud"),
    ),
    (
        "forecast",
        (
            "forecast",
            "predict",
            "prediction",
            "next month",
            "next week",
            "future",
            "time series",
            "projection",
        ),
    ),
]


class MlEngine:
    """Classical ML tasks over tabular datasets (sklearn)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def execute(self, frame: pd.DataFrame, request: MlRunRequest) -> dict[str, Any]:
        if frame.empty and frame.shape[1] == 0:
            raise MlEngineError("Dataset has no columns")

        task = request.task or infer_ml_task(request.query)
        lookup = build_column_lookup(frame)
        horizon = request.horizon or self.settings.ml_default_horizon
        n_clusters = request.n_clusters or self.settings.ml_default_clusters
        contamination = (
            request.contamination
            if request.contamination is not None
            else self.settings.ml_anomaly_contamination
        )
        random_state = self.settings.ml_random_state

        if task == "forecast":
            payload = run_forecast(
                frame,
                lookup,
                target=request.target,
                time_column=request.time_column,
                horizon=horizon,
                limit=request.limit,
                random_state=random_state,
            )
        elif task == "segmentation":
            payload = run_segmentation(
                frame,
                lookup,
                features=request.features,
                n_clusters=n_clusters,
                limit=request.limit,
                random_state=random_state,
            )
        elif task == "anomaly":
            payload = run_anomaly(
                frame,
                lookup,
                features=request.features,
                target=request.target,
                contamination=contamination,
                limit=request.limit,
                random_state=random_state,
            )
        else:
            raise MlEngineError(f"Unsupported ML task '{task}'")

        artifact_path = self._persist_summary(request.dataset_id, payload)
        payload["applied"] = {
            **payload.get("applied", {}),
            "artifact_path": str(artifact_path) if artifact_path else None,
        }
        logger.info(
            "ML task complete dataset_id=%s task=%s model=%s",
            request.dataset_id,
            payload["task"],
            payload["model"],
        )
        return payload

    def _persist_summary(self, dataset_id: str, payload: dict[str, Any]) -> Path | None:
        try:
            root = ensure_directory(self.settings.model_path / dataset_id)
            path = root / f"{payload['task']}_last.json"
            summary = {
                "dataset_id": dataset_id,
                "task": payload["task"],
                "model": payload["model"],
                "summary": payload.get("summary", {}),
                "applied": {
                    k: v
                    for k, v in (payload.get("applied") or {}).items()
                    if k != "artifact_path"
                },
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            return path
        except Exception as exc:  # pragma: no cover - non-critical
            logger.warning("Could not persist ML summary: %s", exc)
            return None


def infer_ml_task(query: str | None) -> MlTask:
    text = (query or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "forecast"
    for task, keywords in _TASK_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return task
    return "forecast"
