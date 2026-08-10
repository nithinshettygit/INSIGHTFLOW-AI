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


def resolve_feature_columns(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    features: list[str] | None,
    *,
    limit: int = 6,
) -> list[str]:
    """Resolve requested features, falling back to ranked dataset numerics."""
    resolved: list[str] = []
    seen: set[str] = set()
    for name in features or []:
        col = resolve_column(name, lookup, label="feature", required=False)
        if col is None or col in seen:
            continue
        try:
            coerce_numeric(frame, col)
        except MlEngineError:
            continue
        resolved.append(col)
        seen.add(col)
        if len(resolved) >= limit:
            break
    if resolved:
        return resolved
    return infer_numeric_features(frame, limit=limit)


def scatter_axis_score(series: pd.Series) -> float:
    """Higher = better continuous scatter axis. Low for discrete counts like Quantity."""
    try:
        numeric = ensure_numeric_series(series, column_name=str(series.name or "axis"))
    except ValueError:
        return -1.0
    usable = numeric.dropna()
    if len(usable) < 5:
        return -1.0
    nunique = int(usable.nunique())
    if nunique < 2:
        return -1.0
    # Discrete low-cardinality columns (quantity 1..14) make striped scatters.
    if nunique < 20:
        return -1.0
    std = float(usable.std(ddof=0) or 0.0)
    if std <= 0:
        return -1.0
    mean_abs = float(np.nanmean(np.abs(usable.to_numpy(dtype=float))) or 1.0)
    cardinality = nunique / max(len(usable), 1)
    return (std / max(mean_abs, 1e-9)) + cardinality


def pick_scatter_axes(
    frame: pd.DataFrame,
    candidates: list[str],
    *,
    preferred_x: str | None = None,
    preferred_y: str | None = None,
) -> tuple[str, str] | None:
    """Pick two continuous axes for scatter; reject striped discrete pairs."""
    preferred = [c for c in (preferred_x, preferred_y) if c]
    ordered = list(dict.fromkeys([*preferred, *candidates]))
    scored: list[tuple[float, str]] = []
    for col in ordered:
        if col not in frame.columns:
            continue
        score = scatter_axis_score(frame[col])
        if score < 0:
            continue
        scored.append((score, col))
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) < 2:
        return None
    # Prefer explicit pair when both are good continuous axes.
    if (
        preferred_x
        and preferred_y
        and preferred_x != preferred_y
        and scatter_axis_score(frame[preferred_x]) >= 0
        and scatter_axis_score(frame[preferred_y]) >= 0
    ):
        return preferred_x, preferred_y
    return scored[0][1], scored[1][1]

def build_column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    columns = [str(c) for c in frame.columns.tolist()]
    return {normalize_column_name(c): c for c in columns}


def coerce_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    try:
        return ensure_numeric_series(frame[column], column_name=column)
    except ValueError as exc:
        raise MlEngineError(str(exc)) from exc


_PREFERRED_FEATURE_TOKENS = (
    "sales",
    "profit",
    "quantity",
    "discount",
    "shipping",
    "revenue",
    "amount",
    "price",
    "cost",
    "income",
    "margin",
    "units",
    "score",
    "rating",
    "tenure",
    "age",
    "income",
    "spend",
    "value",
)

_EXCLUDE_FEATURE_TOKENS = (
    "id",
    "index",
    "row",
    "postal",
    "zip",
    "phone",
    "latitude",
    "longitude",
    "lat",
    "lon",
    "lng",
)


def _score_numeric_columns(
    frame: pd.DataFrame,
    *,
    exclude: set[str] | None = None,
) -> list[tuple[float, str]]:
    exclude = exclude or set()
    scored: list[tuple[float, str]] = []

    for column in frame.columns:
        name = str(column)
        if name in exclude:
            continue
        lower = name.lower()
        if any(token in lower for token in _EXCLUDE_FEATURE_TOKENS):
            if not any(token in lower for token in _PREFERRED_FEATURE_TOKENS):
                continue
        if lower in {"year", "month", "day", "week", "quarter"}:
            continue
        try:
            numeric = ensure_numeric_series(frame[column], column_name=name)
        except ValueError:
            continue
        usable = numeric.dropna()
        if len(usable) < max(5, int(0.4 * max(len(frame), 1))):
            continue
        std = float(usable.std(ddof=0) or 0.0)
        if std <= 0:
            continue
        mean_abs = float(np.nanmean(np.abs(usable.to_numpy(dtype=float))) or 1.0)
        score = std / max(mean_abs, 1e-9)
        if any(token in lower for token in _PREFERRED_FEATURE_TOKENS):
            score += 2.5
        scored.append((score, name))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def infer_numeric_features(
    frame: pd.DataFrame,
    *,
    exclude: set[str] | None = None,
    limit: int = 6,
) -> list[str]:
    """Rank numeric columns for ML across arbitrary datasets."""
    features = [name for _, name in _score_numeric_columns(frame, exclude=exclude)[:limit]]
    if not features:
        raise MlEngineError(
            "No usable numeric feature columns found for this ML task",
        )
    return features


