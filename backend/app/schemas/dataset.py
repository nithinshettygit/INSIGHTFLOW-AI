"""Schemas for dataset upload and metadata."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DatasetType = Literal["csv", "excel", "pdf"]


class DatasetMeta(BaseModel):
    """Stored metadata for an uploaded dataset."""

    dataset_id: str
    original_filename: str
    stored_filename: str
    dataset_type: DatasetType
    content_type: str | None = None
    size_bytes: int
    uploaded_at: datetime
    extra: dict = Field(default_factory=dict)


class UploadResponse(BaseModel):
    """Response returned after a successful upload."""

    message: str = "Dataset uploaded successfully"
    dataset: DatasetMeta


class DatasetListResponse(BaseModel):
    """Collection of uploaded datasets."""

    count: int
    datasets: list[DatasetMeta]
