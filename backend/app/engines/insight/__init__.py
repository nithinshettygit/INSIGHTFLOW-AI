"""Business insight engine — explanation and recommendations (Phase 10)."""

from app.engines.insight.engine import InsightEngine, InsightEngineError
from app.engines.insight.evidence import infer_insight_mode

__all__ = ["InsightEngine", "InsightEngineError", "infer_insight_mode"]
