"""Shared helpers for ML engine tasks."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.engines.intent.entity_grounding import match_column, normalize_column_name
from app.utils.dataframe import ensure_numeric_series


class MlEngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def resolve_column(
    name: str | None,
    lookup: dict[str, str],
    *,
    label: str,
    required: bool = True,
) -> str | None:
    if not name or not str(name).strip():
        if required:
            raise MlEngineError(f"{label} is required")
        return None
    key = normalize_column_name(str(name))
    if key in lookup:
        return lookup[key]
    matched = match_column(str(name), lookup)
    if matched:
        return matched
    if required:
        raise MlEngineError(f"Unknown {label} column '{name}'")
    return None


def resolve_columns(
    names: list[str],
    lookup: dict[str, str],
    *,
    label: str,
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for name in names:
        col = resolve_column(name, lookup, label=label, required=True)
        assert col is not None
        if col not in seen:
            resolved.append(col)
            seen.add(col)
    return resolved


def build_column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    columns = [str(c) for c in frame.columns.tolist()]
    return {normalize_column_name(c): c for c in columns}


def coerce_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    try:
        return ensure_numeric_series(frame[column], column_name=column)
    except ValueError as exc:
        raise MlEngineError(str(exc)) from exc


def infer_numeric_features(
    frame: pd.DataFrame,
    *,
    exclude: set[str] | None = None,
    limit: int = 8,
) -> list[str]:
    exclude = exclude or set()
    features: list[str] = []
    for column in frame.columns:
        name = str(column)
        if name in exclude:
            continue
        series = frame[column]
        try:
            numeric = ensure_numeric_series(series, column_name=name)
        except ValueError:
            continue
        if numeric.notna().sum() < max(5, int(0.5 * len(frame))):
            continue
        features.append(name)
        if len(features) >= limit:
            break
    if not features:
        raise MlEngineError(
            "No usable numeric feature columns found for this ML task",
        )
    return features


def detect_time_column(frame: pd.DataFrame) -> str | None:
    best_name: str | None = None
    best_ratio = 0.0
    for column in frame.columns:
        name = str(column).lower()
        series = frame[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            return str(column)
        hint = any(
            token in name
            for token in ("date", "time", "month", "year", "day", "order_date")
        )
        parsed = pd.to_datetime(series, errors="coerce", utc=False)
        ratio = float(parsed.notna().mean()) if len(series) else 0.0
        if ratio >= 0.8 and (hint or ratio > best_ratio):
            best_name = str(column)
            best_ratio = ratio
            if hint and ratio >= 0.8:
                return best_name
    return best_name


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if np.isnan(number) or np.isinf(number):
            return None
        return number
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if pd.isna(value):
        return None
    return value


def records_from_frame(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    preview = frame.head(limit).copy()
    for column in preview.columns:
        preview[column] = preview[column].map(to_jsonable)
    return preview.to_dict(orient="records")
