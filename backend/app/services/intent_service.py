"""Intent detection application service (LangGraph + Groq + session memory)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.intent import IntentDetector, RuleBasedIntentDetector
from app.engines.intent.graph import build_intent_graph
from app.engines.intent.llm_based import LLMIntentDetector
from app.engines.intent.rules import INTENT_CATALOG
from app.schemas.intent import (
    EnginePass,
    IntentCatalogItem,
    IntentCatalogResponse,
    IntentDetectRequest,
    IntentDetectResponse,
    OrchestrationInfo,
    RoutingInfo,
)
from app.services.dataset_service import DatasetService, get_dataset_service

logger = get_logger(__name__)


class IntentServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def build_intent_detector(settings: Settings | None = None) -> IntentDetector:
    """Create the configured intent detector."""
    settings = settings or get_settings()
    provider = settings.intent_provider.strip().lower()
    if provider in {"llm", "groq", "langgraph"}:
        return LLMIntentDetector(settings=settings)
    return RuleBasedIntentDetector()


class IntentService:
    """Run the LangGraph intent router and return API-facing results."""

    def __init__(
        self,
        detector: IntentDetector | None = None,
        dataset_service: DatasetService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.dataset_service = dataset_service or get_dataset_service()
        self.detector = detector or build_intent_detector(self.settings)
        self.graph = build_intent_graph(self.detector, self.dataset_service)

    def detect(self, request: IntentDetectRequest) -> IntentDetectResponse:
        query = request.query.strip()
        if not query:
            raise IntentServiceError("Query must not be empty")

        session_id = (request.session_id or "").strip() or None
        thread_id = session_id or "anonymous"

        result = self.graph.invoke(
            {
                "query": query,
                "dataset_id": request.dataset_id,
                "session_id": session_id,
                "nodes_executed": [],
            },
            config={"configurable": {"thread_id": thread_id}},
        )

        if result.get("error"):
            message = str(result["error"])
            status = 404 if "not found" in message.lower() else 400
            raise IntentServiceError(message, status_code=status)

        routing_raw = result.get("routing") or {}
        engine_pass_raw = routing_raw.get("engine_pass") or {}
        routing = RoutingInfo(
            engine=routing_raw.get("engine", "none"),
            status=routing_raw.get("status", "planned"),
            phase=routing_raw.get("phase"),
            message=routing_raw.get("message", "No routing information"),
            engine_pass=EnginePass(**engine_pass_raw) if engine_pass_raw else None,
        )

        orchestration = OrchestrationInfo(
            graph="intent_router",
            provider=str(result.get("provider") or "unknown"),
            nodes_executed=list(result.get("nodes_executed") or []),
            context={
                **dict(result.get("context") or {}),
                "memory": dict(result.get("memory") or {}),
                "memory_applied": bool(result.get("memory_applied")),
            },
        )

        logger.info(
            "Intent service complete provider=%s intent=%s engine=%s session=%s memory=%s",
            orchestration.provider,
            result.get("intent"),
            routing.engine,
            session_id,
            result.get("memory_applied"),
        )

        return IntentDetectResponse(
            query=query,
            intent=result.get("intent", "unknown"),
            target_engine=result.get("target_engine", "none"),
            confidence=float(result.get("confidence") or 0.0),
            matched_keywords=list(result.get("matched_keywords") or []),
            rationale=result.get("rationale"),
            entities=dict(result.get("entities") or {}),
            dataset_id=request.dataset_id,
            session_id=session_id,
            reply=result.get("reply"),
            memory_applied=bool(result.get("memory_applied")),
            routing=routing,
            orchestration=orchestration,
        )

    def catalog(self) -> IntentCatalogResponse:
        items = [IntentCatalogItem(**item) for item in INTENT_CATALOG]
        return IntentCatalogResponse(count=len(items), intents=items)


def get_intent_service() -> IntentService:
    return IntentService()
