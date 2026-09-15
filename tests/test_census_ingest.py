import json
import os
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from psbx.population.census_ingest import (
    ACS_TABLE_LAYOUTS,
    BUILDER_VERSION,
    NORMALIZER_VERSION,
    _adjusted_income,
    _cached_sha256,
    _household_income,
    _household_size,
    _normalized_inputs_current,
    _state_inputs_current,
    build_national_aggregate,
    derive_household_constraints,
    derive_person_constraints,
    normalize_census_area,
    parse_area_selection,
    run_census_population_batch,
)
from psbx.population.census_sync import CensusArea
from psbx.population.compress import compress_weighted_population
from psbx.population.integerize import balance_integer_margins
from psbx.population.registry import sha256_file
from psbx.population.schemas import (
    GeographySpec,
    PopulationBuildManifest,
    PopulationConstraint,
)
from psbx.population.variables import canonicalize_donors


def _facts(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"variable_id": variable, "estimate": value, "moe90": 1.0}
            for variable, value in values.items()
        ]
    )


def test_official_sequence_layouts_cover_every_selected_table():
    assert set(ACS_TABLE_LAYOUTS) == {10, 13, 17, 33, 35, 40, 53, 69, 95}
    assert ACS_TABLE_LAYOUTS[10]["B01001"] == (6, 49)
    assert ACS_TABLE_LAYOUTS[40]["B15001"] == (6, 83)
    assert ACS_TABLE_LAYOUTS[40]["B15002"] == (89, 35)
    assert ACS_TABLE_LAYOUTS[95]["B25003"] == (10, 3)


def test_person_constraints_keep_consistent_all_resident_denominators():
    values = {f"B01001_{cell:03d}": 10 for cell in [*range(3, 26), *range(27, 50)]}
    values.update({"B01001_002": 230, "B01001_026": 230})
    for cell, value in zip([3, 4, 5, 6, 7, 8, 9, 12], [100, 90, 20, 40, 10, 30, 50, 120]):
        values[f"B03002_{cell:03d}"] = value
    values.update(
        {
            "B05001_002": 250,
            "B05001_003": 20,
            "B05001_004": 10,
            "B05001_005": 100,
            "B05001_006": 80,
        }
    )
    constraints = derive_person_constraints(_facts(values))
    assert constraints.groupby("dimension")["target_count"].sum().to_dict() == {
        "age_band": 460.0,
        "census_sex": 460.0,
        "citizenship": 460.0,
        "race_ethnicity": 460.0,
    }
    assert set(constraints["universe"]) == {"all_residents"}
    assert constraints["variable_ids"].str.startswith("B").all()


def test_household_constraints_are_separate_and_share_household_total():
    values: dict[str, float] = {}
    for cell, value in {
        3: 10,
        4: 10,
        5: 10,
        6: 10,
        7: 5,
        8: 5,
        10: 30,
        11: 5,
        12: 5,
        13: 5,
        14: 2,
        15: 2,
        16: 1,
    }.items():
        values[f"B11016_{cell:03d}"] = value
    for cell in range(2, 17):
        values[f"B19001_{cell:03d}"] = 5
    values["B19001_017"] = 25
    values.update({"B25003_002": 60, "B25003_003": 40})
    constraints = derive_household_constraints(_facts(values))
    assert constraints.groupby("dimension")["target_count"].sum().to_dict() == {
        "household_income_band": 100.0,
        "household_size": 100.0,
        "tenure": 100.0,
    }
    assert set(constraints["universe"]) == {"households"}


def test_household_size_does_not_turn_missing_values_into_large_households():
    result = _household_size(pd.Series([1, 6, 7, 12, None]))
    assert result.tolist() == ["1", "6", "7_plus", "7_plus", "unknown"]


