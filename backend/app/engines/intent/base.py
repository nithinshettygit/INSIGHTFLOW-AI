"""Extensible intent detector contract.

Phase 4 supports rule-based and Groq LLM detectors behind one interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.intent import IntentName, TargetEngine

INTENT_TO_ENGINE: dict[IntentName, TargetEngine] = {
    "analytics": "analytics",
    "visualization": "visualization",
    "ml": "ml",
    "rag": "rag",
    "insight": "insight",
    "profile": "profiling",
    "unknown": "none",
}


@dataclass(frozen=True)
class IntentMatch:
    """Normalized detection result produced by any IntentDetector."""

    intent: IntentName
    target_engine: TargetEngine
    confidence: float
    matched_keywords: list[str] = field(default_factory=list)
    rationale: str | None = None
    provider: str = "rules"
    entities: dict[str, Any] = field(default_factory=dict)


class IntentDetector(ABC):
    """Strategy interface for intent classification."""

    @abstractmethod
    def detect(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> IntentMatch:
        """Classify a natural-language business query."""
