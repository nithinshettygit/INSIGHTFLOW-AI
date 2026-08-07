"""Dataset upload and registry service.

Phase 2: accept CSV / Excel / PDF files, validate format, persist artifacts.
Phase 3: automatically profile uploads and expose stored profile reports.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from pypdf import PdfReader

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.dataset import DatasetMeta
from app.schemas.profile import DatasetProfile
from app.services.profiling_service import (
    ProfilingService,
    ProfilingServiceError,
    get_profiling_service,
)
from app.utils.csv_io import CsvReadError, read_csv_with_encoding
from app.utils.files import detect_dataset_type, ensure_directory, sanitize_filename

logger = get_logger(__name__)

META_FILENAME = "meta.json"
PROFILE_FILENAME = "profile.json"


class DatasetServiceError(Exception):
    """Domain error for dataset operations."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DatasetService:
    """Handle upload storage, metadata registry, and profile access."""

    def __init__(
        self,
        settings: Settings | None = None,
        profiling_service: ProfilingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.upload_root = ensure_directory(self.settings.upload_path)
        self.profiling_service = profiling_service or get_profiling_service()

    def list_datasets(self) -> list[DatasetMeta]:
        datasets: list[DatasetMeta] = []
        if not self.upload_root.exists():
            return datasets

        for path in sorted(self.upload_root.iterdir()):
            meta_path = path / META_FILENAME
            if path.is_dir() and meta_path.exists():
                try:
                    datasets.append(self._read_meta(meta_path))
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    logger.warning("Skipping corrupt dataset at %s: %s", path, exc)
        return datasets

    def get_dataset(self, dataset_id: str) -> DatasetMeta:
        meta_path = self._dataset_dir(dataset_id) / META_FILENAME
        if not meta_path.exists():
            raise DatasetServiceError("Dataset not found", status_code=404)
        return self._read_meta(meta_path)

    def get_dataset_path(self, dataset_id: str) -> Path:
        meta = self.get_dataset(dataset_id)
        path = self._dataset_dir(dataset_id) / meta.stored_filename
        if not path.exists():
            raise DatasetServiceError("Dataset file not found", status_code=404)
        return path

    def load_dataframe(self, dataset_id: str) -> tuple[pd.DataFrame, DatasetMeta]:
        """Load a tabular dataset into a DataFrame (CSV/Excel only)."""
        meta = self.get_dataset(dataset_id)
        if meta.dataset_type == "pdf":
            raise DatasetServiceError(
                "Analytics requires a CSV or Excel dataset",
                status_code=400,
            )
        path = self.get_dataset_path(dataset_id)
        encoding = None
        if isinstance(meta.extra, dict):
            raw_encoding = meta.extra.get("encoding")
            encoding = raw_encoding if isinstance(raw_encoding, str) else None
        try:
            if meta.dataset_type == "csv":
                frame, _ = read_csv_with_encoding(path, encoding=encoding)
            else:
                frame = pd.read_excel(path, engine="openpyxl")
        except CsvReadError as exc:
            raise DatasetServiceError(str(exc)) from exc
        except Exception as exc:
            raise DatasetServiceError(f"Failed to load dataset: {exc}") from exc
        return frame, meta

    async def upload(self, file: UploadFile) -> DatasetMeta:
        if not file.filename:
            raise DatasetServiceError("Filename is required")

        try:
            safe_name = sanitize_filename(file.filename)
            dataset_type = detect_dataset_type(safe_name)
        except ValueError as exc:
            raise DatasetServiceError(str(exc)) from exc

        dataset_id = uuid.uuid4().hex
        dataset_dir = ensure_directory(self._dataset_dir(dataset_id))
        stored_path = dataset_dir / safe_name

        try:
            size_bytes = await self._write_upload(file, stored_path)
            if size_bytes == 0:
                raise DatasetServiceError("Uploaded file is empty")

            max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
            if size_bytes > max_bytes:
                raise DatasetServiceError(
                    f"File exceeds max size of {self.settings.max_upload_size_mb} MB"
                )

            extra = self._validate_stored_file(stored_path, dataset_type)
        except Exception:
            self._cleanup_dir(dataset_dir)
            raise

        meta = DatasetMeta(
            dataset_id=dataset_id,
            original_filename=safe_name,
            stored_filename=safe_name,
            dataset_type=dataset_type,  # type: ignore[arg-type]
            content_type=file.content_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(timezone.utc),
            extra=extra,
        )

        try:
            profile = self.profiling_service.profile_dataset(meta, stored_path)
            self._write_profile(dataset_dir / PROFILE_FILENAME, profile)
            meta.extra = {
                **meta.extra,
                "profiled": True,
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "duplicate_rows": profile.duplicate_rows,
                "missing_values_total": profile.missing_values_total,
            }
        except ProfilingServiceError as exc:
            self._cleanup_dir(dataset_dir)
            raise DatasetServiceError(exc.message, status_code=exc.status_code) from exc

        self._write_meta(dataset_dir / META_FILENAME, meta)
        self._persist_processed_summary(meta, profile)
        logger.info(
            "Uploaded dataset_id=%s type=%s size=%s name=%s",
            dataset_id,
            dataset_type,
            size_bytes,
            safe_name,
        )
        return meta

    def has_profile(self, dataset_id: str) -> bool:
        return (self._dataset_dir(dataset_id) / PROFILE_FILENAME).exists()

    def get_profile(self, dataset_id: str) -> DatasetProfile:
        """Return cached profile, generating it if missing."""
        self.get_dataset(dataset_id)
        profile_path = self._dataset_dir(dataset_id) / PROFILE_FILENAME
        if profile_path.exists():
            return self._read_profile(profile_path)
        return self.refresh_profile(dataset_id)

    def refresh_profile(self, dataset_id: str) -> DatasetProfile:
        """Recompute and persist a dataset profile."""
        meta = self.get_dataset(dataset_id)
        file_path = self._dataset_dir(dataset_id) / meta.stored_filename
        try:
            profile = self.profiling_service.profile_dataset(meta, file_path)
        except ProfilingServiceError as exc:
            raise DatasetServiceError(exc.message, status_code=exc.status_code) from exc

        dataset_dir = self._dataset_dir(dataset_id)
        self._write_profile(dataset_dir / PROFILE_FILENAME, profile)
        meta.extra = {
            **meta.extra,
            "profiled": True,
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "duplicate_rows": profile.duplicate_rows,
            "missing_values_total": profile.missing_values_total,
        }
        self._write_meta(dataset_dir / META_FILENAME, meta)
        self._persist_processed_summary(meta, profile)
        return profile

    def delete_dataset(self, dataset_id: str) -> None:
        dataset_dir = self._dataset_dir(dataset_id)
        if not dataset_dir.exists():
            raise DatasetServiceError("Dataset not found", status_code=404)
        self._cleanup_dir(dataset_dir)
        processed = self.settings.processed_path / f"{dataset_id}.profile.json"
        if processed.exists():
            processed.unlink(missing_ok=True)
        logger.info("Deleted dataset_id=%s", dataset_id)

    def _dataset_dir(self, dataset_id: str) -> Path:
        # Prevent path traversal via crafted IDs.
        if not dataset_id or any(sep in dataset_id for sep in ("/", "\\", "..")):
            raise DatasetServiceError("Invalid dataset id", status_code=400)
        return self.upload_root / dataset_id

    async def _write_upload(self, file: UploadFile, destination: Path) -> int:
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        size = 0
        try:
            with destination.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise DatasetServiceError(
                            f"File exceeds max size of "
                            f"{self.settings.max_upload_size_mb} MB"
                        )
                    out.write(chunk)
        finally:
            await file.close()
        return size

    def _validate_stored_file(self, path: Path, dataset_type: str) -> dict:
        """Light format validation only — not full profiling."""
        if dataset_type == "csv":
            return self._validate_csv(path)
        if dataset_type == "excel":
            return self._validate_excel(path)
        if dataset_type == "pdf":
            return self._validate_pdf(path)
        raise DatasetServiceError(f"Unsupported dataset type '{dataset_type}'")

    def _validate_csv(self, path: Path) -> dict:
        try:
            frame, encoding = read_csv_with_encoding(path, nrows=5)
        except CsvReadError as exc:
            raise DatasetServiceError(str(exc)) from exc
        if frame.shape[1] == 0:
            raise DatasetServiceError("CSV has no columns")
        return {
            "preview_rows": int(len(frame)),
            "preview_columns": [str(col) for col in frame.columns.tolist()],
            "encoding": encoding,
        }

    def _validate_excel(self, path: Path) -> dict:
        try:
            frame = pd.read_excel(path, nrows=5, engine="openpyxl")
        except Exception as exc:
            raise DatasetServiceError(f"Invalid Excel file: {exc}") from exc
        if frame.shape[1] == 0:
            raise DatasetServiceError("Excel sheet has no columns")
        return {
            "preview_rows": int(len(frame)),
            "preview_columns": [str(col) for col in frame.columns.tolist()],
        }

    def _validate_pdf(self, path: Path) -> dict:
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise DatasetServiceError("Encrypted PDFs are not supported")
            page_count = len(reader.pages)
        except DatasetServiceError:
            raise
        except Exception as exc:
            raise DatasetServiceError(f"Invalid PDF file: {exc}") from exc
        if page_count == 0:
            raise DatasetServiceError("PDF has no pages")
        return {"page_count": page_count}

    def _write_meta(self, path: Path, meta: DatasetMeta) -> None:
        path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    def _read_meta(self, path: Path) -> DatasetMeta:
        return DatasetMeta.model_validate_json(path.read_text(encoding="utf-8"))

    def _write_profile(self, path: Path, profile: DatasetProfile) -> None:
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def _read_profile(self, path: Path) -> DatasetProfile:
        return DatasetProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def _persist_processed_summary(
        self,
        meta: DatasetMeta,
        profile: DatasetProfile,
    ) -> None:
        """Store a compact profile summary under processed/ for later engines."""
        processed_root = ensure_directory(self.settings.processed_path)
        target = processed_root / f"{meta.dataset_id}.profile.json"
        summary = {
            "dataset_id": meta.dataset_id,
            "dataset_type": meta.dataset_type,
            "original_filename": meta.original_filename,
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "duplicate_rows": profile.duplicate_rows,
            "missing_values_total": profile.missing_values_total,
            "profiled_at": profile.profiled_at.isoformat(),
            "column_names": profile.metadata.get("column_names", []),
        }
        target.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _cleanup_dir(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def get_dataset_service() -> DatasetService:
    return DatasetService()
