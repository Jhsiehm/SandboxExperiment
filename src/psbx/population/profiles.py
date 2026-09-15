"""Safe summaries and weighted persona panels for built synthetic populations."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from psbx.paths import repo_root, validate_run_id

PROFILE_DIMENSIONS = (
    "age_band",
    "race_ethnicity",
    "education",
    "citizenship",
    "census_sex",
    "household_income_band",
)

DIMENSION_LABELS = {
    "age_band": "Age",
    "race_ethnicity": "Race and ethnicity",
    "education": "Education",
    "citizenship": "Citizenship",
    "census_sex": "Census sex",
    "household_income_band": "Household income",
}

STATE_REGIONS = {
    "01": "south", "02": "west", "04": "west", "05": "south", "06": "west",
    "08": "west", "09": "northeast", "10": "south", "11": "south", "12": "south",
    "13": "south", "15": "west", "16": "west", "17": "midwest", "18": "midwest",
    "19": "midwest", "20": "midwest", "21": "south", "22": "south", "23": "northeast",
    "24": "south", "25": "northeast", "26": "midwest", "27": "midwest", "28": "south",
    "29": "midwest", "30": "west", "31": "midwest", "32": "west", "33": "northeast",
    "34": "northeast", "35": "west", "36": "northeast", "37": "south", "38": "midwest",
    "39": "midwest", "40": "south", "41": "west", "42": "northeast", "44": "northeast",
    "45": "south", "46": "midwest", "47": "south", "48": "south", "49": "west",
    "50": "northeast", "51": "south", "53": "west", "54": "south", "55": "midwest",
    "56": "west",
}


class PopulationProfileError(ValueError):
    """A requested population profile is absent, invalid, or unsafe to run."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PopulationProfileError(f"could not read {path.name}") from exc
    if not isinstance(payload, dict):
        raise PopulationProfileError(f"{path.name} must contain an object")
    return payload


def _profile_dir(epoch_id: str, population_id: str, root: Path) -> Path:
    safe_id = validate_run_id(population_id)
    base = (root / "data" / "population" / epoch_id).resolve()
    candidate = (base / safe_id).resolve()
    if candidate.parent != base:
        raise PopulationProfileError("population id resolves outside the selected epoch")
    return candidate


