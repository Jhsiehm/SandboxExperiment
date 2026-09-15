"""Normalize the candidate-level result sheets in official FEC workbooks.

The reader intentionally parses only workbook metadata, shared strings, and the requested sheet
XML. Embedded drawings and macros are never executed or expanded.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import pandas as pd

from psbx.population.census_sync import AREAS

from .importer import import_election_frame
from .registry import federal_general_election_day

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_XML_MEMBER_BYTES = 25_000_000
FEC_RESULTS_INDEX = (
    "https://www.fec.gov/introduction-campaign-finance/"
    "election-results-and-voting-information/"
)
_STATE_BY_POSTAL = {area.abbreviation.upper(): area for area in AREAS}


def _safe_member(archive: ZipFile, name: str) -> bytes:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe XLSX member path")
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise ValueError(f"XLSX is missing {name}") from exc
    if info.file_size > MAX_XML_MEMBER_BYTES:
        raise ValueError(f"XLSX XML member is too large: {name}")
    return archive.read(info)


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    payload = _safe_member(archive, "xl/sharedStrings.xml")
    root = ET.fromstring(payload)
    tag = f"{{{MAIN_NS}}}t"
    return ["".join(node.text or "" for node in item.iter(tag)) for item in root]


def _sheet_members(archive: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(_safe_member(archive, "xl/workbook.xml"))
    relationships = ET.fromstring(
        _safe_member(archive, "xl/_rels/workbook.xml.rels")
    )
    targets = {
        node.attrib["Id"]: node.attrib["Target"]
        for node in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        raise ValueError("XLSX workbook has no sheets")
    result = {}
    for sheet in sheets:
        relationship_id = sheet.attrib.get(f"{{{DOC_REL_NS}}}id")
        target = targets.get(str(relationship_id), "")
        member = target.lstrip("/") if target.startswith("/xl/") else f"xl/{target}"
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".xml":
            raise ValueError("unsafe XLSX worksheet relationship")
        result[str(sheet.attrib.get("name") or "")] = str(path)
    return result


def _column_number(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if not match:
        raise ValueError("invalid XLSX cell reference")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number - 1


def read_xlsx_sheet(path: str | Path, name_contains: str) -> list[dict[str, str]]:
    """Read one worksheet as string dictionaries without loading embedded media."""
    try:
        with ZipFile(path) as archive:
            members = _sheet_members(archive)
            matches = [name for name in members if name_contains.casefold() in name.casefold()]
            if len(matches) != 1:
                raise ValueError(
                    f"expected one worksheet containing {name_contains!r}, found {matches}"
                )
            strings = _shared_strings(archive)
            root = ET.fromstring(_safe_member(archive, members[matches[0]]))
    except BadZipFile as exc:
        raise ValueError("FEC workbook is not a valid XLSX archive") from exc

    raw_rows: list[tuple[int, dict[int, str]]] = []
    for row in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r") or len(raw_rows) + 1)
        values = {}
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            column = _column_number(str(cell.attrib.get("r") or ""))
            kind = cell.attrib.get("t")
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            if kind == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t")
                )
            elif value_node is None or value_node.text is None:
                value = ""
            elif kind == "s":
                index = int(value_node.text)
                if not 0 <= index < len(strings):
                    raise ValueError("XLSX shared-string index is out of range")
                value = strings[index]
            else:
                value = value_node.text
            values[column] = str(value).strip()
        raw_rows.append((row_number, values))
    if not raw_rows:
        raise ValueError("FEC result worksheet is empty")
    header = {column: _header(value) for column, value in raw_rows[0][1].items()}
    required = {
        "state abbreviation",
        "state",
        "district",
        "fec id",
        "candidate name",
        "party",
        "general votes",
        "ge winner indicator",
    }
    missing = required - set(header.values())
    if missing:
        raise ValueError("FEC result worksheet is missing columns: " + ", ".join(sorted(missing)))
    return [
        {
            "_row_number": str(row_number),
            **{header[column]: value for column, value in values.items() if column in header},
        }
        for row_number, values in raw_rows[1:]
    ]


def _header(value: str) -> str:
    normalized = " ".join(str(value).strip().casefold().split())
    normalized = normalized.replace(" (when applicable)", "")
    return {"d": "district", "fec id#": "fec id"}.get(normalized, normalized)


def _votes(value: str) -> tuple[int, str] | None:
    normalized = str(value or "").strip().replace(",", "")
    if normalized.casefold() == "unopposed":
        return 0, "unopposed_no_vote_total"
    if not normalized or not normalized.isdigit():
        return None
    return int(normalized), "reported"


def _ordinal(value: int) -> str:
    suffix = "th"
    if value % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _house_district(value: str) -> tuple[str, str | None] | None:
    """Split FEC values such as ``02-Unexpired Term`` into geography and contest parts."""
    normalized = " ".join(str(value or "").strip().split())
    match = re.fullmatch(r"(\d{1,2})(?:-(.+))?", normalized)
    if not match:
        return None
    district = match.group(1).zfill(2)
    qualifier = match.group(2)
    if qualifier:
        qualifier = re.sub(r"[^a-z0-9]+", "-", qualifier.casefold()).strip("-")
    return district, qualifier or None


def _senate_qualifier(value: str) -> str | None:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized or normalized.casefold() == "s":
        return None
    match = re.fullmatch(r"S-(.+)", normalized, flags=re.IGNORECASE)
    if not match:
        return re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-") or None
    return re.sub(r"[^a-z0-9]+", "-", match.group(1).casefold()).strip("-") or None


def _consolidate_ballot_lines(rows: list[dict]) -> tuple[list[dict], int]:
    """Combine fusion-voting party lines for the same candidate and contest."""
    consolidated: dict[tuple[str, str, str], dict] = {}
    merged = 0
    for row in rows:
        candidate_key = row["candidate_id"] or row["candidate_name"].casefold()
        key = (row["contest_id"], row["geography_id"], candidate_key)
        current = consolidated.get(key)
        if current is None:
            consolidated[key] = row.copy()
            continue
        merged += 1
        current["votes"] += row["votes"]
        parties = [part.strip() for part in str(current.get("party") or "").split(" / ")]
        incoming = str(row.get("party") or "").strip()
        if incoming and incoming not in parties:
            parties.append(incoming)
        current["party"] = " / ".join(part for part in parties if part) or None
        current["winner"] = True if current["winner"] or row["winner"] else None
        current["source_record_id"] += f"+{row['_source_row']}"
    return list(consolidated.values()), merged


def normalize_fec_workbook(
    path: str | Path,
    *,
    year: int,
    source_release_date: date,
    source_url: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Create canonical general-election rows for U.S. House and U.S. Senate."""
    if year % 2 or not 2016 <= year <= 2022:
        raise ValueError("the combined-workbook FEC adapter supports even cycles from 2016-2022")
    workbook = Path(path)
    if not workbook.is_file():
        raise FileNotFoundError(workbook)
    source_url = source_url or FEC_RESULTS_INDEX
    election_date = federal_general_election_day(year)
    if source_release_date < election_date:
        raise ValueError("source_release_date cannot precede the election")
    sheets = (
        ("US Senate Results by State", "us_senate"),
        ("US House Results by State", "us_house"),
    )
    canonical = []
    skipped = Counter()
    congress = (year - 1788) // 2 + 1
    for sheet_name, office_level in sheets:
        for row in read_xlsx_sheet(workbook, sheet_name):
            postal = row.get("state abbreviation", "").upper()
            area = _STATE_BY_POSTAL.get(postal)
            if area is None:
                skipped["territory_or_unknown_state"] += 1
                continue
            candidate = row.get("candidate name", "").strip()
            vote_result = _votes(row.get("general votes", ""))
            if not candidate or vote_result is None:
                skipped["non_candidate_or_no_general_votes"] += 1
                continue
            votes, vote_status = vote_result
            raw_district = row.get("district", "").strip()
            district_parts = _house_district(raw_district)
            if office_level == "us_house" and district_parts is None:
                skipped["house_row_without_district"] += 1
                continue
            district, contest_qualifier = district_parts or (
                "",
                _senate_qualifier(raw_district),
            )
            geography_level = "congressional_district" if office_level == "us_house" else "state"
            geography_id = (
                f"district:{area.fips}:{district}"
                if office_level == "us_house"
                else f"state:{area.fips}"
            )
            contest_id = (
                f"{year}-{postal.casefold()}-us-house-{district}"
                f"{'-' + contest_qualifier if contest_qualifier else ''}-general"
                if office_level == "us_house"
                else f"{year}-{postal.casefold()}-us-senate"
                f"{'-' + contest_qualifier if contest_qualifier else ''}-general"
            )
            fec_id = row.get("fec id", "").strip()
            canonical.append(
                {
                    "source_id": "fec_federal_elections_1982_2022",
                    "source_record_id": (
                        f"fec-{year}-{office_level}-{postal.casefold()}-"
                        f"{raw_district or 's'}-{row['_row_number']}"
                    ),
                    "_source_row": row["_row_number"],
                    "election_date": election_date.isoformat(),
                    "election_year": year,
                    "stage": "general",
                    "office_level": office_level,
                    "office_name": (
                        f"U.S. House District {district}"
                        + (
                            f" · {contest_qualifier.replace('-', ' ').title()}"
                            if contest_qualifier
                            else ""
                        )
                        if office_level == "us_house"
                        else "United States Senate"
                    ),
                    "contest_id": contest_id,
                    "geography_level": geography_level,
                    "geography_id": geography_id,
                    "geography_name": (
                        f"{area.name} Congressional District {district}"
                        if office_level == "us_house"
                        else area.name
                    ),
                    "geography_vintage": (
                        f"{_ordinal(congress)} Congress districts"
                        if office_level == "us_house"
                        else f"{year} state boundaries"
                    ),
                    "state_fips": area.fips,
                    "state_postal": postal,
                    "district": district or None,
                    "county_fips": None,
                    "county_name": None,
                    "municipality_name": None,
                    "precinct": None,
                    "candidate_id": None if fec_id.casefold() in {"", "n/a"} else fec_id,
                    "candidate_name": candidate,
                    "party": row.get("party", "").strip() or None,
                    "votes": votes,
                    "vote_status": vote_status,
                    "total_votes_reported": None,
                    "winner": (
                        True
                        if vote_status == "unopposed_no_vote_total"
                        or row.get("ge winner indicator", "").strip().upper() == "W"
                        else None
                    ),
                    "certified": True,
                    "source_url": source_url,
                    "source_release_date": source_release_date.isoformat(),
                }
            )
    if not canonical:
        raise ValueError("FEC workbook produced no general-election candidate rows")
    canonical, merged_ballot_lines = _consolidate_ballot_lines(canonical)
    totals = Counter()
    for row in canonical:
        totals[row["contest_id"]] += int(row["votes"])
    for row in canonical:
        row["total_votes_reported"] = totals[row["contest_id"]]
    warnings = [
        (
            "FEC workbook adapter imported candidate rows with numeric general-election "
            f"votes and skipped {count} {reason.replace('_', ' ')} rows."
        )
        for reason, count in sorted(skipped.items())
        if count
    ]
    warnings.append(
        "The adapter's source_release_date is caller-supplied and must be independently verified."
    )
    if merged_ballot_lines:
        warnings.append(
            "The adapter consolidated "
            f"{merged_ballot_lines} same-candidate ballot-party lines into candidate totals."
        )
    unopposed = sum(row["vote_status"] == "unopposed_no_vote_total" for row in canonical)
    if unopposed:
        warnings.append(
            f"The adapter retained {unopposed} unopposed contests with zero reported votes "
            "and vote_status=unopposed_no_vote_total."
        )
    return pd.DataFrame(canonical).drop(columns=["_source_row"]), warnings


def import_fec_workbook(
    path: str | Path,
    *,
    year: int,
    source_release_date: date,
    dataset_id: str,
    label: str,
    cutoff_date: date,
    source_url: str | None = None,
    output_root: str | Path = "data/elections/normalized",
    force: bool = False,
):
    workbook = Path(path)
    frame, warnings = normalize_fec_workbook(
        workbook,
        year=year,
        source_release_date=source_release_date,
        source_url=source_url,
    )
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    return import_election_frame(
        frame,
        input_sha256=digest,
        dataset_id=dataset_id,
        label=label,
        cutoff_date=cutoff_date,
        output_root=output_root,
        force=force,
        additional_warnings=warnings,
    )
