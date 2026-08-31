"""CDX enumeration + snapshot pull. Build-time Internet Archive access only.

Agent search stays on the local hybrid index. This module is opted-in via
`psbx corpus build --live` and must identify itself per archive.org bot rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from psbx.config import load_sources
from psbx.corpus.ia_http import Pace, ia_client, ia_get
from psbx.corpus.normalize import document_id_for, html_to_text, normalize_text
from psbx.paths import resolve
from psbx.schemas import Document, Epoch

UTC = timezone.utc


def _cutoff_ts(cutoff) -> str:
    return cutoff.strftime("%Y%m%d")


def cache_dir() -> Path:
    d = resolve("data/corpus-cache/wayback")
    d.mkdir(parents=True, exist_ok=True)
    return d


def enumerate_cdx(
    domain: str,
    cutoff,
    paths: list[str],
    cdx_api: str,
    client,
    pace: Pace,
) -> list[dict]:
    """Enumerate captures with to=cutoff, status 200, collapse=digest."""
    rows: list[dict] = []
    to_ts = _cutoff_ts(cutoff)
    for path in paths:
        url = f"https://{domain}{path}"
        params = {
            "url": url,
            "to": to_ts,
            "filter": "statuscode:200",
            "collapse": "digest",
            "output": "json",
            "fl": "timestamp,original,digest,statuscode,mimetype,length",
            "limit": 50,
        }
        resp = ia_get(client, f"{cdx_api}?{urlencode(params)}", pace=pace)
        payload = resp.json()
        if not payload:
            continue
        keys = payload[0]
        for item in payload[1:]:
            rows.append(dict(zip(keys, item)))
    return rows


def fetch_snapshot(original: str, timestamp: str, client, dest: Path, pace: Pace) -> str | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest.read_text(encoding="utf-8", errors="replace")
    ia_url = f"https://web.archive.org/web/{timestamp}id_/{original}"
    try:
        resp = ia_get(client, ia_url, pace=pace)
    except Exception:
        return None
    dest.write_bytes(resp.content)
    return resp.text


def ingest_wayback(epoch: Epoch, live: bool = False, max_docs: int = 40) -> list[Document]:
    """Pull Wayback snapshots. Off by default; fixtures cover Phase 1."""
    if not live:
        return []
    src = load_sources()
    cutoff = epoch.cutoff_date
    delay = float(src["wayback"].get("rate_limit_seconds", 5.0))
    pace = Pace(delay)
    docs: list[Document] = []
    manifest_path = cache_dir() / f"{epoch.id}_cdx.jsonl"
    with ia_client() as client:
        for outlet in src["outlets"]:
            if len(docs) >= max_docs:
                break
            captures = enumerate_cdx(
                outlet["domain"],
                cutoff,
                src["wayback"]["paths"],
                src["wayback"]["cdx_api"],
                client,
                pace,
            )
            with manifest_path.open("a", encoding="utf-8") as mf:
                for cap in captures:
                    mf.write(json.dumps({"outlet": outlet["name"], **cap}) + "\n")
            for cap in captures[:3]:
                ts = cap.get("timestamp") or ""
                original = cap.get("original") or ""
                if not ts or not original:
                    continue
                raw_path = cache_dir() / outlet["domain"] / f"{ts}.html"
                html = fetch_snapshot(original, ts, client, raw_path, pace)
                if not html:
                    continue
                text = normalize_text(html_to_text(html))
                if len(text) < 200:
                    continue
                published = datetime.strptime(ts[:8], "%Y%m%d").replace(tzinfo=UTC)
                if published.date() > cutoff:
                    continue
                docs.append(
                    Document(
                        id=document_id_for(text),
                        url=original,
                        outlet=outlet["name"],
                        published_at=published,
                        title=text[:120],
                        text=text[:20000],
                        source_type=outlet["source_type"],
                        prominence=0.0,
                    )
                )
                if len(docs) >= max_docs:
                    break
    return docs