def _cell_rows(directory: Path) -> Iterator[dict[str, str]]:
    path = directory / "representative_cells.csv"
    if not path.is_file():
        return
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _cell_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_summary_from_rows(rows: Iterator[dict[str, str]]) -> dict[str, Any]:
    counts: dict[str, defaultdict[str, float]] = {
        dimension: defaultdict(float) for dimension in PROFILE_DIMENSIONS
    }
    row_count = 0
    represented_population = 0.0
    for row in rows:
        row_count += 1
        try:
            weight = float(row.get("population_weight") or 0)
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            continue
        represented_population += weight
        for dimension in PROFILE_DIMENSIONS:
            counts[dimension][str(row.get(dimension) or "unspecified")] += weight
    return {
        "representative_cells": row_count,
        "represented_population": represented_population,
        "demographics": _distributions_from_counts(counts),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_population_profile_summary(
    directory: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Write a small checksum-bound cache so dashboard requests never load all cells."""
    cells_path = directory / "representative_cells.csv"
    expected_sha = str(
        (manifest.get("output_sha256") or {}).get("representative_cells.csv") or ""
    )
    if not cells_path.is_file() or len(expected_sha) != 64:
        raise PopulationProfileError("population manifest does not bind representative cells")
    actual_sha = _cell_file_sha256(cells_path)
    if actual_sha != expected_sha:
        raise PopulationProfileError("representative cell checksum does not match manifest")
    stat = cells_path.stat()
    summary = _profile_summary_from_rows(_cell_rows(directory))
    payload = {
        "schema_version": 1,
        "population_id": manifest.get("population_id"),
        "source_sha256": actual_sha,
        "source_bytes": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "source_ctime_ns": stat.st_ctime_ns,
        "source_inode": stat.st_ino,
        **summary,
    }
    _atomic_json(directory / "profile_summary.json", payload)
    return payload


def _profile_summary(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_sha = str(
        (manifest.get("output_sha256") or {}).get("representative_cells.csv") or ""
    )
    cache_path = directory / "profile_summary.json"
    if cache_path.is_file():
        try:
            cached = _read_json(cache_path)
        except PopulationProfileError:
            cached = {}
        cells_path = directory / "representative_cells.csv"
        stat = cells_path.stat() if cells_path.is_file() else None
        if (
            stat is not None
            and
            cached.get("population_id") == manifest.get("population_id")
            and cached.get("source_sha256") == expected_sha
            and cached.get("source_bytes") == stat.st_size
            and cached.get("source_mtime_ns") == stat.st_mtime_ns
            and cached.get("source_ctime_ns") == stat.st_ctime_ns
            and cached.get("source_inode") == stat.st_ino
            and isinstance(cached.get("demographics"), list)
        ):
            return cached
    return write_population_profile_summary(directory, manifest)


def _validation_passed(directory: Path) -> bool:
    path = directory / "population_validation.json"
    if not path.is_file():
        return False
    try:
        return bool(_read_json(path).get("passed"))
    except PopulationProfileError:
        return False


def load_population_profile(
    epoch_id: str,
    population_id: str,
    *,
    root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Load a validated aggregate profile without exposing person-level records."""
    root = root or repo_root()
    directory = _profile_dir(epoch_id, population_id, root)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise PopulationProfileError("population profile is not built")
    manifest = _read_json(manifest_path)
    if str(manifest.get("epoch_id") or "") != epoch_id:
        raise PopulationProfileError("population profile belongs to another epoch")
    if str(manifest.get("population_id") or "") != population_id:
        raise PopulationProfileError("population manifest id does not match its directory")
    if not _validation_passed(directory):
        raise PopulationProfileError("population profile has not passed validation")
    if not (directory / "representative_cells.csv").is_file():
        raise PopulationProfileError("population profile has no representative cells")
    _profile_summary(directory, manifest)
    return directory, manifest


def demographic_distributions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Return display-safe weighted marginals from representative cells."""
    counts: dict[str, defaultdict[str, float]] = {
        dimension: defaultdict(float) for dimension in PROFILE_DIMENSIONS
    }
    for row in rows:
        try:
            weight = float(row.get("population_weight") or 0)
        except (TypeError, ValueError):
            weight = 0
        if weight > 0:
            for dimension in PROFILE_DIMENSIONS:
                counts[dimension][str(row.get(dimension) or "unspecified")] += weight
    return _distributions_from_counts(counts)


def _distributions_from_counts(
    counts_by_dimension: dict[str, defaultdict[str, float]],
) -> list[dict[str, Any]]:
    distributions: list[dict[str, Any]] = []
    for dimension in PROFILE_DIMENSIONS:
        counts = counts_by_dimension[dimension]
        total = sum(counts.values())
        categories = [
            {
                "id": category,
                "label": _category_label(category),
                "count": round(count, 3),
                "share": count / total if total else 0,
            }
            for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        distributions.append(
            {
                "id": dimension,
                "label": DIMENSION_LABELS[dimension],
                "categories": categories,
            }
        )
    return distributions


def _category_label(category: str) -> str:
    label = category.replace("_", " ").replace(" plus", "+").title()
    parts = label.split()
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{parts[0]}–{parts[1]}"
    return label


def public_population_profiles(
    epoch_id: str,
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Catalog validated population builds using aggregate metadata only."""
    root = root or repo_root()
    base = root / "data" / "population" / epoch_id
    profiles: list[dict[str, Any]] = []
    for manifest_path in sorted(base.glob("*/manifest.json")):
        try:
            manifest = _read_json(manifest_path)
        except PopulationProfileError:
            continue
        population_id = str(manifest.get("population_id") or manifest_path.parent.name)
        geography = manifest.get("geography") or {}
        validated = _validation_passed(manifest_path.parent)
        cells_path = manifest_path.parent / "representative_cells.csv"
        try:
            summary = _profile_summary(manifest_path.parent, manifest) if validated else {}
        except PopulationProfileError:
            summary = {}
            validated = False
        has_cells = cells_path.is_file() and int(summary.get("representative_cells") or 0) > 0
        profiles.append(
            {
                "population_id": population_id,
                "label": geography.get("label") or population_id,
                "geography": {
                    "id": geography.get("id") or population_id,
                    "type": geography.get("geography_type") or "custom",
                    "state_fips": str(geography.get("state_fips") or "").zfill(2),
                    "county_fips": geography.get("county_fips"),
                    "county_subdivision": geography.get("county_subdivision"),
                    "place": geography.get("place"),
                    "municipality": geography.get("municipality"),
                    "congressional_district": geography.get("congressional_district"),
                    "state_legislative_district": geography.get(
                        "state_legislative_district"
                    ),
                    "tract": geography.get("tract"),
                    "voting_district": geography.get("voting_district"),
                    "vintage": geography.get("vintage") or "",
                },
                "target_population": int(manifest.get("target_population") or 0),
                "representative_cells": int(
                    manifest.get("representative_cells")
                    or summary.get("representative_cells")
                    or 0
                ),
                "reasoning_calls": int(manifest.get("reasoning_calls") or 0),
                "validated": validated,
                "runnable": validated and has_cells,
                "demographics": summary.get("demographics") if has_cells else [],
                "disclosure": (
                    "Weighted synthetic population; not actual residents and not "
                    "behavioral validation."
                ),
            }
        )
    return profiles


def weighted_persona_catalog(
    epoch_id: str,
    population_id: str,
    n_agents: int,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Systematically sample weighted cells into an explicit, non-inferred panel."""
    if not 1 <= int(n_agents) <= 100:
        raise PopulationProfileError("population swarm must contain 1 to 100 agents")
    directory, manifest = load_population_profile(epoch_id, population_id, root=root)
    total = float(
        manifest.get("represented_population") or manifest.get("target_population") or 0
    )
    if total <= 0:
        raise PopulationProfileError("representative cells have no positive population weight")
    targets = [(index + 0.5) * total / n_agents for index in range(n_agents)]
    sampled: list[dict[str, str]] = []
    cumulative = 0.0
    target_index = 0
    last_positive: dict[str, str] | None = None
    for row in _cell_rows(directory):
        try:
            weight = float(row.get("population_weight") or 0)
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            continue
        last_positive = row
        cumulative += weight
        while target_index < len(targets) and targets[target_index] <= cumulative:
            sampled.append(row)
            target_index += 1
        if target_index == len(targets):
            break
    if last_positive is None:
        raise PopulationProfileError("representative cells have no positive population weight")
    while len(sampled) < n_agents:
        sampled.append(last_positive)

    geography = manifest.get("geography") or {}
    label = str(geography.get("label") or population_id)
    state_fips = str(geography.get("state_fips") or "").zfill(2)
    region = STATE_REGIONS.get(state_fips, "unspecified")
    personas = []
    for index, row in enumerate(sampled):
        age = str(row.get("age_band") or "unspecified").replace("_", "-")
        if age == "65-plus":
            age = "65+"
        education = str(row.get("education") or "unspecified")
        cell_id = str(row.get("cell_id") or f"cell-{index:03d}")
        personas.append(
            {
                "id": f"{population_id}-weighted-{index:03d}",
                "slot": index,
                "label": f"{label} weighted cell {index + 1}: {age}, {education.replace('_', ' ')}",
                "region": region,
                "urbanicity": "unspecified",
                "party_id": "unspecified",
                "age_band": age,
                "education": education,
                "media_diet": [],
                "extra": {
                    "population_id": population_id,
                    "cell_id": cell_id,
                    "census_sex": str(row.get("census_sex") or "unspecified"),
                    "race_ethnicity": str(row.get("race_ethnicity") or "unspecified"),
                    "citizenship": str(row.get("citizenship") or "unspecified"),
                    "household_income_band": str(
                        row.get("household_income_band") or "unspecified"
                    ),
                    "sampling": "systematic probability proportional to population weight",
                },
                "notes": (
                    "Synthetic distributional role. Party, media diet, and urbanicity are "
                    "unspecified rather than inferred from demographic attributes."
                ),
            }
        )
    return {
        "name": f"{population_id}-weighted-{n_agents}",
        "simulation_only": True,
        "not_inferred": True,
        "notes": (
            f"{n_agents} deterministic weighted cells from {population_id}. "
            "This reproduces available synthetic demographic marginals, not political behavior."
        ),
        "personas": personas,
    }
