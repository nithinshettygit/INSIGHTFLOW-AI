"""Plotly visualization engine (Phase 6)."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from app.core.logging import get_logger
from app.engines.analytics.engine import AnalyticsEngine, AnalyticsEngineError, _json_safe
from app.engines.intent.entity_grounding import match_column, normalize_column_name
from app.schemas.analytics import AggregateFunc, FilterSpec
from app.schemas.visualization import ChartType, VisualizationRequest
from app.utils.dataframe import ensure_numeric_series

logger = get_logger(__name__)


class VisualizationEngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class VisualizationEngine:
    """Prepare chart data and emit Plotly figure JSON."""

    def __init__(self, analytics_engine: AnalyticsEngine | None = None) -> None:
        self.analytics = analytics_engine or AnalyticsEngine()

    def execute(
        self,
        frame: pd.DataFrame,
        request: VisualizationRequest,
    ) -> dict[str, Any]:
        if frame.empty and frame.shape[1] == 0:
            raise VisualizationEngineError("Dataset has no columns")

        columns = [str(c) for c in frame.columns.tolist()]
        lookup = {normalize_column_name(c): c for c in columns}

        metrics = self._resolve_columns(request.metrics, lookup, label="metric")
        dimensions = self._resolve_columns(
            request.dimensions,
            lookup,
            label="dimension",
        )
        filters = self._resolve_filters(request.filters, lookup)
        chart_type: ChartType = request.chart_type

        working = frame.copy()
        try:
            working = self.analytics.apply_filters(working, filters)
        except AnalyticsEngineError as exc:
            raise VisualizationEngineError(exc.message, exc.status_code) from exc

        chart_df, encoding = self._prepare_chart_frame(
            working,
            chart_type=chart_type,
            metrics=metrics,
            dimensions=dimensions,
            aggregation=request.aggregation,
            limit=request.limit,
        )
        if chart_df.empty:
            raise VisualizationEngineError("No data available for visualization")

        title = request.title or self._default_title(
            chart_type,
            metrics,
            dimensions,
            request.aggregation,
        )
        figure = self._build_figure(
            chart_df,
            chart_type=chart_type,
            encoding=encoding,
            title=title,
        )

        preview = [
            {str(k): _json_safe(v) for k, v in row.items()}
            for row in chart_df.head(min(request.limit, 25)).to_dict(orient="records")
        ]
        applied = {
            "chart_type": chart_type,
            "metrics": metrics,
            "dimensions": dimensions,
            "filters": [f.model_dump() for f in filters],
            "aggregation": request.aggregation,
            "limit": request.limit,
            "encoding": encoding,
            "row_count_plotted": int(len(chart_df)),
        }
        logger.info(
            "Visualization built type=%s rows=%s metrics=%s dimensions=%s",
            chart_type,
            len(chart_df),
            metrics,
            dimensions,
        )
        return {
            "title": title,
            "applied": applied,
            "data_preview": preview,
            # to_json converts numpy arrays into plain JSON types for FastAPI.
            "plotly_figure": json.loads(pio.to_json(figure, engine="json")),
        }

    def _prepare_chart_frame(
        self,
        frame: pd.DataFrame,
        *,
        chart_type: ChartType,
        metrics: list[str],
        dimensions: list[str],
        aggregation: AggregateFunc,
        limit: int,
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        if chart_type == "scatter":
            return self._prepare_scatter(frame, metrics, dimensions, limit)
        if chart_type == "pie":
            return self._prepare_aggregated(
                frame,
                metrics=metrics,
                dimensions=dimensions,
                aggregation=aggregation,
                limit=limit,
                require_dimension=True,
            )
        # bar / line
        return self._prepare_aggregated(
            frame,
            metrics=metrics,
            dimensions=dimensions,
            aggregation=aggregation,
            limit=limit,
            require_dimension=True,
        )

    def _prepare_aggregated(
        self,
        frame: pd.DataFrame,
        *,
        metrics: list[str],
        dimensions: list[str],
        aggregation: AggregateFunc,
        limit: int,
        require_dimension: bool,
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        if require_dimension and not dimensions:
            raise VisualizationEngineError(
                "bar/line/pie charts require at least one dimension"
            )
        if not metrics:
            raise VisualizationEngineError(
                "bar/line/pie charts require at least one metric"
            )

        metric = metrics[0]
        dimension = dimensions[0]
        try:
            frame = frame.copy()
            frame[metric] = ensure_numeric_series(frame[metric], column_name=metric)
        except ValueError as exc:
            raise VisualizationEngineError(str(exc)) from exc

        grouped = (
            frame.groupby(dimension, dropna=False)[metric]
            .agg(aggregation)
            .reset_index()
        )
        value_col = f"{metric}_{aggregation}"
        grouped = grouped.rename(columns={metric: value_col})
        grouped = grouped.sort_values(value_col, ascending=False).head(limit)

        encoding = {"x": dimension, "y": value_col, "names": dimension, "values": value_col}
        return grouped, encoding

    def _prepare_scatter(
        self,
        frame: pd.DataFrame,
        metrics: list[str],
        dimensions: list[str],
        limit: int,
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        if len(metrics) >= 2:
            x_col, y_col = metrics[0], metrics[1]
            color_col = dimensions[0] if dimensions else None
        elif len(metrics) == 1 and dimensions:
            x_col, y_col = dimensions[0], metrics[0]
            color_col = dimensions[1] if len(dimensions) > 1 else None
        else:
            raise VisualizationEngineError(
                "scatter requires two metrics, or one metric plus one dimension"
            )

        for col in (x_col, y_col):
            if col in metrics:
                try:
                    frame[col] = ensure_numeric_series(frame[col], column_name=col)
                except ValueError as exc:
                    if col == y_col or len(metrics) >= 2:
                        raise VisualizationEngineError(str(exc)) from exc

        cols = [x_col, y_col] + ([color_col] if color_col else [])
        scatter_df = frame[cols].dropna().head(limit)
        encoding = {"x": x_col, "y": y_col}
        if color_col:
            encoding["color"] = color_col
        return scatter_df, encoding

    def _build_figure(
        self,
        chart_df: pd.DataFrame,
        *,
        chart_type: ChartType,
        encoding: dict[str, str],
        title: str,
    ) -> go.Figure:
        if chart_type == "bar":
            fig = px.bar(
                chart_df,
                x=encoding["x"],
                y=encoding["y"],
                title=title,
            )
        elif chart_type == "line":
            # Lines look better sorted by x when possible.
            ordered = chart_df.sort_values(encoding["x"])
            fig = px.line(
                ordered,
                x=encoding["x"],
                y=encoding["y"],
                title=title,
                markers=True,
            )
        elif chart_type == "pie":
            fig = px.pie(
                chart_df,
                names=encoding["names"],
                values=encoding["values"],
                title=title,
            )
        elif chart_type == "scatter":
            fig = px.scatter(
                chart_df,
                x=encoding["x"],
                y=encoding["y"],
                color=encoding.get("color"),
                title=title,
            )
        else:
            raise VisualizationEngineError(f"Unsupported chart type '{chart_type}'")

        fig.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=60, b=40))
        return fig

    def _default_title(
        self,
        chart_type: ChartType,
        metrics: list[str],
        dimensions: list[str],
        aggregation: AggregateFunc,
    ) -> str:
        metric = metrics[0] if metrics else "value"
        dimension = dimensions[0] if dimensions else "index"
        if chart_type == "scatter":
            if len(metrics) >= 2:
                return f"{metrics[1]} vs {metrics[0]}"
            return f"{metric} vs {dimension}"
        return f"{aggregation.title()} of {metric} by {dimension}"

    def _resolve_columns(
        self,
        names: list[str],
        lookup: dict[str, str],
        *,
        label: str,
    ) -> list[str]:
        resolved: list[str] = []
        for name in names:
            match = match_column(str(name), lookup)
            if match is None:
                raise VisualizationEngineError(
                    f"Unknown {label} column '{name}'. "
                    f"Available: {', '.join(lookup.values())}"
                )
            if match not in resolved:
                resolved.append(match)
        return resolved

    def _resolve_filters(
        self,
        filters: list[FilterSpec],
        lookup: dict[str, str],
    ) -> list[FilterSpec]:
        resolved: list[FilterSpec] = []
        for spec in filters:
            match = match_column(spec.field, lookup)
            if match is None:
                raise VisualizationEngineError(f"Unknown filter column '{spec.field}'")
            resolved.append(FilterSpec(field=match, op=spec.op, value=spec.value))
        return resolved
