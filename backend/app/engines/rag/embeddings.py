"""Local hashed n-gram embeddings (no model download required).

Produces fixed-dimension L2-normalized vectors suitable for FAISS
inner-product search. Deterministic and offline — fits Phase 8 RAG
without pulling sentence-transformer weights.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class HashingEmbedder:
    """Character/token n-gram hashing embedder."""

    def __init__(self, dim: int = 384, ngram_min: int = 3, ngram_max: int = 5) -> None:
        if dim < 32:
            raise ValueError("embedding dim must be >= 32")
        self.dim = dim
        self.ngram_min = ngram_min
        self.ngram_max = ngram_max
        self.model_name = f"hashing-ngram-{dim}"

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        matrix = np.vstack([self._embed_one(text) for text in texts])
        return matrix.astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed_one(text).astype(np.float32)

    def _embed_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float64)
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            # Still produce a tiny signal from raw characters so empty-ish
            # strings do not all collapse to identical zeros after normalize.
            tokens = list(text.lower()[:64]) or ["_"]

        for token in tokens:
            self._accumulate(vector, f"t:{token}")
            if len(token) >= self.ngram_min:
                upper = min(self.ngram_max, len(token))
                for n in range(self.ngram_min, upper + 1):
                    for i in range(0, len(token) - n + 1):
                        self._accumulate(vector, f"n:{token[i : i + n]}")

        for i in range(len(tokens) - 1):
            self._accumulate(vector, f"b:{tokens[i]}_{tokens[i + 1]}")

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector.astype(np.float32)

    def _accumulate(self, vector: np.ndarray, feature: str) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % self.dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
