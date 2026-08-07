"""Schemas for automatic dataset profiling (Phase 3)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.dataset import DatasetType


class ColumnProfile(BaseModel):
    """Per-column profiling summary."""

    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_percentage: float
    unique_count: int
    stats: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(BaseModel):
    """Full profiling report for an uploaded dataset."""

    dataset_id: str
    dataset_type: DatasetType
    profiled_at: datetime
    row_count: int | None = None
    column_count: int | None = None
    duplicate_rows: int | None = None
    missing_values_total: int | None = None
    columns: list[ColumnProfile] = Field(default_factory=list)
    numeric_summary: dict[str, dict[str, Any]] = Field(default_factory=dict)
    categorical_summary: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    """API wrapper for a profiling report."""

    message: str = "Dataset profile ready"
    profile: DatasetProfile
    source: Literal["cache", "generated"] = "generated"
