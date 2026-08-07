"""Automatic dataset profiling service (Phase 3).

Deterministic Pandas-based profiling for tabular uploads.
PDF profiles capture document metadata only (RAG arrives in Phase 8).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pypdf import PdfReader

from app.core.logging import get_logger
from app.schemas.dataset import DatasetMeta, DatasetType
from app.schemas.profile import ColumnProfile, DatasetProfile
from app.utils.csv_io import CsvReadError, read_csv_with_encoding

logger = get_logger(__name__)

SAMPLE_ROWS = 5
TOP_CATEGORIES = 5


class ProfilingServiceError(Exception):
    """Domain error for profiling operations."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProfilingService:
    """Build and return structured dataset profiles."""

    def profile_file(
        self,
        *,
        dataset_id: str,
        dataset_type: DatasetType,
        file_path: Path,
        original_filename: str,
        encoding: str | None = None,
    ) -> DatasetProfile:
        if not file_path.exists():
            raise ProfilingServiceError("Dataset file not found", status_code=404)

        if dataset_type in {"csv", "excel"}:
            return self._profile_tabular(
                dataset_id=dataset_id,
                dataset_type=dataset_type,
                file_path=file_path,
                original_filename=original_filename,
                encoding=encoding,
            )
        if dataset_type == "pdf":
            return self._profile_pdf(
                dataset_id=dataset_id,
                file_path=file_path,
                original_filename=original_filename,
            )
        raise ProfilingServiceError(f"Unsupported dataset type '{dataset_type}'")

    def profile_dataset(self, meta: DatasetMeta, file_path: Path) -> DatasetProfile:
        encoding = None
        if isinstance(meta.extra, dict):
            encoding = meta.extra.get("encoding")
        return self.profile_file(
            dataset_id=meta.dataset_id,
            dataset_type=meta.dataset_type,
            file_path=file_path,
            original_filename=meta.original_filename,
            encoding=encoding if isinstance(encoding, str) else None,
        )

    def _profile_tabular(
        self,
        *,
        dataset_id: str,
        dataset_type: DatasetType,
        file_path: Path,
        original_filename: str,
        encoding: str | None = None,
    ) -> DatasetProfile:
        frame, used_encoding = self._load_tabular(
            file_path,
            dataset_type,
            encoding=encoding,
        )
        row_count, column_count = int(frame.shape[0]), int(frame.shape[1])
        duplicate_rows = int(frame.duplicated().sum())
        missing_total = int(frame.isna().sum().sum())

        columns: list[ColumnProfile] = []
        numeric_summary: dict[str, dict[str, Any]] = {}
        categorical_summary: dict[str, dict[str, Any]] = {}

        for name in frame.columns:
            series = frame[name]
            col_name = str(name)
            null_count = int(series.isna().sum())
            non_null = int(series.notna().sum())
            unique_count = int(series.nunique(dropna=True))
            null_pct = round((null_count / row_count) * 100, 2) if row_count else 0.0

            stats: dict[str, Any] = {}
            if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(
                series
            ):
                desc = series.describe()
                stats = {
                    "count": _json_safe(desc.get("count")),
                    "mean": _json_safe(desc.get("mean")),
                    "std": _json_safe(desc.get("std")),
                    "min": _json_safe(desc.get("min")),
                    "25%": _json_safe(desc.get("25%")),
                    "50%": _json_safe(desc.get("50%")),
                    "75%": _json_safe(desc.get("75%")),
                    "max": _json_safe(desc.get("max")),
                }
                numeric_summary[col_name] = stats
            else:
                value_counts = series.astype("string").value_counts(dropna=True).head(
                    TOP_CATEGORIES
                )
                top_values = [
                    {"value": _json_safe(idx), "count": int(count)}
                    for idx, count in value_counts.items()
                ]
                stats = {
                    "unique": unique_count,
                    "top_values": top_values,
                }
                categorical_summary[col_name] = stats

            columns.append(
                ColumnProfile(
                    name=col_name,
                    dtype=str(series.dtype),
                    non_null_count=non_null,
                    null_count=null_count,
                    null_percentage=null_pct,
                    unique_count=unique_count,
                    stats=stats,
                )
            )

        sample = [
            {str(k): _json_safe(v) for k, v in row.items()}
            for row in frame.head(SAMPLE_ROWS).to_dict(orient="records")
        ]

        profile = DatasetProfile(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            profiled_at=datetime.now(timezone.utc),
            row_count=row_count,
            column_count=column_count,
            duplicate_rows=duplicate_rows,
            missing_values_total=missing_total,
            columns=columns,
            numeric_summary=numeric_summary,
            categorical_summary=categorical_summary,
            sample_rows=sample,
            metadata={
                "original_filename": original_filename,
                "memory_usage_bytes": int(frame.memory_usage(deep=True).sum()),
                "column_names": [str(c) for c in frame.columns.tolist()],
                "encoding": used_encoding,
            },
        )
        logger.info(
            "Profiled tabular dataset_id=%s rows=%s cols=%s duplicates=%s missing=%s",
            dataset_id,
            row_count,
            column_count,
            duplicate_rows,
            missing_total,
        )
        return profile

    def _profile_pdf(
        self,
        *,
        dataset_id: str,
        file_path: Path,
        original_filename: str,
    ) -> DatasetProfile:
        try:
            reader = PdfReader(str(file_path))
            if reader.is_encrypted:
                raise ProfilingServiceError("Encrypted PDFs are not supported")
            page_count = len(reader.pages)
            text_sample = ""
            if page_count:
                text_sample = (reader.pages[0].extract_text() or "")[:500]
        except ProfilingServiceError:
            raise
        except Exception as exc:
            raise ProfilingServiceError(f"Failed to profile PDF: {exc}") from exc

        profile = DatasetProfile(
            dataset_id=dataset_id,
            dataset_type="pdf",
            profiled_at=datetime.now(timezone.utc),
            row_count=None,
            column_count=None,
            duplicate_rows=None,
            missing_values_total=None,
            columns=[],
            metadata={
                "original_filename": original_filename,
                "page_count": page_count,
                "text_sample": text_sample,
                "note": "PDF document profile. Use POST /rag/query for document QA.",
            },
        )
        logger.info(
            "Profiled PDF dataset_id=%s pages=%s",
            dataset_id,
            page_count,
        )
        return profile

    def _load_tabular(
        self,
        path: Path,
        dataset_type: DatasetType,
        *,
        encoding: str | None = None,
    ) -> tuple[pd.DataFrame, str | None]:
        try:
            if dataset_type == "csv":
                frame, used_encoding = read_csv_with_encoding(path, encoding=encoding)
            else:
                frame = pd.read_excel(path, engine="openpyxl")
                used_encoding = None
        except CsvReadError as exc:
            raise ProfilingServiceError(str(exc)) from exc
        except Exception as exc:
            raise ProfilingServiceError(
                f"Failed to load {dataset_type} for profiling: {exc}"
            ) from exc

        if frame.empty and frame.shape[1] == 0:
            raise ProfilingServiceError("Dataset has no columns to profile")
        return frame, used_encoding


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-serializable Python types."""
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
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def get_profiling_service() -> ProfilingService:
    return ProfilingService()
