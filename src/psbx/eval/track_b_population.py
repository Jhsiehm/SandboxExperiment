"""Held-out aggregate/survey validation for Track B behavior outputs.

This module compares weighted synthetic response probabilities with held-out aggregate targets. It
must not be used to infer or report how an identifiable person voted.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from psbx.paths import validate_run_id
from psbx.population.schemas import (
    BehaviorTargetResult,
    SurveyTarget,
    TrackBBehaviorValidationReport,
)

FROZEN_BEHAVIOR_METRICS = (
    "mean_absolute_error",
    "root_mean_squared_error",
    "sample_size_weighted_mae",
    "mean_signed_error",
    "max_absolute_error",
    "targets_within_observed_ci95",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid behavior validation seal: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("behavior validation seal must contain an object")
    return payload


def _require_sha256(value: str, label: str) -> str:
    digest = str(value).lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return digest


def _seal_fingerprint(seal: dict[str, Any]) -> str:
    fingerprinted = {
        "schema_version": seal.get("schema_version"),
        "run_id": seal.get("run_id"),
        "model_id": seal.get("model_id"),
        "inputs": seal.get("inputs"),
        "prediction_tasks": seal.get("prediction_tasks"),
        "metric_plan": seal.get("metric_plan"),
    }
    return hashlib.sha256(
        json.dumps(fingerprinted, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _wilson_interval(probability: float, sample_size: int) -> tuple[float, float]:
    z = 1.959963984540054
    denominator = 1 + z**2 / sample_size
    center = (probability + z**2 / (2 * sample_size)) / denominator
    spread = (
        z
        * math.sqrt(probability * (1 - probability) / sample_size + z**2 / (4 * sample_size**2))
        / denominator
    )
    return max(0.0, center - spread), min(1.0, center + spread)


def _validate_prediction_frames(population: pd.DataFrame, responses: pd.DataFrame) -> None:
    required_response = {
        "task_id",
        "synthetic_person_id",
        "predicted_probability",
    }
    missing = required_response - set(responses.columns)
    if missing:
        raise ValueError("response data missing columns: " + ", ".join(sorted(missing)))
    forbidden = {"observed_probability", "target_probability", "ground_truth"}
    leaked = forbidden & set(responses.columns)
    if leaked:
        raise ValueError(
            "prediction artifact contains held-out target columns: " + ", ".join(sorted(leaked))
        )
    if "synthetic_person_id" not in population:
        raise ValueError("population must contain synthetic_person_id")
    if population["synthetic_person_id"].astype(str).duplicated().any():
        raise ValueError("population synthetic_person_id values must be unique")
    if responses[["task_id", "synthetic_person_id"]].astype(str).duplicated().any():
        raise ValueError("response rows must be unique by task_id and synthetic_person_id")
    probabilities = pd.to_numeric(responses["predicted_probability"], errors="coerce")
    if probabilities.isna().any() or not np.isfinite(probabilities).all():
        raise ValueError("predicted_probability contains nonnumeric values")
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("predicted_probability must be in [0, 1]")
    if "population_weight" in population:
        population_weights = pd.to_numeric(population["population_weight"], errors="coerce")
        if (
            population_weights.isna().any()
            or not np.isfinite(population_weights).all()
            or (population_weights <= 0).any()
        ):
            raise ValueError("population_weight must contain finite positive values")
    if "response_weight" in responses:
        response_weights = pd.to_numeric(responses["response_weight"], errors="coerce")
        if (
            response_weights.isna().any()
            or not np.isfinite(response_weights).all()
            or (response_weights < 0).any()
        ):
            raise ValueError("response_weight must contain finite nonnegative values")


def load_survey_targets(path: str | Path) -> list[SurveyTarget]:
    frame = pd.read_csv(path)
    required = {"target_id", "task_id", "observed_probability"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("target file missing columns: " + ", ".join(sorted(missing)))
    rows = []
    for record in frame.to_dict(orient="records"):
        clean = {key: (None if pd.isna(value) else value) for key, value in record.items()}
        rows.append(SurveyTarget.model_validate(clean))
    return rows


def evaluate_behavior_targets(
    *,
    run_id: str,
    population: pd.DataFrame,
    responses: pd.DataFrame,
    targets: list[SurveyTarget],
) -> TrackBBehaviorValidationReport:
    if not targets:
        raise ValueError("at least one held-out behavior target is required")
    _validate_prediction_frames(population, responses)
    population = population.copy()
    population["population_weight"] = (
        pd.to_numeric(population["population_weight"], errors="raise")
        if "population_weight" in population
        else 1.0
    )
    merged = responses.merge(
        population,
        on="synthetic_person_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if (merged["_merge"] != "both").any():
        raise ValueError("some response rows do not match the synthetic population")
    merged.drop(columns=["_merge"], inplace=True)
    if "response_weight" in merged:
        merged["_weight"] = merged["population_weight"] * pd.to_numeric(
            merged["response_weight"], errors="raise"
        )
    else:
        merged["_weight"] = merged["population_weight"]
    merged["predicted_probability"] = pd.to_numeric(
        merged["predicted_probability"], errors="coerce"
    )
    results: list[BehaviorTargetResult] = []
    for target in targets:
        subset = merged.loc[merged["task_id"].astype(str) == target.task_id].copy()
        population_subset = population.copy()
        if target.group_field != "__all__":
            if target.group_field not in subset or target.group_field not in population_subset:
                raise ValueError(f"population is missing target group field {target.group_field}")
            subset = subset.loc[subset[target.group_field].astype(str) == str(target.group_value)]
            population_subset = population_subset.loc[
                population_subset[target.group_field].astype(str) == str(target.group_value)
            ]
        if target.population_universe != "unspecified":
            if "population_universe" not in population_subset:
                raise ValueError(
                    f"target {target.target_id} requires population universe "
                    f"{target.population_universe}"
                )
            observed_universes = set(population_subset["population_universe"].astype(str))
            if observed_universes != {target.population_universe}:
                raise ValueError(f"target {target.target_id} population universe does not match")
        synthetic_population_weight = float(population_subset["population_weight"].sum())
        if synthetic_population_weight <= 0:
            raise ValueError(f"target {target.target_id} has no represented synthetic support")
        covered_population_weight = float(subset["population_weight"].sum())
        coverage = (
            covered_population_weight / synthetic_population_weight
            if synthetic_population_weight > 0
            else 0.0
        )
        if not math.isclose(coverage, 1.0, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(
                f"target {target.target_id} has incomplete synthetic response coverage: "
                f"{coverage:.6f}"
            )
        represented_weight = float(subset["_weight"].sum())
        if represented_weight <= 0:
            raise ValueError(f"target {target.target_id} has no represented synthetic support")
        predicted = float(np.average(subset["predicted_probability"], weights=subset["_weight"]))
        error = predicted - target.observed_probability
        ci_lower = None
        ci_upper = None
        within_ci = None
        support_status = "unknown"
        uncertainty_method = "none"
        uncertainty_is_approximate = False
        if target.observed_ci95_lower is not None and target.observed_ci95_upper is not None:
            ci_lower = target.observed_ci95_lower
            ci_upper = target.observed_ci95_upper
            uncertainty_method = target.uncertainty_method or "published_confidence_interval"
        elif target.published_moe95 is not None:
            ci_lower = max(0.0, target.observed_probability - target.published_moe95)
            ci_upper = min(1.0, target.observed_probability + target.published_moe95)
            uncertainty_method = target.uncertainty_method or "published_survey_moe95"
        elif target.sample_size is not None and target.sample_size > 0:
            ci_lower, ci_upper = _wilson_interval(target.observed_probability, target.sample_size)
            uncertainty_method = "approximate_binomial_wilson_from_nominal_n"
            uncertainty_is_approximate = True
        if ci_lower is not None and ci_upper is not None:
            within_ci = ci_lower <= predicted <= ci_upper
        if target.sample_size is not None and target.sample_size > 0:
            support_status = "weak" if target.sample_size < 100 else "reported"
        weight_sum = float(subset["_weight"].sum())
        weight_square_sum = float((subset["_weight"] ** 2).sum())
        effective_sample_size = weight_sum**2 / weight_square_sum if weight_square_sum > 0 else 0.0
        results.append(
            BehaviorTargetResult(
                target_id=target.target_id,
                task_id=target.task_id,
                group_field=target.group_field,
                group_value=target.group_value,
                observed_probability=target.observed_probability,
                predicted_probability=predicted,
                absolute_error=abs(error),
                squared_error=error**2,
                represented_weight=represented_weight,
                n_simulated_records=len(subset),
                sample_size=target.sample_size,
                observed_ci95_lower=ci_lower,
                observed_ci95_upper=ci_upper,
                predicted_within_observed_ci95=within_ci,
                support_status=support_status,
                population_universe=target.population_universe,
                uncertainty_method=uncertainty_method,
                uncertainty_is_approximate=uncertainty_is_approximate,
                synthetic_population_weight=synthetic_population_weight,
                synthetic_coverage=coverage,
                synthetic_effective_sample_size=effective_sample_size,
                synthetic_support_status="complete",
            )
        )
    mae = float(np.mean([row.absolute_error for row in results]))
    rmse = float(math.sqrt(np.mean([row.squared_error for row in results])))
    sample_sizes = [target.sample_size for target in targets]
    weighted_mae = None
    if results and all(value is not None and value > 0 for value in sample_sizes):
        weighted_mae = float(
            np.average(
                [row.absolute_error for row in results],
                weights=np.asarray(sample_sizes, dtype=float),
            )
        )
    signed_errors = [row.predicted_probability - row.observed_probability for row in results]
    interval_results = [
        row.predicted_within_observed_ci95
        for row in results
        if row.predicted_within_observed_ci95 is not None
    ]
    return TrackBBehaviorValidationReport(
        run_id=run_id,
        n_targets=len(results),
        mean_absolute_error=mae,
        root_mean_squared_error=rmse,
        sample_size_weighted_mae=weighted_mae,
        mean_signed_error=float(np.mean(signed_errors)),
        max_absolute_error=max(row.absolute_error for row in results),
        targets_within_observed_ci95=(
            sum(bool(value) for value in interval_results) if interval_results else None
        ),
        weak_support_targets=sum(
            row.support_status != "reported" or row.synthetic_effective_sample_size < 30
            for row in results
        ),
        weak_survey_support_targets=sum(row.support_status != "reported" for row in results),
        weak_synthetic_support_targets=sum(
            row.synthetic_effective_sample_size < 30 for row in results
        ),
        targets=results,
        notes=[
            "Targets must be held out from runtime agents and behavior-model fitting.",
            "Aggregate fit does not identify any real person's political behavior.",
            "Survey sample size and synthetic response coverage are separate support measures.",
            "Binomial intervals derived only from nominal n are labeled approximate.",
        ],
    )


def evaluate_behavior_files(
    *,
    run_id: str,
    population_path: str | Path,
    responses_path: str | Path,
    targets_path: str | Path,
) -> TrackBBehaviorValidationReport:
    return evaluate_behavior_targets(
        run_id=run_id,
        population=pd.read_csv(population_path),
        responses=pd.read_csv(responses_path),
        targets=load_survey_targets(targets_path),
    )


def seal_behavior_predictions(
    *,
    run_id: str,
    population_path: str | Path,
    responses_path: str | Path,
    training_artifacts: list[str | Path],
    model_id: str,
    output_path: str | Path,
    max_mean_absolute_error: float = 0.10,
    max_root_mean_squared_error: float = 0.15,
    minimum_targets: int = 1,
) -> dict[str, Any]:
    """Seal predictions and metric thresholds before any target artifact is opened."""
    run_id = validate_run_id(run_id)
    population_path = Path(population_path).resolve()
    responses_path = Path(responses_path).resolve()
    output_path = Path(output_path).resolve()
    if not training_artifacts:
        raise ValueError("at least one training/model-card artifact must be declared")
    if not 0 <= max_mean_absolute_error <= 1:
        raise ValueError("max_mean_absolute_error must be in [0, 1]")
    if not 0 <= max_root_mean_squared_error <= 1:
        raise ValueError("max_root_mean_squared_error must be in [0, 1]")
    if minimum_targets < 1:
        raise ValueError("minimum_targets must be positive")
    population = pd.read_csv(population_path)
    responses = pd.read_csv(responses_path)
    _validate_prediction_frames(population, responses)
    population_ids = set(population["synthetic_person_id"].astype(str))
    response_ids = set(responses["synthetic_person_id"].astype(str))
    if not response_ids <= population_ids:
        raise ValueError("some response rows do not match the synthetic population")
    training_rows = []
    for artifact in training_artifacts:
        path = Path(artifact).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path in {population_path, responses_path, output_path}:
            raise ValueError("training artifacts must be separate from predictions and seal")
        training_rows.append({"path": str(path), "sha256": _sha256_file(path)})
    inputs = {
        "population": {"path": str(population_path), "sha256": _sha256_file(population_path)},
        "responses": {"path": str(responses_path), "sha256": _sha256_file(responses_path)},
        "training_artifacts": training_rows,
    }
    metric_plan = {
        "metrics": list(FROZEN_BEHAVIOR_METRICS),
        "thresholds": {
            "max_mean_absolute_error": max_mean_absolute_error,
            "max_root_mean_squared_error": max_root_mean_squared_error,
            "minimum_targets": minimum_targets,
        },
    }
    prediction_tasks = sorted(set(responses["task_id"].astype(str)))
    payload = {
        "schema_version": 2,
        "status": "sealed_predictions",
        "passed": True,
        "run_id": run_id,
        "model_id": model_id,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "prediction_tasks": prediction_tasks,
        "metric_plan": metric_plan,
        "target_artifact_loaded": False,
        "claims": [
            "Predictions and metric thresholds were sealed without a target-file argument.",
            "No demographic attribute is treated as a deterministic political behavior.",
            "Passing aggregate metrics does not validate individual-level predictions.",
        ],
    }
    payload["input_fingerprint"] = _seal_fingerprint(payload)
    if output_path.is_file():
        existing = _read_json(output_path)
        if (
            existing.get("schema_version") != 2
            or existing.get("input_fingerprint") != payload["input_fingerprint"]
            or _seal_fingerprint(existing) != existing.get("input_fingerprint")
            or existing.get("target_artifact_loaded") is not False
            or existing.get("target_artifact_sha256") is not None
        ):
            raise ValueError("refusing to overwrite a different prediction seal")
        _verify_sealed_inputs(existing)
        return {**existing, "status": "skipped_valid", "output_path": str(output_path)}
    _atomic_json(output_path, payload)
    return {**payload, "output_path": str(output_path)}


def _verify_sealed_inputs(seal: dict[str, Any]) -> None:
    inputs = seal.get("inputs") or {}
    rows = [inputs.get("population"), inputs.get("responses")]
    rows.extend(inputs.get("training_artifacts") or [])
    for row in rows:
        if not isinstance(row, dict) or not row.get("path") or not row.get("sha256"):
            raise ValueError("prediction seal has incomplete input provenance")
        path = Path(str(row["path"]))
        if not path.is_file() or _sha256_file(path) != row["sha256"]:
            raise ValueError(f"sealed behavior input changed or is missing: {path.name}")


def evaluate_sealed_behavior(
    *,
    seal_path: str | Path,
    expected_seal_sha256: str,
    targets_path: str | Path,
    expected_target_sha256: str,
    target_provenance_path: str | Path,
    expected_target_provenance_sha256: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Reveal one checksum-pinned target file only after predictions are sealed."""
    seal_path = Path(seal_path).resolve()
    targets_path = Path(targets_path).resolve()
    target_provenance_path = Path(target_provenance_path).resolve()
    output_path = Path(output_path).resolve()
    expected_seal_sha256 = _require_sha256(expected_seal_sha256, "expected seal SHA-256")
    actual_seal_sha256 = _sha256_file(seal_path)
    if actual_seal_sha256 != expected_seal_sha256:
        raise ValueError("prediction seal checksum does not match the pre-reveal value")
    seal = _read_json(seal_path)
    if (
        seal.get("schema_version") != 2
        or seal.get("status") != "sealed_predictions"
        or not seal.get("passed")
    ):
        raise ValueError("behavior predictions are not sealed")
    if seal.get("target_artifact_loaded") is not False:
        raise ValueError("prediction seal does not attest target isolation")
    if seal.get("target_artifact_sha256") is not None:
        raise ValueError("prediction seal must not contain a revealed target checksum")
    if _seal_fingerprint(seal) != seal.get("input_fingerprint"):
        raise ValueError("prediction seal fingerprint does not match its contents")
    _verify_sealed_inputs(seal)
    expected_target_sha256 = _require_sha256(expected_target_sha256, "expected target SHA-256")
    actual_target_sha256 = _sha256_file(targets_path)
    if actual_target_sha256 != expected_target_sha256:
        raise ValueError("held-out target checksum does not match the frozen value")
    expected_target_provenance_sha256 = _require_sha256(
        expected_target_provenance_sha256,
        "expected target provenance SHA-256",
    )
    actual_target_provenance_sha256 = _sha256_file(target_provenance_path)
    if actual_target_provenance_sha256 != expected_target_provenance_sha256:
        raise ValueError("target provenance checksum does not match the frozen value")
    provenance = _read_json(target_provenance_path)
    if provenance.get("zone") != "evaluation_vault":
        raise ValueError("target provenance must declare the evaluation_vault zone")
    target_artifact = provenance.get("target_artifact") or {}
    if (
        target_artifact.get("filename") != targets_path.name
        or target_artifact.get("sha256") != actual_target_sha256
    ):
        raise ValueError("target provenance does not bind the revealed target artifact")
    if provenance.get("prediction_seal_sha256_before_reveal") != actual_seal_sha256:
        raise ValueError("target provenance does not bind the pre-reveal prediction seal")
    if provenance.get("target_exclusion_attestation") is not True:
        raise ValueError("target provenance must attest exclusion from model inputs")
    source = provenance.get("source") or {}
    source_path = Path(str(source.get("local_path") or ""))
    if not source_path.is_absolute():
        source_path = (target_provenance_path.parent / source_path).resolve()
    source_sha256 = _require_sha256(str(source.get("sha256") or ""), "target source SHA-256")
    if not source_path.is_file() or _sha256_file(source_path) != source_sha256:
        raise ValueError("target provenance source artifact is missing or changed")
    if source_sha256 in {row["sha256"] for row in seal["inputs"].get("training_artifacts", [])}:
        raise ValueError("target source artifact appears in declared training inputs")
    target_universes = {target.population_universe for target in load_survey_targets(targets_path)}
    declared_universes = set(provenance.get("population_universes") or [])
    if not target_universes or target_universes != declared_universes:
        raise ValueError("target provenance population universes do not match target rows")
    inputs = seal["inputs"]
    report = evaluate_behavior_files(
        run_id=str(seal["run_id"]),
        population_path=inputs["population"]["path"],
        responses_path=inputs["responses"]["path"],
        targets_path=targets_path,
    )
    report_payload = report.model_dump(mode="json")
    report_payload["metrics_frozen"] = True
    thresholds = seal["metric_plan"]["thresholds"]
    passed = (
        report.n_targets >= int(thresholds["minimum_targets"])
        and report.mean_absolute_error <= float(thresholds["max_mean_absolute_error"])
        and report.root_mean_squared_error <= float(thresholds["max_root_mean_squared_error"])
    )
    payload = {
        "schema_version": 2,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_seal_sha256": actual_seal_sha256,
        "target_artifact": {
            "filename": targets_path.name,
            "sha256": actual_target_sha256,
        },
        "target_provenance": {
            "filename": target_provenance_path.name,
            "sha256": actual_target_provenance_sha256,
            "source_sha256": source_sha256,
            "zone": "evaluation_vault",
            "target_exclusion": (
                "execution_isolated"
                if provenance.get("execution_isolated") is True
                else "attested_not_execution_enforced"
            ),
        },
        "metric_plan": seal["metric_plan"],
        "validation": report_payload,
        "disclosure": (
            "This is aggregate historical validation, not evidence about any identifiable "
            "person and not authorization for targeting or persuasion."
        ),
    }
    _atomic_json(output_path, payload)
    return {**payload, "output_path": str(output_path)}
