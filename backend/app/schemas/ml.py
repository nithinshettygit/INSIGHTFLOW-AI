"""Schemas for the ML Engine (Phase 9)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

MlTask = Literal["forecast", "segmentation", "anomaly"]


class MlRunRequest(BaseModel):
    """Run a classical ML task over an uploaded tabular dataset."""

    dataset_id: str
    task: MlTask | None = Field(
        default=None,
        description="If omitted, inferred from `query` keywords.",
    )
    query: str | None = Field(
        default=None,
        description="Optional natural-language hint used to infer the ML task.",
    )
    target: str | None = Field(
        default=None,
        description="Target/metric column (forecast value, or anomaly focus).",
    )
    time_column: str | None = Field(
        default=None,
        description="Datetime/order column for forecasting.",
    )
    features: list[str] = Field(
        default_factory=list,
        description="Feature columns for segmentation/anomaly. Auto-selected when empty.",
    )
    plot_x: str | None = Field(
        default=None,
        description="Optional X axis for segmentation/anomaly scatter (dataset column).",
    )
    plot_y: str | None = Field(
        default=None,
        description="Optional Y axis for segmentation/anomaly scatter (dataset column).",
    )
    horizon: int = Field(default=7, ge=1, le=365)
    n_clusters: int = Field(default=3, ge=2, le=20)
    contamination: float = Field(default=0.05, gt=0.0, lt=0.5)
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max preview rows returned in results.",
    )


class MlRunResponse(BaseModel):
    dataset_id: str
    task: MlTask
    model: str
    summary: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)
    result_count: int = 0
    applied: dict[str, Any] = Field(default_factory=dict)
    plotly_figure: dict[str, Any] | None = None
