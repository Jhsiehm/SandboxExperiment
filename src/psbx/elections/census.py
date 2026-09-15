"""Plan and execute official ACS demographic pulls for electoral geographies."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from psbx.population.census_api import CensusApiClient
from psbx.population.census_sync import AREAS, CensusArea

ACS5_MAX_VERIFIED_YEAR = 2024
DEFAULT_LEVELS = (
    "state",
    "county",
    "place",
    "congressional_district",
    "state_legislative_upper",
    "state_legislative_lower",
)
ACS_VARIABLES = (
    "NAME",
    "B01001_001E",  # total population
    "B03002_003E",  # non-Hispanic White alone
    "B03002_004E",  # non-Hispanic Black alone
    "B03002_006E",  # non-Hispanic Asian alone
    "B03002_012E",  # Hispanic or Latino
    "B19013_001E",  # median household income
    "B25003_001E",  # occupied housing units
    "B25003_003E",  # renter occupied
)

_CENSUS_GEOGRAPHIES = {
    "state": "state",
    "county": "county",
    "place": "place",
    "congressional_district": "congressional district",
    "state_legislative_upper": "state legislative district (upper chamber)",
    "state_legislative_lower": "state legislative district (lower chamber)",
}


@dataclass(frozen=True)
class CensusElectionRequest:
    request_id: str
    year: int
    dataset: str
    level: str
    state_fips: str
    state_postal: str
    for_clause: str
    in_clauses: tuple[str, ...]
    variables: tuple[str, ...]


def parse_states(selection: str) -> tuple[CensusArea, ...]:
    tokens = [token.strip().casefold() for token in selection.split(",") if token.strip()]
    if not tokens or tokens == ["all"]:
        return AREAS
    by_key = {
        key: area
        for area in AREAS
        for key in (area.fips, area.abbreviation.casefold(), area.name.casefold())
    }
    unknown = sorted({token for token in tokens if token not in by_key})
    if unknown:
        raise ValueError("unknown state selection: " + ", ".join(unknown))
    selected = []
    seen = set()
    for token in tokens:
        area = by_key[token]
        if area.fips not in seen:
            selected.append(area)
            seen.add(area.fips)
    return tuple(selected)


def parse_levels(selection: str) -> tuple[str, ...]:
    tokens = tuple(token.strip() for token in selection.split(",") if token.strip())
    levels = DEFAULT_LEVELS if not tokens or tokens == ("all",) else tokens
    unknown = sorted(set(levels) - _CENSUS_GEOGRAPHIES.keys())
    if unknown:
        raise ValueError("unknown Census geography level: " + ", ".join(unknown))
    return tuple(dict.fromkeys(levels))


def census_election_plan(
    *,
    year: int = ACS5_MAX_VERIFIED_YEAR,
    levels: tuple[str, ...] = DEFAULT_LEVELS,
    states: tuple[CensusArea, ...] = AREAS,
) -> list[CensusElectionRequest]:
    if not 2009 <= year <= ACS5_MAX_VERIFIED_YEAR:
        raise ValueError(
            f"ACS 5-year year must be 2009-{ACS5_MAX_VERIFIED_YEAR}; newer releases "
            "must be source-verified before use"
        )
    unknown = sorted(set(levels) - _CENSUS_GEOGRAPHIES.keys())
    if unknown:
        raise ValueError("unknown Census geography level: " + ", ".join(unknown))
    requests = []
    for area in states:
        for level in levels:
            census_name = _CENSUS_GEOGRAPHIES[level]
            if level == "state":
                for_clause = f"state:{area.fips}"
                in_clauses: tuple[str, ...] = ()
            else:
                for_clause = f"{census_name}:*"
                in_clauses = (f"state:{area.fips}",)
            requests.append(
                CensusElectionRequest(
                    request_id=f"acs5-{year}-{area.abbreviation}-{level}",
                    year=year,
                    dataset=f"{year}/acs/acs5",
                    level=level,
                    state_fips=area.fips,
                    state_postal=area.abbreviation.upper(),
                    for_clause=for_clause,
                    in_clauses=in_clauses,
                    variables=ACS_VARIABLES,
                )
            )
    return requests


def summarize_census_plan(requests: list[CensusElectionRequest]) -> dict:
    return {
        "network_enabled": False,
        "request_count": len(requests),
        "years": sorted({request.year for request in requests}),
        "states": sorted({request.state_postal for request in requests}),
        "levels": dict(sorted(Counter(request.level for request in requests).items())),
        "variables": list(ACS_VARIABLES),
        "note": "Planning is offline. Use --execute to opt into Census API requests.",
        "requests": [asdict(request) for request in requests],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute_census_plan(
    requests: list[CensusElectionRequest],
    *,
    output_root: str | Path = "data/elections/census",
    cache_root: str | Path = "data/census-cache/api",
    max_requests: int = 350,
    force: bool = False,
    progress=None,
) -> dict:
    if len(requests) > max_requests:
        raise ValueError(
            f"Census plan has {len(requests)} requests, exceeding max_requests={max_requests}"
        )
    if not requests:
        raise ValueError("Census plan has no requests")
    years = {request.year for request in requests}
    if len(years) != 1:
        raise ValueError("one Census execution manifest may contain only one data year")
    client = CensusApiClient(cache_root=cache_root, allow_network=True)
    if not client.api_key:
        raise RuntimeError(
            "CENSUS_API_KEY is required for new Census API downloads; planning remains offline"
        )
    year = next(iter(years))
    destination = Path(output_root) / f"acs5-{year}-electoral-geographies"
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "manifest.json"
    if manifest_path.exists() and not force:
        raise FileExistsError(f"Census dataset already exists: {destination}; pass force=True")
    artifacts = []
    failures = []
    coverage: dict[str, dict] = {}
    for index, request in enumerate(requests, start=1):
        relative = Path(request.state_postal) / f"{request.level}.csv"
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            frame = client.query(
                dataset=request.dataset,
                variables=request.variables,
                for_clause=request.for_clause,
                in_clauses=request.in_clauses,
            )
            temporary = output.with_suffix(".csv.tmp")
            frame.to_csv(temporary, index=False)
            os.replace(temporary, output)
            geography_column = _CENSUS_GEOGRAPHIES[request.level]
            ids = (
                sorted(frame[geography_column].astype(str).unique())
                if geography_column in frame
                else []
            )
            state = coverage.setdefault(
                request.state_postal,
                {"levels": [], "geography_counts": {}, "geography_ids": {}},
            )
            state["levels"].append(request.level)
            state["geography_counts"][request.level] = len(frame)
            state["geography_ids"][request.level] = ids
            artifacts.append(
                {
                    **asdict(request),
                    "local_path": str(relative),
                    "rows": len(frame),
                    "sha256": _sha256(output),
                    "status": "downloaded",
                }
            )
        except Exception as exc:
            message = f"{request.request_id}: {type(exc).__name__}: {exc}"
            failures.append(message)
            artifacts.append({**asdict(request), "status": "failed", "error": message})
        if progress is not None:
            progress(index, len(requests), request)
    for state in coverage.values():
        state["levels"] = sorted(set(state["levels"]))
    payload = {
        "schema_version": 1,
        "dataset_id": f"acs5-{year}-electoral-geographies",
        "label": f"{year} ACS 5-year electoral geographies",
        "kind": "census",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "request_count": len(requests),
        "successful_requests": len(requests) - len(failures),
        "failed_requests": len(failures),
        "passed": not failures,
        "states": sorted(coverage),
        "geography_levels": sorted({request.level for request in requests}),
        "coverage_by_state": coverage,
        "variables": list(ACS_VARIABLES),
        "failures": failures,
        "artifacts": artifacts,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)
    return {"manifest_path": str(manifest_path), **payload}
