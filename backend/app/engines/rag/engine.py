"""PDF retrieval with Groq-generated answers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pypdf import PdfReader

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.rag.chunking import chunk_pages
from app.engines.rag.embeddings import HashingEmbedder
from app.engines.rag.prompts import RAG_SYSTEM_PROMPT, build_rag_user_prompt
from app.engines.rag.store import FaissChunkStore, IndexMeta

logger = get_logger(__name__)


class RagEngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RagEngine:
    """Document QA over uploaded PDFs using FAISS retrieval and Groq."""

    def __init__(self, settings: Settings | None = None, store: FaissChunkStore | None = None, embedder: HashingEmbedder | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or FaissChunkStore(self.settings.rag_path)
        self.embedder = embedder or HashingEmbedder(dim=self.settings.rag_embedding_dim)
        self._llm: ChatGroq | None = None

    def index_pdf(self, *, dataset_id: str, pdf_path: Path, source_filename: str, force: bool = False) -> dict[str, Any]:
        if self.store.exists(dataset_id) and not force:
            meta = self.store.load_meta(dataset_id)
            if meta is not None:
                return {"dataset_id": dataset_id, "indexed": meta.chunk_count > 0, "chunk_count": meta.chunk_count, "page_count": meta.page_count, "embedding_model": meta.embedding_model, "reused": True}
        pages, page_count = self._extract_pages(pdf_path)
        chunks = chunk_pages(pages, chunk_size=self.settings.rag_chunk_size, chunk_overlap=self.settings.rag_chunk_overlap)
        vectors = self.embedder.embed_texts([chunk.text for chunk in chunks])
        meta = IndexMeta(dataset_id=dataset_id, embedding_dim=self.embedder.dim, embedding_model=self.embedder.model_name, chunk_count=len(chunks), page_count=page_count, chunk_size=self.settings.rag_chunk_size, chunk_overlap=self.settings.rag_chunk_overlap, source_filename=source_filename)
        self.store.save(dataset_id, vectors, chunks, meta)
        logger.info("RAG indexed dataset_id=%s pages=%s chunks=%s", dataset_id, page_count, len(chunks))
        return {"dataset_id": dataset_id, "indexed": len(chunks) > 0, "chunk_count": len(chunks), "page_count": page_count, "embedding_model": self.embedder.model_name, "reused": False}

    def status(self, dataset_id: str) -> dict[str, Any]:
        meta = self.store.load_meta(dataset_id)
        if meta is None:
            return {"dataset_id": dataset_id, "indexed": False, "chunk_count": 0, "page_count": 0, "embedding_model": None}
        return {"dataset_id": dataset_id, "indexed": meta.chunk_count > 0, "chunk_count": meta.chunk_count, "page_count": meta.page_count, "embedding_model": meta.embedding_model, "source_filename": meta.source_filename}

    def delete_index(self, dataset_id: str) -> None:
        self.store.delete(dataset_id)

    def query(self, *, dataset_id: str, question: str, top_k: int | None = None) -> dict[str, Any]:
        cleaned = question.strip()
        if not cleaned:
            raise RagEngineError("Question is required")
        if not self.store.exists(dataset_id):
            raise RagEngineError("No RAG index for this dataset. Re-upload the PDF or POST /rag/index.", status_code=404)
        meta = self.store.load_meta(dataset_id)
        if meta is None or meta.chunk_count == 0:
            raise RagEngineError("PDF has no extractable text to search. Try a text-based PDF (not a scanned image-only document).")
        if not self.settings.groq_api_key.strip():
            raise RagEngineError("GROQ_API_KEY is required for LLM document answers", status_code=503)
        k = top_k or self.settings.rag_top_k
        hits = self.store.search(dataset_id, self.embedder.embed_query(cleaned), k)
        sources = [{"chunk_id": chunk.chunk_id, "page_number": chunk.page_number, "score": round(score, 4), "text": chunk.text} for chunk, score in hits]
        answer, provider = self._synthesize_with_llm(cleaned, sources)
        return {"dataset_id": dataset_id, "question": cleaned, "answer": answer, "sources": sources, "provider": provider, "applied": {"top_k": k, "chunk_count": meta.chunk_count, "embedding_model": meta.embedding_model, "synthesize": True}}

    def _extract_pages(self, pdf_path: Path) -> tuple[list[tuple[int, str]], int]:
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise RagEngineError("Encrypted PDFs are not supported")
            return [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)], len(reader.pages)
        except RagEngineError:
            raise
        except Exception as exc:
            raise RagEngineError(f"Failed to read PDF: {exc}") from exc

    def _synthesize_with_llm(self, question: str, sources: list[dict[str, Any]]) -> tuple[str, str]:
        try:
            response = self._get_llm().invoke([SystemMessage(content=RAG_SYSTEM_PROMPT), HumanMessage(content=build_rag_user_prompt(question, sources))])
            content = getattr(response, "content", None)
            text = " ".join(str(part) for part in content).strip() if isinstance(content, list) else str(content or "").strip()
            if not text:
                raise RagEngineError("Empty LLM response")
            return text, "groq"
        except RagEngineError:
            raise
        except Exception as exc:
            logger.exception("RAG LLM synthesis failed: %s", exc)
            raise RagEngineError("LLM document answer failed. Please try again.", status_code=503) from exc

    def _get_llm(self) -> ChatGroq:
        if self._llm is None:
            self._llm = ChatGroq(api_key=self.settings.groq_api_key, model=self.settings.groq_model, temperature=self.settings.rag_temperature)
        return self._llm
