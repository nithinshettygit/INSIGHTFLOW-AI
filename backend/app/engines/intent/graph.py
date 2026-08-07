"""Simple LangGraph intent orchestration: context → classify → ground → route."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.core.logging import get_logger
from app.engines.intent.base import IntentDetector
from app.engines.intent.entity_grounding import build_schema_columns, ground_entities
from app.engines.intent.rules import ENGINE_ROUTING
from app.services.dataset_service import DatasetService, DatasetServiceError

logger = get_logger(__name__)


class IntentGraphState(TypedDict, total=False):
    query: str
    dataset_id: str | None
    context: dict[str, Any]
    intent: str
    target_engine: str
    confidence: float
    matched_keywords: list[str]
    rationale: str | None
    provider: str
    entities: dict[str, Any]
    routing: dict[str, Any]
    nodes_executed: list[str]
    error: str | None


def build_intent_graph(
    detector: IntentDetector,
    dataset_service: DatasetService,
):
    """Compile a 4-node LangGraph for intent routing with entity grounding."""

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

        logger.debug(
            "Intent schema loaded dataset_id=%s columns=%s",
            dataset_id,
            len(context.get("column_names") or []),
        )
        return {
            **state,
            "context": context,
            "nodes_executed": nodes,
            "error": None,
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
            next_action = "Queued for future engine implementation"

        routing = {
            "engine": engine,
            "status": status,
            "phase": route_meta.get("phase"),
            "message": route_meta["message"],
            "engine_pass": {
                "accepted": True,
                "execute_now": status == "ready",
                "next_action": next_action,
            },
        }
        logger.info(
            "Intent routed intent=%s engine=%s status=%s provider=%s",
            state.get("intent"),
            engine,
            status,
            state.get("provider"),
        )
        return {**state, "routing": routing, "nodes_executed": nodes}

    graph = StateGraph(IntentGraphState)
    graph.add_node("load_context", load_context)
    graph.add_node("classify", classify)
    graph.add_node("ground_entities", ground)
    graph.add_node("route", route)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify")
    graph.add_edge("classify", "ground_entities")
    graph.add_edge("ground_entities", "route")
    graph.add_edge("route", END)
    return graph.compile()