def test_legacy_2006_2010_pums_education_codes_are_recoded_by_vintage():
    donors = canonicalize_donors(
        pd.DataFrame(
            {
                "AGEP": [40, 40, 40, 40, 40, 10],
                "SCHL": [8, 9, 12, 13, 16, 9],
            }
        )
    )
    assert donors["education"].tolist() == [
        "less_than_high_school",
        "high_school_or_equivalent",
        "some_college_or_associate",
        "bachelors",
        "graduate_or_professional",
        "under_18_or_not_applicable",
    ]


def test_five_year_pums_income_is_adjusted_before_binning():
    adjusted = _adjusted_income(
        pd.Series([24_000, 25_000, None]),
        pd.Series([1_100_000, 900_000, 1_000_000]),
    )
    assert adjusted.iloc[0] == pytest.approx(26_400)
    assert adjusted.iloc[1] == pytest.approx(22_500)
    assert pd.isna(adjusted.iloc[2])


def test_adjusted_fractional_income_uses_gapless_half_open_bands():
    result = _household_income(
        pd.Series([24_999.9, 25_000.0, 49_999.9, 74_999.56978, 149_999.75148])
    )
    assert result.tolist() == [
        "under_25k",
        "25k_49k",
        "25k_49k",
        "50k_74k",
        "100k_149k",
    ]


def test_weighted_compression_preserves_exact_represented_total():
    frame = pd.DataFrame(
        {
            "age_band": ["18_24", "18_24", "65_plus"],
            "population_weight": [7, 5, 11],
        }
    )
    cells = compress_weighted_population(frame, ["age_band"])
    assert cells["population_weight"].sum() == 23
    assert cells.set_index("age_band")["population_weight"].to_dict() == {
        "18_24": 12,
        "65_plus": 11,
    }


def test_balanced_integerization_repairs_margins_without_changing_other_margins():
    donors = pd.DataFrame(
        {
            "a": ["a1", "a2", "a1", "a2"],
            "b": ["b1", "b1", "b2", "b2"],
        }
    )
    constraints = [
        PopulationConstraint(dimension="a", category="a1", target_count=2, source_id="x"),
        PopulationConstraint(dimension="a", category="a2", target_count=2, source_id="x"),
        PopulationConstraint(dimension="b", category="b1", target_count=2, source_id="x"),
        PopulationConstraint(dimension="b", category="b2", target_count=2, source_id="x"),
    ]
    result = balance_integer_margins(donors, [2, 0, 1, 1], constraints)
    assert result.sum() == 4
    assert result[[0, 2]].sum() == 2
    assert result[[1, 3]].sum() == 2
    assert result[[0, 1]].sum() == 2
    assert result[[2, 3]].sum() == 2


def test_area_selection_supports_abbreviations_and_fips():
    selected = parse_area_selection("wy,11,ca")
    assert [area.abbreviation for area in selected] == ["wy", "dc", "ca"]
    with pytest.raises(ValueError, match="unknown state"):
        parse_area_selection("zz")


def test_manifest_rejects_a_mismatched_represented_total():
    with pytest.raises(ValueError, match="represented_population"):
        PopulationBuildManifest(
            population_id="fixture",
            epoch_id="e2012",
            cutoff_date=date(2012, 6, 30),
            experiment_mode="sealed_forecast",
            geography=GeographySpec(
                id="state:56",
                label="Wyoming",
                geography_type="state",
                state_fips="56",
            ),
            universe="all_residents",
            target_population=10,
            represented_population=9,
            synthetic_records=2,
            representative_cells=2,
            reasoning_calls=0,
            seed=1,
            source_ids=["fixture"],
            input_sha256={},
            created_at=datetime.now(timezone.utc),
        )


