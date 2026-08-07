"""Tests for Phase 6 Visualization Engine."""

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.visualization import VisualizationEngine
from app.main import create_app
from app.schemas.visualization import VisualizationRequest


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
        b"region,sales,profit,quantity\n"
        b"East,100,20,2\n"
        b"West,200,40,3\n"
        b"East,50,10,1\n"
        b"West,150,30,4\n"
    )
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def test_bar_chart(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "bar",
            "metrics": ["sales"],
            "dimensions": ["region"],
            "aggregation": "sum",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["chart_type"] == "bar"
    assert payload["library"] == "plotly"
    assert "data" in payload["plotly_figure"]
    assert "layout" in payload["plotly_figure"]
    assert payload["applied"]["row_count_plotted"] == 2
    assert any(row["region"] == "West" for row in payload["data_preview"])


def test_line_pie_scatter_charts(client: TestClient) -> None:
    dataset_id = _upload_sales_csv(client)

    line = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "line",
            "metrics": ["sales"],
            "dimensions": ["region"],
        },
    )
    assert line.status_code == 200, line.text

    pie = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "pie",
            "metrics": ["sales"],
            "dimensions": ["region"],
        },
    )
    assert pie.status_code == 200, pie.text
    assert pie.json()["plotly_figure"]["data"][0]["type"] == "pie"

    scatter = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "scatter",
            "metrics": ["sales", "profit"],
        },
    )
    assert scatter.status_code == 200, scatter.text
    assert scatter.json()["applied"]["encoding"]["x"] == "sales"
    assert scatter.json()["applied"]["encoding"]["y"] == "profit"


def test_bar_chart_coerces_object_numeric_metric(client: TestClient) -> None:
    """Superstore-like CSVs often store numeric fields as text."""
    content = (
        b"region,sales\n"
        b"East,100\n"
        b"West,200\n"
        b"East,50\n"
    )
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales_text.csv", content, "text/csv")},
    )
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "bar",
            "metrics": ["sales"],
            "dimensions": ["region"],
            "aggregation": "sum",
        },
    )
    assert response.status_code == 200, response.text
    preview = response.json()["data_preview"]
    east = next(row for row in preview if row["region"] == "East")
    assert east["sales_sum"] == 150

    dataset_id = _upload_sales_csv(client)
    response = client.post(
        "/api/v1/visualization/chart",
        json={
            "dataset_id": dataset_id,
            "chart_type": "bar",
            "metrics": ["sales"],
            "dimensions": [],
        },
    )
    assert response.status_code == 400
    assert "dimension" in response.json()["detail"].lower()


def test_engine_unit_bar() -> None:
    frame = pd.DataFrame(
        {
            "region": ["East", "West", "East"],
            "sales": [10, 40, 20],
        }
    )
    engine = VisualizationEngine()
    result = engine.execute(
        frame,
        VisualizationRequest(
            dataset_id="x",
            chart_type="bar",
            metrics=["sales"],
            dimensions=["region"],
            aggregation="sum",
        ),
    )
    assert result["applied"]["row_count_plotted"] == 2
    assert "data" in result["plotly_figure"]


def test_intent_marks_visualization_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "Show a bar chart of sales by region"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "visualization"
    assert body["routing"]["status"] == "ready"
    assert body["routing"]["engine_pass"]["execute_now"] is True
