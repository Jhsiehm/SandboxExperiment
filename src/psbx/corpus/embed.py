"""Deterministic hashing embeddings; optional sentence-transformers backend."""

from __future__ import annotations

import hashlib
import re

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
DEFAULT_DIM = 256


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def hash_embed(text: str, dim: int = DEFAULT_DIM) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for tok in tokenize(text):
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "little")
        vec[h % dim] += 1.0
        vec[(h >> 8) % dim] -= 0.5
    n = float(np.linalg.norm(vec))
    if n > 0:
        vec /= n
    return vec


def st_embed(texts: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    return np.asarray(model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def embed_texts(texts: list[str], backend: str = "hashing") -> np.ndarray:
    if backend == "sentence-transformers":
        try:
            return st_embed(texts)
        except Exception:
            backend = "hashing"
    return np.vstack([hash_embed(t) for t in texts])
