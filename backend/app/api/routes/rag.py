"""RAG Engine API endpoints (Phase 8)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from app.schemas.rag import (
    RagIndexRequest,
    RagIndexResponse,
    RagQueryRequest,
    RagQueryResponse,
    RagStatusResponse,
)
from app.services.rag_service import RagService, RagServiceError, get_rag_service

router = APIRouter(prefix="/rag", tags=["rag"])
logger = get_logger(__name__)


@router.post("/index", response_model=RagIndexResponse)
def index_dataset(
    request: RagIndexRequest,
    service: RagService = Depends(get_rag_service),
) -> RagIndexResponse:
    """Build or reuse a FAISS index for an uploaded PDF dataset."""
    try:
        return service.index_dataset(request.dataset_id, force=request.force)
    except RagServiceError as exc:
        logger.warning("RAG index rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{dataset_id}/status", response_model=RagStatusResponse)
def rag_status(
    dataset_id: str,
    service: RagService = Depends(get_rag_service),
) -> RagStatusResponse:
    """Return whether a PDF dataset has an index and how many chunks."""
    try:
        return service.status(dataset_id)
    except RagServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/query", response_model=RagQueryResponse)
def rag_query(
    request: RagQueryRequest,
    service: RagService = Depends(get_rag_service),
) -> RagQueryResponse:
    """Retrieve PDF passages and generate an LLM document answer."""
    try:
        return service.query(request)
    except RagServiceError as exc:
        logger.warning("RAG query rejected: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
