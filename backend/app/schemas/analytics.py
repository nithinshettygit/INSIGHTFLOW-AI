"""Schemas for the Analytics Engine (Phase 5)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AggregateFunc = Literal["sum", "mean", "count", "min", "max", "median"]
FilterOp = Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"]
SortOrder = Literal["asc", "desc"]


class FilterSpec(BaseModel):
    field: str
    op: FilterOp = "eq"
    value: Any


class SortSpec(BaseModel):
    field: str
    order: SortOrder = "desc"


class AggregationSpec(BaseModel):
    column: str
    func: AggregateFunc = "sum"


class AnalyticsQueryRequest(BaseModel):
    """Deterministic analytics query over an uploaded tabular dataset."""

    dataset_id: str
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(
        default_factory=list,
        description="Group-by columns.",
    )
    filters: list[FilterSpec] = Field(default_factory=list)
    aggregations: list[AggregateFunc] = Field(
        default_factory=lambda: ["sum", "mean", "count"],
        description="Aggregation functions applied to each metric.",
    )
    sort_by: list[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=1000)
    include_kpis: bool = True


class AnalyticsQueryResponse(BaseModel):
    dataset_id: str
    row_count_before: int
    row_count_after_filter: int
    applied: dict[str, Any]
    kpis: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)
    result_count: int = 0
