from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaderboard.anes import RUN_ID, build_anes_results_payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_anes_payload_reports_missing_bundle(tmp_path: Path):
    payload = build_anes_results_payload(tmp_path)
    assert payload == {
        "available": False,
        "status": "not_built",
        "run_id": RUN_ID,
        "message": (
            "The official ANES 2012 structural result bundle has not been built "
            "in this workspace."
        ),
    }


def test_anes_payload_is_curated_and_computes_deltas(tmp_path: Path):
    experiment = tmp_path / "data" / "runs" / RUN_ID / "anes-society"
    output = experiment / "container-output"
    _write_json(
        output / "evaluation.json",
        {
            "engine": "provider_free_structural_mock",
            "scientific_result": False,
            "warning": "structural only",
            "target_field": "held_out_vote",
            "target_population_reference": {
                "n_valid_two_party": 80,
                "weighted_observed_republican_share": 0.46,
                "weight_source": "evaluation_vault",
            },
            "summary": [
                {
                    "treatment": "independent",
                    "mean_brier": 0.08,
                    "mean_agreement": 0.92,
                    "mean_cohen_kappa": 0.81,
                    "mean_predicted_republican_share": 0.44,
                },
                {
                    "treatment": "society",
                    "mean_brier": 0.10,
                    "mean_agreement": 0.90,
                    "mean_cohen_kappa": 0.77,
                    "mean_predicted_republican_share": 0.41,
                },
            ],
            "per_replication": [{"treatment": "independent", "replication": 0}],
            "prediction_seal_sha256": "prediction-seal",
        },
    )
    _write_json(
        experiment / "runtime" / "manifest.json",
        {
            "run_id": RUN_ID,
            "n_profiles": 100,
            "profile_fields": ["age", "party"],
            "information_cutoff": "2012-11-05",
            "weighting_status": "official_weight",
        },
    )
    _write_json(
        experiment / "question_bank.jsonl.manifest.json",
        {"counts": {"total": 998}},
    )
    _write_json(
        output / "prediction-seal.json",
        {"replications": 5, "max_agents": 120, "predictions_sha256": "predictions"},
    )
    (output / "predictions.jsonl").write_text("{}\n{}\n")
    (output / "interaction_summaries.jsonl").write_text("{}\n")

    payload = build_anes_results_payload(tmp_path)

    assert payload["available"] is True
    assert payload["dataset"]["respondents"] == 100
    assert payload["structural_run"]["prediction_count"] == 2
    assert payload["structural_run"]["interaction_summary_count"] == 1
    deltas = payload["deltas_society_minus_independent"]
    assert deltas["brier"] == pytest.approx(0.02)
    assert deltas["agreement"] == pytest.approx(-0.02)
    assert deltas["cohen_kappa"] == pytest.approx(-0.04)
    assert deltas["predicted_republican_share"] == pytest.approx(-0.03)
    serialized = json.dumps(payload)
    assert str(tmp_path) not in serialized
    assert "artifact" not in serialized
