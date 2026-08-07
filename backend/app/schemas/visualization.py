"""Schemas for the Visualization Engine (Phase 6)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analytics import AggregateFunc, FilterSpec

ChartType = Literal["bar", "line", "pie", "scatter"]


class VisualizationRequest(BaseModel):
    """Build a Plotly chart from an uploaded tabular dataset."""

    dataset_id: str
    chart_type: ChartType = "bar"
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(
        default_factory=list,
        description="Category / x-axis columns.",
    )
    filters: list[FilterSpec] = Field(default_factory=list)
    aggregation: AggregateFunc = "sum"
    limit: int = Field(default=50, ge=1, le=500)
    title: str | None = None


class VisualizationResponse(BaseModel):
    dataset_id: str
    chart_type: ChartType
    title: str
    applied: dict[str, Any]
    data_preview: list[dict[str, Any]] = Field(default_factory=list)
    plotly_figure: dict[str, Any]
    library: str = "plotly"
