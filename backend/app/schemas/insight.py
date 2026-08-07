"""Schemas for the Business Insight Engine (Phase 10)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

InsightMode = Literal["explanation", "recommendation", "root_cause"]


class InsightAnalyzeRequest(BaseModel):
    """Ask for business explanation / recommendations / root-cause analysis.

    The engine builds a compact evidence pack from profile + analytics (+ ML)
    and only then optionally calls an LLM — never the raw dataset.
    """

    dataset_id: str
    question: str = Field(min_length=1, max_length=4000)
    mode: InsightMode | None = Field(
        default=None,
        description="If omitted, inferred from the question.",
    )
    focus_metrics: list[str] = Field(default_factory=list)
    focus_dimensions: list[str] = Field(default_factory=list)
    include_ml_context: bool = True
    synthesize: bool | None = Field(
        default=None,
        description="If true, use Groq for reasoning. Defaults to INSIGHT_USE_LLM.",
    )


class InsightFinding(BaseModel):
    title: str
    detail: str
    severity: Literal["low", "medium", "high"] = "medium"


class InsightRecommendation(BaseModel):
    action: str
    rationale: str
    priority: int = Field(default=2, ge=1, le=5)


class InsightRootCause(BaseModel):
    cause: str
    evidence: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class InsightAnalyzeResponse(BaseModel):
    dataset_id: str
    mode: InsightMode
    question: str
    headline: str
    explanation: str
    findings: list[InsightFinding] = Field(default_factory=list)
    recommendations: list[InsightRecommendation] = Field(default_factory=list)
    root_causes: list[InsightRootCause] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    provider: str
    applied: dict[str, Any] = Field(default_factory=dict)
