from pathlib import Path
import tempfile

import pytest
from pydantic import ValidationError

from app.core.config import CONFIG_PATH, PROJECT_ROOT, _load_settings, get_settings


def test_load_settings_uses_yaml_and_only_env_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "GROQ_API_KEY=dotenv-secret\n"
        "CORS_ORIGINS=http://dotenv.example\n"
        "APP_NAME=ignored-env-name\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "http://environment.example")
    monkeypatch.setenv("APP_NAME", "ignored-process-name")

    settings = _load_settings(CONFIG_PATH, dotenv_path)

    assert settings.app_name == "InsightFlow AI"
    assert settings.debug is True
    assert settings.api_port == 8000
    assert settings.rag_chunk_size == 800
    assert settings.groq_api_key == "dotenv-secret"
    assert settings.cors_origins == "http://environment.example"


def test_load_settings_rejects_unknown_yaml_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("app:\n  unexpected: value\n", encoding="utf-8")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    with pytest.raises(ValueError, match="Unknown configuration key: app.unexpected"):
        _load_settings(config_path, dotenv_path)


def test_load_settings_requires_yaml_values_not_in_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("app:\n  name: YAML Name\n", encoding="utf-8")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("APP_ENV=ignored-env-value\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("APP_ENV", "ignored-process-value")

    with pytest.raises(ValidationError):
        _load_settings(config_path, dotenv_path)


def test_relative_storage_paths_use_vercel_temp_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERCEL", "1")

    settings = get_settings()

    assert settings.upload_path == (
        Path(tempfile.gettempdir()) / settings.upload_dir
    ).resolve()
    assert settings.model_path == (
        Path(tempfile.gettempdir()) / settings.model_dir
    ).resolve()
    assert settings.rag_path == (
        Path(tempfile.gettempdir()) / settings.rag_dir
    ).resolve()


def test_relative_storage_paths_use_project_root_outside_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERCEL", raising=False)

    settings = get_settings()

    assert settings.upload_path == (PROJECT_ROOT / settings.upload_dir).resolve()
