"""Tests for Phase 10 Business Insight Engine."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.insight import infer_insight_mode
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("RAG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("INSIGHT_USE_LLM", "false")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _upload_sales_csv(client: TestClient) -> str:
    content = (
        b"region,category,sales,profit\n"
        b"East,Furniture,100,20\n"
        b"West,Furniture,250,40\n"
        b"East,Technology,80,10\n"
        b"West,Technology,300,90\n"
        b"Central,Office,120,15\n"
        b"East,Office,60,5\n"
    )
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def test_infer_insight_mode() -> None:
    assert infer_insight_mode("Why did profit drop in the West?") == "root_cause"
    assert infer_insight_mode("Recommend actions to improve sales") == "recommendation"
    assert infer_insight_mode("Explain the sales pattern") == "explanation"


def test_insight_root_cause_deterministic(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/insight/analyze",
        json={
            "dataset_id": dataset_id,
            "question": "Why is profit uneven across regions?",
            "mode": "root_cause",
            "focus_metrics": ["profit", "sales"],
            "focus_dimensions": ["region"],
            "synthesize": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "root_cause"
    assert payload["provider"] in {"deterministic", "deterministic_fallback"}
    assert payload["headline"]
    assert payload["explanation"]
    assert payload["findings"]
    assert payload["evidence"]["kpis"]
    assert payload["evidence"]["segment_contrasts"]


def test_insight_recommendation_mode(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/insight/analyze",
        json={
            "dataset_id": dataset_id,
            "question": "What should we do to improve sales?",
            "synthesize": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "recommendation"
    assert payload["recommendations"]
    assert payload["recommendations"][0]["action"]


def test_insight_explanation_includes_evidence(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/insight/analyze",
        json={
            "dataset_id": dataset_id,
            "question": "Explain the dataset performance",
            "mode": "explanation",
            "synthesize": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "explanation"
    assert "profile" in payload["evidence"]
    assert payload["applied"]["synthesize"] is False


def test_insight_pdf_profile_only(client: TestClient) -> None:
    from io import BytesIO

    from pypdf import PdfWriter

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("note.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/v1/insight/analyze",
        json={
            "dataset_id": dataset_id,
            "question": "Explain this document dataset",
            "synthesize": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] in {"deterministic", "deterministic_fallback"}
    assert payload["evidence"]["dataset"]["dataset_type"] == "pdf"


def test_intent_marks_insight_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "Why did profit drop last quarter?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "insight"
    assert body["target_engine"] == "insight"
    assert body["routing"]["status"] == "ready"
