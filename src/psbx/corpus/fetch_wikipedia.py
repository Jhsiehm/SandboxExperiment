"""Wikipedia ingest. Phase 1 uses dated fixture pages; ZIM/XML dump is the live path."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from psbx.corpus.normalize import document_id_for
from psbx.paths import resolve
from psbx.schemas import Document, Epoch

UTC = timezone.utc

# Original summaries of articles as they stood in mid-2012 — not current wiki text.
WIKI_PAGES = [
    {
        "title": "United States fiscal cliff",
        "url": "https://en.wikipedia.org/wiki/United_States_fiscal_cliff",
        "published_at": "2012-06-15T00:00:00+00:00",
        "text": (
            "As of June 2012 the phrase fiscal cliff describes the scheduled expiration of "
            "the 2001 and 2003 tax cuts and the onset of Budget Control Act sequestration "
            "in January 2013. No enacted compromise exists. Whether Congress delays "
            "sequestration or extends all tax rates remains an open legislative question."
        ),
    },
    {
        "title": "Syrian civil war",
        "url": "https://en.wikipedia.org/wiki/Syrian_civil_war",
        "published_at": "2012-06-20T00:00:00+00:00",
        "text": (
            "By mid-2012 the uprising against Bashar al-Assad had become an armed conflict. "
            "Kofi Annan's six-point plan had not produced a lasting ceasefire. The UN "
            "Security Council remained divided. Assad continued to hold office in Damascus."
        ),
    },
    {
        "title": "European debt crisis",
        "url": "https://en.wikipedia.org/wiki/European_debt_crisis",
        "published_at": "2012-06-18T00:00:00+00:00",
        "text": (
            "Greece held a repeat parliamentary election on 17 June 2012. A euro-area exit "
            "was widely discussed but had not occurred. Spain sought bank aid. The ECB had "
            "not yet announced Outright Monetary Transactions."
        ),
    },
]


def wiki_cache_dir() -> Path:
    return resolve("data/corpus-cache/wikipedia")


def ingest_wikipedia(epoch: Epoch, live: bool = False) -> list[Document]:
    """Dated fixture pages plus optional Kiwix/JSONL dump under corpus-cache."""
    del live
    docs = _fixture_pages(epoch)
    cache = wiki_cache_dir()
    if not cache.exists():
        return docs
    for path in sorted(cache.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                published = datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            if published.date() > epoch.cutoff_date:
                continue
            text = (row.get("text") or "").strip()
            if len(text) < 80:
                continue
            docs.append(
                Document(
                    id=document_id_for(text),
                    url=row.get("url") or "https://en.wikipedia.org/",
                    outlet="Wikipedia",
                    published_at=published,
                    title=row.get("title") or text[:80],
                    text=text[:20000],
                    source_type="wiki",
                    prominence=0.0,
                    syndication_count=1,
                    provenance=(
                        "Local Wikipedia cache row; authenticity not independently verified."
                    ),
                )
            )
    return docs


def _fixture_pages(epoch: Epoch) -> list[Document]:
    docs: list[Document] = []
    for page in WIKI_PAGES:
        published = datetime.fromisoformat(page["published_at"])
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        if published.date() > epoch.cutoff_date:
            continue
        text = page["text"]
        docs.append(
            Document(
                id=document_id_for(text),
                url=page["url"],
                outlet="Wikipedia",
                published_at=published,
                title=page["title"],
                text=text,
                source_type="wiki",
                prominence=0.0,
                syndication_count=1,
                provenance="Original reconstruction for offline practice.",
                authenticity="reconstructed_fixture",
                timestamp_basis="fixture_as_of",
            )
        )
    return docs
