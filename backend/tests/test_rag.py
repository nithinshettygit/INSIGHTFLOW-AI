"""Tests for Phase 8 RAG Engine."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.core.config import get_settings
from app.engines.rag.chunking import chunk_pages
from app.engines.rag.embeddings import HashingEmbedder
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("RAG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("INTENT_PROVIDER", "rules")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("RAG_USE_LLM", "false")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _pdf_with_text(lines: list[str]) -> bytes:
    """Build a minimal single-page PDF containing the given text lines."""
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    page = writer.pages[0]

    y = 360
    content_lines = ["BT", "/F1 12 Tf"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"1 0 0 1 50 {y} Tm ({safe}) Tj")
        y -= 18
    content_lines.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(content_lines).encode("latin-1", errors="replace"))

    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = stream

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload_policy_pdf(client: TestClient) -> str:
    content = _pdf_with_text(
        [
            "Refund Policy Handbook",
            "Customers may request a refund within 30 days of purchase.",
            "Digital goods are non-refundable after download.",
            "Contact support@example.com for billing disputes.",
        ]
    )
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("refund-policy.pdf", content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]["dataset_id"]


def test_chunking_overlap() -> None:
    pages = [(1, "word " * 200)]
    chunks = chunk_pages(pages, chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(chunk.page_number == 1 for chunk in chunks)


def test_hashing_embedder_normalized() -> None:
    embedder = HashingEmbedder(dim=64)
    vector = embedder.embed_query("refund policy within 30 days")
    assert vector.shape == (64,)
    assert abs(float((vector**2).sum()) - 1.0) < 1e-5


def test_pdf_upload_auto_indexes(client: TestClient) -> None:
    dataset_id = _upload_policy_pdf(client)
    status = client.get(f"/api/v1/rag/{dataset_id}/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["indexed"] is True
    assert body["chunk_count"] >= 1


def test_rag_query_extractive(client: TestClient) -> None:
    dataset_id = _upload_policy_pdf(client)
    response = client.post(
        "/api/v1/rag/query",
        json={
            "dataset_id": dataset_id,
            "question": "What is the refund window for customers?",
            "top_k": 3,
            "synthesize": False,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] in {"extractive", "extractive_fallback"}
    assert payload["sources"]
    joined = (payload["answer"] + " " + " ".join(s["text"] for s in payload["sources"])).lower()
    assert "refund" in joined
    assert "30" in joined


def test_rag_rejects_csv(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset"]["dataset_id"]
    response = client.post(
        "/api/v1/rag/query",
        json={"dataset_id": dataset_id, "question": "What does this say?"},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_rag_index_force_reuse(client: TestClient) -> None:
    dataset_id = _upload_policy_pdf(client)
    first = client.post("/api/v1/rag/index", json={"dataset_id": dataset_id})
    assert first.status_code == 200
    assert first.json()["reused"] is True

    forced = client.post(
        "/api/v1/rag/index",
        json={"dataset_id": dataset_id, "force": True},
    )
    assert forced.status_code == 200
    assert forced.json()["reused"] is False
    assert forced.json()["indexed"] is True


def test_intent_marks_rag_ready(client: TestClient) -> None:
    response = client.post(
        "/api/v1/intent/detect",
        json={"query": "What does the PDF say about refunds?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "rag"
    assert body["target_engine"] == "rag"
    assert body["routing"]["status"] == "ready"


def test_delete_dataset_removes_rag_index(
    client: TestClient,
    tmp_path: Path,
) -> None:
    dataset_id = _upload_policy_pdf(client)
    rag_dir = tmp_path / "rag" / dataset_id
    assert rag_dir.exists()
    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert deleted.status_code == 204
    assert not rag_dir.exists()
