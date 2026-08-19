"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (parent of app/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
# repository root (parent of backend/)
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Central settings for InsightFlow AI backend.

    Values are read from environment variables and optional `.env` files.
    Paths that are relative resolve against the repository root.
    """

    model_config = SettingsConfigDict(
        env_file=(
            str(PROJECT_ROOT / ".env"),
            str(BACKEND_ROOT / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="InsightFlow AI", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(
        default="qwen/qwen3.6-27b",
        alias="GROQ_MODEL",
    )
    intent_temperature: float = Field(default=0.0, alias="INTENT_TEMPERATURE")

    upload_dir: str = Field(default="backend/data/uploads", alias="UPLOAD_DIR")
    model_dir: str = Field(default="backend/models", alias="MODEL_DIR")
    rag_dir: str = Field(default="backend/data/rag", alias="RAG_DIR")

    database_url: str = Field(
        default="sqlite:///./backend/data/insightflow.db",
        alias="DATABASE_URL",
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_upload_size_mb: int = Field(default=25, alias="MAX_UPLOAD_SIZE_MB")
    # Comma-separated browser origins allowed for CORS (Netlify/Vercel URLs).
    cors_origins: str = Field(
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:3000,http://127.0.0.1:3000"
        ),
        alias="CORS_ORIGINS",
    )

    # RAG (Phase 8)
    rag_chunk_size: int = Field(default=800, alias="RAG_CHUNK_SIZE")
    rag_chunk_overlap: int = Field(default=120, alias="RAG_CHUNK_OVERLAP")
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K")
    rag_embedding_dim: int = Field(default=384, alias="RAG_EMBEDDING_DIM")
    rag_temperature: float = Field(default=0.0, alias="RAG_TEMPERATURE")

    # ML (Phase 9)
    ml_default_horizon: int = Field(default=7, alias="ML_DEFAULT_HORIZON")
    ml_default_clusters: int = Field(default=3, alias="ML_DEFAULT_CLUSTERS")
    ml_anomaly_contamination: float = Field(
        default=0.05,
        alias="ML_ANOMALY_CONTAMINATION",
    )
    ml_random_state: int = Field(default=42, alias="ML_RANDOM_STATE")

    # Insight (Phase 10)
    insight_temperature: float = Field(default=0.1, alias="INSIGHT_TEMPERATURE")

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


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
