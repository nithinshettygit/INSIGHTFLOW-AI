"""Tests for Phase 9 ML Engine."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.ml import infer_ml_task
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("RAG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _upload_sales_csv(client: TestClient) -> str:
    content = (
        b"order_date,region,sales,profit,quantity\n"
        b"2024-01-01,East,100,20,2\n"
        b"2024-01-08,West,200,40,3\n"
        b"2024-01-15,East,150,30,2\n"
        b"2024-01-22,West,180,35,4\n"
        b"2024-01-29,East,220,50,5\n"
        b"2024-02-05,West,210,45,3\n"
        b"2024-02-12,East,260,60,6\n"
        b"2024-02-19,West,240,55,4\n"
        b"2024-02-26,East,300,70,7\n"
        b"2024-03-04,West,280,65,5\n"
        b"2024-03-11,East,320,80,8\n"
        b"2024-03-18,West,310,75,6\n"
    )
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def test_infer_ml_task() -> None:
    assert infer_ml_task("Forecast next month sales") == "forecast"
    assert infer_ml_task("Segment customers by spend") == "segmentation"
    assert infer_ml_task("Detect anomalies in daily orders") == "anomaly"


def test_forecast(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/ml/run",
        json={
            "dataset_id": dataset_id,
            "task": "forecast",
            "target": "sales",
            "time_column": "order_date",
            "horizon": 5,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task"] == "forecast"
    assert payload["model"] == "linear_trend_seasonal_blend"
    assert payload["summary"]["horizon"] == 5
    assert payload["plotly_figure"] is not None
    assert any(row.get("kind") == "forecast" for row in payload["results"])


def test_segmentation(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/ml/run",
        json={
            "dataset_id": dataset_id,
            "task": "segmentation",
            "features": ["sales", "profit", "quantity"],
            "n_clusters": 3,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task"] == "segmentation"
    assert payload["summary"]["n_clusters"] == 3
    assert "cluster_sizes" in payload["summary"]
    assert payload["plotly_figure"] is not None


def test_anomaly(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/ml/run",
        json={
            "dataset_id": dataset_id,
            "task": "anomaly",
            "features": ["sales", "profit", "quantity"],
            "contamination": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task"] == "anomaly"
    assert payload["summary"]["anomaly_count"] >= 1
    assert "anomaly" in payload["results"][0]


def test_ml_rejects_pdf(client: TestClient) -> None:
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
        "/api/v1/ml/run",
        json={"dataset_id": dataset_id, "task": "forecast", "query": "forecast sales"},
    )
    assert response.status_code == 400


def test_infer_task_from_query(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/ml/run",
        json={
            "dataset_id": dataset_id,
            "query": "Detect anomalies in sales and profit",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["task"] == "anomaly"


def test_intent_marks_ml_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "Forecast next month sales"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "ml"
    assert body["target_engine"] == "ml"
    assert body["routing"]["status"] == "ready"
