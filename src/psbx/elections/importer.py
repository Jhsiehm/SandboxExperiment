"""Validation-first import of normalized aggregate election returns."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from .schemas import ElectionImportManifest, ElectionResultRow

REQUIRED_COLUMNS = tuple(ElectionResultRow.model_fields)
_DATASET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True, dtype=False)
    raise ValueError("normalized election input must be .csv, .jsonl, or .ndjson")


def _none_if_blank(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return None if text == "" else text


def _parse_bool(value, *, nullable: bool) -> bool | None:
    normalized = _none_if_blank(value)
    if normalized is None and nullable:
        return None
    lowered = str(normalized).casefold()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value {value!r}")


def _coerce_row(payload: dict) -> dict:
    optional = {
        "source_record_id",
        "state_fips",
        "state_postal",
        "district",
        "county_fips",
        "county_name",
        "municipality_name",
        "precinct",
        "candidate_id",
        "party",
        "total_votes_reported",
        "winner",
    }
    row = {key: _none_if_blank(payload.get(key)) for key in REQUIRED_COLUMNS}
    for key in optional:
        row[key] = _none_if_blank(payload.get(key))
    row["votes"] = int(str(row["votes"]).replace(",", ""))
    if row["total_votes_reported"] is not None:
        row["total_votes_reported"] = int(
            str(row["total_votes_reported"]).replace(",", "")
        )
    row["winner"] = _parse_bool(payload.get("winner"), nullable=True)
    row["certified"] = _parse_bool(payload.get("certified"), nullable=False)
    row["election_year"] = int(row["election_year"])
    return row


def validate_election_frame(
    frame: pd.DataFrame,
    *,
    cutoff_date: date,
    allow_uncertified: bool = False,
) -> tuple[list[ElectionResultRow], list[str]]:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    # Nullable fields still need a named column so source adapters are explicit.
    if missing:
        raise ValueError("normalized election input is missing columns: " + ", ".join(missing))
    records: list[ElectionResultRow] = []
    errors: list[str] = []
    for index, raw in frame.iterrows():
        try:
            record = ElectionResultRow.model_validate(_coerce_row(raw.to_dict()))
            if record.source_release_date > cutoff_date:
                raise ValueError(
                    f"source release {record.source_release_date} is after cutoff {cutoff_date}"
                )
            if not allow_uncertified and not record.certified:
                raise ValueError("uncertified result blocked; pass allow_uncertified explicitly")
            records.append(record)
        except (TypeError, ValueError, ValidationError) as exc:
            errors.append(f"row {index + 2}: {exc}")
    if errors:
        sample = "; ".join(errors[:10])
        suffix = f"; plus {len(errors) - 10} more" if len(errors) > 10 else ""
        raise ValueError(f"election import validation failed: {sample}{suffix}")

    duplicate_keys = [
        (
            row.source_id,
            row.contest_id,
            row.geography_id,
            row.candidate_id or row.candidate_name.casefold(),
        )
        for row in records
    ]
    if len(set(duplicate_keys)) != len(duplicate_keys):
        raise ValueError("duplicate candidate/result rows detected within a contest geography")

    warnings = []
    if allow_uncertified and any(not row.certified for row in records):
        warnings.append(
            "Dataset contains uncertified rows and must not be treated as final results."
        )
    return records, warnings


def _coverage(records: list[ElectionResultRow]) -> dict[str, dict]:
    coverage: dict[str, dict] = {}
    for record in records:
        key = record.state_postal or record.state_fips or "US"
        row = coverage.setdefault(
            key,
            {
                "rows": 0,
                "contests": set(),
                "years": set(),
                "geography_levels": set(),
                "office_levels": set(),
                "geography_ids": {},
            },
        )
        row["rows"] += 1
        row["contests"].add(record.contest_id)
        row["years"].add(record.election_year)
        row["geography_levels"].add(record.geography_level)
        row["office_levels"].add(record.office_level)
        row["geography_ids"].setdefault(record.geography_level, set()).add(
            record.geography_id
        )
    serializable = {}
    for state, row in sorted(coverage.items()):
        serializable[state] = {
            "rows": row["rows"],
            "contests": len(row["contests"]),
            "years": sorted(row["years"]),
            "geography_levels": sorted(row["geography_levels"]),
            "office_levels": sorted(row["office_levels"]),
            "geography_ids": {
                level: sorted(ids) for level, ids in sorted(row["geography_ids"].items())
            },
        }
    return serializable


def import_election_results(
    input_path: str | Path,
    *,
    dataset_id: str,
    label: str,
    cutoff_date: date,
    output_root: str | Path = "data/elections/normalized",
    allow_uncertified: bool = False,
    force: bool = False,
) -> ElectionImportManifest:
    """Validate and persist a canonical CSV plus checksum-bound manifest."""
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return import_election_frame(
        _read_rows(source),
        input_sha256=_sha256(source),
        dataset_id=dataset_id,
        label=label,
        cutoff_date=cutoff_date,
        output_root=output_root,
        allow_uncertified=allow_uncertified,
        force=force,
    )


def import_election_frame(
    frame: pd.DataFrame,
    *,
    input_sha256: str,
    dataset_id: str,
    label: str,
    cutoff_date: date,
    output_root: str | Path = "data/elections/normalized",
    allow_uncertified: bool = False,
    force: bool = False,
    additional_warnings: list[str] | None = None,
) -> ElectionImportManifest:
    """Validate an adapter frame and bind its output to the original source checksum."""
    if not _DATASET_ID.fullmatch(dataset_id):
        raise ValueError("dataset_id contains unsafe characters")
    normalized_sha = str(input_sha256).strip().casefold()
    if len(normalized_sha) != 64 or any(ch not in "0123456789abcdef" for ch in normalized_sha):
        raise ValueError("input_sha256 must be a 64-character hexadecimal digest")
    records, warnings = validate_election_frame(
        frame, cutoff_date=cutoff_date, allow_uncertified=allow_uncertified
    )
    warnings.extend(additional_warnings or [])
    if not records:
        raise ValueError("election input contains no result rows")
    destination = Path(output_root) / dataset_id
    if destination.exists() and any(destination.iterdir()) and not force:
        raise FileExistsError(f"dataset already exists: {destination}; pass force=True to replace")
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "results.csv"
    temporary = destination / "results.csv.tmp"
    normalized = pd.DataFrame(
        [row.model_dump(mode="json") for row in records], columns=REQUIRED_COLUMNS
    )
    normalized.to_csv(temporary, index=False)
    os.replace(temporary, output)
    coverage = _coverage(records)
    manifest = ElectionImportManifest(
        dataset_id=dataset_id,
        label=label.strip() or dataset_id,
        created_at=datetime.now(timezone.utc),
        cutoff_date=cutoff_date,
        input_sha256=normalized_sha,
        output_sha256=_sha256(output),
        rows=len(records),
        contests=len({row.contest_id for row in records}),
        certified_rows=sum(row.certified for row in records),
        source_ids=sorted({row.source_id for row in records}),
        years=sorted({row.election_year for row in records}),
        stages=sorted({row.stage for row in records}),
        office_levels=sorted({row.office_level for row in records}),
        geography_levels=sorted({row.geography_level for row in records}),
        states=sorted(coverage),
        coverage_by_state=coverage,
        normalized_output="results.csv",
        warnings=warnings,
    )
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def filter_election_results(
    frame: pd.DataFrame,
    *,
    years: set[int] | None = None,
    source_ids: set[str] | None = None,
    states: set[str] | None = None,
    geography_levels: set[str] | None = None,
    office_levels: set[str] | None = None,
    stages: set[str] | None = None,
) -> pd.DataFrame:
    """Apply conjunctive dataset filters without changing the source file."""
    selected = frame.copy()
    filters = (
        ("election_year", {str(value) for value in years} if years else None),
        ("source_id", source_ids),
        ("state_postal", {value.upper() for value in states} if states else None),
        ("geography_level", geography_levels),
        ("office_level", office_levels),
        ("stage", stages),
    )
    for column, values in filters:
        if values:
            selected = selected[selected[column].astype(str).isin(values)]
    return selected.reset_index(drop=True)
