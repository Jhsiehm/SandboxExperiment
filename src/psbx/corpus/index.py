"""Hybrid BM25 + vector index with cutoff enforcement and RRF fusion."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import numpy as np
from rank_bm25 import BM25Okapi

from psbx.corpus.embed import embed_texts, tokenize
from psbx.io import read_jsonl, write_json, write_jsonl
from psbx.paths import resolve
from psbx.schemas import Document, Epoch, SearchHit

RRF_K = 60
SOURCE_TYPES = ("news", "wire", "wiki", "gov", "trade", "survey", "ad", "academic")
SILO_DIRNAME = "silos"


def _canon_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = parsed.query
    rebuilt = urlunparse(("", host, path, "", query, ""))
    return rebuilt.lstrip("/")


def _as_date(value: datetime) -> date:
    return value.date()


class HybridIndex:
    def __init__(self, docs: list[Document], embeddings: np.ndarray, cutoff: date):
        if len(docs) != len(embeddings):
            raise ValueError("docs/embeddings length mismatch")
        self.docs = docs
        self.by_id = {d.id: d for d in docs}
        self.by_url = {_canon_url(d.url): d for d in docs if d.url}
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
                "query-time leakage: "
                f"{doc.id} published_at={doc.published_at.date()} > {self.cutoff}"
            )
        return doc

    def get(self, document_id: str) -> Document:
        doc = self.by_id.get(document_id)
        if doc is None:
            raise KeyError(document_id)
        return self._enforce(doc)

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        allowed = set(source_types) if source_types else None
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
            if allowed is not None and doc.source_type not in allowed:
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
                    source_type=doc.source_type,
                    authenticity=doc.authenticity,
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

    def lookup_url(self, url: str) -> Document | None:
        """Return the indexed document for a URL, or None. Never hits the live web."""
        key = _canon_url(url)
        if not key:
            return None
        doc = self.by_url.get(key)
        if doc is None:
            return None
        return self._enforce(doc)


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


def source_silo_path(epoch: Epoch, source_type: str) -> Path:
    """Generated index path for one epoch/source-type isolation cell."""
    if source_type not in SOURCE_TYPES:
        choices = ", ".join(SOURCE_TYPES)
        raise ValueError(f"unknown source type {source_type!r}; choose one of: {choices}")
    return resolve(epoch.corpus_index_path) / SILO_DIRNAME / source_type


def save_index(
    docs: list[Document],
    embeddings: np.ndarray,
    epoch: Epoch,
    *,
    destination: str | Path | None = None,
    silo_counts: dict[str, int] | None = None,
) -> Path:
    dest = resolve(destination or epoch.corpus_index_path)
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
            "source_types": sorted({str(doc.source_type) for doc in docs}),
            "authenticity_counts": dict(
                sorted(Counter(doc.authenticity for doc in docs).items())
            ),
            "research_eligible_documents": sum(1 for doc in docs if doc.research_eligible),
            "silos": dict(sorted((silo_counts or {}).items())),
        },
    )
    return dest


def save_source_silos(docs: list[Document], embeddings: np.ndarray, epoch: Epoch) -> dict[str, int]:
    """Write one immutable-at-runtime index per source type for an epoch."""
    silo_root = resolve(epoch.corpus_index_path) / SILO_DIRNAME
    if silo_root.exists():
        shutil.rmtree(silo_root)
    positions: dict[str, list[int]] = defaultdict(list)
    for index, doc in enumerate(docs):
        positions[str(doc.source_type)].append(index)
    counts: dict[str, int] = {}
    for source_type, indices in sorted(positions.items()):
        selected = [docs[index] for index in indices]
        selected_embeddings = embeddings[np.asarray(indices, dtype=np.int64)]
        save_index(
            selected,
            selected_embeddings,
            epoch,
            destination=source_silo_path(epoch, source_type),
        )
        counts[source_type] = len(selected)
    return counts


def load_index(epoch: Epoch, source_type: str | None = None) -> HybridIndex:
    dest = source_silo_path(epoch, source_type) if source_type else resolve(epoch.corpus_index_path)
    docs = read_jsonl(dest / "documents.jsonl", Document)
    embeddings = np.load(dest / "embeddings.npy")
    meta = json.loads((dest / "meta.json").read_text(encoding="utf-8"))
    if meta.get("epoch_id") != epoch.id:
        raise ValueError(f"index epoch {meta.get('epoch_id')} != requested epoch {epoch.id}")
    cutoff = date.fromisoformat(meta["cutoff_date"])
    if cutoff != epoch.cutoff_date:
        raise ValueError(f"index cutoff {cutoff} != epoch {epoch.cutoff_date}")
    for doc in docs:
        if doc.published_at.date() > cutoff:
            raise AssertionError(f"stored leakage: {doc.id}")
        if source_type and doc.source_type != source_type:
            raise AssertionError(
                f"source silo leakage: {doc.id} type={doc.source_type} != {source_type}"
            )
    return HybridIndex(docs, embeddings, cutoff)
