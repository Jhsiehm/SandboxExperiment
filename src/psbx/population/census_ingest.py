"""Normalize the pinned e2012 Census pack and build state-scale weighted populations.

The production path deliberately keeps represented residents as integer-weighted cells.  It never
expands a state into one CSV row per resident and it never copies PUMS serial numbers into a runtime
artifact. Person, household, and CVAP universes remain separate throughout the pipeline.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import zipfile
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from psbx.paths import repo_root

from .census_sync import ACS_SEQUENCES, AREAS, CensusArea
from .compress import allocate_reasoning_budget, compress_weighted_population
from .constraints import load_constraints, validate_constraints
from .integerize import balance_integer_margins, integerize_weights
from .registry import sha256_file
from .schemas import GeographySpec, PopulationBuildManifest, PopulationSpec
from .synthesize import rake_donors
from .validate import validate_weighted_population
from .variables import canonicalize_donors

DEFAULT_CENSUS_ROOT = Path("data/population-input/e2012/census")
DEFAULT_NORMALIZED_ROOT = Path("data/population-input/e2012/normalized")
DEFAULT_POPULATION_ROOT = Path("data/population")
NATIONAL_AREA = CensusArea("00", "us", "United States")
NORMALIZER_VERSION = 4
BUILDER_VERSION = 3

# Zero-based columns verified against the official 2010 5-year Summary File Seq*.xls templates.
# The selected ranges are contiguous; the first six sequence-file fields are metadata.
ACS_TABLE_LAYOUTS: dict[int, dict[str, tuple[int, int]]] = {
    10: {"B01001": (6, 49)},
    13: {"B03002": (37, 21)},
    17: {"B05001": (6, 6)},
    33: {"B11016": (150, 16)},
    35: {"B12001": (6, 19)},
    40: {"B15001": (6, 83), "B15002": (89, 35)},
    53: {"B19001": (6, 17)},
    69: {"B23001": (6, 173)},
    95: {"B25003": (10, 3)},
}

TABLE_UNIVERSES = {
    "B01001": "total population",
    "B03002": "total population",
    "B05001": "total population",
    "B11016": "households",
    "B12001": "population 15 years and over",
    "B15001": "population 18 years and over",
    "B15002": "population 25 years and over",
    "B19001": "households",
    "B23001": "population 16 years and over",
    "B25003": "occupied housing units",
}

PERSON_CELL_FIELDS = [
    "age_band",
    "census_sex",
    "race_ethnicity",
    "citizenship",
    "education",
    "household_income_band",
    "employment",
    "tenure",
    "marital_status",
    "household_size",
]
HOUSEHOLD_CELL_FIELDS = ["household_size", "household_income_band", "tenure"]


class _DigestSession:
    """Explicit, operation-scoped digest reuse for immutable batch inputs.

    Callers may share a session only while they own a top-level operation whose raw
    input directory is treated as immutable. Independent verification calls never
    receive a session and therefore always read the complete file again.
    """

    def __init__(self) -> None:
        self._digests: dict[Path, str] = {}

    def sha256(self, path: Path) -> str:
        resolved = path.resolve()
        digest = self._digests.get(resolved)
        if digest is None:
            digest = sha256_file(resolved)
            self._digests[resolved] = digest
        return digest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def _single_member(archive: zipfile.ZipFile, suffix: str) -> str:
    members = [name for name in archive.namelist() if name.lower().endswith(suffix.lower())]
    if len(members) != 1:
        raise ValueError(
            f"expected one ZIP member ending in {suffix!r}, found {len(members)}"
        )
    return members[0]


def _raw_manifest(census_root: Path) -> dict[str, Any]:
    payload = json.loads((census_root / "manifest.json").read_text(encoding="utf-8"))
    if not payload.get("passed"):
        raise ValueError("Census input manifest has not passed ZIP/checksum verification")
    return payload


def _artifact_index(census_root: Path) -> dict[str, dict[str, Any]]:
    manifest = _raw_manifest(census_root)
    return {
        str(row["artifact_id"]): row
        for row in manifest.get("artifacts", [])
        if isinstance(row, dict) and row.get("artifact_id")
    }


def _input_artifact_ids(area: CensusArea, *, include_pums: bool) -> list[str]:
    abbr = area.abbreviation
    ids = [f"acs5-{abbr}-seq-{sequence:04d}" for sequence in ACS_SEQUENCES]
    ids.append(f"decennial-dp-{abbr}")
    if include_pums:
        ids.extend([f"pums-person-{abbr}", f"pums-housing-{abbr}"])
    ids.extend(["acs5-geography-files", "acs5-summary-templates", "cvap-2006-2010"])
    return ids


def _cached_sha256(path: Path, *, session: _DigestSession | None = None) -> str:
    """Return a SHA-256 without treating filesystem metadata as content identity.

    The legacy name is retained for internal compatibility. With no explicit batch
    session this is an authoritative verification and re-reads every byte. A session
    is an opt-in performance boundary for one controlled batch whose source tree is
    not modified during the operation; it must never outlive that operation.
    """
    if session is not None:
        return session.sha256(path)
    return sha256_file(path)


def _verified_area_artifacts(
    census_root: Path,
    area: CensusArea,
    *,
    digest_session: _DigestSession | None = None,
) -> list[dict[str, Any]]:
    """Verify the current bytes and cutoff status before any derived file is written."""
    index = _artifact_index(census_root)
    artifact_ids = _input_artifact_ids(area, include_pums=area.abbreviation != "us")
    missing = [artifact_id for artifact_id in artifact_ids if artifact_id not in index]
    if missing:
        raise ValueError("raw manifest missing required artifacts: " + ", ".join(missing))
    cutoff = date(2012, 6, 30)
    verified: list[dict[str, Any]] = []
    root = census_root.resolve()
    for artifact_id in artifact_ids:
        artifact = index[artifact_id]
        release_value = artifact.get("release_date")
        try:
            release_date = date.fromisoformat(str(release_value))
        except ValueError as exc:
            raise ValueError(f"artifact has invalid release date: {artifact_id}") from exc
        if not artifact.get("release_verified") or release_date > cutoff:
            raise ValueError(f"artifact is not cutoff-approved: {artifact_id}")
        if artifact.get("status") not in {"downloaded", "existing_verified"}:
            raise ValueError(f"artifact is not checksum-ready: {artifact_id}")
        expected = str(artifact.get("sha256") or "")
        if len(expected) != 64:
            raise ValueError(f"artifact is missing SHA-256: {artifact_id}")
        relative_path = artifact.get("relative_path")
        if not relative_path:
            raise ValueError(f"artifact is missing its relative path: {artifact_id}")
        local_path = (census_root / str(relative_path)).resolve()
        if not local_path.is_relative_to(root):
            raise ValueError(f"artifact path escapes Census root: {artifact_id}")
        if not local_path.is_file():
            raise FileNotFoundError(local_path)
        try:
            with zipfile.ZipFile(local_path) as archive:
                archive.infolist()
        except zipfile.BadZipFile as exc:
            raise ValueError(f"artifact is not a readable ZIP: {artifact_id}") from exc
        actual = _cached_sha256(local_path, session=digest_session)
        if actual != expected:
            raise ValueError(f"artifact checksum mismatch: {artifact_id}")
        verified.append(
            {
                "artifact_id": artifact_id,
                "source_id": artifact.get("source_id"),
                "provider": "United States Census Bureau",
                "title": artifact_id,
                "url": artifact.get("url"),
                "filename": Path(str(relative_path)).name,
                "relative_path": str(relative_path),
                "sha256": actual,
                "bytes": local_path.stat().st_size,
                "downloaded_at": artifact.get("downloaded_at"),
                "release_date": release_date.isoformat(),
                "release_verified": True,
                "geography_id": artifact.get("geography_id"),
                "geography_vintage": "2010",
                "family": artifact.get("family"),
                "zone": "population_build",
                "access": "public",
                "license": "United States Census Bureau public data; see source terms",
            }
        )
    return verified


def _geography_record(census_root: Path, area: CensusArea) -> dict[str, str]:
    path = census_root / "raw/acs5-summary/support/2010_ACS_Geography_Files.zip"
    member = f"geog/g20105{area.abbreviation}.csv"
    target_level = "010" if area.abbreviation == "us" else "040"
    with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""))
        for row in reader:
            if len(row) < 50:
                continue
            if row[2] == target_level and row[3] == "00":
                if area.abbreviation != "us" and row[9] != area.fips:
                    continue
                return {
                    "sumlevel": row[2],
                    "component": row[3],
                    "logical_record_number": row[4],
                    "geoid": row[48],
                    "name": row[49],
                }
    raise ValueError(f"state/national total geography record not found for {area.abbreviation}")


def _number(value: str) -> float | None:
    value = value.strip()
    if not value or value in {".", "-", "null"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_acs_table_facts(census_root: Path, area: CensusArea) -> pd.DataFrame:
    """Read selected estimate and 90% MOE cells for the state/national total record."""
    geography = _geography_record(census_root, area)
    logrecno = geography["logical_record_number"]
    records: list[dict[str, Any]] = []
    abbr = area.abbreviation
    for sequence, tables in ACS_TABLE_LAYOUTS.items():
        path = census_root / f"raw/acs5-summary/{abbr}/20105{abbr}{sequence:04d}000.zip"
        with zipfile.ZipFile(path) as archive:
            estimate_candidates = [
                name for name in archive.namelist() if name.rsplit("/", 1)[-1].startswith("e")
            ]
            moe_candidates = [
                name for name in archive.namelist() if name.rsplit("/", 1)[-1].startswith("m")
            ]
            if len(estimate_candidates) != 1 or len(moe_candidates) != 1:
                raise ValueError(f"ACS sequence archive has unexpected members: {path}")
            estimate_row = _sequence_row(archive, estimate_candidates[0], logrecno)
            moe_row = _sequence_row(archive, moe_candidates[0], logrecno)
        for table_id, (start, count) in tables.items():
            for offset in range(count):
                variable_id = f"{table_id}_{offset + 1:03d}"
                records.append(
                    {
                        "geography_id": geography["geoid"],
                        "geography_name": geography["name"],
                        "table_id": table_id,
                        "variable_id": variable_id,
                        "estimate": _number(estimate_row[start + offset]),
                        "moe90": _number(moe_row[start + offset]),
                        "universe": TABLE_UNIVERSES[table_id],
                        "sequence": sequence,
                        "source_id": "acs5_2006_2010",
                        "artifact_id": f"acs5-{abbr}-seq-{sequence:04d}",
                        "reference_period": "2006-2010",
                        "release_date": "2011-12-08",
                        "geography_vintage": "2010",
                    }
                )
    return pd.DataFrame(records)


def _sequence_row(
    archive: zipfile.ZipFile, member: str, logical_record_number: str
) -> list[str]:
    with archive.open(member) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        for row in reader:
            if len(row) >= 6 and row[5] == logical_record_number:
                return row
    raise ValueError(f"logical record {logical_record_number} not found in {member}")


def _fact_maps(facts: pd.DataFrame) -> tuple[dict[str, float], dict[str, float]]:
    estimates: dict[str, float] = {}
    moes: dict[str, float] = {}
    for row in facts.to_dict(orient="records"):
        variable = str(row["variable_id"])
        if row["estimate"] is not None and not pd.isna(row["estimate"]):
            estimates[variable] = float(row["estimate"])
        if row["moe90"] is not None and not pd.isna(row["moe90"]):
            moes[variable] = float(row["moe90"])
    return estimates, moes


def _derived_constraint(
    dimension: str,
    category: str,
    variables: Iterable[str],
    estimates: dict[str, float],
    moes: dict[str, float],
    *,
    universe: str,
) -> dict[str, Any]:
    variables = list(variables)
    missing = [variable for variable in variables if variable not in estimates]
    if missing:
        raise ValueError("missing ACS estimate cells: " + ", ".join(missing))
    return {
        "dimension": dimension,
        "category": category,
        "target_count": float(sum(estimates[variable] for variable in variables)),
        "source_id": "acs5_2006_2010",
        "universe": universe,
        "role": "raking",
        "moe90": math.sqrt(sum(moes.get(variable, 0.0) ** 2 for variable in variables)),
        "table_id": variables[0].split("_", 1)[0],
        "variable_ids": "|".join(variables),
        "transformation": (
            "direct published cell" if len(variables) == 1 else "sum; MOE=root-sum-square"
        ),
        "reference_period": "2006-2010",
        "release_date": "2011-12-08",
        "geography_vintage": "2010",
        "notes": "ACS estimates and 90% margins of error retained before integerization",
    }


def derive_person_constraints(facts: pd.DataFrame) -> pd.DataFrame:
    estimates, moes = _fact_maps(facts)
    rows: list[dict[str, Any]] = []
    age_groups = {
        "under_18": [*range(3, 7), *range(27, 31)],
        "18_24": [*range(7, 11), *range(31, 35)],
        "25_34": [11, 12, 35, 36],
        "35_44": [13, 14, 37, 38],
        "45_54": [15, 16, 39, 40],
        "55_64": [17, 18, 19, 41, 42, 43],
        "65_plus": [*range(20, 26), *range(44, 50)],
    }
    for category, cells in age_groups.items():
        rows.append(
            _derived_constraint(
                "age_band",
                category,
                (f"B01001_{cell:03d}" for cell in cells),
                estimates,
                moes,
                universe="all_residents",
            )
        )
    for category, cell in {"male": 2, "female": 26}.items():
        rows.append(
            _derived_constraint(
                "census_sex",
                category,
                [f"B01001_{cell:03d}"],
                estimates,
                moes,
                universe="all_residents",
            )
        )
    race_cells = {
        "white_non_hispanic": 3,
        "black_non_hispanic": 4,
        "american_indian_alaska_native_non_hispanic": 5,
        "asian_non_hispanic": 6,
        "native_hawaiian_pacific_islander_non_hispanic": 7,
        "other_non_hispanic": 8,
        "two_or_more_non_hispanic": 9,
        "hispanic_any_race": 12,
    }
    for category, cell in race_cells.items():
        rows.append(
            _derived_constraint(
                "race_ethnicity",
                category,
                [f"B03002_{cell:03d}"],
                estimates,
                moes,
                universe="all_residents",
            )
        )
    rows.append(
        _derived_constraint(
            "citizenship",
            "citizen",
            (f"B05001_{cell:03d}" for cell in range(2, 6)),
            estimates,
            moes,
            universe="all_residents",
        )
    )
    rows.append(
        _derived_constraint(
            "citizenship",
            "noncitizen",
            ["B05001_006"],
            estimates,
            moes,
            universe="all_residents",
        )
    )
    return pd.DataFrame(rows)


def derive_household_constraints(facts: pd.DataFrame) -> pd.DataFrame:
    estimates, moes = _fact_maps(facts)
    rows: list[dict[str, Any]] = []
    size_cells = {
        "1": [10],
        "2": [3, 11],
        "3": [4, 12],
        "4": [5, 13],
        "5": [6, 14],
        "6": [7, 15],
        "7_plus": [8, 16],
    }
    for category, cells in size_cells.items():
        rows.append(
            _derived_constraint(
                "household_size",
                category,
                (f"B11016_{cell:03d}" for cell in cells),
                estimates,
                moes,
                universe="households",
            )
        )
    income_cells = {
        "under_25k": [2, 3, 4, 5],
        "25k_49k": [6, 7, 8, 9, 10],
        "50k_74k": [11, 12],
        "75k_99k": [13],
        "100k_149k": [14, 15],
        "150k_199k": [16],
        "200k_plus": [17],
    }
    for category, cells in income_cells.items():
        rows.append(
            _derived_constraint(
                "household_income_band",
                category,
                (f"B19001_{cell:03d}" for cell in cells),
                estimates,
                moes,
                universe="households",
            )
        )
    for category, cell in {"owner": 2, "renter": 3}.items():
        rows.append(
            _derived_constraint(
                "tenure",
                category,
                [f"B25003_{cell:03d}"],
                estimates,
                moes,
                universe="households",
            )
        )
    return pd.DataFrame(rows)


def read_cvap_facts(census_root: Path, area: CensusArea) -> pd.DataFrame:
    path = census_root / "raw/cvap/CVAP_2006-2010_ACS_csv_files.zip"
    member = "CVAP Files/Nation.csv" if area.abbreviation == "us" else "CVAP Files/State.csv"
    with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
        frame = pd.read_csv(raw)
    geoid = "01000US" if area.abbreviation == "us" else f"04000US{area.fips}"
    selected = frame.loc[frame["GEOID"].astype(str) == geoid].copy()
    if selected.empty:
        raise ValueError(f"CVAP rows not found for {geoid}")
    selected["source_id"] = "cvap_2006_2010"
    selected["artifact_id"] = "cvap-2006-2010"
    selected["reference_period"] = "2006-2010"
    selected["release_date"] = "2012-02-09"
    selected["geography_vintage"] = "2010"
    selected["universe_note"] = (
        "TOT total; ADU age 18+; CIT citizens; CVAP citizen voting age. "
        "These denominators are not person-raking substitutes."
    )
    return selected


def read_decennial_dp_total(census_root: Path, area: CensusArea) -> int:
    abbr = area.abbreviation
    path = census_root / f"raw/decennial-dp/{abbr}/{abbr}2010.dp.zip"
    with zipfile.ZipFile(path) as archive:
        member = f"{abbr}000012010.dp"
        with archive.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for row in reader:
                if len(row) > 5 and row[4] == "0000001":
                    return int(float(row[5]))
    raise ValueError(f"DP-1 total record not found for {abbr}")


def _household_size(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    result = pd.Series("unknown", index=values.index, dtype="object")
    for size in range(1, 7):
        result.loc[numeric == size] = str(size)
    result.loc[numeric >= 7] = "7_plus"
    return result


def _household_income(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    result = pd.Series("unavailable", index=values.index, dtype="object")
    bounds = [
        (numeric < 25_000, "under_25k"),
        ((numeric >= 25_000) & (numeric < 50_000), "25k_49k"),
        ((numeric >= 50_000) & (numeric < 75_000), "50k_74k"),
        ((numeric >= 75_000) & (numeric < 100_000), "75k_99k"),
        ((numeric >= 100_000) & (numeric < 150_000), "100k_149k"),
        ((numeric >= 150_000) & (numeric < 200_000), "150k_199k"),
        (numeric >= 200_000, "200k_plus"),
    ]
    for mask, label in bounds:
        result.loc[mask] = label
    return result


def _adjusted_income(values: pd.Series, factors: pd.Series) -> pd.Series:
    """Convert 5-year PUMS dollar values to the file's constant-dollar basis."""
    income = pd.to_numeric(values, errors="coerce")
    adjustment = pd.to_numeric(factors, errors="coerce") / 1_000_000
    return income * adjustment


