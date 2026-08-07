"""FAISS-backed chunk store with on-disk persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.engines.rag.chunking import TextChunk
from app.utils.files import ensure_directory


@dataclass
class StoredChunk:
    chunk_id: str
    text: str
    page_number: int | None
    char_start: int
    char_end: int
    index: int


@dataclass
class IndexMeta:
    dataset_id: str
    embedding_dim: int
    embedding_model: str
    chunk_count: int
    page_count: int
    chunk_size: int
    chunk_overlap: int
    source_filename: str


class FaissChunkStore:
    """Persist FAISS index + chunk payload beside each dataset."""

    INDEX_NAME = "index.faiss"
    CHUNKS_NAME = "chunks.json"
    META_NAME = "meta.json"

    def __init__(self, root: Path) -> None:
        self.root = ensure_directory(root)

    def dataset_dir(self, dataset_id: str) -> Path:
        if not dataset_id or any(sep in dataset_id for sep in ("/", "\\", "..")):
            raise ValueError("Invalid dataset id")
        return self.root / dataset_id

    def exists(self, dataset_id: str) -> bool:
        directory = self.dataset_dir(dataset_id)
        return (directory / self.INDEX_NAME).exists() and (
            directory / self.CHUNKS_NAME
        ).exists()

    def delete(self, dataset_id: str) -> None:
        directory = self.dataset_dir(dataset_id)
        if not directory.exists():
            return
        for name in (self.INDEX_NAME, self.CHUNKS_NAME, self.META_NAME):
            path = directory / name
            if path.exists():
                path.unlink()
        try:
            directory.rmdir()
        except OSError:
            pass

    def save(
        self,
        dataset_id: str,
        vectors: np.ndarray,
        chunks: list[TextChunk],
        meta: IndexMeta,
    ) -> None:
        if vectors.ndim != 2:
            raise ValueError("vectors must be 2-D")
        if len(chunks) != vectors.shape[0]:
            raise ValueError("chunk/vector count mismatch")

        directory = ensure_directory(self.dataset_dir(dataset_id))
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        if len(chunks):
            matrix = np.ascontiguousarray(vectors.astype(np.float32))
            index.add(matrix)

        faiss.write_index(index, str(directory / self.INDEX_NAME))
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "index": i,
            }
            for i, chunk in enumerate(chunks)
        ]
        (directory / self.CHUNKS_NAME).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        (directory / self.META_NAME).write_text(
            json.dumps(asdict(meta), indent=2),
            encoding="utf-8",
        )

    def load_meta(self, dataset_id: str) -> IndexMeta | None:
        path = self.dataset_dir(dataset_id) / self.META_NAME
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return IndexMeta(**raw)

    def search(
        self,
        dataset_id: str,
        query_vector: np.ndarray,
        top_k: int,
    ) -> list[tuple[StoredChunk, float]]:
        directory = self.dataset_dir(dataset_id)
        index_path = directory / self.INDEX_NAME
        chunks_path = directory / self.CHUNKS_NAME
        if not index_path.exists() or not chunks_path.exists():
            raise FileNotFoundError(f"No RAG index for dataset {dataset_id}")

        index = faiss.read_index(str(index_path))
        raw_chunks: list[dict[str, Any]] = json.loads(
            chunks_path.read_text(encoding="utf-8")
        )
        if index.ntotal == 0 or not raw_chunks:
            return []

        vector = np.ascontiguousarray(query_vector.reshape(1, -1).astype(np.float32))
        k = min(max(top_k, 1), index.ntotal)
        scores, indices = index.search(vector, k)

        results: list[tuple[StoredChunk, float]] = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx < 0 or idx >= len(raw_chunks):
                continue
            item = raw_chunks[idx]
            chunk = StoredChunk(
                chunk_id=item["chunk_id"],
                text=item["text"],
                page_number=item.get("page_number"),
                char_start=item.get("char_start", 0),
                char_end=item.get("char_end", 0),
                index=int(item.get("index", idx)),
            )
            results.append((chunk, float(score)))
        return results
