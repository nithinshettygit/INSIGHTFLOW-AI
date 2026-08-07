"""Tests for the Phase 1 health API skeleton."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_root_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert "InsightFlow AI" in payload["message"]
    assert payload["health"] == "/api/v1/health"


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "insightflow-ai"
    assert "version" in payload
    assert "environment" in payload
