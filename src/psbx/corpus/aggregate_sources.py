"""Survey / ad / academic fixtures → cutoff-locked Documents.

These are aggregated sources of truth for the demographic swarm (Track B).
Headlines remain the media stimulus (Track A). No live 2026 scrape. Post-cutoff
Gallup MIP points are eval targets only and must not enter the index.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from psbx.corpus.normalize import document_id_for
from psbx.io import read_json
from psbx.paths import resolve
from psbx.schemas import CONDITIONER_SOURCE_TYPES, Document, Epoch

UTC = timezone.utc
SURVEYS = "data/sources/surveys_e2012.json"
ADS = "data/sources/ads_e2012.json"
ACADEMIC = "data/sources/academic_e2012.json"
GALLUP_MIP = "data/sources/gallup_mip_2012.json"


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        published = value
    else:
        published = datetime.fromisoformat(value)
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return published


def _month_end(month: str) -> datetime:
    year, mon = (int(p) for p in month.split("-"))
    if mon == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, mon + 1, 1)
    last = date.fromordinal(nxt.toordinal() - 1)
    return datetime(last.year, last.month, last.day, 12, 0, 0, tzinfo=UTC)


def _record_to_document(raw: dict[str, Any]) -> Document:
    text = str(raw["text"]).strip()
    source_type = raw["source_type"]
    if source_type not in CONDITIONER_SOURCE_TYPES:
        raise ValueError(f"expected conditioner source_type, got {source_type}")
    return Document(
        id=document_id_for(text),
        url=raw["url"],
        outlet=raw["outlet"],
        published_at=_dt(raw["published_at"]),
        title=raw["title"],
        text=text,
        source_type=source_type,
        prominence=0.0,
        syndication_count=int(raw.get("syndication_count") or 1),
        gdelt_mention_count=int(raw.get("gdelt_mention_count") or 0),
        front_page_minutes=float(raw.get("front_page_minutes") or 0.0),
        provenance=str(raw.get("provenance") or "") or None,
        authenticity="reconstructed_fixture",
        timestamp_basis="fixture_as_of",
    )


def load_fixture_records(path: str | Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise ValueError(f"expected records list in {path}")
    return rows


def gallup_mip_documents(cutoff: date, path: str | Path = GALLUP_MIP) -> list[Document]:
    """Pre-cutoff MIP months only. Later months stay in the JSON for eval targets."""
    payload = read_json(path)
    docs: list[Document] = []
    for point in payload.get("points") or []:
        month = str(point["month"])
        published = _month_end(month)
        if published.date() > cutoff:
            continue
        econ = float(point.get("economy_plus_unemployment") or 0.0)
        deficit = float(point.get("deficit") or 0.0)
        health = float(point.get("healthcare") or 0.0)
        war = float(point.get("war_terrorism") or 0.0)
        imm = float(point.get("immigration") or 0.0)
        text = (
            f"Gallup Most Important Problem public summary for {month}: "
            f"economy-plus-unemployment share {econ:.2f}, deficit {deficit:.2f}, "
            f"healthcare {health:.2f}, war/terrorism {war:.2f}, immigration {imm:.2f}. "
            "Attributed aggregate from Gallup historical MIP series public summaries. "
            "Not a claim about any identifiable person."
        )
        docs.append(
            Document(
                id=document_id_for(text),
                url=f"https://news.gallup.com/poll/mip-{month}",
                outlet="Gallup",
                published_at=published,
                title=f"Gallup Most Important Problem, {month} (public summary)",
                text=text,
                source_type="survey",
                prominence=0.0,
                syndication_count=20,
                gdelt_mention_count=10,
                front_page_minutes=40,
                provenance=str(payload.get("source") or "Gallup historical MIP series"),
                authenticity="reconstructed_fixture",
                timestamp_basis="fixture_as_of",
            )
        )
    return docs


def ingest_aggregate_sources(
    epoch: Epoch,
    *,
    surveys: str | Path = SURVEYS,
    ads: str | Path = ADS,
    academic: str | Path = ACADEMIC,
    gallup: str | Path = GALLUP_MIP,
) -> list[Document]:
    """Load fixtures and drop anything with published_at > cutoff."""
    docs: list[Document] = []
    for path in (surveys, ads, academic):
        resolved = resolve(path)
        if not resolved.exists():
            continue
        for raw in load_fixture_records(resolved):
            docs.append(_record_to_document(raw))
    docs.extend(gallup_mip_documents(epoch.cutoff_date, gallup))
    kept: list[Document] = []
    seen: set[str] = set()
    for doc in docs:
        if doc.published_at.date() > epoch.cutoff_date:
            continue
        if doc.id in seen:
            continue
        seen.add(doc.id)
        kept.append(doc)
    return kept
