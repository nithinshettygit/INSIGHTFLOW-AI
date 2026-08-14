"""Simple LangGraph intent orchestration with session memory.

Flow: load_context → load_memory → classify → apply_memory → ground → route → save_memory
Checkpointed with LangGraph MemorySaver (thread_id = session_id).
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.core.logging import get_logger
from app.engines.intent.base import IntentDetector
from app.engines.intent.entity_grounding import build_schema_columns, ground_entities
from app.engines.intent.memory import (
    apply_conversation_memory,
    get_session_memory_store,
)
from app.services.dataset_service import DatasetService, DatasetServiceError

logger = get_logger(__name__)

# Process-wide checkpointer so session threads survive across requests.
_CHECKPOINTER = MemorySaver()

ENGINE_ROUTING = {
    "analytics": {"status": "ready", "phase": "Phase 5", "message": "Routed to Analytics Engine."},
    "visualization": {"status": "ready", "phase": "Phase 6", "message": "Routed to Visualization Engine."},
    "ml": {"status": "ready", "phase": "Phase 9", "message": "Routed to ML Engine."},
    "rag": {"status": "ready", "phase": "Phase 8", "message": "Routed to RAG Engine."},
    "insight": {"status": "ready", "phase": "Phase 10", "message": "Routed to Insight Engine."},
    "profiling": {"status": "ready", "phase": "Phase 3", "message": "Routed to profiling service."},
    "none": {"status": "planned", "phase": None, "message": "No engine matched."},
}


class IntentGraphState(TypedDict, total=False):
    query: str
    dataset_id: str | None
    session_id: str | None
    context: dict[str, Any]
    memory: dict[str, Any]
    intent: str
    target_engine: str
    confidence: float
    matched_keywords: list[str]
    rationale: str | None
    provider: str
    entities: dict[str, Any]
    routing: dict[str, Any]
    reply: str | None
    memory_applied: bool
    end_conversation: bool
    nodes_executed: list[str]
    error: str | None


def build_intent_graph(
    detector: IntentDetector,
    dataset_service: DatasetService,
    *,
    checkpointer: MemorySaver | None = None,
):
    """Compile intent router with optional LangGraph MemorySaver."""

    store = get_session_memory_store()

    def load_context(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("load_context")
        dataset_id = state.get("dataset_id")
        context: dict[str, Any] = {
            "dataset_id": dataset_id,
            "dataset_type": None,
            "row_count": None,
            "column_count": None,
            "page_count": None,
            "columns": [],
            "column_names": [],
        }

        if dataset_id:
            try:
                meta = dataset_service.get_dataset(dataset_id)
            except DatasetServiceError as exc:
                return {
                    **state,
                    "nodes_executed": nodes,
                    "error": exc.message,
                }

            extra = meta.extra or {}
            columns: list[dict[str, str]] = []
            column_names: list[str] = []
            page_count = extra.get("page_count")
            row_count = extra.get("row_count")
            column_count = extra.get("column_count")

            try:
                profile = dataset_service.get_profile(dataset_id)
                columns = build_schema_columns(profile.columns)
                column_names = [c["name"] for c in columns]
                if not column_names:
                    column_names = list((profile.metadata or {}).get("column_names") or [])
                    columns = [
                        {
                            "name": name,
                            "dtype": "unknown",
                            "role_hint": "categorical",
                        }
                        for name in column_names
                    ]
                page_count = (profile.metadata or {}).get("page_count", page_count)
                row_count = profile.row_count if profile.row_count is not None else row_count
                column_count = (
                    profile.column_count
                    if profile.column_count is not None
                    else column_count
                )
            except DatasetServiceError:
                preview = extra.get("preview_columns") or []
                column_names = [str(c) for c in preview]
                columns = [
                    {
                        "name": name,
                        "dtype": "unknown",
                        "role_hint": "categorical",
                    }
                    for name in column_names
                ]

            context.update(
                {
                    "dataset_type": meta.dataset_type,
                    "row_count": row_count,
                    "column_count": column_count or len(column_names) or None,
                    "page_count": page_count,
                    "columns": columns,
                    "column_names": column_names,
                }
            )

        return {
            **state,
            "context": context,
            "nodes_executed": nodes,
            "error": None,
        }

    def load_memory(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("load_memory")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        session_id = state.get("session_id")
        memory = store.get(session_id) if session_id else None
        snapshot = memory.snapshot() if memory else {}
        context = dict(state.get("context") or {})
        if snapshot:
            context["conversation_memory"] = snapshot
        return {
            **state,
            "context": context,
            "memory": snapshot,
            "nodes_executed": nodes,
        }

    def classify(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("classify")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        match = detector.detect(state["query"], context=state.get("context"))
        return {
            **state,
            "intent": match.intent,
            "target_engine": match.target_engine,
            "confidence": match.confidence,
            "matched_keywords": match.matched_keywords,
            "rationale": match.rationale,
            "provider": match.provider,
            "entities": match.entities,
            "nodes_executed": nodes,
        }

    def apply_memory(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("apply_memory")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        session_id = state.get("session_id")
        memory = store.get(session_id) if session_id else None
        context = state.get("context") or {}
        columns = list(context.get("columns") or [])
        updated = apply_conversation_memory(
            query=state.get("query") or "",
            intent=state.get("intent") or "unknown",
            target_engine=state.get("target_engine") or "none",
            confidence=float(state.get("confidence") or 0.0),
            entities=dict(state.get("entities") or {}),
            rationale=state.get("rationale"),
            provider=str(state.get("provider") or "unknown"),
            memory=memory,
            columns=columns,
        )
        return {
            **state,
            "intent": updated["intent"],
            "target_engine": updated["target_engine"],
            "confidence": updated["confidence"],
            "entities": updated["entities"],
            "rationale": updated["rationale"],
            "provider": updated["provider"],
            "memory_applied": bool(updated["memory_applied"]),
            "reply": updated.get("reply"),
            "end_conversation": bool(updated.get("end_conversation")),
            "nodes_executed": nodes,
        }

    def ground(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("ground_entities")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        context = state.get("context") or {}
        column_names = list(context.get("column_names") or [])
        entities = ground_entities(state.get("entities"), column_names)
        return {
            **state,
            "entities": entities,
            "nodes_executed": nodes,
        }

    def route(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("route")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        engine = state.get("target_engine") or "none"
        intent = state.get("intent") or "unknown"
        if intent == "unknown":
            engine = "none"

        route_meta = ENGINE_ROUTING.get(engine, ENGINE_ROUTING["none"])
        status = route_meta["status"]
        if engine in {
            "profiling",
            "analytics",
            "visualization",
            "rag",
            "ml",
            "insight",
        }:
            status = "ready"

        if engine == "profiling":
            next_action = "Call GET /api/v1/datasets/{dataset_id}/profile"
        elif engine == "analytics":
            next_action = (
                "Call POST /api/v1/analytics/query with grounded metrics/dimensions/filters"
            )
        elif engine == "visualization":
            next_action = (
                "Call POST /api/v1/visualization/chart with chart_type/metrics/dimensions"
            )
        elif engine == "rag":
            next_action = "Call POST /api/v1/rag/query with dataset_id and question"
        elif engine == "ml":
            next_action = (
                "Call POST /api/v1/ml/run with task=forecast|segmentation|anomaly"
            )
        elif engine == "insight":
            next_action = (
                "Call POST /api/v1/insight/analyze with question and optional mode"
            )
        else:
            next_action = "Reply briefly; no engine execution"

        reply = state.get("reply")
        if engine == "none" or intent == "unknown":
            reply = reply or route_meta.get(
                "reply",
                "I can help with KPIs, charts, forecasts, document QA, or insights. "
                "Try asking about sales by region or a bar chart.",
            )
            status = "planned"

        routing = {
            "engine": engine,
            "status": status,
            "phase": route_meta.get("phase"),
            "message": reply or route_meta["message"],
            "engine_pass": {
                "accepted": engine != "none",
                "execute_now": status == "ready",
                "next_action": next_action,
            },
        }
        logger.info(
            "Intent routed intent=%s engine=%s status=%s provider=%s memory=%s",
            intent,
            engine,
            status,
            state.get("provider"),
            state.get("memory_applied"),
        )
        return {
            **state,
            "target_engine": engine,
            "routing": routing,
            "reply": reply,
            "nodes_executed": nodes,
        }

    def save_memory(state: IntentGraphState) -> IntentGraphState:
        nodes = list(state.get("nodes_executed") or [])
        nodes.append("save_memory")
        if state.get("error"):
            return {**state, "nodes_executed": nodes}

        session_id = state.get("session_id")
        if not session_id:
            return {**state, "nodes_executed": nodes}

        memory = store.remember_turn(
            session_id,
            query=state.get("query") or "",
            intent=state.get("intent") or "unknown",
            engine=state.get("target_engine") or "none",
            entities=dict(state.get("entities") or {}),
            dataset_id=state.get("dataset_id"),
        )
        if state.get("end_conversation"):
            memory = store.reset_topic(session_id) or memory
            logger.info("Conversation closed; cleared active topic session=%s", session_id)
        return {
            **state,
            "memory": memory.snapshot(),
            "nodes_executed": nodes,
        }

    graph = StateGraph(IntentGraphState)
    graph.add_node("load_context", load_context)
    graph.add_node("load_memory", load_memory)
    graph.add_node("classify", classify)
    graph.add_node("apply_memory", apply_memory)
    graph.add_node("ground_entities", ground)
    graph.add_node("route", route)
    graph.add_node("save_memory", save_memory)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "load_memory")
    graph.add_edge("load_memory", "classify")
    graph.add_edge("classify", "apply_memory")
    graph.add_edge("apply_memory", "ground_entities")
    graph.add_edge("ground_entities", "route")
    graph.add_edge("route", "save_memory")
    graph.add_edge("save_memory", END)
    return graph.compile(checkpointer=checkpointer or _CHECKPOINTER)
