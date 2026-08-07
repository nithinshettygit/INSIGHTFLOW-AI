"""Reusable business services."""

from __future__ import annotations

from typing import Any

__all__ = [
    "DatasetService",
    "get_dataset_service",
    "ProfilingService",
    "get_profiling_service",
    "IntentService",
    "get_intent_service",
]


def __getattr__(name: str) -> Any:
    # Lazy exports avoid circular imports (intent graph ↔ dataset service).
    if name in {"DatasetService", "get_dataset_service"}:
        from app.services.dataset_service import DatasetService, get_dataset_service

        values = {
            "DatasetService": DatasetService,
            "get_dataset_service": get_dataset_service,
        }
        return values[name]
    if name in {"ProfilingService", "get_profiling_service"}:
        from app.services.profiling_service import (
            ProfilingService,
            get_profiling_service,
        )

        values = {
            "ProfilingService": ProfilingService,
            "get_profiling_service": get_profiling_service,
        }
        return values[name]
    if name in {"IntentService", "get_intent_service"}:
        from app.services.intent_service import IntentService, get_intent_service

        values = {
            "IntentService": IntentService,
            "get_intent_service": get_intent_service,
        }
        return values[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
