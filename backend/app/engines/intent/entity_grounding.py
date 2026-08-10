"""Deterministic grounding of LLM entities to real dataset columns."""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_CHART_TYPES = {
    "bar",
    "line",
    "pie",
    "scatter",
    "histogram",
    "area",
    "box",
}

# Object-dtype measure columns (e.g. sales stored as strings) still act as metrics.
_MEASURE_NAMES = {
    "sales",
    "profit",
    "quantity",
    "discount",
    "shipping_cost",
    "shippingcost",
    "revenue",
    "amount",
    "price",
    "cost",
    "income",
    "margin",
    "units",
    "qty",
}


def role_hint_from_dtype(dtype: str) -> str:
    text = (dtype or "").lower()
    if any(token in text for token in ("int", "float", "double", "decimal", "number")):
        return "numeric"
    if "bool" in text:
        return "boolean"
    if any(token in text for token in ("datetime", "date", "time")):
        return "datetime"
    return "categorical"


def is_measure_column(name: str, role_hint: str | None = None) -> bool:
    """True for numeric roles or common KPI column names (even if dtype is object)."""
    if (role_hint or "").lower() == "numeric":
        return True
    return normalize_column_name(str(name or "")) in _MEASURE_NAMES


def build_schema_columns(profile_columns: list[Any] | None) -> list[dict[str, str]]:
    """Build compact column schema for LLM context."""
    schema: list[dict[str, str]] = []
    for col in profile_columns or []:
        if hasattr(col, "name"):
            name = str(col.name)
            dtype = str(getattr(col, "dtype", "unknown"))
        elif isinstance(col, dict):
            name = str(col.get("name", "")).strip()
            dtype = str(col.get("dtype", "unknown"))
        else:
            continue
        if not name:
            continue
        role = role_hint_from_dtype(dtype)
        if role == "categorical" and is_measure_column(name, role):
            role = "numeric"
        schema.append(
            {
                "name": name,
                "dtype": dtype,
                "role_hint": role,
            }
        )
    return schema


def ground_entities(
    entities: dict[str, Any] | None,
    column_names: list[str] | None,
) -> dict[str, Any]:
    """Resolve entity column references to actual dataset column names.

    Unmatched metric/dimension/filter fields are dropped. chart_type is
    normalized against an allowlist.
    """
    entities = dict(entities or {})
    columns = [str(c) for c in (column_names or []) if str(c).strip()]
    lookup = {_normalize_name(c): c for c in columns}

    resolved: dict[str, str] = {}
    dropped: list[str] = []

    grounded = {
        "metrics": _ground_name_list(
            entities.get("metrics"),
            lookup,
            resolved,
            dropped,
        ),
        "dimensions": _ground_name_list(
            entities.get("dimensions"),
            lookup,
            resolved,
            dropped,
        ),
        "features": _ground_name_list(
            entities.get("features") or entities.get("metrics"),
            lookup,
            resolved,
            dropped,
        ),
        "chart_type": _ground_chart_type(entities.get("chart_type")),
        "filters": _ground_filters(
            entities.get("filters"),
            lookup,
            resolved,
            dropped,
        ),
        "ml_task": _ground_ml_task(entities.get("ml_task") or entities.get("task")),
        "plot_x": _match_column(str(entities["plot_x"]), lookup)
        if entities.get("plot_x") not in (None, "")
        else None,
        "plot_y": _match_column(str(entities["plot_y"]), lookup)
        if entities.get("plot_y") not in (None, "")
        else None,
        "time_column": _match_column(str(entities["time_column"]), lookup)
        if entities.get("time_column") not in (None, "")
        else None,
        "n_clusters": _ground_int(entities.get("n_clusters"), default=None, min_value=2, max_value=20),
        "horizon": _ground_int(entities.get("horizon"), default=None, min_value=1, max_value=365),
        "grounding": {
            "available_columns": columns,
            "resolved": resolved,
            "dropped": dropped,
        },
    }
    if grounded["plot_x"]:
        resolved[str(entities.get("plot_x"))] = grounded["plot_x"]
    if grounded["plot_y"]:
        resolved[str(entities.get("plot_y"))] = grounded["plot_y"]
    if grounded["time_column"]:
        resolved[str(entities.get("time_column"))] = grounded["time_column"]

    # Never group by a KPI/measure column (sales stored as object still counts).
    measure_dims = [
        name
        for name in grounded["dimensions"]
        if is_measure_column(name, "categorical")
    ]
    if measure_dims:
        for name in measure_dims:
            if name not in grounded["metrics"]:
                grounded["metrics"].append(name)
        grounded["dimensions"] = [
            name for name in grounded["dimensions"] if name not in measure_dims
        ]
        logger.info("Moved measure columns out of dimensions: %s", measure_dims)

    if dropped:
        logger.info("Dropped ungrounded entity refs: %s", dropped)
    if resolved:
        logger.debug("Grounded entity refs: %s", resolved)
    return grounded


def _ground_name_list(
    values: Any,
    lookup: dict[str, str],
    resolved: dict[str, str],
    dropped: list[str],
) -> list[str]:
    if not isinstance(values, list):
        return []
    grounded: list[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        match = _match_column(text, lookup)
        if match is None:
            dropped.append(text)
            continue
        resolved[text] = match
        if match not in grounded:
            grounded.append(match)
    return grounded


def _ground_filters(
    values: Any,
    lookup: dict[str, str],
    resolved: dict[str, str],
    dropped: list[str],
) -> list[Any]:
    if not isinstance(values, list):
        return []

    grounded: list[Any] = []
    for item in values:
        if isinstance(item, str):
            match = _match_column(item, lookup)
            if match is None:
                dropped.append(item)
            else:
                resolved[item] = match
                grounded.append(match)
            continue

        if isinstance(item, dict):
            field = item.get("field") or item.get("column") or item.get("name")
            if field is None:
                grounded.append(item)
                continue
            match = _match_column(str(field), lookup)
            if match is None:
                dropped.append(str(field))
                continue
            resolved[str(field)] = match
            cleaned = dict(item)
            if "field" in cleaned:
                cleaned["field"] = match
            elif "column" in cleaned:
                cleaned["column"] = match
            else:
                cleaned["name"] = match
            grounded.append(cleaned)
            continue

    return grounded


def _ground_chart_type(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+chart$", "", text).strip()
    text = re.sub(r"\s+plot$", "", text).strip()
    if text in ALLOWED_CHART_TYPES:
        return text
    return None


def _ground_ml_task(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"forecast", "segmentation", "anomaly"}:
        return text
    if "segment" in text or "cluster" in text:
        return "segmentation"
    if "anomal" in text or "outlier" in text:
        return "anomaly"
    if "forecast" in text or "predict" in text:
        return "forecast"
    return None


def _ground_int(
    value: Any,
    *,
    default: int | None,
    min_value: int,
    max_value: int,
) -> int | None:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < min_value or number > max_value:
        return default
    return number


def match_column(value: str, lookup: dict[str, str]) -> str | None:
    """Resolve a free-text column reference against a normalized lookup map."""
    direct = lookup.get(normalize_column_name(value))
    if direct:
        return direct

    # Soft alias: allow compact forms like "sales" matching "order_sales" only when unique.
    needle = normalize_column_name(value)
    candidates = [
        original
        for key, original in lookup.items()
        if needle and (needle == key or needle in key or key in needle)
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def normalize_column_name(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("%", " percent ")
    text = re.sub(r"[^\w]+", "_", text)
    return text.strip("_")


# Backward-compatible private aliases
_match_column = match_column
_normalize_name = normalize_column_name