def _household_tenure(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.map({1: "owner", 2: "owner", 3: "renter", 4: "renter"}).fillna(
        "unknown"
    )


def aggregate_pums_cells(
    census_root: Path,
    area: CensusArea,
    *,
    chunksize: int = 200_000,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Join safe PUMS attributes and aggregate them without retaining row identifiers."""
    abbr = area.abbreviation
    housing_path = census_root / f"raw/pums/{abbr}/csv_h{abbr}.zip"
    person_path = census_root / f"raw/pums/{abbr}/csv_p{abbr}.zip"
    with zipfile.ZipFile(housing_path) as archive:
        with archive.open(_single_member(archive, ".csv")) as raw:
            housing = pd.read_csv(
                raw,
                usecols=["SERIALNO", "WGTP", "NP", "TEN", "HINCP", "ADJINC"],
                dtype={"SERIALNO": "string"},
                low_memory=False,
            )
    housing["HINCP"] = _adjusted_income(housing["HINCP"], housing["ADJINC"])
    housing["household_size"] = _household_size(housing["NP"])
    housing["household_income_band"] = _household_income(housing["HINCP"])
    housing["tenure"] = _household_tenure(housing["TEN"])
    household_cells = (
        housing.groupby(HOUSEHOLD_CELL_FIELDS, dropna=False, sort=True)["WGTP"]
        .sum()
        .rename("donor_weight")
        .reset_index()
    )
    household_cells = household_cells.loc[household_cells["donor_weight"] > 0]
    join = housing[["SERIALNO", "NP", "TEN", "HINCP"]]
    person_groups: list[pd.DataFrame] = []
    person_rows = 0
    columns = [
        "SERIALNO",
        "PWGTP",
        "AGEP",
        "CIT",
        "MAR",
        "SCHL",
        "SEX",
        "ESR",
        "HISP",
        "RAC1P",
    ]
    with zipfile.ZipFile(person_path) as archive:
        with archive.open(_single_member(archive, ".csv")) as raw:
            chunks = pd.read_csv(
                raw,
                usecols=columns,
                dtype={"SERIALNO": "string"},
                chunksize=chunksize,
                low_memory=False,
            )
            for chunk in chunks:
                person_rows += len(chunk)
                merged = chunk.merge(join, on="SERIALNO", how="left", validate="many_to_one")
                canonical = canonicalize_donors(merged)
                canonical["household_size"] = _household_size(merged["NP"])
                grouped = (
                    canonical.groupby(
                        PERSON_CELL_FIELDS, dropna=False, sort=False
                    )["donor_weight"]
                    .sum()
                    .reset_index()
                )
                person_groups.append(grouped)
    person_cells = (
        pd.concat(person_groups, ignore_index=True)
        .groupby(PERSON_CELL_FIELDS, dropna=False, sort=True)["donor_weight"]
        .sum()
        .reset_index()
    )
    person_cells = person_cells.loc[person_cells["donor_weight"] > 0].reset_index(drop=True)
    household_cells = household_cells.reset_index(drop=True)
    return person_cells, household_cells, {
        "raw_person_rows": person_rows,
        "raw_housing_rows": len(housing),
        "person_donor_cells": len(person_cells),
        "household_donor_cells": len(household_cells),
    }


def _totals(frame: pd.DataFrame) -> dict[str, float]:
    return {
        str(dimension): float(group["target_count"].sum())
        for dimension, group in frame.groupby("dimension")
    }


def _manifest_outputs_valid(directory: Path, manifest_name: str) -> bool:
    path = directory / manifest_name
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not payload.get("passed"):
        return False
    for name, expected in (payload.get("output_sha256") or {}).items():
        candidate = directory / name
        if not candidate.is_file() or sha256_file(candidate) != expected:
            return False
    return bool(payload.get("output_sha256"))


def _normalized_inputs_current(
    destination: Path,
    census_root: Path,
    area: CensusArea,
    *,
    verified_artifacts: list[dict[str, Any]] | None = None,
) -> bool:
    if not _manifest_outputs_valid(destination, "normalized_manifest.json"):
        return False
    payload = json.loads(
        (destination / "normalized_manifest.json").read_text(encoding="utf-8")
    )
    if payload.get("normalizer_version") != NORMALIZER_VERSION:
        return False
    acquisition_manifest = census_root / "manifest.json"
    if payload.get("acquisition_manifest_sha256") != _cached_sha256(acquisition_manifest):
        return False
    source_registry = repo_root() / "config/population_sources.yaml"
    if not source_registry.is_file():
        raise FileNotFoundError(
            f"required population source registry is missing: {source_registry}"
        )
    if payload.get("source_registry_sha256") != sha256_file(source_registry):
        return False
    recorded = {
        str(row.get("artifact_id")): str(row.get("sha256"))
        for row in payload.get("artifacts", [])
        if isinstance(row, dict)
    }
    verified_artifacts = verified_artifacts or _verified_area_artifacts(census_root, area)
    return all(
        recorded.get(str(artifact["artifact_id"])) == str(artifact["sha256"])
        for artifact in verified_artifacts
    )


def _state_inputs_current(
    output: Path,
    normalized: Path,
    *,
    expected_seed: int,
    expected_reasoning_budget: int,
) -> bool:
    if not _manifest_outputs_valid(output, "manifest.json"):
        return False
    payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if payload.get("builder_version") != BUILDER_VERSION:
        return False
    if payload.get("seed") != expected_seed:
        return False
    if payload.get("reasoning_calls") != expected_reasoning_budget:
        return False
    recorded = payload.get("input_sha256") or {}
    inputs = (
        "normalized_manifest.json",
        "person_constraints.csv",
        "household_constraints.csv",
        "person_donor_cells.csv",
        "household_donor_cells.csv",
    )
    return all(
        (normalized / name).is_file()
        and recorded.get(name) == sha256_file(normalized / name)
        for name in inputs
    )


def _national_inputs_current(
    output: Path,
    population_root: Path,
    normalized_root: Path,
    *,
    expected_reasoning_budget: int,
) -> bool:
    if not _manifest_outputs_valid(output, "manifest.json"):
        return False
    payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if payload.get("builder_version") != BUILDER_VERSION:
        return False
    if payload.get("reasoning_calls") != expected_reasoning_budget:
        return False
    recorded = payload.get("input_sha256") or {}
    national_normalization = normalized_root / "us/normalized_manifest.json"
    if (
        not national_normalization.is_file()
        or recorded.get("national-normalization")
        != sha256_file(national_normalization)
    ):
        return False
    for area in AREAS:
        state_id = f"state-{area.abbreviation}-e2012"
        path = population_root / "e2012" / state_id / "manifest.json"
        if not path.is_file() or recorded.get(state_id) != sha256_file(path):
            return False
    return True


def normalize_census_area(
    area: CensusArea,
    *,
    census_root: str | Path = DEFAULT_CENSUS_ROOT,
    normalized_root: str | Path = DEFAULT_NORMALIZED_ROOT,
    force: bool = False,
    _digest_session: _DigestSession | None = None,
) -> dict[str, Any]:
    census_root = Path(census_root)
    destination = Path(normalized_root) / area.abbreviation
    source_registry = repo_root() / "config/population_sources.yaml"
    if not source_registry.is_file():
        raise FileNotFoundError(
            f"required population source registry is missing: {source_registry}"
        )
    verified_artifacts = _verified_area_artifacts(
        census_root, area, digest_session=_digest_session
    )
    if not force and _normalized_inputs_current(
        destination,
        census_root,
        area,
        verified_artifacts=verified_artifacts,
    ):
        return {
            "area": area.abbreviation,
            "status": "skipped_valid",
            "output_dir": str(destination),
        }
    facts = read_acs_table_facts(census_root, area)
    person_constraints = derive_person_constraints(facts)
    household_constraints = derive_household_constraints(facts)
    cvap = read_cvap_facts(census_root, area)
    dp_total = read_decennial_dp_total(census_root, area)
    counts: dict[str, int] = {}
    if area.abbreviation != "us":
        person_cells, household_cells, counts = aggregate_pums_cells(census_root, area)
        _atomic_csv(destination / "person_donor_cells.csv", person_cells)
        _atomic_csv(destination / "household_donor_cells.csv", household_cells)
    _atomic_csv(destination / "acs_table_facts.csv", facts)
    _atomic_csv(destination / "person_constraints.csv", person_constraints)
    _atomic_csv(destination / "household_constraints.csv", household_constraints)
    _atomic_csv(destination / "cvap_facts.csv", cvap)
    person_totals = _totals(person_constraints)
    household_totals = _totals(household_constraints)
    target = int(round(person_totals["age_band"]))
    summary = {
        "area": area.abbreviation,
        "state_fips": area.fips,
        "label": area.name,
        "person_target_source": "ACS 2006-2010 B01001_001-compatible age cells",
        "person_target_population": target,
        "person_dimension_totals": person_totals,
        "household_dimension_totals": household_totals,
        "decennial_2010_dp1_total": dp_total,
        "acs_minus_decennial": target - dp_total,
        "reference_period_warning": (
            "The 2006-2010 ACS estimate and April 1, 2010 decennial count are different "
            "reference concepts; the DP total is retained as a comparison, not silently forced."
        ),
        "cvap_total": int(cvap.loc[cvap["LNNUMBER"] == 1, "CVAP_EST"].iloc[0]),
        "household_model": "separate weighted household cells; not linked to person cells",
        "dimension_status": {
            "age_band": "fitted_all_residents",
            "census_sex": "fitted_all_residents",
            "race_ethnicity": "fitted_all_residents",
            "citizenship": "fitted_all_residents",
            "education": "donor_derived_not_fitted; ACS 25+ facts retained separately",
            "employment": "donor_derived_not_fitted; ACS 16+ facts retained separately",
            "marital_status": "donor_derived_not_fitted; ACS 15+ facts retained separately",
            "household_income_band": "donor_derived_in_person_cells; fitted_household_model",
            "tenure": "donor_derived_in_person_cells; fitted_household_model",
            "household_size": "donor_derived_in_person_cells; fitted_household_model",
            "cvap": "separate_citizen_voting_age_facts_not_person_raking",
            "decennial_dp1": "comparison_total_not_acs_raking_target",
        },
        **counts,
    }
    _atomic_json(destination / "source_summary.json", summary)
    outputs = [
        "acs_table_facts.csv",
        "person_constraints.csv",
        "household_constraints.csv",
        "cvap_facts.csv",
        "source_summary.json",
    ]
    if area.abbreviation != "us":
        outputs.extend(["person_donor_cells.csv", "household_donor_cells.csv"])
    manifest = {
        "schema_version": 1,
        "normalizer_version": NORMALIZER_VERSION,
        "area": area.abbreviation,
        "state_fips": area.fips,
        "epoch_id": "e2012",
        "cutoff_date": "2012-06-30",
        "reference_period": "2006-2010",
        "geography_vintage": "2010",
        "zone": "population_build",
        "generated_at": _now(),
        "passed": True,
        "acquisition_manifest_sha256": _cached_sha256(census_root / "manifest.json"),
        "source_registry_sha256": sha256_file(source_registry),
        "release_verification_method": (
            "official historical Census URLs and release dates; exact local bytes pinned by SHA-256"
        ),
        "artifacts": verified_artifacts,
        "transformations": [
            "Official Seq*.xls offsets map ACS estimate/MOE sequence columns.",
            "Derived sums use root-sum-square 90% MOEs and retain source variable IDs.",
            "PUMS person and housing records join on SERIALNO only inside the build zone.",
            "SCHL uses the official legacy 2006-2010 PUMS codes 01 through 16.",
            "HINCP is converted with ADJINC/1,000,000 before income-band assignment.",
            "No PUMS serial number or row-level donor record is written to normalized outputs.",
            "Person, household, and CVAP universes remain separate.",
        ],
        "output_sha256": {name: sha256_file(destination / name) for name in outputs},
    }
    _atomic_json(destination / "normalized_manifest.json", manifest)
    return {
        "area": area.abbreviation,
        "status": "normalized",
        "output_dir": str(destination),
        "summary": summary,
    }


def _state_spec(area: CensusArea, target: int, *, seed: int) -> PopulationSpec:
    return PopulationSpec(
        id=f"state-{area.abbreviation}-e2012",
        epoch_id="e2012",
        cutoff_date=date(2012, 6, 30),
        geography=GeographySpec(
            id=f"state:{area.fips}",
            label=area.name,
            geography_type="state",
            state_fips=area.fips,
            vintage="2010",
        ),
        universe="all_residents",
        target_population=target,
        source_ids=[
            "census_2010_dp1",
            "acs5_2006_2010",
            "acs_pums_2006_2010",
            "cvap_2006_2010",
        ],
        constraints_path="unused",
        donors_path="unused",
        seed=seed,
        tolerance=1e-5,
        validation_tvd_tolerance=0.001,
        validation_moe_ratio_tolerance=2.0,
        profile_fields=PERSON_CELL_FIELDS,
        representative_cell_fields=PERSON_CELL_FIELDS,
    )


def _household_spec(area: CensusArea, target: int, *, seed: int) -> PopulationSpec:
    return PopulationSpec(
        id=f"state-{area.abbreviation}-households-e2012",
        epoch_id="e2012",
        cutoff_date=date(2012, 6, 30),
        geography=GeographySpec(
            id=f"state:{area.fips}",
            label=f"{area.name} households",
            geography_type="state",
            state_fips=area.fips,
            vintage="2010",
        ),
        universe="households",
        target_population=target,
        source_ids=["acs5_2006_2010", "acs_pums_2006_2010"],
        constraints_path="unused",
        donors_path="unused",
        seed=seed,
        tolerance=1e-5,
        validation_tvd_tolerance=0.001,
        validation_moe_ratio_tolerance=2.0,
        profile_fields=HOUSEHOLD_CELL_FIELDS,
        representative_cell_fields=HOUSEHOLD_CELL_FIELDS,
    )


def _integerized_cells(
    donors: pd.DataFrame,
    constraints_path: Path,
    spec: PopulationSpec,
    fields: list[str],
    *,
    reasoning_budget: int,
) -> tuple[pd.DataFrame, Any, Any]:
    constraints = load_constraints(constraints_path)
    validate_constraints(spec, constraints)
    raking = rake_donors(
        donors,
        constraints,
        target_population=spec.target_population,
        max_iterations=spec.max_iterations,
        tolerance=spec.tolerance,
    )
    counts = integerize_weights(raking.weights, spec.target_population, spec.seed)
    counts = balance_integer_margins(raking.donors, counts, constraints)
    weighted = raking.donors[fields].copy()
    weighted["population_weight"] = counts
    weighted = weighted.loc[weighted["population_weight"] > 0]
    cells = compress_weighted_population(weighted, fields)
    cells = allocate_reasoning_budget(cells, reasoning_budget)
    report = validate_weighted_population(cells, constraints, spec)
    return cells, raking, report


def build_state_population(
    area: CensusArea,
    *,
    census_root: str | Path = DEFAULT_CENSUS_ROOT,
    normalized_root: str | Path = DEFAULT_NORMALIZED_ROOT,
    population_root: str | Path = DEFAULT_POPULATION_ROOT,
    seed: int = 20120630,
    reasoning_budget: int = 100,
    force: bool = False,
    _digest_session: _DigestSession | None = None,
) -> dict[str, Any]:
    normalized = Path(normalized_root) / area.abbreviation
    verified_artifacts = _verified_area_artifacts(
        Path(census_root), area, digest_session=_digest_session
    )
    if not _normalized_inputs_current(
        normalized,
        Path(census_root),
        area,
        verified_artifacts=verified_artifacts,
    ):
        raise ValueError(
            f"current verified normalization required before state build: {area.abbreviation}"
        )
    summary = json.loads((normalized / "source_summary.json").read_text(encoding="utf-8"))
    target = int(summary["person_target_population"])
    spec = _state_spec(area, target, seed=seed + int(area.fips))
    output = Path(population_root) / "e2012" / spec.id
    if not force and _state_inputs_current(
        output,
        normalized,
        expected_seed=spec.seed,
        expected_reasoning_budget=reasoning_budget,
    ):
        return {"area": area.abbreviation, "status": "skipped_valid", "output_dir": str(output)}
    donors = pd.read_csv(normalized / "person_donor_cells.csv")
    cells, raking, report = _integerized_cells(
        donors,
        normalized / "person_constraints.csv",
        spec,
        PERSON_CELL_FIELDS,
        reasoning_budget=reasoning_budget,
    )
    cells["cell_id"] = area.abbreviation + "-" + cells["cell_id"].astype(str)
    cells.insert(1, "state_fips", area.fips)
    cells.insert(2, "state_abbreviation", area.abbreviation.upper())
    _atomic_csv(output / "representative_cells.csv", cells)
    _atomic_csv(
        output / "raking_history.csv",
        pd.DataFrame([row.model_dump(mode="json") for row in raking.history]),
    )
    _atomic_csv(
        output / "constraints_used.csv",
        pd.read_csv(normalized / "person_constraints.csv"),
    )
    _atomic_json(output / "population_validation.json", report.model_dump(mode="json"))

    household_constraints = load_constraints(normalized / "household_constraints.csv")
    household_target = int(
        round(
            sum(
                row.target_count
                for row in household_constraints
                if row.dimension == "household_size"
            )
        )
    )
    household_spec = _household_spec(area, household_target, seed=spec.seed)
    household_donors = pd.read_csv(normalized / "household_donor_cells.csv")
    household_cells, household_raking, household_report = _integerized_cells(
        household_donors,
        normalized / "household_constraints.csv",
        household_spec,
        HOUSEHOLD_CELL_FIELDS,
        reasoning_budget=0,
    )
    household_report = household_report.model_copy(
        update={
            "household_integrity": "separate_household_model",
            "notes": household_report.notes
            + ["Household cells are not linked to person cells or exposed as actual households."],
        }
    )
    _atomic_csv(output / "household_cells.csv", household_cells)
    _atomic_csv(
        output / "household_raking_history.csv",
        pd.DataFrame([row.model_dump(mode="json") for row in household_raking.history]),
    )
    _atomic_json(
        output / "household_validation.json", household_report.model_dump(mode="json")
    )
    _atomic_json(
        output / "source_summary.json",
        {
            **summary,
            "normalization_manifest_sha256": sha256_file(
                normalized / "normalized_manifest.json"
            ),
        },
    )
    input_hashes = {
        name: sha256_file(normalized / name)
        for name in (
            "normalized_manifest.json",
            "person_constraints.csv",
            "household_constraints.csv",
            "person_donor_cells.csv",
            "household_donor_cells.csv",
        )
    }
    manifest = PopulationBuildManifest(
        population_id=spec.id,
        epoch_id=spec.epoch_id,
        cutoff_date=spec.cutoff_date,
        experiment_mode=spec.experiment_mode,
        geography=spec.geography,
        universe=spec.universe,
        target_population=target,
        represented_population=target,
        synthetic_records=len(cells),
        representative_cells=len(cells),
        reasoning_calls=int(cells["reasoning_calls"].sum()),
        seed=spec.seed,
        source_ids=spec.source_ids,
        input_sha256=input_hashes,
        created_at=datetime.now(timezone.utc),
        algorithm="cell-level iterative proportional fitting plus seeded integer weights",
        representation_mode="weighted_cells",
        claims=[
            "integer weights represent population counts; rows are not actual residents",
            "PUMS identifiers and raw donor rows are absent from runtime outputs",
            "the household model is separate and not linked to person cells",
            "population fidelity does not establish political-behavior fidelity",
        ],
    )
    outputs = [
        "representative_cells.csv",
        "raking_history.csv",
        "constraints_used.csv",
        "population_validation.json",
        "household_cells.csv",
        "household_raking_history.csv",
        "household_validation.json",
        "source_summary.json",
    ]
    manifest = manifest.model_copy(
        update={"output_sha256": {name: sha256_file(output / name) for name in outputs}}
    )
    payload = manifest.model_dump(mode="json")
    payload["builder_version"] = BUILDER_VERSION
    payload["dimension_status"] = summary["dimension_status"]
    payload["passed"] = bool(report.passed and household_report.passed)
    payload["household_target"] = household_target
    payload["household_representative_cells"] = len(household_cells)
    _atomic_json(output / "manifest.json", payload)
    from .profiles import write_population_profile_summary

    write_population_profile_summary(output, payload)
    return {
        "area": area.abbreviation,
        "status": "built" if payload["passed"] else "validation_failed",
        "output_dir": str(output),
        "manifest": payload,
        "validation": report.model_dump(mode="json"),
        "household_validation": household_report.model_dump(mode="json"),
    }


def build_national_aggregate(
    *,
    normalized_root: str | Path = DEFAULT_NORMALIZED_ROOT,
    population_root: str | Path = DEFAULT_POPULATION_ROOT,
    reasoning_budget: int = 250,
    force: bool = False,
) -> dict[str, Any]:
    population_root = Path(population_root)
    normalized_root = Path(normalized_root)
    output = population_root / "e2012" / "national-us-e2012"
    if not force and _national_inputs_current(
        output,
        population_root,
        normalized_root,
        expected_reasoning_budget=reasoning_budget,
    ):
        return {"area": "us", "status": "skipped_valid", "output_dir": str(output)}
    frames: list[pd.DataFrame] = []
    parents: list[str] = []
    parent_hashes: dict[str, str] = {}
    for area in AREAS:
        state_id = f"state-{area.abbreviation}-e2012"
        state_dir = population_root / "e2012" / state_id
        manifest_path = state_dir / "manifest.json"
        if not _manifest_outputs_valid(state_dir, "manifest.json"):
            raise ValueError(
                f"validated state build required before national aggregation: {state_id}"
            )
        state_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        geography = state_manifest.get("geography") or {}
        if (
            state_manifest.get("population_id") != state_id
            or state_manifest.get("epoch_id") != "e2012"
            or state_manifest.get("representation_mode") != "weighted_cells"
            or geography.get("id") != f"state:{area.fips}"
            or geography.get("state_fips") != area.fips
        ):
            raise ValueError(f"state parent manifest contract mismatch: {state_id}")
        frames.append(
            pd.read_csv(
                state_dir / "representative_cells.csv",
                dtype={"state_fips": str},
            )
        )
        parents.append(state_id)
        parent_hashes[state_id] = sha256_file(manifest_path)
    cells = pd.concat(frames, ignore_index=True)
    if not cells["cell_id"].is_unique:
        raise ValueError("national aggregate requires globally unique state cell IDs")
    total = int(cells["population_weight"].sum())
    cells["population_share"] = cells["population_weight"] / total
    cells = cells.drop(columns=["reasoning_calls"], errors="ignore")
    cells = allocate_reasoning_budget(cells, reasoning_budget)
    _atomic_csv(output / "representative_cells.csv", cells)
    national_summary = json.loads(
        (normalized_root / "us/source_summary.json").read_text(encoding="utf-8")
    )
    published = int(national_summary["person_target_population"])
    validation = {
        "population_id": "national-us-e2012",
        "epoch_id": "e2012",
        "geography_id": "us:1",
        "universe": "all_residents",
        "target_population": total,
        "actual_population": total,
        "passed": True,
        "state_builds": len(AREAS),
        "state_sum": total,
        "published_national_acs_estimate": published,
        "state_sum_minus_published_national": total - published,
        "consistency_rule": (
            "National runtime population is the exact union of validated state cells."
        ),
        "notes": [
            "Published national and independently published state ACS estimates may differ "
            "slightly.",
            "Rows are weighted synthetic cells, not actual residents.",
            "Population fidelity does not establish political-behavior fidelity.",
        ],
    }
    _atomic_json(output / "population_validation.json", validation)
    geography = GeographySpec(
        id="us:1",
        label="United States",
        geography_type="custom",
        state_fips="00",
        vintage="2010",
    )
    manifest = PopulationBuildManifest(
        population_id="national-us-e2012",
        epoch_id="e2012",
        cutoff_date=date(2012, 6, 30),
        experiment_mode="sealed_forecast",
        geography=geography,
        universe="all_residents",
        target_population=total,
        represented_population=total,
        synthetic_records=len(cells),
        representative_cells=len(cells),
        reasoning_calls=int(cells["reasoning_calls"].sum()),
        seed=20120630,
        source_ids=[
            "census_2010_dp1",
            "acs5_2006_2010",
            "acs_pums_2006_2010",
            "cvap_2006_2010",
        ],
        input_sha256={
            **parent_hashes,
            "national-normalization": sha256_file(
                normalized_root / "us/normalized_manifest.json"
            ),
        },
        created_at=datetime.now(timezone.utc),
        algorithm="exact union of 51 validated state/D.C. weighted-cell populations",
        representation_mode="weighted_cells",
        parent_population_ids=parents,
        claims=[
            "national weights are an exact aggregate of the state and D.C. builds",
            "rows are weighted synthetic cells, not actual residents",
            "population fidelity does not establish political-behavior fidelity",
        ],
    )
    outputs = ["representative_cells.csv", "population_validation.json"]
    manifest = manifest.model_copy(
        update={"output_sha256": {name: sha256_file(output / name) for name in outputs}}
    )
    payload = manifest.model_dump(mode="json")
    payload["builder_version"] = BUILDER_VERSION
    payload["passed"] = True
    payload["published_national_acs_estimate"] = published
    payload["state_sum_minus_published_national"] = total - published
    _atomic_json(output / "manifest.json", payload)
    from .profiles import write_population_profile_summary

    write_population_profile_summary(output, payload)
    return {
        "area": "us",
        "status": "built",
        "output_dir": str(output),
        "manifest": payload,
        "validation": validation,
    }


def parse_area_selection(value: str) -> list[CensusArea]:
    requested = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not requested or requested == ["all"]:
        return list(AREAS)
    by_abbreviation = {area.abbreviation: area for area in AREAS}
    by_fips = {area.fips: area for area in AREAS}
    selected: list[CensusArea] = []
    for token in requested:
        area = by_abbreviation.get(token) or by_fips.get(token.zfill(2))
        if area is None:
            raise ValueError(f"unknown state/D.C. area: {token}")
        if area not in selected:
            selected.append(area)
    return selected


def run_census_population_batch(
    *,
    areas: Iterable[CensusArea] = AREAS,
    census_root: str | Path = DEFAULT_CENSUS_ROOT,
    normalized_root: str | Path = DEFAULT_NORMALIZED_ROOT,
    population_root: str | Path = DEFAULT_POPULATION_ROOT,
    seed: int = 20120630,
    reasoning_budget: int = 100,
    force: bool = False,
    progress: Callable[[str, CensusArea, int, int], None] | None = None,
) -> dict[str, Any]:
    selected = list(areas)
    # Raw Census inputs are read-only for this command. Reuse their verified hashes
    # only inside this batch so shared support archives are not re-read for every
    # state. A new invocation creates a new session and performs fresh verification.
    digest_session = _DigestSession()
    status_path = Path(normalized_root) / "batch_status.json"
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, area in enumerate(selected, start=1):
        try:
            if progress:
                progress("normalize", area, index, len(selected))
            normalized = normalize_census_area(
                area,
                census_root=census_root,
                normalized_root=normalized_root,
                force=force,
                _digest_session=digest_session,
            )
            if progress:
                progress("build", area, index, len(selected))
            built = build_state_population(
                area,
                census_root=census_root,
                normalized_root=normalized_root,
                population_root=population_root,
                seed=seed,
                reasoning_budget=reasoning_budget,
                force=force,
                _digest_session=digest_session,
            )
            if built.get("status") not in {"built", "skipped_valid"}:
                raise RuntimeError(
                    f"state build did not pass validation: {area.abbreviation}"
                )
            results.append({"area": area.abbreviation, "normalized": normalized, "built": built})
        except Exception as exc:
            failures.append({"area": area.abbreviation, "error": str(exc)})
        _atomic_json(
            status_path,
            {
                "schema_version": 1,
                "updated_at": _now(),
                "requested_areas": [row.abbreviation for row in selected],
                "completed_areas": [row["area"] for row in results],
                "failures": failures,
                "resumable": True,
                "passed": not failures and len(results) == len(selected),
            },
        )
    national: dict[str, Any] | None = None
    complete_national_scope = {area.abbreviation for area in selected} == {
        area.abbreviation for area in AREAS
    }
    if not failures and complete_national_scope:
        try:
            normalize_census_area(
                NATIONAL_AREA,
                census_root=census_root,
                normalized_root=normalized_root,
                force=force,
                _digest_session=digest_session,
            )
            national = build_national_aggregate(
                normalized_root=normalized_root,
                population_root=population_root,
                reasoning_budget=max(reasoning_budget, 250),
                force=force,
            )
            if national.get("status") not in {"built", "skipped_valid"}:
                raise RuntimeError("national aggregate did not pass validation")
        except Exception as exc:
            failures.append({"area": "us", "error": str(exc)})
    passed = not failures and len(results) == len(selected)
    _atomic_json(
        status_path,
        {
            "schema_version": 1,
            "updated_at": _now(),
            "requested_areas": [row.abbreviation for row in selected],
            "completed_areas": [row["area"] for row in results],
            "failures": failures,
            "national": None if national is None else national.get("status"),
            "resumable": True,
            "passed": passed,
        },
    )
    return {
        "requested": len(selected),
        "completed": len(results),
        "failures": failures,
        "national": national,
        "status_path": str(status_path),
        "passed": passed,
    }
