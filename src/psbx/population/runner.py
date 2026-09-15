"""End-to-end Track B population build and artifact persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from .compress import allocate_reasoning_budget, compress_population
from .constraints import (
    constraints_to_frame,
    load_constraints,
    sample_constraint_realization,
    validate_constraints,
)
from .donors import filter_to_universe, load_donors, validate_donor_support
from .registry import (
    load_source_registry,
    plan_source_decisions,
    sha256_file,
    validate_source_selection,
)
from .schemas import (
    PopulationBuildManifest,
    PopulationConstraint,
    PopulationSource,
    PopulationSpec,
)
from .synthesize import build_synthetic_population
from .validate import validate_population


def load_population_spec(path: str | Path) -> PopulationSpec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("population config must be a mapping")
    return PopulationSpec.model_validate(data)


def _resolve(path: str | Path, *, base_dir: str | Path = ".") -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else Path(base_dir) / candidate


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _validate_epoch_contract(spec: PopulationSpec, *, base_dir: Path) -> None:
    """Keep Track B's declared cutoff tied to the repository epoch registry."""
    from psbx.config import load_epochs

    epoch_path = (base_dir / "config/epochs.yaml").resolve()
    epochs = load_epochs(epoch_path)
    epoch = epochs.get(spec.epoch_id)
    if epoch is None:
        raise ValueError(f"unknown population epoch_id: {spec.epoch_id}")
    if spec.cutoff_date != epoch.cutoff_date:
        raise ValueError(
            f"population cutoff {spec.cutoff_date} does not match "
            f"epoch {spec.epoch_id} cutoff {epoch.cutoff_date}"
        )


def _validate_input_source_roles(
    spec: PopulationSpec,
    sources: dict[str, PopulationSource],
    constraints: list[PopulationConstraint],
) -> None:
    selected = set(spec.source_ids)
    constraint_source_ids = {row.source_id for row in constraints}
    unselected = constraint_source_ids - selected
    if unselected:
        raise ValueError(
            "constraints reference unselected sources: " + ", ".join(sorted(unselected))
        )
    wrong_role = {
        source_id
        for source_id in constraint_source_ids
        if sources[source_id].role != "population_constraint"
    }
    if wrong_role:
        raise ValueError(
            "constraint sources have the wrong registry role: "
            + ", ".join(sorted(wrong_role))
        )
    donor_sources = [
        sources[source_id]
        for source_id in spec.source_ids
        if sources[source_id].role == "donor_microdata"
    ]
    if not donor_sources:
        raise ValueError("population build requires a selected donor_microdata source")


def plan_population(config_path: str | Path, *, base_dir: str | Path = ".") -> dict:
    base = Path(base_dir)
    config = _resolve(config_path, base_dir=base_dir)
    spec = load_population_spec(config)
    _validate_epoch_contract(spec, base_dir=base)
    registry_path = _resolve(spec.source_registry, base_dir=base_dir)
    sources = load_source_registry(registry_path)
    decisions = plan_source_decisions(spec, sources)
    return {
        "population_id": spec.id,
        "epoch_id": spec.epoch_id,
        "cutoff_date": spec.cutoff_date.isoformat(),
        "experiment_mode": spec.experiment_mode,
        "geography": spec.geography.model_dump(mode="json"),
        "universe": spec.universe,
        "target_population": spec.target_population,
        "source_decisions": [row.model_dump(mode="json") for row in decisions],
        "artifact_manifest_required": any(
            sources[source_id].requires_artifact_release_verification
            for source_id in spec.source_ids
            if source_id in sources
        ),
    }


