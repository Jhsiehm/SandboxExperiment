import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from psbx.eval.track_b_population import (
    evaluate_behavior_files,
    evaluate_behavior_targets,
    evaluate_sealed_behavior,
    seal_behavior_predictions,
)
from psbx.population.schemas import SurveyTarget


def test_held_out_behavior_target_evaluation():
    report = evaluate_behavior_files(
        run_id="fixture-eval",
        population_path="tests/fixtures/validation_population.csv",
        responses_path="tests/fixtures/simulated_responses.csv",
        targets_path="tests/fixtures/survey_targets.csv",
    )
    assert report.n_targets == 3
    assert 0 <= report.mean_absolute_error < 0.05
    assert 0 <= report.root_mean_squared_error < 0.05
    assert report.sample_size_weighted_mae is not None


def test_missing_subgroup_support_fails():
    population = pd.read_csv("tests/fixtures/validation_population.csv")
    responses = pd.read_csv("tests/fixtures/simulated_responses.csv")
    targets = [
        SurveyTarget(
            target_id="missing",
            task_id="turnout_fixture",
            group_field="age_band",
            group_value="not_present",
            observed_probability=0.5,
        )
    ]
    with pytest.raises(ValueError, match="no represented synthetic support"):
        evaluate_behavior_targets(
            run_id="fixture-eval",
            population=population,
            responses=responses,
            targets=targets,
        )


def test_empty_held_out_target_set_fails():
    with pytest.raises(ValueError, match="at least one held-out"):
        evaluate_behavior_targets(
            run_id="fixture-eval",
            population=pd.read_csv("tests/fixtures/validation_population.csv"),
            responses=pd.read_csv("tests/fixtures/simulated_responses.csv"),
            targets=[],
        )


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target_provenance(tmp_path, targets, seal, universe="unspecified"):
    source = tmp_path / "source-report.pdf"
    source.write_bytes(b"fixture source report")
    provenance = tmp_path / "target-provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "zone": "evaluation_vault",
                "target_artifact": {
                    "filename": targets.name,
                    "sha256": _sha256(targets),
                },
                "prediction_seal_sha256_before_reveal": _sha256(seal),
                "target_exclusion_attestation": True,
                "execution_isolated": False,
                "population_universes": [universe],
                "source": {
                    "local_path": source.name,
                    "sha256": _sha256(source),
                },
            }
        ),
        encoding="utf-8",
    )
    return provenance


def test_prediction_seal_precedes_target_reveal_and_freezes_metrics(tmp_path):
    training = tmp_path / "model-card.json"
    training.write_text(
        json.dumps({"model": "fixture-probabilistic-baseline", "target_access": False}),
        encoding="utf-8",
    )
    seal_path = tmp_path / "prediction-seal.json"
    sealed = seal_behavior_predictions(
        run_id="fixture-sealed-eval",
        population_path="tests/fixtures/validation_population.csv",
        responses_path="tests/fixtures/simulated_responses.csv",
        training_artifacts=[training],
        model_id="fixture-probabilistic-baseline",
        output_path=seal_path,
        max_mean_absolute_error=0.05,
        max_root_mean_squared_error=0.05,
        minimum_targets=3,
    )
    serialized_seal = seal_path.read_text(encoding="utf-8")
    target_path = tmp_path / "held-out-targets.csv"
    target_path.write_bytes(Path("tests/fixtures/survey_targets.csv").read_bytes())
    target_digest = _sha256(target_path)
    provenance = _target_provenance(tmp_path, target_path, seal_path)
    assert sealed["target_artifact_loaded"] is False
    assert target_digest not in serialized_seal
    assert target_path.name not in serialized_seal
    assert "observed_probability" not in serialized_seal
    result = evaluate_sealed_behavior(
        seal_path=seal_path,
        expected_seal_sha256=_sha256(seal_path),
        targets_path=target_path,
        expected_target_sha256=target_digest,
        target_provenance_path=provenance,
        expected_target_provenance_sha256=_sha256(provenance),
        output_path=tmp_path / "validation-report.json",
    )
    assert result["passed"] is True
    assert result["validation"]["metrics_frozen"] is True
    assert result["validation"]["targets_within_observed_ci95"] == 3
    assert result["prediction_seal_sha256"] == _sha256(seal_path)


def test_sealed_evaluation_rejects_target_and_prediction_tampering(tmp_path):
    population = tmp_path / "population.csv"
    responses = tmp_path / "responses.csv"
    training = tmp_path / "training.json"
    population.write_bytes(Path("tests/fixtures/validation_population.csv").read_bytes())
    responses.write_bytes(Path("tests/fixtures/simulated_responses.csv").read_bytes())
    training.write_text("{}", encoding="utf-8")
    seal_path = tmp_path / "seal.json"
    seal_behavior_predictions(
        run_id="tamper-check",
        population_path=population,
        responses_path=responses,
        training_artifacts=[training],
        model_id="fixture",
        output_path=seal_path,
    )
    targets = tmp_path / "targets.csv"
    targets.write_bytes(Path("tests/fixtures/survey_targets.csv").read_bytes())
    provenance = _target_provenance(tmp_path, targets, seal_path)
    with pytest.raises(ValueError, match="target checksum"):
        evaluate_sealed_behavior(
            seal_path=seal_path,
            expected_seal_sha256=_sha256(seal_path),
            targets_path=targets,
            expected_target_sha256="0" * 64,
            target_provenance_path=provenance,
            expected_target_provenance_sha256=_sha256(provenance),
            output_path=tmp_path / "report.json",
        )
    responses.write_text(
        responses.read_text(encoding="utf-8").replace("0.25", "0.99"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="input changed"):
        evaluate_sealed_behavior(
            seal_path=seal_path,
            expected_seal_sha256=_sha256(seal_path),
            targets_path=targets,
            expected_target_sha256=_sha256(targets),
            target_provenance_path=provenance,
            expected_target_provenance_sha256=_sha256(provenance),
            output_path=tmp_path / "report.json",
        )


def test_prediction_seal_rejects_embedded_ground_truth(tmp_path):
    responses = pd.read_csv("tests/fixtures/simulated_responses.csv")
    responses["observed_probability"] = 0.5
    responses_path = tmp_path / "responses.csv"
    responses.to_csv(responses_path, index=False)
    training = tmp_path / "training.json"
    training.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="held-out target columns"):
        seal_behavior_predictions(
            run_id="leak-check",
            population_path="tests/fixtures/validation_population.csv",
            responses_path=responses_path,
            training_artifacts=[training],
            model_id="fixture",
            output_path=tmp_path / "seal.json",
        )


