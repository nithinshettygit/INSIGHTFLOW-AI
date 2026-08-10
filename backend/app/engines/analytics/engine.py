"""Deterministic Pandas analytics engine (Phase 5)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.engines.intent.entity_grounding import match_column, normalize_column_name
from app.schemas.analytics import (
    AggregateFunc,
    AnalyticsQueryRequest,
    FilterSpec,
    SortSpec,
)
from app.utils.dataframe import ensure_numeric_series

logger = get_logger(__name__)

SUPPORTED_FUNCS: dict[str, str] = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
    "min": "min",
    "max": "max",
    "median": "median",
}


class AnalyticsEngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AnalyticsEngine:
    """Run filter → aggregate/KPI → sort → limit over a DataFrame."""

    def execute(
        self,
        frame: pd.DataFrame,
        request: AnalyticsQueryRequest,
    ) -> dict[str, Any]:
        if frame.empty and frame.shape[1] == 0:
            raise AnalyticsEngineError("Dataset has no columns")

        columns = [str(c) for c in frame.columns.tolist()]
        lookup = {normalize_column_name(c): c for c in columns}

        metrics = self._resolve_columns(request.metrics, lookup, label="metric")
        dimensions = self._resolve_columns(
            request.dimensions,
            lookup,
            label="dimension",
        )
        filters = self._resolve_filters(request.filters, lookup)

        working = frame.copy()
        for metric in metrics:
            try:
                working[metric] = ensure_numeric_series(
                    working[metric],
                    column_name=metric,
                )
            except ValueError:
                # Leave non-coercible metrics as-is; aggregate() will count-only.
                pass

        row_count_before = int(len(working))
        working = self.apply_filters(working, filters)
        row_count_after = int(len(working))

        kpis: dict[str, Any] = {}
        if request.include_kpis:
            kpis = self.compute_kpis(working, metrics)

        if dimensions:
            results_df = self.aggregate(
                working,
                metrics=metrics,
                dimensions=dimensions,
                funcs=request.aggregations,
            )
        elif metrics:
            # No group-by: return one aggregated summary row.
            results_df = self.aggregate(
                working,
                metrics=metrics,
                dimensions=[],
                funcs=request.aggregations,
            )
        else:
            # Raw filtered rows preview when no metrics/dimensions provided.
            results_df = working.copy()

        # Resolve sort fields against result columns (supports sales_sum aliases).
        sort_by = self._resolve_sorts(request.sort_by, results_df)
        results_df = self.apply_sort(results_df, sort_by)
        if request.limit:
            results_df = results_df.head(request.limit)

        results = [
            {str(k): _json_safe(v) for k, v in row.items()}
            for row in results_df.to_dict(orient="records")
        ]

        applied = {
            "metrics": metrics,
            "dimensions": dimensions,
            "filters": [f.model_dump() for f in filters],
            "aggregations": list(request.aggregations),
            "sort_by": [s.model_dump() for s in sort_by],
            "limit": request.limit,
        }
        logger.info(
            "Analytics complete before=%s after=%s groups=%s results=%s",
            row_count_before,
            row_count_after,
            dimensions,
            len(results),
        )
        return {
            "row_count_before": row_count_before,
            "row_count_after_filter": row_count_after,
            "applied": applied,
            "kpis": kpis,
            "results": results,
            "result_count": len(results),
        }

    def apply_filters(
        self,
        frame: pd.DataFrame,
        filters: list[FilterSpec],
    ) -> pd.DataFrame:
        working = frame
        for spec in filters:
            column = working[spec.field]
            op = spec.op
            value = spec.value
            if op == "eq":
                mask = column == value
            elif op == "ne":
                mask = column != value
            elif op == "gt":
                mask = column > value
            elif op == "gte":
                mask = column >= value
            elif op == "lt":
                mask = column < value
            elif op == "lte":
                mask = column <= value
            elif op == "contains":
                mask = column.astype("string").str.contains(
                    str(value),
                    case=False,
                    na=False,
                )
            elif op == "in":
                if not isinstance(value, list):
                    raise AnalyticsEngineError(
                        f"Filter op 'in' requires a list value for '{spec.field}'"
                    )
                mask = column.isin(value)
            else:
                raise AnalyticsEngineError(f"Unsupported filter op '{op}'")
            working = working.loc[mask]
        return working

    def compute_kpis(
        self,
        frame: pd.DataFrame,
        metrics: list[str],
    ) -> dict[str, Any]:
        kpis: dict[str, Any] = {
            "row_count": int(len(frame)),
        }
        target_cols = metrics or [
            str(c)
            for c in frame.columns
            if pd.api.types.is_numeric_dtype(frame[c])
            and not pd.api.types.is_bool_dtype(frame[c])
        ]
        # Keep KPI payload bounded.
        for col in target_cols[:12]:
            series = frame[col]
            try:
                series = ensure_numeric_series(series, column_name=col)
            except ValueError:
                kpis[col] = {"count": int(series.notna().sum())}
                continue
            kpis[col] = {
                "count": _json_safe(series.count()),
                "sum": _json_safe(series.sum()),
                "mean": _json_safe(series.mean()),
                "min": _json_safe(series.min()),
                "max": _json_safe(series.max()),
            }
        return kpis

    def aggregate(
        self,
        frame: pd.DataFrame,
        *,
        metrics: list[str],
        dimensions: list[str],
        funcs: list[AggregateFunc],
    ) -> pd.DataFrame:
        if not metrics:
            if dimensions:
                grouped = (
                    frame.groupby(dimensions, dropna=False)
                    .size()
                    .reset_index(name="count")
                )
                return grouped
            return pd.DataFrame([{"count": int(len(frame))}])

        valid_funcs = [SUPPORTED_FUNCS[f] for f in funcs if f in SUPPORTED_FUNCS]
        if not valid_funcs:
            raise AnalyticsEngineError("No valid aggregation functions provided")

        agg_map: dict[str, list[str]] = {}
        working = frame.copy()
        for metric in metrics:
            try:
                working[metric] = ensure_numeric_series(
                    working[metric],
                    column_name=metric,
                )
                agg_map[metric] = valid_funcs
            except ValueError:
                # Non-numeric metrics: count only.
                agg_map[metric] = ["count"]

        if dimensions:
            grouped = working.groupby(dimensions, dropna=False).agg(agg_map)
            # Flatten MultiIndex columns: sales_sum, sales_mean, ...
            grouped.columns = [
                f"{col}_{fn}" if fn else str(col)
                for col, fn in grouped.columns.to_list()
            ]
            return grouped.reset_index()

        summary: dict[str, Any] = {}
        for metric, fns in agg_map.items():
            for fn in fns:
                key = f"{metric}_{fn}"
                if fn == "sum":
                    summary[key] = working[metric].sum()
                elif fn == "mean":
                    summary[key] = working[metric].mean()
                elif fn == "count":
                    summary[key] = working[metric].count()
                elif fn == "min":
                    summary[key] = working[metric].min()
                elif fn == "max":
                    summary[key] = working[metric].max()
                elif fn == "median":
                    summary[key] = working[metric].median()
        return pd.DataFrame([summary])

    def apply_sort(
        self,
        frame: pd.DataFrame,
        sort_by: list[SortSpec],
    ) -> pd.DataFrame:
        if frame.empty or not sort_by:
            return frame
        by = [s.field for s in sort_by]
        ascending = [s.order == "asc" for s in sort_by]
        missing = [c for c in by if c not in frame.columns]
        if missing:
            # Allow sorting by generated agg columns with exact names only.
            raise AnalyticsEngineError(
                f"Sort field(s) not in result columns: {', '.join(missing)}"
            )
        return frame.sort_values(by=by, ascending=ascending, kind="mergesort")

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
                raise AnalyticsEngineError(
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
                raise AnalyticsEngineError(f"Unknown filter column '{spec.field}'")
            resolved.append(
                FilterSpec(field=match, op=spec.op, value=spec.value)
            )
        return resolved

    def _resolve_sorts(
        self,
        sorts: list[SortSpec],
        result_frame: pd.DataFrame,
    ) -> list[SortSpec]:
        if not sorts:
            return []
        columns = [str(c) for c in result_frame.columns.tolist()]
        lookup = {normalize_column_name(c): c for c in columns}
        resolved: list[SortSpec] = []
        for spec in sorts:
            key = normalize_column_name(spec.field)
            match = lookup.get(key)
            if match is None and spec.field in result_frame.columns:
                match = spec.field
            if match is None:
                # Map bare metric names onto aggregated result columns.
                # Prefer max/min for extreme sorts, else sum/mean/count.
                preferred = (
                    ("min", "mean", "sum", "count", "median", "max")
                    if spec.order == "asc"
                    else ("max", "sum", "mean", "count", "median", "min")
                )
                for suffix in preferred:
                    candidate = lookup.get(f"{key}_{suffix}")
                    if candidate is not None:
                        match = candidate
                        break
                if match is None:
                    # Last resort: any column that starts with the metric name.
                    for col_key, original in lookup.items():
                        if col_key.startswith(f"{key}_"):
                            match = original
                            break
            if match is None:
                raise AnalyticsEngineError(
                    f"Sort field '{spec.field}' not in result columns: "
                    f"{', '.join(columns)}"
                )
            resolved.append(SortSpec(field=match, order=spec.order))
        return resolved


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)