def infer_target_column(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    preferred: str | None = None,
) -> str:
    """Pick a numeric target/metric column for forecast or anomaly focus."""
    if preferred:
        resolved = resolve_column(preferred, lookup, label="target", required=False)
        if resolved is not None:
            try:
                coerce_numeric(frame, resolved)
                return resolved
            except MlEngineError:
                pass

    ranked = _score_numeric_columns(frame)
    if ranked:
        return ranked[0][1]
    raise MlEngineError("Could not find a numeric target column in this dataset")


def detect_time_column(frame: pd.DataFrame) -> str | None:
    """Pick the best date/time column for forecasting.

    Prefers real date columns (order_date, ship_date) over bare year integers.
    Integer years like 2014 must NOT be parsed as Unix timestamps (that lands
    near 1970-01-01 and collapses Plotly charts).
    """
    scored: list[tuple[float, str]] = []
    for column in frame.columns:
        name = str(column)
        lower = name.lower()
        series = frame[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            return name

        # Strong preference for explicit date fields.
        if any(token in lower for token in ("order_date", "ship_date", "date", "timestamp")):
            parsed = _safe_parse_dates(series)
            ratio = float(parsed.notna().mean()) if len(series) else 0.0
            if ratio >= 0.6:
                scored.append((3.0 + ratio, name))
                continue

        # Bare year / month columns: keep as period labels, but rank lower.
        if lower in {"year", "yr"} or lower.endswith("_year"):
            if _looks_like_year_values(series):
                scored.append((1.5, name))
            continue
        if lower in {"month", "period"}:
            scored.append((1.0, name))
            continue

        parsed = _safe_parse_dates(series)
        ratio = float(parsed.notna().mean()) if len(series) else 0.0
        if ratio >= 0.85:
            scored.append((2.0 + ratio, name))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def parse_time_series(series: pd.Series, column_name: str | None = None) -> pd.Series:
    """Parse a column into timestamps without treating year ints as Unix time."""
    name = (column_name or getattr(series, "name", "") or "").lower()
    if _looks_like_year_values(series) or name in {"year", "yr"} or name.endswith("_year"):
        years = pd.to_numeric(series, errors="coerce")
        return pd.to_datetime(years.round().astype("Int64").astype(str), format="%Y", errors="coerce")

    if name in {"month"} and pd.api.types.is_numeric_dtype(series):
        # Month numbers alone are not a timeline; leave unusable for datetime axis.
        return pd.to_datetime(series, errors="coerce")

    return _safe_parse_dates(series)


def _safe_parse_dates(series: pd.Series) -> pd.Series:
    """Parse dates; never feed small integers to to_datetime as epoch units."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    if _looks_like_year_values(series):
        years = pd.to_numeric(series, errors="coerce")
        return pd.to_datetime(
            years.round().astype("Int64").astype(str),
            format="%Y",
            errors="coerce",
        )

    # Avoid pd.to_datetime(int) epoch interpretation for numeric codes.
    if pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        sample = numeric.dropna()
        if sample.empty:
            return pd.Series(pd.NaT, index=series.index)
        median = float(sample.median())
        if 1e9 <= median <= 4e9:  # seconds
            return pd.to_datetime(numeric, unit="s", errors="coerce")
        if 1e12 <= median <= 4e12:  # milliseconds
            return pd.to_datetime(numeric, unit="ms", errors="coerce")
        return pd.Series(pd.NaT, index=series.index)

    text = series.astype("string")
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        parsed = pd.to_datetime(text, errors="coerce", format=fmt)
        if float(parsed.notna().mean()) >= 0.8:
            return parsed
    return pd.to_datetime(text, errors="coerce", dayfirst=True, utc=False)


def _looks_like_year_values(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return False
    # Calendar years commonly used in SuperStore-style data.
    return bool(((valid >= 1900) & (valid <= 2100)).mean() >= 0.9)


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