def test_sealed_evaluation_rejects_post_reveal_seal_edits(tmp_path):
    training = tmp_path / "training.json"
    training.write_text("{}", encoding="utf-8")
    seal_path = tmp_path / "seal.json"
    seal_behavior_predictions(
        run_id="seal-tamper",
        population_path="tests/fixtures/validation_population.csv",
        responses_path="tests/fixtures/simulated_responses.csv",
        training_artifacts=[training],
        model_id="fixture",
        output_path=seal_path,
        max_mean_absolute_error=0,
        max_root_mean_squared_error=0,
        minimum_targets=99,
    )
    frozen_seal_sha = _sha256(seal_path)
    targets = tmp_path / "targets.csv"
    targets.write_bytes(Path("tests/fixtures/survey_targets.csv").read_bytes())
    provenance = _target_provenance(tmp_path, targets, seal_path)
    edited = json.loads(seal_path.read_text(encoding="utf-8"))
    edited["metric_plan"]["thresholds"] = {
        "max_mean_absolute_error": 1,
        "max_root_mean_squared_error": 1,
        "minimum_targets": 1,
    }
    seal_path.write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(ValueError, match="pre-reveal"):
        evaluate_sealed_behavior(
            seal_path=seal_path,
            expected_seal_sha256=frozen_seal_sha,
            targets_path=targets,
            expected_target_sha256=_sha256(targets),
            target_provenance_path=provenance,
            expected_target_provenance_sha256=_sha256(provenance),
            output_path=tmp_path / "report.json",
        )
    with pytest.raises(ValueError, match="fingerprint"):
        evaluate_sealed_behavior(
            seal_path=seal_path,
            expected_seal_sha256=_sha256(seal_path),
            targets_path=targets,
            expected_target_sha256=_sha256(targets),
            target_provenance_path=provenance,
            expected_target_provenance_sha256=_sha256(provenance),
            output_path=tmp_path / "report.json",
        )


def test_behavior_evaluation_requires_complete_positive_synthetic_support():
    population = pd.read_csv("tests/fixtures/validation_population.csv")
    responses = pd.read_csv("tests/fixtures/simulated_responses.csv").iloc[:1]
    target = SurveyTarget(
        target_id="all",
        task_id="turnout_fixture",
        observed_probability=0.5,
        sample_size=1000,
    )
    with pytest.raises(ValueError, match="incomplete synthetic response coverage"):
        evaluate_behavior_targets(
            run_id="coverage",
            population=population,
            responses=responses,
            targets=[target],
        )
    responses = pd.read_csv("tests/fixtures/simulated_responses.csv")
    responses["response_weight"] = -1
    with pytest.raises(ValueError, match="finite nonnegative"):
        evaluate_behavior_targets(
            run_id="negative-weight",
            population=population,
            responses=responses,
            targets=[target],
        )


def test_published_survey_moe_is_used_instead_of_nominal_binomial_interval():
    report = evaluate_behavior_targets(
        run_id="published-moe",
        population=pd.read_csv("tests/fixtures/validation_population.csv"),
        responses=pd.read_csv("tests/fixtures/simulated_responses.csv"),
        targets=[
            SurveyTarget(
                target_id="all",
                task_id="turnout_fixture",
                observed_probability=0.52,
                sample_size=600,
                published_moe95=0.03,
                uncertainty_method="published_weighted_survey_moe95",
            )
        ],
    )
    result = report.targets[0]
    assert result.observed_ci95_lower == pytest.approx(0.49)
    assert result.observed_ci95_upper == pytest.approx(0.55)
    assert result.uncertainty_method == "published_weighted_survey_moe95"
    assert result.uncertainty_is_approximate is False
    assert result.synthetic_coverage == pytest.approx(1.0)


def test_target_population_universe_must_match_population():
    population = pd.read_csv("tests/fixtures/validation_population.csv")
    population["population_universe"] = "all_residents"
    with pytest.raises(ValueError, match="universe does not match"):
        evaluate_behavior_targets(
            run_id="universe",
            population=population,
            responses=pd.read_csv("tests/fixtures/simulated_responses.csv"),
            targets=[
                SurveyTarget(
                    target_id="adults",
                    task_id="turnout_fixture",
                    observed_probability=0.5,
                    population_universe="adults_18_plus",
                )
            ],
        )