def test_batch_fails_when_a_state_build_returns_validation_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "psbx.population.census_ingest.normalize_census_area",
        lambda *args, **kwargs: {"status": "normalized"},
    )
    monkeypatch.setattr(
        "psbx.population.census_ingest.build_state_population",
        lambda *args, **kwargs: {"status": "validation_failed"},
    )
    selected = parse_area_selection("wy")
    result = run_census_population_batch(
        areas=selected,
        normalized_root=tmp_path,
        population_root=tmp_path / "population",
    )
    assert result["passed"] is False
    assert result["completed"] == 0
    assert result["failures"][0]["area"] == "wy"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _raw_fixture(
    tmp_path: Path,
    *,
    release_date: str = "2012-06-30",
    expected_sha: str | None = None,
) -> tuple[Path, CensusArea]:
    root = tmp_path / "census"
    archive_path = root / "raw/example.zip"
    archive_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("payload.txt", "historical")
    digest = expected_sha or sha256_file(archive_path)
    _write_json(
        root / "manifest.json",
        {
            "passed": True,
            "artifacts": [
                {
                    "artifact_id": "only",
                    "release_date": release_date,
                    "release_verified": True,
                    "status": "downloaded",
                    "sha256": digest,
                    "relative_path": "raw/example.zip",
                }
            ],
        },
    )
    return root, CensusArea("56", "wy", "Wyoming")


def test_digest_cache_detects_same_size_same_mtime_replacement(tmp_path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"alpha")
    original_stat = path.stat()
    original = _cached_sha256(path)
    path.write_bytes(b"bravo")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert _cached_sha256(path) != original


@pytest.mark.parametrize(
    ("release_date", "expected_sha", "error"),
    [
        ("2012-07-01", None, "cutoff-approved"),
        ("2012-06-30", "0" * 64, "checksum mismatch"),
    ],
)
def test_cutoff_and_checksum_fail_before_normalized_writes(
    tmp_path, monkeypatch, release_date, expected_sha, error
):
    root, area = _raw_fixture(
        tmp_path,
        release_date=release_date,
        expected_sha=expected_sha,
    )
    project = tmp_path / "project"
    _write_json(project / "config/population_sources.yaml", {})
    monkeypatch.setenv("PSBX_ROOT", str(project))
    monkeypatch.setattr(
        "psbx.population.census_ingest._input_artifact_ids",
        lambda *args, **kwargs: ["only"],
    )
    output = tmp_path / "normalized"
    with pytest.raises(ValueError, match=error):
        normalize_census_area(area, census_root=root, normalized_root=output)
    assert not output.exists()


def test_missing_source_registry_is_rejected_before_normalization(tmp_path, monkeypatch):
    root, area = _raw_fixture(tmp_path)
    monkeypatch.setenv("PSBX_ROOT", str(tmp_path / "missing-project"))
    with pytest.raises(FileNotFoundError, match="source registry"):
        normalize_census_area(area, census_root=root, normalized_root=tmp_path / "output")


