"""Curated, path-free ANES 2012 experiment results for the local viewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from psbx.paths import repo_root

RUN_ID = "anes2012-society-official-structural"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def _metric_delta(
    independent: dict[str, Any], society: dict[str, Any], field: str
) -> float | None:
    left = independent.get(field)
    right = society.get(field)
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return float(right) - float(left)


def build_anes_results_payload(root: Path | None = None) -> dict[str, Any]:
    """Return public experiment metadata without leaking artifact paths or target rows."""

    base = (root or repo_root()).resolve()
    experiment = base / "data" / "runs" / RUN_ID / "anes-society"
    container_output = experiment / "container-output"
    evaluation_path = container_output / "evaluation.json"
    if not evaluation_path.is_file():
        evaluation_path = experiment / "evaluation.json"

    evaluation = _read_json(evaluation_path)
    if not evaluation:
        return {
            "available": False,
            "status": "not_built",
            "run_id": RUN_ID,
            "message": (
                "The official ANES 2012 structural result bundle has not been built "
                "in this workspace."
            ),
        }

    runtime = _read_json(experiment / "runtime" / "manifest.json")
    question_bank = _read_json(experiment / "question_bank.jsonl.manifest.json")
    paper = _read_json(experiment / "paper-study2-replication.json")
    split_seal = _read_json(experiment / "split-seal.json")
    prediction_seal = _read_json(container_output / "prediction-seal.json")
    election = _read_json(
        base / "data" / "elections" / "normalized" / "fec-federal-2012" / "manifest.json"
    )

    summaries = evaluation.get("summary") or []
    by_treatment = {
        str(row.get("treatment")): row
        for row in summaries
        if isinstance(row, dict) and row.get("treatment")
    }
    independent = by_treatment.get("independent", {})
    society = by_treatment.get("society", {})
    target = evaluation.get("target_population_reference") or {}

    profile_fields = runtime.get("profile_fields") or []
    election_states = election.get("states") or []
    limitations = [
        (
            "The displayed experiment uses a deterministic provider-free structural mock, "
            "not a live language model, so its scores are not evidence of human-response "
            "fidelity."
        ),
        (
            "The hosted GPT-4.1 mini runner requires network access on the host; it cannot "
            "call the provider from a Docker container running with network disabled."
        ),
        (
            "The ANES source was released after the election. Pre-election responses are "
            "treated as private contemporaneous covariates, while the vote outcome remains "
            "in the evaluation vault."
        ),
        (
            "The normalized comparison layer currently covers federal President, U.S. "
            "House, and U.S. Senate contests; exhaustive state and local election results "
            "are not yet loaded."
        ),
        (
            "A fully authenticated election-eve corpus and the full model-powered question "
            "experiment have not yet been executed."
        ),
    ]

    return {
        "available": True,
        "status": "structural_validation_complete",
        "run_id": runtime.get("run_id") or RUN_ID,
        "experiment": {
            "design": runtime.get("design") or "society_treatment",
            "engine": evaluation.get("engine"),
            "scientific_result": bool(evaluation.get("scientific_result")),
            "warning": evaluation.get("warning"),
            "target_field": evaluation.get("target_field"),
        },
        "boundary": {
            "information_cutoff": runtime.get("information_cutoff"),
            "election_date": runtime.get("election_date"),
            "source_release_date": runtime.get("source_release_date"),
            "source_was_public_at_cutoff": runtime.get("source_was_public_at_cutoff"),
            "profile_collection_timing": runtime.get("profile_collection_timing"),
            "guardrail": runtime.get("guardrail"),
            "interpretation": runtime.get("interpretation"),
        },
        "dataset": {
            "respondents": runtime.get("n_profiles"),
            "profile_field_count": len(profile_fields),
            "profile_fields": profile_fields,
            "weighting_status": runtime.get("weighting_status"),
            "valid_two_party_outcomes": target.get("n_valid_two_party"),
            "weighted_observed_republican_share": target.get(
                "weighted_observed_republican_share"
            ),
            "weight_source": target.get("weight_source"),
        },
        "question_bank": {
            "counts": question_bank.get("counts") or {},
            "definition": question_bank.get("definition"),
        },
        "structural_run": {
            "replications": prediction_seal.get("replications"),
            "max_agents_per_replication": prediction_seal.get("max_agents"),
            "group_size": prediction_seal.get("group_size"),
            "rounds": prediction_seal.get("rounds"),
            "sampling": prediction_seal.get("profile_sampling"),
            "weight_application": prediction_seal.get("survey_weight_application"),
            "network_access_required": prediction_seal.get("network_access_required"),
            "prediction_count": _line_count(container_output / "predictions.jsonl"),
            "interaction_summary_count": _line_count(
                container_output / "interaction_summaries.jsonl"
            ),
        },
        "arms": summaries,
        "deltas_society_minus_independent": {
            field.removeprefix("mean_"): _metric_delta(independent, society, field)
            for field in (
                "mean_brier",
                "mean_agreement",
                "mean_cohen_kappa",
                "mean_predicted_republican_share",
            )
        },
        "per_replication": evaluation.get("per_replication") or [],
        "paper_study2": {
            key: paper.get(key)
            for key in (
                "source",
                "n_all_rows",
                "n_two_party_comparison",
                "full_sample_mean_p_romney",
                "two_party_mean_p_romney",
                "observed_two_party_romney_share",
                "brier",
                "agreement",
                "cohen_kappa",
                "threshold",
                "weighting",
            )
        },
        "federal_elections": {
            "dataset_id": election.get("dataset_id"),
            "candidate_rows": election.get("rows"),
            "contests": election.get("contests"),
            "states_and_dc": len(election_states),
            "office_levels": election.get("office_levels") or [],
            "geography_levels": election.get("geography_levels") or [],
            "cutoff_date": election.get("cutoff_date"),
        },
        "seals": {
            "source_dta_sha256": split_seal.get("source_sha256"),
            "runtime_profiles_sha256": split_seal.get("runtime_profiles_sha256"),
            "evaluation_targets_sha256": split_seal.get("evaluation_targets_sha256"),
            "split_seal_sha256": split_seal.get("seal_sha256"),
            "prediction_seal_sha256": evaluation.get("prediction_seal_sha256"),
            "predictions_sha256": prediction_seal.get("predictions_sha256"),
        },
        "limitations": limitations,
    }
