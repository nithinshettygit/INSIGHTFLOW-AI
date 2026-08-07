"""Tests for Phase 5 Analytics Engine."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.analytics import AnalyticsEngine
from app.main import create_app
from app.schemas.analytics import AnalyticsQueryRequest, FilterSpec, SortSpec
import pandas as pd


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _upload_sales_csv(client: TestClient) -> str:
    content = (
        b"region,sales,quantity\n"
        b"East,100,2\n"
        b"West,200,3\n"
        b"East,50,1\n"
        b"West,150,4\n"
    )
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def test_analytics_groupby_and_kpis(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/analytics/query",
        json={
            "dataset_id": dataset_id,
            "metrics": ["sales"],
            "dimensions": ["region"],
            "aggregations": ["sum", "mean", "count"],
            "sort_by": [{"field": "sales_sum", "order": "desc"}],
            "limit": 10,
            "include_kpis": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["row_count_before"] == 4
    assert payload["row_count_after_filter"] == 4
    assert payload["result_count"] == 2
    assert payload["kpis"]["row_count"] == 4
    assert payload["kpis"]["sales"]["sum"] == 500
    # West total 350, East total 150
    assert payload["results"][0]["region"] == "West"
    assert payload["results"][0]["sales_sum"] == 350


def test_analytics_filter_and_sort(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/analytics/query",
        json={
            "dataset_id": dataset_id,
            "metrics": ["sales"],
            "dimensions": ["region"],
            "filters": [{"field": "region", "op": "eq", "value": "East"}],
            "aggregations": ["sum"],
            "include_kpis": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["row_count_after_filter"] == 2
    assert payload["result_count"] == 1
    assert payload["results"][0]["sales_sum"] == 150
    assert payload["kpis"]["sales"]["sum"] == 150


def test_analytics_rejects_pdf(client: TestClient) -> None:
    from io import BytesIO

    from pypdf import PdfWriter

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("doc.pdf", buffer.getvalue(), "application/pdf")},
    )
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/v1/analytics/query",
        json={"dataset_id": dataset_id, "metrics": ["sales"]},
    )
    assert response.status_code == 400
    assert "CSV or Excel" in response.json()["detail"]


def test_analytics_unknown_column(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/analytics/query",
        json={
            "dataset_id": dataset_id,
            "metrics": ["not_real"],
        },
    )
    assert response.status_code == 400
    assert "Unknown metric" in response.json()["detail"]


def test_engine_unit_aggregate() -> None:
    frame = pd.DataFrame(
        {
            "region": ["East", "West", "East"],
            "sales": [10, 20, 30],
        }
    )
    engine = AnalyticsEngine()
    result = engine.execute(
        frame,
        AnalyticsQueryRequest(
            dataset_id="x",
            metrics=["sales"],
            dimensions=["region"],
            filters=[FilterSpec(field="region", op="ne", value="West")],
            aggregations=["sum"],
            sort_by=[SortSpec(field="sales_sum", order="desc")],
        ),
    )
    assert result["row_count_after_filter"] == 2
    assert result["results"][0]["sales_sum"] == 40


def test_intent_marks_analytics_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "What is the total sales by region?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "analytics"
    assert body["routing"]["status"] == "ready"
    assert body["routing"]["engine_pass"]["execute_now"] is True
