"""Schemas for the RAG Engine (Phase 8)."""

from typing import Any

from pydantic import BaseModel, Field


class RagIndexRequest(BaseModel):
    dataset_id: str
    force: bool = False


class RagIndexResponse(BaseModel):
    dataset_id: str
    indexed: bool
    chunk_count: int
    page_count: int
    embedding_model: str | None = None
    reused: bool = False
    message: str = "RAG index ready"


class RagStatusResponse(BaseModel):
    dataset_id: str
    indexed: bool
    chunk_count: int = 0
    page_count: int = 0
    embedding_model: str | None = None
    source_filename: str | None = None


class RagSource(BaseModel):
    chunk_id: str
    page_number: int | None = None
    score: float
    text: str


class RagQueryRequest(BaseModel):
    dataset_id: str
    question: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    synthesize: bool | None = Field(
        default=None,
        description="If true, use Groq to synthesize an answer from retrieved passages.",
    )


class RagQueryResponse(BaseModel):
    dataset_id: str
    question: str
    answer: str
    sources: list[RagSource] = Field(default_factory=list)
    provider: str
    applied: dict[str, Any] = Field(default_factory=dict)