def run_population_build(
    config_path: str | Path,
    *,
    base_dir: str | Path = ".",
    output_override: str | Path | None = None,
) -> dict:
    base = Path(base_dir)
    config = _resolve(config_path, base_dir=base)
    spec = load_population_spec(config)
    _validate_epoch_contract(spec, base_dir=base)
    sources = load_source_registry(_resolve(spec.source_registry, base_dir=base))
    decisions = validate_source_selection(spec, sources, base_dir=base)

    constraints_path = _resolve(spec.constraints_path, base_dir=base)
    donors_path = _resolve(spec.donors_path, base_dir=base)
    constraints = load_constraints(constraints_path)
    _validate_input_source_roles(spec, sources, constraints)
    validate_constraints(spec, constraints)
    if spec.sample_moe_realization:
        constraints = sample_constraint_realization(
            constraints,
            target_population=spec.target_population,
            seed=spec.seed,
        )
    donors = filter_to_universe(load_donors(donors_path), spec.universe)
    validate_donor_support(donors, constraints)

    population, raking = build_synthetic_population(donors, constraints, spec)
    validation = validate_population(population, constraints, spec)
    cells = compress_population(population, spec.representative_cell_fields)
    cells = allocate_reasoning_budget(cells, spec.reasoning_call_budget)

    output_root = (
        Path(output_override)
        if output_override
        else _resolve(spec.output_root, base_dir=base)
    )
    out = output_root / spec.epoch_id / spec.id
    out.mkdir(parents=True, exist_ok=True)
    people_path = out / "synthetic_people.csv"
    cells_path = out / "representative_cells.csv"
    history_path = out / "raking_history.csv"
    constraints_output_path = out / "constraints_used.csv"
    validation_path = out / "population_validation.json"
    decisions_path = out / "source_decisions.json"
    manifest_path = out / "manifest.json"

    population.to_csv(people_path, index=False)
    cells.to_csv(cells_path, index=False)
    pd.DataFrame([row.model_dump(mode="json") for row in raking.history]).to_csv(
        history_path, index=False
    )
    constraints_to_frame(constraints).to_csv(constraints_output_path, index=False)
    _write_json(validation_path, validation)
    _write_json(decisions_path, [row.model_dump(mode="json") for row in decisions])

    input_hashes = {
        str(constraints_path): sha256_file(constraints_path),
        str(donors_path): sha256_file(donors_path),
        str(config): sha256_file(config),
        str(_resolve(spec.source_registry, base_dir=base)): sha256_file(
            _resolve(spec.source_registry, base_dir=base)
        ),
    }
    if spec.artifact_manifest_path:
        artifact_manifest = _resolve(spec.artifact_manifest_path, base_dir=base)
        input_hashes[str(artifact_manifest)] = sha256_file(artifact_manifest)
    manifest = PopulationBuildManifest(
        population_id=spec.id,
        epoch_id=spec.epoch_id,
        cutoff_date=spec.cutoff_date,
        experiment_mode=spec.experiment_mode,
        geography=spec.geography,
        universe=spec.universe,
        target_population=spec.target_population,
        synthetic_records=len(population),
        representative_cells=len(cells),
        reasoning_calls=int(cells["reasoning_calls"].sum()),
        seed=spec.seed,
        source_ids=spec.source_ids,
        input_sha256=input_hashes,
        created_at=datetime.now(timezone.utc),
    )
    _write_json(manifest_path, manifest)
    output_hashes = {
        path.name: sha256_file(path)
        for path in (
            people_path,
            cells_path,
            history_path,
            constraints_output_path,
            validation_path,
            decisions_path,
        )
    }
    manifest = manifest.model_copy(update={"output_sha256": output_hashes})
    _write_json(manifest_path, manifest)

    return {
        "output_dir": str(out),
        "manifest": manifest.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
    }


def validate_population_file(
    config_path: str | Path,
    population_path: str | Path,
    *,
    base_dir: str | Path = ".",
) -> dict:
    base = Path(base_dir)
    spec = load_population_spec(_resolve(config_path, base_dir=base))
    _validate_epoch_contract(spec, base_dir=base)
    constraints = load_constraints(_resolve(spec.constraints_path, base_dir=base))
    validate_constraints(spec, constraints)
    population = pd.read_csv(_resolve(population_path, base_dir=base))
    report = validate_population(population, constraints, spec)
    return report.model_dump(mode="json")
