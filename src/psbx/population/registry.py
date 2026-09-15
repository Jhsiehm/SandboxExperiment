"""Cutoff-aware source and artifact gatekeeping for Track B."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .schemas import (
    ArtifactManifest,
    DataZone,
    PopulationSource,
    PopulationSpec,
    SourceDecision,
)


def _read_mapping(path: str | Path) -> dict:
    src = Path(path)
    text = src.read_text(encoding="utf-8")
    if src.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"expected a mapping in {src}")
    return data


def load_source_registry(path: str | Path) -> dict[str, PopulationSource]:
    data = _read_mapping(path)
    rows = data.get("sources")
    if not isinstance(rows, list):
        raise ValueError("population source registry requires a 'sources' list")
    sources = [PopulationSource.model_validate(row) for row in rows]
    by_id = {source.id: source for source in sources}
    if len(by_id) != len(sources):
        raise ValueError("population source IDs must be unique")
    return by_id


def load_artifact_manifest(path: str | Path) -> ArtifactManifest:
    return ArtifactManifest.model_validate(_read_mapping(path))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_source_decisions(
    spec: PopulationSpec,
    sources: dict[str, PopulationSource],
    *,
    zone: DataZone = "population_build",
) -> list[SourceDecision]:
    decisions: list[SourceDecision] = []
    for source_id in spec.source_ids:
        source = sources.get(source_id)
        if source is None:
            decisions.append(
                SourceDecision(
                    source_id=source_id,
                    eligible=False,
                    zone=zone,
                    decision="source ID is not present in the registry",
                )
            )
            continue
        if zone not in source.allowed_zones:
            decisions.append(
                SourceDecision(
                    source_id=source.id,
                    eligible=False,
                    zone=zone,
                    release_date=source.release_date,
                    decision=f"source role does not permit zone={zone}",
                )
            )
            continue
        if spec.experiment_mode == "sealed_forecast":
            if not source.release_verified or source.release_date is None:
                decisions.append(
                    SourceDecision(
                        source_id=source.id,
                        eligible=False,
                        zone=zone,
                        release_date=source.release_date,
                        decision="sealed mode requires a verified release date",
                    )
                )
                continue
            if source.release_date > spec.cutoff_date:
                decisions.append(
                    SourceDecision(
                        source_id=source.id,
                        eligible=False,
                        zone=zone,
                        release_date=source.release_date,
                        decision=(
                            f"release date {source.release_date} is after cutoff "
                            f"{spec.cutoff_date}"
                        ),
                    )
                )
                continue
        decisions.append(
            SourceDecision(
                source_id=source.id,
                eligible=True,
                zone=zone,
                release_date=source.release_date,
                decision="source-level cutoff check passed",
            )
        )
    return decisions


def verify_artifact_manifest(
    spec: PopulationSpec,
    sources: dict[str, PopulationSource],
    *,
    base_dir: str | Path = ".",
) -> None:
    required = {
        source_id
        for source_id in spec.source_ids
        if sources[source_id].requires_artifact_release_verification
    }
    if not required:
        return
    if not spec.artifact_manifest_path:
        joined = ", ".join(sorted(required))
        raise ValueError(
            "selected real-data sources require an artifact manifest before build: " + joined
        )
    manifest_path = Path(spec.artifact_manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = Path(base_dir) / manifest_path
    manifest = load_artifact_manifest(manifest_path)
    by_id = {artifact.artifact_id: artifact for artifact in manifest.artifacts}
    if len(by_id) != len(manifest.artifacts):
        raise ValueError("artifact manifest artifact IDs must be unique")
    by_source: dict[str, list] = {}
    for artifact in manifest.artifacts:
        by_source.setdefault(artifact.source_id, []).append(artifact)
    missing_sources = required - by_source.keys()
    if missing_sources:
        raise ValueError(
            "artifact manifest is missing sources: " + ", ".join(sorted(missing_sources))
        )
    missing_ids = set(spec.required_artifact_ids) - by_id.keys()
    if missing_ids:
        raise ValueError(
            "artifact manifest is missing required artifact IDs: "
            + ", ".join(sorted(missing_ids))
        )
    wrong_source_ids = [
        artifact_id
        for artifact_id in spec.required_artifact_ids
        if by_id[artifact_id].source_id not in required
    ]
    if wrong_source_ids:
        raise ValueError(
            "required artifact IDs do not belong to selected verified sources: "
            + ", ".join(sorted(wrong_source_ids))
        )
    selected_artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.source_id in required
    ]
    for artifact in selected_artifacts:
        if artifact.zone != "population_build":
            raise ValueError(f"artifact {artifact.artifact_id} is not in population_build zone")
        if not artifact.release_verified:
            raise ValueError(f"artifact {artifact.artifact_id} release is not verified")
        if spec.experiment_mode == "sealed_forecast" and artifact.release_date > spec.cutoff_date:
            raise ValueError(
                f"artifact {artifact.artifact_id} was released after cutoff {spec.cutoff_date}"
            )
        local_path = Path(artifact.local_path)
        if not local_path.is_absolute():
            local_path = manifest_path.parent / local_path
        if not local_path.exists():
            raise FileNotFoundError(local_path)
        actual = sha256_file(local_path)
        if actual != artifact.sha256:
            raise ValueError(
                f"checksum mismatch for {artifact.artifact_id}: "
                f"expected {artifact.sha256}, got {actual}"
            )


def validate_source_selection(
    spec: PopulationSpec,
    sources: dict[str, PopulationSource],
    *,
    base_dir: str | Path = ".",
) -> list[SourceDecision]:
    decisions = plan_source_decisions(spec, sources)
    blocked = [decision for decision in decisions if not decision.eligible]
    if blocked:
        detail = "; ".join(f"{row.source_id}: {row.decision}" for row in blocked)
        raise ValueError("population source selection blocked: " + detail)
    verify_artifact_manifest(spec, sources, base_dir=base_dir)
    return decisions
