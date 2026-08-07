"""Schemas for intent detection and query routing (Phase 4)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "analytics",
    "visualization",
    "ml",
    "rag",
    "insight",
    "profile",
    "unknown",
]

TargetEngine = Literal[
    "analytics",
    "visualization",
    "ml",
    "rag",
    "insight",
    "profiling",
    "none",
]


class IntentDetectRequest(BaseModel):
    """User query submitted for intent classification."""

    query: str = Field(..., min_length=1, max_length=2000)
    dataset_id: str | None = Field(
        default=None,
        description="Optional dataset context for LLM routing.",
    )
    session_id: str | None = Field(
        default=None,
        description="Chat session id for in-memory LangGraph conversation continuity.",
        max_length=128,
    )


class EnginePass(BaseModel):
    """Deterministic handoff plan for the selected engine."""

    accepted: bool = True
    execute_now: bool = False
    next_action: str


class RoutingInfo(BaseModel):
    """Where the query should be sent next."""

    engine: TargetEngine
    status: Literal["ready", "planned"] = "planned"
    phase: str | None = None
    message: str
    engine_pass: EnginePass | None = None


class OrchestrationInfo(BaseModel):
    """LangGraph execution metadata."""

    graph: str = "intent_router"
    provider: str
    nodes_executed: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class IntentDetectResponse(BaseModel):
    """Result of LLM/LangGraph intent detection."""

    query: str
    intent: IntentName
    target_engine: TargetEngine
    confidence: float = Field(ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)
    rationale: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = None
    session_id: str | None = None
    reply: str | None = Field(
        default=None,
        description="Short assistant reply for unknown/none intents.",
    )
    memory_applied: bool = False
    routing: RoutingInfo
    orchestration: OrchestrationInfo


class IntentCatalogItem(BaseModel):
    """Describes one supported intent for clients."""

    intent: IntentName
    target_engine: TargetEngine
    description: str
    example_queries: list[str] = Field(default_factory=list)


class IntentCatalogResponse(BaseModel):
    """List of supported intents."""

    count: int
    intents: list[IntentCatalogItem]
