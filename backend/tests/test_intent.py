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
        "classify",
        "ground_entities",
        "route",
    ]


def test_unknown_intent(client: TestClient) -> None:
    response = client.post("/api/v1/intent/detect", json={"query": "hello there"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "unknown"
    assert payload["target_engine"] == "none"


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
        {"query": "What does the document say?", "dataset_id": None, "nodes_executed": []}
    )
    assert result["intent"] == "rag"
    assert result["provider"] == "groq"
    assert result["routing"]["engine"] == "rag"
    assert result["nodes_executed"] == [
        "load_context",
        "classify",
        "ground_entities",
        "route",
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
