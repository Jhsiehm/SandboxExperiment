from datetime import date
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from psbx.cli import app
from psbx.config import load_population
from psbx.population.registry import (
    load_source_registry,
    plan_source_decisions,
    validate_source_selection,
    verify_artifact_manifest,
)
from psbx.population.runner import (
    load_population_spec,
    plan_population,
    validate_population_file,
)
from psbx.population.schemas import GeographySpec, PopulationSource, PopulationSpec


def test_fixture_sources_are_cutoff_safe():
    spec = load_population()
    sources = load_source_registry(spec.source_registry)
    decisions = validate_source_selection(spec, sources)
    assert decisions
    assert all(row.eligible for row in decisions)


def test_population_commands_are_mounted_on_main_cli():
    result = CliRunner().invoke(
        app,
        ["population", "plan", "--config", "config/track_b_fixture.yaml"],
    )
    assert result.exit_code == 0, result.output
    assert '"population_id": "fixture-township-e2012"' in result.output


def test_population_spec_rejects_unsafe_output_identifiers():
    spec = load_population_spec("config/track_b_fixture.yaml")
    payload = spec.model_dump(mode="json")
    payload["id"] = "../../outside"
    with pytest.raises(ValueError, match="run_id"):
        PopulationSpec.model_validate(payload)


def test_population_plan_cannot_override_registered_epoch_cutoff(tmp_path: Path):
    payload = yaml.safe_load(Path("config/track_b_fixture.yaml").read_text(encoding="utf-8"))
    payload["cutoff_date"] = "2013-06-30"
    config = tmp_path / "wrong-cutoff.yaml"
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        plan_population(config)


def test_population_validation_cannot_override_registered_epoch_cutoff(tmp_path: Path):
    payload = yaml.safe_load(Path("config/track_b_fixture.yaml").read_text(encoding="utf-8"))
    payload["cutoff_date"] = "2013-06-30"
    config = tmp_path / "wrong-cutoff.yaml"
    config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        validate_population_file(
            config,
            "tests/fixtures/validation_population.csv",
        )


def test_geography_rejects_nonnumeric_state_fips():
    with pytest.raises(ValueError, match="two digits"):
        GeographySpec(
            id="bad-state",
            label="Bad state",
            geography_type="state",
            state_fips="XX",
        )


def test_unverified_build_source_fails_closed():
    spec = load_population_spec("config/track_b_fixture.yaml").model_copy(
        update={"source_ids": ["tiger_2010"]}
    )
    sources = load_source_registry(spec.source_registry)
    decisions = plan_source_decisions(spec, sources)
    assert decisions[0].eligible is False
    with pytest.raises(ValueError, match="verified release date"):
        validate_source_selection(spec, sources)


def test_post_cutoff_source_is_blocked_in_sealed_mode():
    spec = load_population_spec("config/track_b_fixture.yaml").model_copy(
        update={"source_ids": ["future"]}
    )
    sources = {
        "future": PopulationSource(
            id="future",
            provider="test",
            title="future source",
            role="population_constraint",
            release_date=date(2013, 1, 1),
            release_verified=True,
            allowed_zones=["population_build"],
            requires_artifact_release_verification=False,
        )
    }
    with pytest.raises(ValueError, match="after cutoff"):
        validate_source_selection(spec, sources)


def test_evaluation_only_source_cannot_enter_population_build():
    spec = load_population_spec("config/track_b_fixture.yaml").model_copy(
        update={"source_ids": ["anes_2012"]}
    )
    sources = load_source_registry(spec.source_registry)
    with pytest.raises(ValueError, match="does not permit zone"):
        validate_source_selection(spec, sources)


def test_artifact_verification_keeps_multiple_artifacts_per_source(tmp_path: Path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")
    import hashlib

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "id": "fixture-artifacts",
        "artifacts": [
            {
                "source_id": "real",
                "artifact_id": "real-first",
                "local_path": str(first),
                "release_date": "2012-01-01",
                "release_verified": True,
                "sha256": digest(first),
                "zone": "population_build",
            },
            {
                "source_id": "real",
                "artifact_id": "real-second",
                "local_path": str(second),
                "release_date": "2012-01-02",
                "release_verified": True,
                "sha256": digest(second),
                "zone": "population_build",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    source = PopulationSource(
        id="real",
        provider="fixture",
        title="fixture",
        role="population_constraint",
        release_date=date(2012, 1, 1),
        release_verified=True,
        allowed_zones=["population_build"],
        requires_artifact_release_verification=True,
    )
    spec = load_population_spec("config/track_b_fixture.yaml").model_copy(
        update={
            "source_ids": ["real"],
            "artifact_manifest_path": str(manifest_path),
            "required_artifact_ids": ["real-first", "real-second"],
        }
    )
    verify_artifact_manifest(spec, {"real": source})
    second.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="real-second"):
        verify_artifact_manifest(spec, {"real": source})


def test_artifact_verification_requires_declared_artifact_ids(tmp_path: Path):
    path = tmp_path / "only.csv"
    path.write_text("only\n", encoding="utf-8")
    import hashlib

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "id": "fixture-artifacts",
                "artifacts": [
                    {
                        "source_id": "real",
                        "artifact_id": "real-first",
                        "local_path": str(path),
                        "release_date": "2012-01-01",
                        "release_verified": True,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "zone": "population_build",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = PopulationSource(
        id="real",
        provider="fixture",
        title="fixture",
        role="population_constraint",
        release_date=date(2012, 1, 1),
        release_verified=True,
        allowed_zones=["population_build"],
        requires_artifact_release_verification=True,
    )
    spec = load_population_spec("config/track_b_fixture.yaml").model_copy(
        update={
            "source_ids": ["real"],
            "artifact_manifest_path": str(manifest_path),
            "required_artifact_ids": ["real-first", "real-missing"],
        }
    )
    with pytest.raises(ValueError, match="real-missing"):
        verify_artifact_manifest(spec, {"real": source})