def test_normalization_resume_rejects_stale_inputs_provenance_and_outputs(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    registry = project / "config/population_sources.yaml"
    _write_json(registry, {"sources": []})
    monkeypatch.setenv("PSBX_ROOT", str(project))
    root = tmp_path / "census"
    _write_json(root / "manifest.json", {"passed": True, "artifacts": []})
    destination = tmp_path / "normalized"
    output = destination / "facts.csv"
    output.parent.mkdir(parents=True)
    output.write_text("x\n1\n", encoding="utf-8")
    artifact = {"artifact_id": "only", "sha256": "a" * 64}
    manifest = {
        "passed": True,
        "normalizer_version": NORMALIZER_VERSION,
        "acquisition_manifest_sha256": sha256_file(root / "manifest.json"),
        "source_registry_sha256": sha256_file(registry),
        "artifacts": [artifact],
        "output_sha256": {"facts.csv": sha256_file(output)},
    }
    _write_json(destination / "normalized_manifest.json", manifest)
    area = CensusArea("56", "wy", "Wyoming")
    assert _normalized_inputs_current(
        destination, root, area, verified_artifacts=[artifact]
    )
    output.write_text("x\n2\n", encoding="utf-8")
    assert not _normalized_inputs_current(
        destination, root, area, verified_artifacts=[artifact]
    )
    output.write_text("x\n1\n", encoding="utf-8")
    manifest["source_registry_sha256"] = None
    _write_json(destination / "normalized_manifest.json", manifest)
    assert not _normalized_inputs_current(
        destination, root, area, verified_artifacts=[artifact]
    )
    manifest["source_registry_sha256"] = sha256_file(registry)
    _write_json(destination / "normalized_manifest.json", manifest)
    _write_json(root / "manifest.json", {"passed": True, "artifacts": [], "changed": True})
    assert not _normalized_inputs_current(
        destination, root, area, verified_artifacts=[artifact]
    )


def test_state_resume_binds_seed_budget_inputs_and_output_hashes(tmp_path):
    normalized = tmp_path / "normalized"
    input_names = (
        "normalized_manifest.json",
        "person_constraints.csv",
        "household_constraints.csv",
        "person_donor_cells.csv",
        "household_donor_cells.csv",
    )
    normalized.mkdir()
    for name in input_names:
        (normalized / name).write_text(name, encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    cells = output / "representative_cells.csv"
    cells.write_text("cell_id,population_weight\na,1\n", encoding="utf-8")
    manifest = {
        "passed": True,
        "builder_version": BUILDER_VERSION,
        "seed": 7,
        "reasoning_calls": 12,
        "input_sha256": {
            name: sha256_file(normalized / name) for name in input_names
        },
        "output_sha256": {"representative_cells.csv": sha256_file(cells)},
    }
    _write_json(output / "manifest.json", manifest)
    assert _state_inputs_current(
        output, normalized, expected_seed=7, expected_reasoning_budget=12
    )
    assert not _state_inputs_current(
        output, normalized, expected_seed=8, expected_reasoning_budget=12
    )
    assert not _state_inputs_current(
        output, normalized, expected_seed=7, expected_reasoning_budget=13
    )
    (normalized / "person_constraints.csv").write_text("tampered", encoding="utf-8")
    assert not _state_inputs_current(
        output, normalized, expected_seed=7, expected_reasoning_budget=12
    )
    (normalized / "person_constraints.csv").write_text(
        "person_constraints.csv", encoding="utf-8"
    )
    cells.write_text("cell_id,population_weight\na,2\n", encoding="utf-8")
    assert not _state_inputs_current(
        output, normalized, expected_seed=7, expected_reasoning_budget=12
    )


def test_national_aggregate_preserves_two_character_state_fips(tmp_path, monkeypatch):
    area = CensusArea("01", "al", "Alabama")
    monkeypatch.setattr("psbx.population.census_ingest.AREAS", (area,))
    population_root = tmp_path / "population"
    state_dir = population_root / "e2012/state-al-e2012"
    state_dir.mkdir(parents=True)
    cells = pd.DataFrame(
        {"cell_id": ["state-al-cell"], "population_weight": [10], "state_fips": ["01"]}
    )
    cells.to_csv(state_dir / "representative_cells.csv", index=False)
    state_manifest = {
        "passed": True,
        "population_id": "state-al-e2012",
        "epoch_id": "e2012",
        "representation_mode": "weighted_cells",
        "geography": {"id": "state:01", "state_fips": "01"},
        "output_sha256": {
            "representative_cells.csv": sha256_file(
                state_dir / "representative_cells.csv"
            )
        },
    }
    _write_json(state_dir / "manifest.json", state_manifest)
    normalized_root = tmp_path / "normalized"
    _write_json(
        normalized_root / "us/source_summary.json",
        {"person_target_population": 10},
    )
    _write_json(normalized_root / "us/normalized_manifest.json", {"passed": True})
    result = build_national_aggregate(
        normalized_root=normalized_root,
        population_root=population_root,
        reasoning_budget=1,
    )
    assert result["status"] == "built"
    national = pd.read_csv(
        population_root / "e2012/national-us-e2012/representative_cells.csv",
        dtype={"state_fips": str},
    )
    assert national["state_fips"].tolist() == ["01"]
