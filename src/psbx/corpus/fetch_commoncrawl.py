"""Ingest local Common Crawl / pywb WARCs into the Document index.

Do not use this as the agent search UI. Drop CC-MAIN-2012-* (or pywb) WARCs
under data/corpus-cache/commoncrawl/ and they join the hybrid index at build.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from psbx.config import load_sources
from psbx.corpus.normalize import document_id_for, html_to_text, normalize_text
from psbx.paths import resolve
from psbx.schemas import Document, Epoch

UTC = timezone.utc


def warc_dir() -> Path:
    return resolve("data/corpus-cache/commoncrawl")


def _outlet_for_url(url: str, outlets: list[dict]) -> dict | None:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    for outlet in outlets:
        domain = outlet["domain"].lower().removeprefix("www.")
        if host == domain or host.endswith("." + domain):
            return outlet
    return None


def _warc_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = list(root.rglob("*.warc.gz")) + list(root.rglob("*.warc"))
    return sorted(p for p in files if p.is_file())


def ingest_commoncrawl(epoch: Epoch, live: bool = False) -> list[Document]:
    """Read local WARCs. `live` is ignored — no CC index crawl from this process."""
    del live
    paths = _warc_paths(warc_dir())
    if not paths:
        return []
    outlets = load_sources()["outlets"]
    docs: list[Document] = []
    try:
        from warcio.archiveiterator import ArchiveIterator
    except ImportError:
        return []
    for path in paths:
        with path.open("rb") as fh:
            for record in ArchiveIterator(fh):
                if record.rec_type != "response":
                    continue
                url = record.rec_headers.get_header("WARC-Target-URI") or ""
                outlet = _outlet_for_url(url, outlets)
                if outlet is None:
                    continue
                stamp = record.rec_headers.get_header("WARC-Date") or ""
                try:
                    published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                if published.date() > epoch.cutoff_date:
                    continue
                payload = record.content_stream().read()
                try:
                    html = payload.decode("utf-8", errors="replace")
                except Exception:
                    continue
                text = normalize_text(html_to_text(html))
                if len(text) < 200:
                    continue
                docs.append(
                    Document(
                        id=document_id_for(text),
                        url=url,
                        outlet=outlet["name"],
                        published_at=published,
                        title=text[:120],
                        text=text[:20000],
                        source_type=outlet.get("source_type") or "news",
                        prominence=0.0,
                    )
                )
    return docs
