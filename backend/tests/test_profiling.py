"""Tests for Phase 3 automatic dataset profiling."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _csv_bytes() -> bytes:
    return (
        b"name,revenue,region\n"
        b"Alpha,100,East\n"
        b"Beta,200,West\n"
        b"Alpha,100,East\n"
        b"Gamma,,East\n"
    )


def _xlsx_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "sample.xlsx"
    pd.DataFrame(
        {"name": ["Alpha", "Beta"], "revenue": [100, 200]}
    ).to_excel(path, index=False)
    return path.read_bytes()


def _pdf_bytes() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


def test_upload_auto_profiles_csv(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", _csv_bytes(), "text/csv")},
    )
    assert response.status_code == 201
    dataset = response.json()["dataset"]
    assert dataset["extra"]["profiled"] is True
    assert dataset["extra"]["row_count"] == 4
    assert dataset["extra"]["column_count"] == 3
    assert dataset["extra"]["duplicate_rows"] == 1
    assert dataset["extra"]["missing_values_total"] == 1

    dataset_id = dataset["dataset_id"]
    profile_resp = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile_resp.status_code == 200
    body = profile_resp.json()
    assert body["source"] == "cache"
    profile = body["profile"]
    assert profile["row_count"] == 4
    assert profile["column_count"] == 3
    assert profile["duplicate_rows"] == 1
    assert profile["missing_values_total"] == 1
    assert "revenue" in profile["numeric_summary"]
    assert "region" in profile["categorical_summary"]
    assert len(profile["columns"]) == 3
    assert len(profile["sample_rows"]) == 4

    processed = Path(tmp_path / "processed" / f"{dataset_id}.profile.json")
    assert processed.exists()


def test_upload_profiles_excel_and_pdf(client: TestClient, tmp_path: Path) -> None:
    excel = client.post(
        "/api/v1/datasets/upload",
        files={
            "file": (
                "sales.xlsx",
                _xlsx_bytes(tmp_path),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert excel.status_code == 201
    excel_id = excel.json()["dataset"]["dataset_id"]
    excel_profile = client.get(f"/api/v1/datasets/{excel_id}/profile").json()["profile"]
    assert excel_profile["row_count"] == 2
    assert excel_profile["column_count"] == 2

    pdf = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("brief.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert pdf.status_code == 201
    pdf_id = pdf.json()["dataset"]["dataset_id"]
    pdf_profile = client.get(f"/api/v1/datasets/{pdf_id}/profile").json()["profile"]
    assert pdf_profile["dataset_type"] == "pdf"
    assert pdf_profile["metadata"]["page_count"] == 1
    assert pdf_profile["row_count"] is None


def test_refresh_profile(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", _csv_bytes(), "text/csv")},
    )
    dataset_id = upload.json()["dataset"]["dataset_id"]
    refreshed = client.post(f"/api/v1/datasets/{dataset_id}/profile")
    assert refreshed.status_code == 200
    assert refreshed.json()["source"] == "generated"
    assert refreshed.json()["profile"]["row_count"] == 4
