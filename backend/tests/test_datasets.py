"""Tests for Phase 2 dataset upload APIs."""

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
    return b"name,revenue\nAlpha,100\nBeta,200\n"


def _xlsx_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "sample.xlsx"
    pd.DataFrame({"name": ["Alpha", "Beta"], "revenue": [100, 200]}).to_excel(
        path, index=False
    )
    return path.read_bytes()


def _pdf_bytes() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)
    return buffer.getvalue()


def test_upload_csv(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", _csv_bytes(), "text/csv")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset"]["dataset_type"] == "csv"
    assert payload["dataset"]["original_filename"] == "sales.csv"
    assert "name" in payload["dataset"]["extra"]["preview_columns"]
    assert payload["dataset"]["extra"]["encoding"] == "utf-8"


def test_upload_csv_cp1252_encoding(client: TestClient) -> None:
    """Superstore-style CSVs often use Windows-1252, not UTF-8."""
    content = "city,note\nSão Paulo,café\n".encode("cp1252")
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("latin.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    extra = response.json()["dataset"]["extra"]
    assert extra["encoding"] in {"cp1252", "latin-1"}
    assert extra["profiled"] is True
    assert extra["row_count"] == 1


def test_upload_excel(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/datasets/upload",
        files={
            "file": (
                "sales.xlsx",
                _xlsx_bytes(tmp_path),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["dataset"]["dataset_type"] == "excel"


def test_upload_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("brief.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    payload = response.json()["dataset"]
    assert payload["dataset_type"] == "pdf"
    assert payload["extra"]["page_count"] == 1


def test_reject_unsupported_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_list_get_delete_dataset(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", _csv_bytes(), "text/csv")},
    )
    dataset_id = upload.json()["dataset"]["dataset_id"]

    listed = client.get("/api/v1/datasets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    detail = client.get(f"/api/v1/datasets/{dataset_id}")
    assert detail.status_code == 200
    assert detail.json()["dataset_id"] == dataset_id

    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/datasets/{dataset_id}")
    assert missing.status_code == 404
