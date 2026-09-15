"""CDX enumeration + snapshot pull. Build-time Internet Archive access only.

Agent search stays on the local hybrid index. This module is opted-in via
`psbx corpus build --live` and must identify itself per archive.org bot rules.

e2012 web ingest is Wayback with `to=` the epoch cutoff (2012-06-30). Do not
use the CC-MAIN-2012 HTML dump or CC-MAIN-2013-20 (May–June 2013 captures).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlencode

from psbx.config import load_sources
from psbx.corpus.ia_http import Pace, ia_client, ia_get
from psbx.corpus.normalize import document_id_for, html_to_text, normalize_text
from psbx.paths import resolve
from psbx.schemas import Document, Epoch

UTC = timezone.utc
DEFAULT_MAX_DOCS = 400
CDX_FIELDS = "timestamp,original,digest,statuscode,mimetype,length"
_SKIP_URL_BITS = (
    "/search?",
    "/login",
    "/subscribe",
    "/cdn-cgi",
    "/wp-admin",
    "/interactive/embed",
)


def _cutoff_ts(cutoff) -> str:
    return cutoff.strftime("%Y%m%d")


def cache_dir() -> Path:
    d = resolve("data/corpus-cache/wayback")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_cdx(payload) -> list[dict]:
    if not payload or not isinstance(payload, list) or len(payload) < 2:
        return []
    keys = payload[0]
    if not isinstance(keys, list):
        return []
    rows: list[dict] = []
    for item in payload[1:]:
        if isinstance(item, list):
            rows.append(dict(zip(keys, item)))
    return rows


def _cdx_query(cdx_api: str, params: list[tuple[str, str]], client, pace: Pace) -> list[dict]:
    try:
        resp = ia_get(client, f"{cdx_api}?{urlencode(params)}", pace=pace)
        return _parse_cdx(resp.json())
    except Exception:
        return []


def enumerate_cdx(
    domain: str,
    cutoff,
    paths: list[str],
    cdx_api: str,
    client,
    pace: Pace,
    *,
    path_limit: int = 25,
    domain_limit: int = 80,
) -> list[dict]:
    """Enumerate captures with to=cutoff, status 200, collapse=digest.

    Section paths plus one domain-wide query so `--live` can grow past a
    handful of homepages without an unbounded crawl.
    """
    rows: list[dict] = []
    to_ts = _cutoff_ts(cutoff)
    seen: set[str] = set()

    def _keep(row: dict) -> None:
        original = (row.get("original") or "").strip()
        mime = (row.get("mimetype") or "").lower()
        if not original or original in seen:
            return
        if mime and "html" not in mime and mime != "warc/revisit":
            return
        lowered = original.lower()
        if any(bit in lowered for bit in _SKIP_URL_BITS):
            return
        seen.add(original)
        rows.append(row)

    domain_params = [
        ("url", f"{domain}/*"),
        ("matchType", "domain"),
        ("to", to_ts),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "digest"),
        ("output", "json"),
        ("fl", CDX_FIELDS),
        ("limit", str(domain_limit)),
    ]
    for row in _cdx_query(cdx_api, domain_params, client, pace):
        _keep(row)

    if len(rows) >= domain_limit:
        return rows

    for path in paths:
        url = f"https://{domain}{path}"
        path_params = [
            ("url", url),
            ("to", to_ts),
            ("filter", "statuscode:200"),
            ("collapse", "digest"),
            ("output", "json"),
            ("fl", CDX_FIELDS),
            ("limit", str(path_limit)),
        ]
        for row in _cdx_query(cdx_api, path_params, client, pace):
            _keep(row)
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


def _wayback_reachable(client, cdx_api: str) -> bool:
    """One short CDX probe so a down web.archive.org does not stall `--live`."""
    query = urlencode(
        {"url": "example.com", "to": "20120630", "output": "json", "limit": "1"}
    )
    probe = f"{cdx_api}?{query}"
    try:
        resp = client.get(probe, timeout=12.0)
        return resp.status_code < 500
    except Exception:
        return False


def ingest_wayback(
    epoch: Epoch, live: bool = False, max_docs: int = DEFAULT_MAX_DOCS
) -> list[Document]:
    """Pull Wayback snapshots. Off by default; fixtures cover Phase 1.

    Bounded: hundreds of docs, not an unbounded crawl. Re-running `--live`
    reuses cached snapshots under data/corpus-cache/wayback/.
    """
    if not live:
        return []
    src = load_sources()
    cutoff = epoch.cutoff_date
    delay = float(src["wayback"].get("rate_limit_seconds", 5.0))
    pace = Pace(delay)
    docs: list[Document] = []
    seen_ids: set[str] = set()
    outlets = list(src["outlets"])
    per_outlet = max(8, min(25, max_docs // max(len(outlets), 1)))
    manifest_path = cache_dir() / f"{epoch.id}_cdx.jsonl"
    with ia_client() as client:
        if not _wayback_reachable(client, src["wayback"]["cdx_api"]):
            print(
                "wayback CDX unreachable (web.archive.org timed out); "
                "skipping live snapshots. Resume with: "
                "psbx corpus build --epoch e2012 --live --max-docs 400",
                flush=True,
            )
            return []
        for outlet in outlets:
            if len(docs) >= max_docs:
                break
            captures = enumerate_cdx(
                outlet["domain"],
                cutoff,
                src["wayback"]["paths"],
                src["wayback"]["cdx_api"],
                client,
                pace,
                path_limit=20,
                domain_limit=max(40, per_outlet * 3),
            )
            with manifest_path.open("a", encoding="utf-8") as mf:
                for cap in captures:
                    mf.write(json.dumps({"outlet": outlet["name"], **cap}) + "\n")
            taken = 0
            for cap in captures:
                if len(docs) >= max_docs or taken >= per_outlet:
                    break
                ts = cap.get("timestamp") or ""
                original = cap.get("original") or ""
                if not ts or not original:
                    continue
                try:
                    published = datetime.strptime(ts[:8], "%Y%m%d").replace(tzinfo=UTC)
                except ValueError:
                    continue
                if published.date() > cutoff:
                    continue
                slug = (cap.get("digest") or sha1(original.encode("utf-8")).hexdigest())[:12]
                raw_path = cache_dir() / outlet["domain"] / f"{ts}_{slug}.html"
                html = fetch_snapshot(original, ts, client, raw_path, pace)
                if not html:
                    continue
                text = normalize_text(html_to_text(html))
                if len(text) < 200:
                    continue
                doc_id = document_id_for(text)
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                docs.append(
                    Document(
                        id=doc_id,
                        url=original,
                        outlet=outlet["name"],
                        published_at=published,
                        title=text[:120],
                        text=text[:20000],
                        source_type=outlet["source_type"],
                        prominence=0.0,
                    )
                )
                taken += 1
    return docs
