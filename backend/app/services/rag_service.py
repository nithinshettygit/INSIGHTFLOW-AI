"""RAG application service (Phase 8)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.engines.rag import RagEngine, RagEngineError
from app.schemas.rag import (
    RagIndexResponse,
    RagQueryRequest,
    RagQueryResponse,
    RagSource,
    RagStatusResponse,
)
from app.services.dataset_service import DatasetService, DatasetServiceError, get_dataset_service

logger = get_logger(__name__)


class RagServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RagService:
    """Index PDF datasets and answer document questions."""

    def __init__(
        self,
        dataset_service: DatasetService | None = None,
        engine: RagEngine | None = None,
    ) -> None:
        self.dataset_service = dataset_service or get_dataset_service()
        self.engine = engine or RagEngine()

    def index_dataset(self, dataset_id: str, *, force: bool = False) -> RagIndexResponse:
        try:
            meta = self.dataset_service.get_dataset(dataset_id)
        except DatasetServiceError as exc:
            raise RagServiceError(exc.message, status_code=exc.status_code) from exc

        if meta.dataset_type != "pdf":
            raise RagServiceError(
                "RAG indexing requires a PDF dataset",
                status_code=400,
            )

        try:
            pdf_path = self.dataset_service.get_dataset_path(dataset_id)
            result = self.engine.index_pdf(
                dataset_id=dataset_id,
                pdf_path=pdf_path,
                source_filename=meta.original_filename,
                force=force,
            )
        except RagEngineError as exc:
            raise RagServiceError(exc.message, status_code=exc.status_code) from exc

        self._stamp_dataset_meta(
            dataset_id,
            indexed=bool(result["indexed"]),
            chunk_count=int(result["chunk_count"]),
            page_count=int(result["page_count"]),
        )
        message = (
            "RAG index reused"
            if result.get("reused")
            else (
                "RAG index built"
                if result["indexed"]
                else "PDF indexed but no extractable text found"
            )
        )
        logger.info(
            "RAG index dataset_id=%s chunks=%s reused=%s",
            dataset_id,
            result["chunk_count"],
            result.get("reused"),
        )
        return RagIndexResponse(
            dataset_id=result["dataset_id"],
            indexed=bool(result["indexed"]),
            chunk_count=int(result["chunk_count"]),
            page_count=int(result["page_count"]),
            embedding_model=result.get("embedding_model"),
            reused=bool(result.get("reused")),
            message=message,
        )

    def status(self, dataset_id: str) -> RagStatusResponse:
        try:
            self.dataset_service.get_dataset(dataset_id)
        except DatasetServiceError as exc:
            raise RagServiceError(exc.message, status_code=exc.status_code) from exc
        payload = self.engine.status(dataset_id)
        return RagStatusResponse(**payload)

    def query(self, request: RagQueryRequest) -> RagQueryResponse:
        try:
            meta = self.dataset_service.get_dataset(request.dataset_id)
        except DatasetServiceError as exc:
            raise RagServiceError(exc.message, status_code=exc.status_code) from exc

        if meta.dataset_type != "pdf":
            raise RagServiceError(
                "Document QA requires a PDF dataset",
                status_code=400,
            )

        if not self.engine.store.exists(request.dataset_id):
            # Auto-index on first query for older uploads created before Phase 8.
            self.index_dataset(request.dataset_id, force=False)

        try:
            payload = self.engine.query(
                dataset_id=request.dataset_id,
                question=request.question,
                top_k=request.top_k,
            )
        except RagEngineError as exc:
            raise RagServiceError(exc.message, status_code=exc.status_code) from exc

        return RagQueryResponse(
            dataset_id=payload["dataset_id"],
            question=payload["question"],
            answer=payload["answer"],
            sources=[RagSource(**item) for item in payload["sources"]],
            provider=payload["provider"],
            applied=payload["applied"],
        )

    def delete_index(self, dataset_id: str) -> None:
        self.engine.delete_index(dataset_id)

    def _stamp_dataset_meta(
        self,
        dataset_id: str,
        *,
        indexed: bool,
        chunk_count: int,
        page_count: int,
    ) -> None:
        """Best-effort update of dataset meta.extra with RAG status."""
        try:
            meta = self.dataset_service.get_dataset(dataset_id)
            meta.extra = {
                **(meta.extra or {}),
                "rag_indexed": indexed,
                "rag_chunk_count": chunk_count,
                "rag_page_count": page_count,
            }
            meta_path = (
                self.dataset_service._dataset_dir(dataset_id)  # noqa: SLF001
                / "meta.json"
            )
            self.dataset_service._write_meta(meta_path, meta)  # noqa: SLF001
        except Exception as exc:  # pragma: no cover - non-critical
            logger.warning("Could not stamp RAG meta for %s: %s", dataset_id, exc)


def get_rag_service() -> RagService:
    return RagService()
