"""Build compact evidence packs for the Insight Engine (no raw row dumps)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.intent.entity_grounding import match_column, normalize_column_name
from app.schemas.profile import DatasetProfile
from app.utils.dataframe import ensure_numeric_series

logger = get_logger(__name__)


def infer_insight_mode(question: str) -> str:
    text = (question or "").lower()
    if any(
        token in text
        for token in (
            "root cause",
            "why did",
            "why is",
            "why are",
            "what caused",
            "driver of",
            "drivers of",
        )
    ):
        return "root_cause"
    if any(
        token in text
        for token in (
            "recommend",
            "recommendation",
            "suggest",
            "suggestion",
            "what should",
            "next step",
            "action",
            "how can we improve",
        )
    ):
        return "recommendation"
    return "explanation"


def build_evidence_pack(
    *,
    meta: Any,
    profile: DatasetProfile | None,
    frame: pd.DataFrame | None,
    focus_metrics: list[str],
    focus_dimensions: list[str],
    include_ml_context: bool,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    pack: dict[str, Any] = {
        "dataset": {
            "dataset_id": getattr(meta, "dataset_id", None),
            "filename": getattr(meta, "original_filename", None),
            "dataset_type": getattr(meta, "dataset_type", None),
        },
        "profile": _profile_summary(profile),
        "kpis": {},
        "segment_contrasts": [],
        "ml_context": [],
        "notes": [],
    }

    if frame is None or frame.empty:
        pack["notes"].append("No tabular frame available for KPI/segment evidence.")
        if include_ml_context:
            pack["ml_context"] = _load_ml_summaries(
                getattr(meta, "dataset_id", ""),
                settings.model_path,
            )
        return pack

    lookup = {
        normalize_column_name(str(c)): str(c) for c in frame.columns.tolist()
    }
    metrics = _resolve_names(focus_metrics, lookup) or _auto_metrics(frame, lookup)
    dimensions = _resolve_names(focus_dimensions, lookup) or _auto_dimensions(
        frame,
        lookup,
        exclude=set(metrics),
    )

    working = frame.copy()
    usable_metrics: list[str] = []
    for metric in metrics[:4]:
        try:
            working[metric] = ensure_numeric_series(working[metric], column_name=metric)
            usable_metrics.append(metric)
        except ValueError:
            continue

    kpis: dict[str, Any] = {}
    for metric in usable_metrics:
        series = working[metric].dropna()
        if series.empty:
            continue
        kpis[metric] = {
            "sum": _num(series.sum()),
            "mean": _num(series.mean()),
            "min": _num(series.min()),
            "max": _num(series.max()),
            "std": _num(series.std()),
            "non_null": int(series.shape[0]),
        }
    pack["kpis"] = kpis
    pack["focus"] = {"metrics": usable_metrics, "dimensions": dimensions[:3]}

    contrasts: list[dict[str, Any]] = []
    for dim in dimensions[:2]:
        for metric in usable_metrics[:2]:
            contrast = _segment_contrast(working, dim, metric)
            if contrast:
                contrasts.append(contrast)
    pack["segment_contrasts"] = contrasts[:6]

    if include_ml_context:
        pack["ml_context"] = _load_ml_summaries(
            getattr(meta, "dataset_id", ""),
            settings.model_path,
        )

    if not kpis:
        pack["notes"].append("No numeric metrics could be summarized.")
    if not contrasts:
        pack["notes"].append("No segment contrasts available.")
    return pack


def _profile_summary(profile: DatasetProfile | None) -> dict[str, Any]:
    if profile is None:
        return {}
    high_null = [
        {
            "name": col.name,
            "null_percentage": col.null_percentage,
            "dtype": col.dtype,
        }
        for col in profile.columns
        if col.null_percentage >= 10
    ][:8]
    numeric_highlights = {
        name: {
            k: stats.get(k)
            for k in ("mean", "min", "max", "std", "sum")
            if k in stats
        }
        for name, stats in list((profile.numeric_summary or {}).items())[:6]
        for stats in [stats or {}]
    }
    categorical_highlights = {}
    for name, summary in list((profile.categorical_summary or {}).items())[:4]:
        top = summary.get("top_values") or summary.get("top") or []
        categorical_highlights[name] = top[:5] if isinstance(top, list) else top

    return {
        "row_count": profile.row_count,
        "column_count": profile.column_count,
        "duplicate_rows": profile.duplicate_rows,
        "missing_values_total": profile.missing_values_total,
        "high_null_columns": high_null,
        "numeric_highlights": numeric_highlights,
        "categorical_highlights": categorical_highlights,
        "metadata_note": (profile.metadata or {}).get("note"),
        "page_count": (profile.metadata or {}).get("page_count"),
    }


def _segment_contrast(
    frame: pd.DataFrame,
    dimension: str,
    metric: str,
) -> dict[str, Any] | None:
    try:
        grouped = (
            frame.groupby(dimension, dropna=False)[metric]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .sort_values("sum", ascending=False)
        )
    except Exception:
        return None
    if grouped.empty or len(grouped) < 2:
        return None

    top = grouped.iloc[0]
    bottom = grouped.iloc[-1]
    total = float(grouped["sum"].sum()) or 1.0
    return {
        "dimension": dimension,
        "metric": metric,
        "top_segment": {
            "value": _safe(top[dimension]),
            "sum": _num(top["sum"]),
            "mean": _num(top["mean"]),
            "count": int(top["count"]),
            "share": round(float(top["sum"]) / total, 4),
        },
        "bottom_segment": {
            "value": _safe(bottom[dimension]),
            "sum": _num(bottom["sum"]),
            "mean": _num(bottom["mean"]),
            "count": int(bottom["count"]),
            "share": round(float(bottom["sum"]) / total, 4),
        },
        "segment_count": int(len(grouped)),
    }


def _auto_metrics(frame: pd.DataFrame, lookup: dict[str, str]) -> list[str]:
    preferred = ("sales", "revenue", "profit", "quantity", "amount", "orders")
    found: list[str] = []
    for name in preferred:
        resolved = _resolve_names([name], lookup)
        if resolved:
            found.extend(resolved)
    if found:
        return list(dict.fromkeys(found))[:4]

    for column in frame.columns:
        try:
            ensure_numeric_series(frame[column], column_name=str(column))
            found.append(str(column))
        except ValueError:
            continue
        if len(found) >= 3:
            break
    return found


def _auto_dimensions(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    exclude: set[str],
) -> list[str]:
    preferred = (
        "region",
        "category",
        "sub-category",
        "subcategory",
        "segment",
        "product",
        "city",
        "state",
        "customer",
    )
    found: list[str] = []
    for name in preferred:
        resolved = _resolve_names([name], lookup)
        for col in resolved:
            if col not in exclude:
                found.append(col)
    if found:
        return list(dict.fromkeys(found))[:3]

    for column in frame.columns:
        col = str(column)
        if col in exclude:
            continue
        series = frame[column]
        unique = int(series.nunique(dropna=True))
        if 2 <= unique <= min(50, max(2, int(len(frame) * 0.5))):
            if not pd.api.types.is_numeric_dtype(series):
                found.append(col)
        if len(found) >= 2:
            break
    return found


def _resolve_names(names: list[str], lookup: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for name in names:
        if not name:
            continue
        key = normalize_column_name(str(name))
        if key in lookup:
            resolved.append(lookup[key])
            continue
        matched = match_column(str(name), lookup)
        if matched:
            resolved.append(matched)
    return list(dict.fromkeys(resolved))


def _load_ml_summaries(dataset_id: str, model_root: Path) -> list[dict[str, Any]]:
    if not dataset_id:
        return []
    directory = model_root / dataset_id
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*_last.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items.append(
                {
                    "task": payload.get("task"),
                    "model": payload.get("model"),
                    "summary": payload.get("summary"),
                    "saved_at": payload.get("saved_at"),
                }
            )
        except Exception as exc:
            logger.debug("Skip ML summary %s: %s", path, exc)
    return items[:3]


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return round(number, 4)


def _safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value if isinstance(value, (str, int, float, bool)) else str(value)
