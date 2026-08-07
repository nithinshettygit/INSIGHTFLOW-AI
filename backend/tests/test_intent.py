"""Tests for Phase 4 LangGraph intent detection."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.intent import RuleBasedIntentDetector
from app.engines.intent.base import IntentMatch
from app.engines.intent.entity_grounding import ground_entities
from app.engines.intent.graph import build_intent_graph
from app.engines.intent.llm_based import LLMIntentDetector, _parse_json_content
from app.main import create_app
from app.schemas.intent import IntentDetectRequest
from app.services.dataset_service import DatasetService
from app.services.intent_service import IntentService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Keep API tests offline/deterministic.
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("query", "intent", "engine"),
    [
        ("What is the total sales by region?", "analytics", "analytics"),
        ("Show a bar chart of revenue by category", "visualization", "visualization"),
        ("Forecast next month sales", "ml", "ml"),
        ("What does the PDF say about refunds?", "rag", "rag"),
        ("Why did profit drop last quarter?", "insight", "insight"),
        ("How many missing values are in the dataset?", "profile", "profiling"),
    ],
)
def test_detect_common_intents(
    client: TestClient,
    query: str,
    intent: str,
    engine: str,
) -> None:
    response = client.post("/api/v1/intent/detect", json={"query": query})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["intent"] == intent
    assert payload["target_engine"] == engine
    assert payload["confidence"] > 0
    assert payload["routing"]["engine"] == engine
    assert payload["orchestration"]["nodes_executed"] == [
        "load_context",
        "load_memory",
        "classify",
        "apply_memory",
        "ground_entities",
        "route",
        "save_memory",
    ]


def test_unknown_intent(client: TestClient) -> None:
    response = client.post("/api/v1/intent/detect", json={"query": "hello there"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "unknown"
    assert payload["target_engine"] == "none"
    assert payload["reply"]
    assert payload["routing"]["engine_pass"]["execute_now"] is False


def test_session_memory_followup_inherits_topic(client: TestClient) -> None:
    session_id = "test-session-memory-1"
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "What is the total sales by region?",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["intent"] == "analytics"

    follow = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "what about profit?",
            "session_id": session_id,
        },
    )
    assert follow.status_code == 200, follow.text
    body = follow.json()
    # Follow-up should stay on analytics topic via memory (or classify analytics).
    assert body["target_engine"] == "analytics"
    assert body["intent"] == "analytics"


def test_fresh_analytics_after_viz_does_not_invent_filters() -> None:
    from app.engines.intent.memory import (
        SessionMemory,
        apply_conversation_memory,
    )

    memory = SessionMemory(session_id="unit-fresh")
    memory.last_intent = "visualization"
    memory.last_engine = "visualization"
    memory.last_entities = {
        "metrics": ["Sales"],
        "dimensions": ["Region"],
        "chart_type": "bar",
        "filters": [],
    }
    memory.last_query = "Bar chart of sales by region"

    columns = [
        {"name": "Sales", "dtype": "float", "role_hint": "numeric"},
        {"name": "Country", "dtype": "object", "role_hint": "categorical"},
        {"name": "Region", "dtype": "object", "role_hint": "categorical"},
    ]
    updated = apply_conversation_memory(
        query="which country has lowest sales",
        intent="analytics",
        target_engine="analytics",
        confidence=0.95,
        entities={
            "metrics": ["Sales"],
            "dimensions": ["Country"],
            "filters": [],
        },
        rationale="lowest country",
        provider="groq",
        memory=memory,
        columns=columns,
    )
    filters = updated["entities"].get("filters") or []
    assert filters == []
    assert updated["entities"].get("dimensions") == ["Country"]
    assert updated["entities"].get("metrics") == ["Sales"]
    assert updated["intent"] == "analytics"


def test_enrich_does_not_use_sales_as_dimension() -> None:
    from app.engines.intent.memory import (
        SessionMemory,
        apply_conversation_memory,
    )

    memory = SessionMemory(session_id="unit-sales-dim")
    memory.last_intent = "visualization"
    memory.last_engine = "visualization"
    memory.last_entities = {
        "metrics": ["sales"],
        "dimensions": ["region"],
        "chart_type": "bar",
        "filters": [],
    }
    columns = [
        {"name": "sales", "dtype": "object", "role_hint": "categorical"},
        {"name": "region", "dtype": "object", "role_hint": "categorical"},
        {"name": "country", "dtype": "object", "role_hint": "categorical"},
    ]
    updated = apply_conversation_memory(
        query="which region has lowest sales",
        intent="analytics",
        target_engine="analytics",
        confidence=1.0,
        entities={"metrics": ["sales"], "dimensions": ["region"], "filters": []},
        rationale="lowest region",
        provider="groq",
        memory=memory,
        columns=columns,
    )
    assert updated["entities"]["metrics"] == ["sales"]
    assert updated["entities"]["dimensions"] == ["region"]
    assert "sales" not in (updated["entities"].get("dimensions") or [])


def test_gibberish_does_not_resume_memory(client: TestClient) -> None:
    session_id = "test-session-memory-gibberish"
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "What is the total sales by region?",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200
    assert first.json()["intent"] == "analytics"

    junk = client.post(
        "/api/v1/intent/detect",
        json={"query": "dsd", "session_id": session_id},
    )
    assert junk.status_code == 200, junk.text
    body = junk.json()
    assert body["intent"] == "unknown"
    assert body["target_engine"] == "none"
    assert body["memory_applied"] is False


def test_history_question_uses_memory_reply(client: TestClient) -> None:
    session_id = "test-session-memory-history"
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "What is the total sales by region?",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200

    history = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "what did i asked previously",
            "session_id": session_id,
        },
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["intent"] == "unknown"
    assert body["target_engine"] == "none"
    assert body["memory_applied"] is True
    assert "total sales by region" in (body["reply"] or "").lower()


def test_conversation_closing_clears_topic(client: TestClient) -> None:
    session_id = "test-session-memory-close"
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "What is the total sales by region?",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200
    assert first.json()["intent"] == "analytics"

    for closer in ("bai", "fine", "thanks", "ok"):
        closing = client.post(
            "/api/v1/intent/detect",
            json={"query": closer, "session_id": session_id},
        )
        assert closing.status_code == 200, closing.text
        body = closing.json()
        assert body["intent"] == "unknown"
        assert body["target_engine"] == "none"
        assert body["reply"]
        assert body["routing"]["engine_pass"]["execute_now"] is False

    # After closing, gibberish must not resume analytics.
    junk = client.post(
        "/api/v1/intent/detect",
        json={"query": "dsd", "session_id": session_id},
    )
    assert junk.status_code == 200
    assert junk.json()["intent"] == "unknown"
    assert junk.json()["target_engine"] == "none"


def test_viz_followup_adds_category_filter(client: TestClient, tmp_path: Path) -> None:
    upload = client.post(
        "/api/v1/datasets/upload",
        files={
            "file": (
                "sales.csv",
                b"Sales,Profit,Category,Region\n10,1,Technology,Central\n20,2,Furniture,East\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code in {200, 201}, upload.text
    dataset_id = upload.json()["dataset"]["dataset_id"]
    session_id = "test-session-memory-viz-filter"

    # Seed prior viz topic with known entities via remember path by detecting twice
    # after forcing a visualization classification (rules match "bar chart").
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "Show a bar chart of sales by category",
            "session_id": session_id,
            "dataset_id": dataset_id,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["intent"] == "visualization"

    # Manually seed entities into session memory for deterministic enrichment.
    from app.engines.intent.memory import get_session_memory_store

    get_session_memory_store().remember_turn(
        session_id,
        query="Show a bar chart of sales by category",
        intent="visualization",
        engine="visualization",
        entities={
            "metrics": ["Sales"],
            "dimensions": ["Category"],
            "chart_type": "bar",
            "filters": [],
        },
        dataset_id=dataset_id,
    )

    follow = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "what about technology",
            "session_id": session_id,
            "dataset_id": dataset_id,
        },
    )
    assert follow.status_code == 200, follow.text
    body = follow.json()
    assert body["intent"] == "visualization"
    assert body["memory_applied"] is True
    filters = body["entities"].get("filters") or []
    assert any(
        str(item.get("value", "")).lower() == "technology"
        for item in filters
        if isinstance(item, dict)
    )


def test_explicit_visualization_not_overridden_by_memory(client: TestClient) -> None:
    session_id = "test-session-memory-viz"
    first = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "What is the total sales by region?",
            "session_id": session_id,
        },
    )
    assert first.status_code == 200
    assert first.json()["intent"] == "analytics"

    viz = client.post(
        "/api/v1/intent/detect",
        json={
            "query": "Show a bar chart of sales by category",
            "session_id": session_id,
        },
    )
    assert viz.status_code == 200, viz.text
    body = viz.json()
    assert body["intent"] == "visualization"
    assert body["target_engine"] == "visualization"


def test_profile_routing_is_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "profile the dataset schema"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["routing"]["status"] == "ready"
    assert body["routing"]["engine_pass"]["execute_now"] is True


def test_dataset_id_validation(client: TestClient) -> None:
    missing = client.post(
        "/api/v1/intent/detect",
        json={"query": "total sales", "dataset_id": "doesnotexist"},
    )
    assert missing.status_code == 404

    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", b"a,b\n1,2\n", "text/csv")},
    )
    dataset_id = upload.json()["dataset"]["dataset_id"]
    ok = client.post(
        "/api/v1/intent/detect",
        json={"query": "total sales", "dataset_id": dataset_id},
    )
    assert ok.status_code == 200
    assert ok.json()["dataset_id"] == dataset_id
    context = ok.json()["orchestration"]["context"]
    assert context["dataset_type"] == "csv"
    assert "a" in context["column_names"]
    assert "b" in context["column_names"]
    assert any(col["name"] == "a" for col in context["columns"])


def test_intent_catalog(client: TestClient) -> None:
    response = client.get("/api/v1/intent/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 6
    names = {item["intent"] for item in payload["intents"]}
    assert {"analytics", "visualization", "ml", "rag", "insight", "profile"} <= names


def test_detector_is_deterministic() -> None:
    detector = RuleBasedIntentDetector()
    first = detector.detect("Show a pie chart of market share")
    second = detector.detect("Show a pie chart of market share")
    assert first == second
    assert first.intent == "visualization"


def test_parse_json_content_strips_fences() -> None:
    payload = _parse_json_content(
        '```json\n{"intent":"analytics","confidence":0.9,"rationale":"sum"}\n```'
    )
    assert payload["intent"] == "analytics"


def test_llm_detector_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("INTENT_PROVIDER", "llm")
    get_settings.cache_clear()
    detector = LLMIntentDetector(settings=get_settings())
    match = detector.detect("Show a bar chart of sales")
    assert match.intent == "visualization"
    assert match.provider == "rules_fallback"
    get_settings.cache_clear()


def test_graph_with_mocked_llm_detector(tmp_path: Path) -> None:
    settings_upload = tmp_path / "uploads"
    settings_upload.mkdir()
    dataset_service = DatasetService()
    dataset_service.upload_root = settings_upload

    detector = MagicMock()
    detector.detect.return_value = IntentMatch(
        intent="rag",
        target_engine="rag",
        confidence=0.91,
        rationale="PDF question",
        provider="groq",
        entities={"metrics": []},
    )
    graph = build_intent_graph(detector, dataset_service)
    result = graph.invoke(
        {
            "query": "What does the document say?",
            "dataset_id": None,
            "session_id": "mock-thread",
            "nodes_executed": [],
        },
        config={"configurable": {"thread_id": "mock-thread"}},
    )
    assert result["intent"] == "rag"
    assert result["provider"] == "groq"
    assert result["routing"]["engine"] == "rag"
    assert result["nodes_executed"] == [
        "load_context",
        "load_memory",
        "classify",
        "apply_memory",
        "ground_entities",
        "route",
        "save_memory",
    ]


def test_ground_entities_resolves_and_drops() -> None:
    grounded = ground_entities(
        {
            "metrics": ["sales", "not_a_column"],
            "dimensions": ["REGION"],
            "chart_type": "bar chart",
            "filters": [{"field": "Segment", "op": "=", "value": "Consumer"}],
        },
        ["Sales", "Region", "Segment", "Profit"],
    )
    assert grounded["metrics"] == ["Sales"]
    assert grounded["dimensions"] == ["Region"]
    assert grounded["chart_type"] == "bar"
    assert grounded["filters"][0]["field"] == "Segment"
    assert grounded["grounding"]["dropped"] == ["not_a_column"]
    assert grounded["grounding"]["resolved"]["sales"] == "Sales"


def test_intent_service_uses_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    get_settings.cache_clear()
    service = IntentService()
    response = service.detect(IntentDetectRequest(query="Forecast next month sales"))
    assert response.intent == "ml"
    assert response.orchestration.graph == "intent_router"
    assert "classify" in response.orchestration.nodes_executed
    get_settings.cache_clear()
