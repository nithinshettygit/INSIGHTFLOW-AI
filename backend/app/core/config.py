"""Application configuration loaded from YAML and secret environment values."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict

# backend/ directory (parent of app/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
# repository root (parent of backend/)
PROJECT_ROOT = BACKEND_ROOT.parent
CONFIG_PATH = PROJECT_ROOT / "configuration" / "config.yaml"
DOTENV_PATH = PROJECT_ROOT / ".env"

_CONFIG_FIELD_MAP: dict[str, dict[str, str]] = {
    "app": {
        "name": "app_name",
        "environment": "app_env",
        "debug": "debug",
    },
    "api": {
        "host": "api_host",
        "port": "api_port",
        "prefix": "api_prefix",
    },
    "logging": {"level": "log_level"},
    "groq": {"model": "groq_model"},
    "paths": {
        "uploads": "upload_dir",
        "models": "model_dir",
        "rag": "rag_dir",
    },
    "uploads": {"max_size_mb": "max_upload_size_mb"},
    "rag": {
        "use_llm": "rag_use_llm",
        "chunk_size": "rag_chunk_size",
        "chunk_overlap": "rag_chunk_overlap",
        "top_k": "rag_top_k",
        "embedding_dim": "rag_embedding_dim",
        "temperature": "rag_temperature",
    },
    "intent": {
        "provider": "intent_provider",
        "temperature": "intent_temperature",
    },
    "ml": {
        "default_horizon": "ml_default_horizon",
        "default_clusters": "ml_default_clusters",
        "anomaly_contamination": "ml_anomaly_contamination",
        "random_state": "ml_random_state",
    },
    "insight": {
        "use_llm": "insight_use_llm",
        "temperature": "insight_temperature",
    },
}

_ENV_FIELDS = {
    "GROQ_API_KEY": "groq_api_key",
    "CORS_ORIGINS": "cors_origins",
}


class Settings(BaseModel):
    """Validated application settings."""

    model_config = ConfigDict(extra="forbid")

    app_name: str
    app_env: str
    debug: bool
    api_host: str
    api_port: int
    api_prefix: str
    groq_api_key: str = ""
    groq_model: str
    intent_temperature: float
    upload_dir: str
    model_dir: str
    rag_dir: str
    log_level: str
    max_upload_size_mb: int
    cors_origins: str
    rag_use_llm: bool
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_top_k: int
    rag_embedding_dim: int
    rag_temperature: float
    intent_provider: str
    ml_default_horizon: int
    ml_default_clusters: int
    ml_anomaly_contamination: float
    ml_random_state: int
    insight_use_llm: bool
    insight_temperature: float

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local"}

    def resolve_path(self, value: str) -> Path:
        """Resolve a configured path against the project root when relative."""
        path = Path(value)
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()

    @property
    def upload_path(self) -> Path:
        return self.resolve_path(self.upload_dir)

    @property
    def model_path(self) -> Path:
        return self.resolve_path(self.model_dir)

    @property
    def rag_path(self) -> Path:
        return self.resolve_path(self.rag_dir)


def _read_yaml_settings(config_path: Path) -> dict[str, Any]:
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw_config, dict):
        raise ValueError(f"Configuration must be a YAML mapping: {config_path}")

    values: dict[str, Any] = {}
    for section, section_values in raw_config.items():
        field_map = _CONFIG_FIELD_MAP.get(section)
        if field_map is None:
            raise ValueError(f"Unknown configuration section: {section}")
        if not isinstance(section_values, dict):
            raise ValueError(f"Configuration section must be a mapping: {section}")

        for key, value in section_values.items():
            field_name = field_map.get(key)
            if field_name is None:
                raise ValueError(f"Unknown configuration key: {section}.{key}")
            values[field_name] = value
    return values


def _load_settings(config_path: Path, dotenv_path: Path) -> Settings:
    """Load YAML settings and allow only secrets/runtime origins from environment."""
    values = _read_yaml_settings(config_path)
    dotenv = dotenv_values(dotenv_path)
    for env_name, field_name in _ENV_FIELDS.items():
        value = os.environ.get(env_name)
        if value is None:
            value = dotenv.get(env_name)
        if value is not None:
            values[field_name] = value
    return Settings.model_validate(values)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return _load_settings(CONFIG_PATH, DOTENV_PATH)
