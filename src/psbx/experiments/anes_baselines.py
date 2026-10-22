"""Outcome-fitted ANES 2012 baselines evaluated with full-sample cross-fitting.

These models are retrospective comparators, not runtime agents. They open the
evaluation vault by design, and every fitted probability is out-of-fold so no
respondent is scored by a model trained on that respondent's target.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from psbx.experiments.anes_society import (
    PAPER_STUDY_2_PROFILE_FIELDS,
    STRICT_PRE_ELECTION_PROFILE_FIELDS,
    _sha256_file,
)
from psbx.paths import resolve


def _load_profiles(path: str | Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    with resolve(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            flat = {
                "synthetic_person_id": str(row["synthetic_person_id"]),
                **dict(row.get("profile") or {}),
            }
            rows.append(flat)
    if not rows:
        raise ValueError("profile file is empty")
    frame = pd.DataFrame(rows)
    if frame["synthetic_person_id"].duplicated().any():
        raise ValueError("profile file contains duplicate synthetic person IDs")
    return frame


def _profile_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = resolve(path).parent / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("profile file requires a sibling runtime manifest")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _categorical_frame(frame: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError("profile frame is missing fields: " + ", ".join(sorted(missing)))
    result = pd.DataFrame(index=frame.index)
    for field in fields:
        values = frame[field]
        result[field] = values.map(
            lambda value: "__MISSING__" if value is None or pd.isna(value) else f"v:{value}"
        )
    return result


def _one_hot_matrix(frame: pd.DataFrame, fields: list[str]) -> np.ndarray:
    categorical = _categorical_frame(frame, fields)
    columns = []
    for field in fields:
        for value in sorted(categorical[field].unique()):
            columns.append((categorical[field] == value).to_numpy(dtype=float))
    if not columns:
        raise ValueError("logistic baseline requires at least one feature")
    return np.column_stack([np.ones(len(frame)), *columns])


def _stratified_folds(y: np.ndarray, n_folds: int, seed: int) -> np.ndarray:
    if n_folds < 2:
        raise ValueError("cross-fitting requires at least two folds")
    if min(np.bincount(y, minlength=2)) < n_folds:
        raise ValueError("each outcome class must contain at least one row per fold")
    rng = np.random.default_rng(seed)
    assignments = np.empty(len(y), dtype=int)
    for outcome in (0, 1):
        indices = np.flatnonzero(y == outcome)
        rng.shuffle(indices)
        assignments[indices] = np.arange(len(indices)) % n_folds
    return assignments


def _fit_weighted_logistic(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    *,
    l2: float = 1.0,
) -> np.ndarray:
    normalized_weights = weights / float(np.mean(weights))

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        linear = x @ beta
        loss = float(
            np.sum(normalized_weights * (np.logaddexp(0.0, linear) - y * linear))
            + 0.5 * l2 * np.dot(beta[1:], beta[1:])
        )
        probability = expit(linear)
        gradient = x.T @ (normalized_weights * (probability - y))
        gradient[1:] += l2 * beta[1:]
        return loss, gradient

    result = minimize(
        objective,
        np.zeros(x.shape[1], dtype=float),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-10},
    )
    if not result.success:
        raise RuntimeError("logistic baseline failed to converge: " + result.message)
    return np.asarray(result.x, dtype=float)


def _cross_fitted_logistic(
    frame: pd.DataFrame,
    fields: list[str],
    y: np.ndarray,
    weights: np.ndarray,
    folds: np.ndarray,
) -> np.ndarray:
    x = _one_hot_matrix(frame, fields)
    probabilities = np.empty(len(frame), dtype=float)
    for fold in sorted(np.unique(folds)):
        test = folds == fold
        train = ~test
        beta = _fit_weighted_logistic(x[train], y[train], weights[train])
        probabilities[test] = expit(x[test] @ beta)
    return np.clip(probabilities, 1e-6, 1 - 1e-6)


def _fit_categorical_naive_bayes(
    train: pd.DataFrame,
    fields: list[str],
    y: np.ndarray,
    weights: np.ndarray,
    vocabularies: dict[str, list[str]],
    *,
    alpha: float = 1.0,
) -> dict[str, Any]:
    class_weight = np.array([weights[y == outcome].sum() for outcome in (0, 1)])
    priors = (class_weight + alpha) / (class_weight.sum() + 2 * alpha)
    likelihoods: dict[str, dict[str, np.ndarray]] = {}
    for field in fields:
        likelihoods[field] = {}
        vocabulary = vocabularies[field]
        for value in vocabulary:
            mask = train[field].to_numpy() == value
            counts = np.array(
                [weights[mask & (y == outcome)].sum() for outcome in (0, 1)],
                dtype=float,
            )
            likelihoods[field][value] = (counts + alpha) / (class_weight + alpha * len(vocabulary))
    return {"priors": priors, "likelihoods": likelihoods}


def _predict_categorical_naive_bayes(
    model: dict[str, Any],
    frame: pd.DataFrame,
    fields: list[str],
) -> np.ndarray:
    log_probability = np.tile(np.log(model["priors"]), (len(frame), 1))
    for field in fields:
        lookup = model["likelihoods"][field]
        for row_index, value in enumerate(frame[field]):
            log_probability[row_index] += np.log(lookup[value])
    normalizer = np.logaddexp(log_probability[:, 0], log_probability[:, 1])
    return np.exp(log_probability[:, 1] - normalizer)


def _cross_fitted_naive_bayes(
    frame: pd.DataFrame,
    fields: list[str],
    y: np.ndarray,
    weights: np.ndarray,
    folds: np.ndarray,
) -> np.ndarray:
    categorical = _categorical_frame(frame, fields)
    vocabularies = {field: sorted(categorical[field].unique()) for field in fields}
    probabilities = np.empty(len(frame), dtype=float)
    for fold in sorted(np.unique(folds)):
        test = folds == fold
        train = ~test
        model = _fit_categorical_naive_bayes(
            categorical.loc[train],
            fields,
            y[train],
            weights[train],
            vocabularies,
        )
        probabilities[test] = _predict_categorical_naive_bayes(
            model,
            categorical.loc[test],
            fields,
        )
    return np.clip(probabilities, 1e-6, 1 - 1e-6)


def _weighted_kappa(y: np.ndarray, predicted: np.ndarray, weights: np.ndarray) -> float:
    total = float(weights.sum())
    observed = float(np.sum(weights * (y == predicted)) / total)
    actual_positive = float(np.sum(weights * y) / total)
    predicted_positive = float(np.sum(weights * predicted) / total)
    expected = actual_positive * predicted_positive + (1 - actual_positive) * (
        1 - predicted_positive
    )
    if math.isclose(expected, 1.0):
        return 0.0
    return (observed - expected) / (1 - expected)


def _metrics(probability: np.ndarray, y: np.ndarray, weights: np.ndarray) -> dict[str, float]:
    predicted = (probability >= 0.5).astype(int)
    clipped = np.clip(probability, 1e-12, 1 - 1e-12)
    return {
        "brier": float(np.average((probability - y) ** 2, weights=weights)),
        "agreement": float(np.average(predicted == y, weights=weights)),
        "cohen_kappa": float(_weighted_kappa(y, predicted, weights)),
        "log_loss": float(
            np.average(-(y * np.log(clipped) + (1 - y) * np.log(1 - clipped)), weights=weights)
        ),
        "mean_predicted_republican_share": float(np.average(probability, weights=weights)),
        "observed_republican_share": float(np.average(y, weights=weights)),
    }


def evaluate_anes_statistical_baselines(
    strict_profiles_path: str | Path,
    paper_profiles_path: str | Path,
    targets_path: str | Path,
    output_path: str | Path,
    *,
    target_field: str = "presvote2012_x",
    folds: int = 5,
    seed: int = 220906899,
    expected_n: int | None = 4188,
) -> dict[str, Any]:
    """Evaluate deterministic and outcome-fitted comparators on every valid two-party case."""
    strict_manifest = _profile_manifest(strict_profiles_path)
    paper_manifest = _profile_manifest(paper_profiles_path)
    if strict_manifest.get("profile_timing_policy") != "strict_pre_election":
        raise ValueError("strict baseline input lacks the strict_pre_election policy")
    if paper_manifest.get("profile_timing_policy") != "paper_faithful":
        raise ValueError("paper baseline input lacks the paper_faithful policy")

    strict = _load_profiles(strict_profiles_path)
    paper = _load_profiles(paper_profiles_path)
    targets = pd.read_csv(resolve(targets_path))
    required_targets = {"synthetic_person_id", "population_weight", target_field}
    missing_targets = required_targets - set(targets.columns)
    if missing_targets:
        raise ValueError("target file is missing: " + ", ".join(sorted(missing_targets)))
    if set(strict["synthetic_person_id"]) != set(paper["synthetic_person_id"]):
        raise ValueError("strict and paper profile sets contain different respondents")

    frame = strict.merge(
        paper,
        on="synthetic_person_id",
        how="inner",
        validate="one_to_one",
        suffixes=("", "__paper"),
    ).merge(targets, on="synthetic_person_id", how="left", validate="one_to_one")
    target = pd.to_numeric(frame[target_field], errors="coerce")
    frame = frame.loc[target.isin([1, 2])].reset_index(drop=True)
    if expected_n is not None and len(frame) != expected_n:
        raise ValueError(
            f"expected {expected_n:,} valid two-party respondents, found {len(frame):,}"
        )
    y = (pd.to_numeric(frame[target_field], errors="raise") == 2).astype(int).to_numpy()
    weights = pd.to_numeric(frame["population_weight"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("evaluation weights must be finite and positive")
    fold_assignments = _stratified_folds(y, folds, seed)

    strict_fields = list(STRICT_PRE_ELECTION_PROFILE_FIELDS)
    paper_fields = list(PAPER_STUDY_2_PROFILE_FIELDS)
    paper_frame = frame[
        [f"{field}__paper" if field in strict_fields else field for field in paper_fields]
    ].copy()
    paper_frame.columns = paper_fields

    pid = pd.to_numeric(frame["pid_x"], errors="coerce")
    requested_party_rule = np.where(pid.isin([1, 2]), 0.0, 1.0)
    model_probabilities = {
        "party_id_strong_or_weak_democrat_rule": requested_party_rule,
        "logistic_party_id_and_ideology": _cross_fitted_logistic(
            frame,
            ["pid_x", "libcpre_self"],
            y,
            weights,
            fold_assignments,
        ),
        "logistic_strict_pre_election": _cross_fitted_logistic(
            frame,
            strict_fields,
            y,
            weights,
            fold_assignments,
        ),
        "categorical_naive_bayes_strict_pre_election": _cross_fitted_naive_bayes(
            frame,
            strict_fields,
            y,
            weights,
            fold_assignments,
        ),
        "logistic_paper_faithful": _cross_fitted_logistic(
            paper_frame,
            paper_fields,
            y,
            weights,
            fold_assignments,
        ),
        "categorical_naive_bayes_paper_faithful": _cross_fitted_naive_bayes(
            paper_frame,
            paper_fields,
            y,
            weights,
            fold_assignments,
        ),
    }

    predictions_path = resolve(output_path).with_name("statistical-baseline-predictions.jsonl")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    with predictions_path.open("w", encoding="utf-8") as handle:
        for model_id, probability in model_probabilities.items():
            for index, value in enumerate(probability):
                handle.write(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "model_id": model_id,
                            "synthetic_person_id": frame.loc[index, "synthetic_person_id"],
                            "fold": int(fold_assignments[index]),
                            "predicted_probability_romney": float(value),
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )

    results = []
    for model_id, probability in model_probabilities.items():
        results.append(
            {
                "model_id": model_id,
                "n": len(frame),
                "weighted": _metrics(probability, y, weights),
                "unweighted": _metrics(probability, y, np.ones(len(frame))),
            }
        )
    by_model = {row["model_id"]: row for row in results}
    post_field_sensitivity = {
        "logistic_weighted_brier_delta_paper_minus_strict": (
            by_model["logistic_paper_faithful"]["weighted"]["brier"]
            - by_model["logistic_strict_pre_election"]["weighted"]["brier"]
        ),
        "naive_bayes_weighted_brier_delta_paper_minus_strict": (
            by_model["categorical_naive_bayes_paper_faithful"]["weighted"]["brier"]
            - by_model["categorical_naive_bayes_strict_pre_election"]["weighted"]["brier"]
        ),
        "interpretation": (
            "Negative values mean the paper-faithful model had lower Brier error. This is a "
            "retrospective sensitivity comparison, not evidence that post-election fields are "
            "valid "
            "forecast inputs."
        ),
    }
    report = {
        "schema_version": 1,
        "artifact_type": "retrospective_outcome_fitted_baselines",
        "scientific_result": False,
        "target_access_required": True,
        "runtime_eligible": False,
        "n_valid_two_party": len(frame),
        "cross_fitting": {
            "folds": folds,
            "seed": seed,
            "method": "stratified out-of-fold prediction",
            "guarantee": (
                "No respondent is scored by a fitted model trained on that respondent's target."
            ),
        },
        "party_rule": {
            "definition": "pid_x in {1, 2} predicts Obama; every other code predicts Romney.",
            "noise": False,
            "fitted": False,
        },
        "strict_fields": strict_fields,
        "paper_faithful_fields": paper_fields,
        "post_election_fields_in_paper_profile": ["discuss_disc", "patriot_flag"],
        "results": results,
        "post_field_sensitivity": post_field_sensitivity,
        "inputs": {
            "strict_profiles_sha256": _sha256_file(resolve(strict_profiles_path)),
            "paper_profiles_sha256": _sha256_file(resolve(paper_profiles_path)),
            "targets_sha256": _sha256_file(resolve(targets_path)),
        },
        "predictions": str(predictions_path),
    }
    report["predictions_sha256"] = _sha256_file(predictions_path)
    destination = resolve(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(destination)
    return report
