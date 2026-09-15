"""Public, path-free dashboard summary for the Track B population foundation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from psbx.elections.catalog import public_data_layers
from psbx.paths import repo_root
from psbx.population.census_sync import ACS_SEQUENCES, AREAS, census_artifact_plan
from psbx.population.profiles import public_population_profiles

FAMILY_LABELS = {
    "pums_person": "PUMS person records",
    "pums_housing": "PUMS housing records",
    "decennial_demographic_profile": "2010 demographic profiles",
    "acs5_summary_sequence": "ACS 5-year summary sequences",
    "support": "Geography + table support files",
    "cvap": "Citizen voting-age population",
}

TABLE_LABELS = {
    "B01001": "Sex by age",
    "B03002": "Race and Hispanic origin",
    "B05001": "Citizenship status",
    "B11016": "Household type and size",
    "B12001": "Marital status",
    "B15001": "Education by age and sex",
    "B15002": "Educational attainment",
    "B19001": "Household income",
    "B23001": "Employment status",
    "B25003": "Housing tenure",
}

# 2012 House apportionment (D.C. is represented as one selectable at-large area).
CONGRESSIONAL_DISTRICTS_2012 = {
    "AL": 7, "AK": 1, "AZ": 9, "AR": 4, "CA": 53, "CO": 7, "CT": 5,
    "DE": 1, "DC": 1, "FL": 27, "GA": 14, "HI": 2, "ID": 2, "IL": 18,
    "IN": 9, "IA": 4, "KS": 4, "KY": 6, "LA": 6, "ME": 2, "MD": 8,
    "MA": 9, "MI": 14, "MN": 8, "MS": 4, "MO": 8, "MT": 1, "NE": 3,
    "NV": 4, "NH": 2, "NJ": 12, "NM": 3, "NY": 27, "NC": 13, "ND": 1,
    "OH": 16, "OK": 5, "OR": 5, "PA": 18, "RI": 2, "SC": 7, "SD": 1,
    "TN": 9, "TX": 36, "UT": 4, "VT": 1, "VA": 11, "WA": 10, "WV": 3,
    "WI": 8, "WY": 1,
}

# An adjacency-minded tile cartogram keeps every state and D.C. large enough to select.
STATE_TILE_POSITIONS = {
    "WA": (0, 0), "ID": (1, 1), "MT": (2, 0), "ND": (3, 0), "MN": (4, 0),
    "WI": (5, 1), "MI": (6, 0), "NY": (8, 1), "VT": (9, 0), "NH": (10, 0),
    "ME": (11, 0), "OR": (0, 1), "NV": (1, 2), "WY": (2, 1), "SD": (3, 1),
    "IA": (4, 2), "IL": (5, 2), "IN": (6, 2), "OH": (7, 2), "PA": (8, 2),
    "NJ": (9, 2), "CT": (10, 1), "MA": (11, 1), "CA": (0, 2), "UT": (1, 3),
    "CO": (2, 2), "NE": (3, 2), "MO": (4, 3), "KY": (5, 3), "WV": (6, 3),
    "VA": (7, 3), "MD": (8, 3), "DE": (9, 3), "RI": (10, 2), "AZ": (0, 3),
    "NM": (1, 4), "KS": (2, 3), "OK": (3, 4), "AR": (4, 4), "TN": (5, 4),
    "NC": (6, 4), "SC": (7, 4), "DC": (8, 4), "TX": (2, 5), "LA": (3, 5),
    "MS": (4, 5), "AL": (5, 5), "GA": (6, 5), "FL": (7, 6), "AK": (0, 6),
    "HI": (1, 6),
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _family_rows(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("family", "unknown")) for row in artifacts)
    order = (
        "pums_person",
        "pums_housing",
        "decennial_demographic_profile",
        "acs5_summary_sequence",
        "support",
        "cvap",
    )
    return [
        {"id": family, "label": FAMILY_LABELS[family], "artifacts": counts[family]}
        for family in order
    ]


def _state_rows(
    artifacts: list[dict[str, Any]], profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    expected = 3 + len(ACS_SEQUENCES)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        grouped.setdefault(str(artifact.get("geography_id", "")), []).append(artifact)
    rows = []
    for area in AREAS:
        abbreviation = area.abbreviation.upper()
        state_artifacts = grouped.get(f"state:{area.fips}", [])
        good = sum(
            row.get("status") in {"downloaded", "existing_verified"}
            and bool(row.get("sha256"))
            for row in state_artifacts
        )
        rows.append(
            {
                "fips": area.fips,
                "abbreviation": abbreviation,
                "name": area.name,
                "artifacts": good,
                "expected_artifacts": expected,
                "ready": good == expected,
                "district_count": CONGRESSIONAL_DISTRICTS_2012[abbreviation],
                "map_col": STATE_TILE_POSITIONS[abbreviation][0],
                "map_row": STATE_TILE_POSITIONS[abbreviation][1],
                "population_profiles": [
                    profile["population_id"]
                    for profile in profiles
                    if profile["geography"]["state_fips"] == area.fips
                ],
            }
        )
    return rows


def _fixture_summary(root: Path, epoch_id: str) -> dict[str, Any]:
    candidates = sorted((root / "data" / "population" / epoch_id).glob("*/manifest.json"))
    manifest_path = next(
        (
            path
            for path in candidates
            if str((_read_json(path) or {}).get("population_id") or "").startswith(
                "fixture-"
            )
        ),
        None,
    )
    if manifest_path is None:
        return {
            "status": "not_built",
            "validated": False,
            "label": "Offline fixture not built",
        }
    manifest = _read_json(manifest_path) or {}
    validation = _read_json(manifest_path.parent / "population_validation.json") or {}
    validated = bool(validation.get("passed"))
    variation = validation.get("total_variation_by_dimension") or {}
    max_variation = max((float(value) for value in variation.values()), default=None)
    geography = manifest.get("geography") or {}
    return {
        "status": "validated" if validated else "needs_review",
        "validated": validated,
        "label": geography.get("label") or manifest.get("population_id") or "Fixture",
        "population_id": manifest.get("population_id"),
        "target_population": manifest.get("target_population"),
        "synthetic_records": manifest.get("synthetic_records"),
        "representative_cells": manifest.get("representative_cells"),
        "reasoning_calls": manifest.get("reasoning_calls"),
        "max_total_variation": max_variation,
        "household_integrity": validation.get("household_integrity"),
    }


def _convergence_summary(root: Path, epoch_id: str) -> dict[str, Any]:
    reports = []
    base = root / "data/population" / epoch_id / "national-us-e2012/experiments"
    for path in base.glob("convergence-*/report.json"):
        report = _read_json(path)
        if report and report.get("passed") and (report.get("config") or {}).get(
            "schema_version"
        ) == 3:
            reports.append(report)
    if not reports:
        return {"status": "not_run", "passed": False}
    report = max(reports, key=lambda row: str(row.get("created_at") or ""))
    numeric = [
        row
        for row in report.get("summary", [])
        if str(row.get("condition") or "").isdigit()
    ]
    reference = next(
        (row for row in numeric if int(row.get("agent_budget") or 0) == 250),
        numeric[-1] if numeric else {},
    )
    return {
        "status": "complete",
        "passed": True,
        "run_id": report.get("run_id"),
        "conditions": len(numeric),
        "replications_per_condition": int(reference.get("replications") or 0),
        "reference_budget": int(reference.get("agent_budget") or 0),
        "reference_mean_dimension_tvd": reference.get("mean_dimension_tvd"),
        "reference_worst_dimension_tvd": reference.get("worst_dimension_tvd"),
        "actual_llm_calls": int((report.get("config") or {}).get("actual_llm_calls") or 0),
        "scope": "demographic representation only",
    }


def _behavior_summary(root: Path, epoch_id: str) -> dict[str, Any]:
    reports = []
    pattern = root / "data/evaluation-vault" / epoch_id
    for path in pattern.glob("*/validation_report_v2.json"):
        report = _read_json(path)
        if report and report.get("schema_version") == 2:
            reports.append(report)
    if not reports:
        return {
            "status": "not_run",
            "passed": False,
            "scope": "No sealed behavior calibration is available.",
        }
    report = max(reports, key=lambda row: str(row.get("evaluated_at") or ""))
    validation = report.get("validation") or {}
    provenance = report.get("target_provenance") or {}
    return {
        "status": report.get("status"),
        "passed": bool(report.get("passed")),
        "run_id": validation.get("run_id"),
        "targets": int(validation.get("n_targets") or 0),
        "mean_absolute_error": validation.get("mean_absolute_error"),
        "metrics_frozen": bool(validation.get("metrics_frozen")),
        "target_exclusion": provenance.get("target_exclusion"),
        "analyst_blind": False,
        "scope": (
            "Retrospective, mechanically sealed neutral-baseline calibration; "
            "not independent analyst-blind behavioral validation."
        ),
    }


def population_dashboard_payload(
    epoch_id: str = "e2012", *, root: Path | None = None
) -> dict[str, Any]:
    """Summarize build artifacts without exposing paths, donor rows, or person records."""
    root = root or repo_root()
    manifest = _read_json(
        root / "data" / "population-input" / epoch_id / "census" / "manifest.json"
    )
    planned_count = len(census_artifact_plan())
    if manifest is None:
        artifacts: list[dict[str, Any]] = []
        census_status = "not_downloaded"
        total_bytes = 0
        last_checked_at = None
        passed = False
    else:
        artifacts = [row for row in manifest.get("artifacts", []) if isinstance(row, dict)]
        ready_artifacts = [
            row
            for row in artifacts
            if row.get("status") in {"downloaded", "existing_verified"}
            and bool(row.get("sha256"))
        ]
        ready_count = len(ready_artifacts)
        passed = bool(manifest.get("passed")) and ready_count == planned_count
        census_status = "verified" if passed else "incomplete"
        total_bytes = int(manifest.get("total_bytes") or 0)
        last_checked_at = manifest.get("generated_at")

    ready_artifacts = [
        row
        for row in artifacts
        if row.get("status") in {"downloaded", "existing_verified"}
        and bool(row.get("sha256"))
    ]
    expected_national = sum(
        artifact.geography_id == "us:1" for artifact in census_artifact_plan()
    )
    national_ready = (
        sum(row.get("geography_id") == "us:1" for row in ready_artifacts)
        == expected_national
    )

    profiles = public_population_profiles(epoch_id, root=root)
    states = _state_rows(artifacts, profiles)
    fixture = _fixture_summary(root, epoch_id)
    state_builds = sum(
        profile["validated"] and profile["geography"]["type"] == "state"
        for profile in profiles
    )
    national_population = next(
        (
            profile
            for profile in profiles
            if profile["population_id"] == "national-us-e2012"
            and profile["runnable"]
        ),
        None,
    )
    normalizations = sum(
        bool((_read_json(path) or {}).get("passed"))
        for path in (
            root / "data/population-input" / epoch_id / "normalized"
        ).glob("*/normalized_manifest.json")
    )
    convergence = _convergence_summary(root, epoch_id)
    behavior = _behavior_summary(root, epoch_id)
    data_catalog = public_data_layers(epoch_id, root=root)
    data_catalog["layers"].insert(
        1,
        {
            "id": f"{epoch_id}-census-source-pack",
            "kind": "census",
            "label": "2010 Census and ACS source pack",
            "status": "source_only" if ready_artifacts else "not_downloaded",
            "years": [2010],
            "states": [row["fips"] for row in states if row["ready"]],
            "geography_levels": ["state"],
            "coverage_by_state": {
                row["fips"]: {
                    "geography_levels": ["state"],
                    "geography_ids": {"state": [f"state:{row['fips']}"]},
                    "status": "source_only",
                }
                for row in states
                if row["ready"]
            },
            "synthetic": False,
            "runtime_access": False,
            "use": "population_build_source_only",
            "note": (
                "Checksum-verified input archives. This is source coverage, not a "
                "district-level normalized demographic dataset."
            ),
        },
    )
    tables = [
        {"code": code, "label": TABLE_LABELS[code]}
        for codes in ACS_SEQUENCES.values()
        for code in codes
    ]
    validated_profiles = sum(profile["validated"] for profile in profiles)
    runnable_profiles = sum(profile["runnable"] for profile in profiles)
    profile_status = (
        "full_state_and_national_profiles_ready"
        if state_builds == len(AREAS) and national_population
        else "practice_fixture_ready"
        if fixture["validated"]
        else "validated_profiles_available"
        if runnable_profiles
        else "no_validated_profiles"
    )
    return {
        "track": "B",
        "epoch_id": epoch_id,
        "cutoff_date": manifest.get("cutoff_date") if manifest else "2012-06-30",
        "census": {
            "status": census_status,
            "passed": passed,
            "artifact_count": len(ready_artifacts),
            "expected_artifact_count": planned_count,
            "total_bytes": total_bytes,
            "states_plus_dc": len(states),
            "states_ready": sum(row["ready"] for row in states),
            "national_aggregate": national_ready,
            "last_checked_at": last_checked_at,
            "families": _family_rows(ready_artifacts),
            "tables": tables,
            "states": states,
        },
        "builds": {
            "state_populations": state_builds,
            "expected_state_populations": len(AREAS),
            "normalizations": normalizations,
            "expected_normalizations": len(AREAS) + 1,
            "validated_profiles": validated_profiles,
            "national_population": national_population,
            "fixture": fixture,
        },
        "profile_contract": {
            "status": profile_status,
            "runnable_profiles": runnable_profiles,
            "practice_fixture_ready": bool(fixture["validated"]),
            "can_weight_swarm": runnable_profiles > 0,
            "build_command": f"psbx practice prepare --epoch {epoch_id}",
            "full_census_profiles_ready": bool(
                state_builds == len(AREAS) and national_population
            ),
            "claim_scope": (
                "Only profiles listed as runnable have passed local validation. "
                "A fixture profile is synthetic practice data, not U.S. coverage."
            ),
        },
        "convergence": convergence,
        "behavior_validation": behavior,
        "explorer": {
            "default_geography": "us:1",
            "district_vintage": "2012 congressional apportionment",
            "district_profiles_available": sum(
                profile["geography"]["type"]
                in {"voting_district", "county", "county_subdivision", "tract"}
                for profile in profiles
            ),
            "profiles": profiles,
        },
        "data_catalog": data_catalog,
        "pipeline": [
            {
                "label": "Acquire historical inputs",
                "status": "complete" if census_status == "verified" else census_status,
                "detail": "Official, pre-cutoff Census archives",
            },
            {
                "label": "Parse constraints + donors",
                "status": "complete" if normalizations == len(AREAS) + 1 else "waiting",
                "detail": f"{normalizations} of {len(AREAS) + 1} areas normalized",
            },
            {
                "label": "Synthesize 51 populations",
                "status": "complete" if state_builds == len(AREAS) else "waiting",
                "detail": f"{state_builds} of {len(AREAS)} state/D.C. builds complete",
            },
            {
                "label": "Measure convergence",
                "status": "complete" if convergence["passed"] else "waiting",
                "detail": (
                    f"{convergence.get('conditions', 0)} agent budgets × "
                    f"{convergence.get('replications_per_condition', 0)} seeds; "
                    "demographic fit only"
                ),
            },
            {
                "label": "Calibrate behavior",
                "status": "limited" if behavior["passed"] else "waiting",
                "detail": behavior["scope"],
            },
        ],
        "claims": [
            "Downloaded Census inputs are not synthetic populations.",
            "Synthetic records are statistically constructed and are not actual residents.",
            "Population fidelity does not establish political-behavior fidelity.",
            "No live LLM population simulation is part of this foundation build.",
            (
                "No validated population profile is present in this workspace."
                if not runnable_profiles
                else f"{runnable_profiles} validated profile(s) are runnable; coverage is "
                "limited to their declared geographies."
            ),
        ],
    }
