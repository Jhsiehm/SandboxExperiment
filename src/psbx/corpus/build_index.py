"""Build a cutoff-enforced hybrid index from fixtures plus optional live ingest."""

from __future__ import annotations

from datetime import timezone

from psbx.corpus.aggregate_sources import ingest_aggregate_sources
from psbx.corpus.embed import embed_texts
from psbx.corpus.fetch_commoncrawl import ingest_commoncrawl
from psbx.corpus.fetch_gdelt import ingest_gdelt
from psbx.corpus.fetch_wayback import DEFAULT_MAX_DOCS, ingest_wayback
from psbx.corpus.fetch_wikipedia import ingest_wikipedia
from psbx.corpus.index import HybridIndex, save_index
from psbx.corpus.prominence import apply_prominence
from psbx.corpus.seed_documents import seed_documents
from psbx.schemas import Document, Epoch


def collect_documents(
    epoch: Epoch, live: bool = False, max_docs: int = DEFAULT_MAX_DOCS
) -> list[Document]:
    docs = [
        *seed_documents(),
        *ingest_aggregate_sources(epoch),
        *ingest_wikipedia(epoch, live=live),
        *ingest_commoncrawl(epoch, live=live),
        *ingest_wayback(epoch, live=live, max_docs=max_docs),
        *ingest_gdelt(epoch, live=live),
    ]
    seen: set[str] = set()
    kept: list[Document] = []
    for doc in docs:
        published = doc.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
            doc = doc.model_copy(update={"published_at": published})
        if doc.published_at.date() > epoch.cutoff_date:
            continue
        if doc.id in seen:
            continue
        seen.add(doc.id)
        kept.append(doc)
    if not kept:
        raise RuntimeError("no documents survived cutoff filter")
    return apply_prominence(kept)


def build_index(
    epoch: Epoch,
    live: bool = False,
    backend: str = "hashing",
    max_docs: int = DEFAULT_MAX_DOCS,
) -> HybridIndex:
    docs = collect_documents(epoch, live=live, max_docs=max_docs)
    texts = [f"{d.title}\n{d.text}" for d in docs]
    embeddings = embed_texts(texts, backend=backend)
    for doc in docs:
        assert doc.published_at.date() <= epoch.cutoff_date, doc.id
    save_index(docs, embeddings, epoch)
    return HybridIndex(docs, embeddings, epoch.cutoff_date)
