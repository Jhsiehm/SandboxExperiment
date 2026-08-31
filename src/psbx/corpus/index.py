"""Hybrid BM25 + vector index with cutoff enforcement and RRF fusion."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from psbx.corpus.embed import embed_texts, tokenize
from psbx.io import read_jsonl, write_json, write_jsonl
from psbx.paths import resolve
from psbx.schemas import Document, Epoch, SearchHit

RRF_K = 60


def _as_date(value: datetime) -> date:
    return value.date()


class HybridIndex:
    def __init__(self, docs: list[Document], embeddings: np.ndarray, cutoff: date):
        if len(docs) != len(embeddings):
            raise ValueError("docs/embeddings length mismatch")
        self.docs = docs
        self.by_id = {d.id: d for d in docs}
        self.embeddings = embeddings
        self.cutoff = cutoff
        self._tokens = [tokenize(f"{d.title} {d.text}") for d in docs]
        self._bm25 = BM25Okapi(self._tokens)
        self._assert_cutoff(docs, cutoff)

    @staticmethod
    def _assert_cutoff(docs: list[Document], cutoff: date | None = None) -> None:
        for doc in docs:
            limit = cutoff
            if limit is None:
                continue
            if _as_date(doc.published_at) > limit:
                raise AssertionError(
                    f"future leakage: {doc.id} published_at={doc.published_at.date()} > {limit}"
                )

    def _enforce(self, doc: Document) -> Document:
        if _as_date(doc.published_at) > self.cutoff:
            raise AssertionError(
                f"query-time leakage: {doc.id} published_at={doc.published_at.date()} > {self.cutoff}"
            )
        return doc

    def get(self, document_id: str) -> Document:
        doc = self.by_id.get(document_id)
        if doc is None:
            raise KeyError(document_id)
        return self._enforce(doc)

    def search(self, query: str, k: int = 10, min_prominence: float = 0.0) -> list[SearchHit]:
        bm25_scores = self._bm25.get_scores(tokenize(query))
        bm25_order = list(np.argsort(bm25_scores)[::-1])
        qvec = embed_texts([query], backend="hashing")[0]
        sims = self.embeddings @ qvec
        vec_order = list(np.argsort(sims)[::-1])
        fused = _rrf([bm25_order, vec_order])
        hits: list[SearchHit] = []
        for idx in fused:
            doc = self.docs[idx]
            if doc.prominence < min_prominence:
                continue
            self._enforce(doc)
            snippet = _snippet(doc.text, query)
            hits.append(
                SearchHit(
                    document_id=doc.id,
                    title=doc.title,
                    outlet=doc.outlet,
                    published_at=doc.published_at,
                    snippet=snippet,
                    prominence=doc.prominence,
                )
            )
            if len(hits) >= k:
                break
        return hits

    def public_document(self, document_id: str) -> dict:
        doc = self.get(document_id)
        payload = doc.model_dump(mode="json")
        payload.pop("embedding", None)
        return payload


def _rrf(rank_lists: list[list[int]], k: int = RRF_K) -> list[int]:
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return [idx for idx, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


def _snippet(text: str, query: str, width: int = 240) -> str:
    tokens = [t for t in tokenize(query) if len(t) > 2]
    lower = text.lower()
    pos = 0
    for tok in tokens:
        found = lower.find(tok)
        if found >= 0:
            pos = found
            break
    start = max(0, pos - 40)
    end = min(len(text), start + width)
    return text[start:end].strip()


def save_index(docs: list[Document], embeddings: np.ndarray, epoch: Epoch) -> Path:
    dest = resolve(epoch.corpus_index_path)
    dest.mkdir(parents=True, exist_ok=True)
    slim = [d.model_copy(update={"embedding": None}) for d in docs]
    write_jsonl(dest / "documents.jsonl", slim)
    np.save(dest / "embeddings.npy", embeddings)
    write_json(
        dest / "meta.json",
        {
            "epoch_id": epoch.id,
            "cutoff_date": epoch.cutoff_date.isoformat(),
            "n_docs": len(docs),
            "embedding_dim": int(embeddings.shape[1]) if len(embeddings) else 0,
        },
    )
    return dest


def load_index(epoch: Epoch) -> HybridIndex:
    dest = resolve(epoch.corpus_index_path)
    docs = read_jsonl(dest / "documents.jsonl", Document)
    embeddings = np.load(dest / "embeddings.npy")
    meta = json.loads((dest / "meta.json").read_text(encoding="utf-8"))
    cutoff = date.fromisoformat(meta["cutoff_date"])
    if cutoff != epoch.cutoff_date:
        raise ValueError(f"index cutoff {cutoff} != epoch {epoch.cutoff_date}")
    for doc in docs:
        if doc.published_at.date() > cutoff:
            raise AssertionError(f"stored leakage: {doc.id}")
    return HybridIndex(docs, embeddings, cutoff)
