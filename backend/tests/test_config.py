"""Tests for configuration loading."""

from app.core.config import Settings, get_settings


def test_default_settings() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_name == "InsightFlow AI"
    assert settings.api_port == 8000
    assert settings.api_prefix == "/api/v1"
    assert settings.upload_path.name == "uploads"


def test_resolve_path_relative() -> None:
    settings = Settings()
    resolved = settings.resolve_path("backend/data/uploads")
    assert resolved.is_absolute()
    assert resolved.name == "uploads"
