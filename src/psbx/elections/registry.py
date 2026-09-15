"""Election-source registry and nationwide coverage planning."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from .schemas import ElectionSource


def load_election_sources(
    path: str | Path = "config/election_sources.yaml",
) -> dict[str, ElectionSource]:
    source_path = Path(path)
    payload = (
        json.loads(source_path.read_text(encoding="utf-8"))
        if source_path.suffix.lower() == ".json"
        else yaml.safe_load(source_path.read_text(encoding="utf-8"))
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("election source registry requires a 'sources' list")
    sources = [ElectionSource.model_validate(row) for row in payload["sources"]]
    by_id = {source.id: source for source in sources}
    if len(by_id) != len(sources):
        raise ValueError("election source IDs must be unique")
    return by_id


def source_applies(source: ElectionSource, year: int) -> bool:
    return (source.year_start is None or source.year_start <= year) and (
        source.year_end is None or year <= source.year_end
    )


def federal_coverage_plan(
    *,
    start_year: int = 1982,
    through_year: int = 2026,
    as_of: date | None = None,
    registry_path: str | Path = "config/election_sources.yaml",
) -> dict:
    """Report source availability without claiming that documents are normalized data."""
    if not 1788 <= start_year <= through_year <= 2200:
        raise ValueError("invalid year range")
    as_of = as_of or date.today()
    sources = load_election_sources(registry_path)
    federal = [source for source in sources.values() if source.scope == "federal"]
    rows = []
    for year in range(start_year, through_year + 1):
        if year % 2:
            rows.append(
                {
                    "year": year,
                    "status": "not_scheduled_federal_cycle",
                    "source_ids": [],
                    "normalized": False,
                    "note": "Regular federal general elections occur in even-numbered years.",
                }
            )
            continue
        election_day = federal_general_election_day(year)
        applicable = [source for source in federal if source_applies(source, year)]
        if election_day > as_of:
            status = "future_pending"
            note = (
                f"General election is scheduled for {election_day.isoformat()}; "
                "results do not exist yet."
            )
        elif not applicable:
            status = "source_gap"
            note = "No authoritative source is registered for this year."
        elif any(source.normalized for source in applicable):
            status = "normalized_source_registered"
            note = "At least one registered source supplies normalized records."
        else:
            status = "official_documents_available"
            note = (
                "Official source documents are available but still require normalization "
                "and validation."
            )
        rows.append(
            {
                "year": year,
                "election_day": election_day.isoformat(),
                "status": status,
                "source_ids": [source.id for source in applicable],
                "normalized": any(source.normalized for source in applicable),
                "note": note,
            }
        )
    return {
        "as_of": as_of.isoformat(),
        "start_year": start_year,
        "through_year": through_year,
        "cycles": rows,
        "summary": {
            "official_document_cycles": sum(
                row["status"] == "official_documents_available" for row in rows
            ),
            "normalized_cycles": sum(
                row["status"] == "normalized_source_registered" for row in rows
            ),
            "future_cycles": sum(row["status"] == "future_pending" for row in rows),
            "source_gaps": sum(row["status"] == "source_gap" for row in rows),
        },
    }


def federal_general_election_day(year: int) -> date:
    """First Tuesday after the first Monday in November."""
    first = date(year, 11, 1)
    days_to_monday = (7 - first.weekday()) % 7
    first_monday = first.fromordinal(first.toordinal() + days_to_monday)
    return first_monday.fromordinal(first_monday.toordinal() + 1)
