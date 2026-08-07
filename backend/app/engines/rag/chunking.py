"""Deterministic text chunking for document indexing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    text: str
    page_number: int | None
    char_start: int
    char_end: int


def chunk_pages(
    pages: list[tuple[int, str]],
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[TextChunk]:
    """Split page texts into overlapping character windows.

    ``pages`` is a list of ``(page_number, text)`` pairs (1-based pages).
    """
    if chunk_size < 64:
        raise ValueError("chunk_size must be >= 64")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    chunks: list[TextChunk] = []
    seq = 0
    for page_number, raw in pages:
        text = _normalize_whitespace(raw)
        if not text:
            continue
        start = 0
        length = len(text)
        while start < length:
            end = min(start + chunk_size, length)
            piece = text[start:end].strip()
            if piece:
                seq += 1
                chunks.append(
                    TextChunk(
                        chunk_id=f"p{page_number}-c{seq}",
                        text=piece,
                        page_number=page_number,
                        char_start=start,
                        char_end=end,
                    )
                )
            if end >= length:
                break
            start = max(0, end - chunk_overlap)
    return chunks


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())
