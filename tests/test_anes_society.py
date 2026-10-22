import json
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from psbx.experiments.anes_society import (
    ANES_2012_PROFILE_TIMING,
    STRICT_PRE_ELECTION_PROFILE_FIELDS,
    AnesSocietySpec,
    _parse_questionnaire_text,
    _require_balanced_prediction_panel,
    audit_runtime_payload,
    evaluate_paper_study2_replication,
    evaluate_vote_predictions,
    load_cutoff_world,
    prepare_anes_split,
    render_anes_2012_profile,
    run_live_llm_vote_society,
    run_provider_free_society,
    sandbox_doctor,
    sealed_container_command,
    verify_prepared_runtime_profiles,
)


def _spec(**updates):
    values = {
        "run_id": "anes-test",
        "design": "society_treatment",
        "information_cutoff": date(2012, 11, 5),
        "election_date": date(2012, 11, 6),
        "case_id_field": "caseid",
        "profile_fields": ["pid_x", "libcpre_self"],
        "target_fields": ["presvote2012_x"],
        "profile_timing_policy": "strict_pre_election",
        "source_release_date": date(2016, 5, 24),
        "replications": 2,
        "max_agents": 4,
        "group_size": 2,
        "interaction_rounds": 2,
    }
    values.update(updates)
    return AnesSocietySpec.model_validate(values)


def test_questionnaire_parser_inventories_and_excludes_sensitive_items():
    text = """
[[PAGE 1]]
section: TEST
"Question label" (TEST_CHOICE)
........................................................................................................
Which option do you choose?
........................................................................................................
1. First
2. Second
response type: Single Punch
response order: Order as listed
"RESTRICTED: name" (TEST_NAME)
........................................................................................................
What is your name?
........................................................................................................
response type: Text entry
"""
    questions = _parse_questionnaire_text(text, "pre", "a" * 64)
    assert [question.variable for question in questions] == ["TEST_CHOICE", "TEST_NAME"]
    assert questions[0].experimental_eligible is True
    assert questions[0].response_options == ["1. First", "2. Second"]
    assert questions[0].temporal_role == "contemporaneous_profile_candidate"
    assert questions[0].vote_forecast_runtime_allowed is True
    assert questions[1].experimental_eligible is False
    assert set(questions[1].exclusion_reasons) == {
        "free_text_response",
        "restricted_or_identifying",
    }


def test_questionnaire_parser_makes_duplicate_specification_ids_unique():
    text = """
[[PAGE 1]]
"First wording" (DUP_VAR)
........................................................................................................
First question?
........................................................................................................
1. Yes
2. No
response type: Single Punch
"Second wording" (DUP_VAR)
........................................................................................................
Second question?
........................................................................................................
1. Yes
2. No
response type: Single Punch
"""
    questions = _parse_questionnaire_text(text, "post", "a" * 64)
    assert [question.question_id for question in questions] == [
        "anes2012-post-dup_var",
        "anes2012-post-dup_var-2",
    ]
    assert [question.occurrence for question in questions] == [1, 2]
    assert all(question.vote_forecast_runtime_allowed is False for question in questions)


def test_spec_rejects_target_as_profile():
    with pytest.raises(ValueError, match="overlap"):
        _spec(profile_fields=["pid_x", "presvote2012_x"])


def test_strict_profile_policy_rejects_codebook_post_election_fields():
    with pytest.raises(ValueError, match="post-election fields"):
        _spec(profile_fields=["pid_x", "discuss_disc"])


def test_strict_profile_field_set_excludes_only_verified_post_fields():
    assert set(STRICT_PRE_ELECTION_PROFILE_FIELDS) == set(ANES_2012_PROFILE_TIMING) - {
        "discuss_disc",
        "patriot_flag",
    }


def test_prepare_split_keeps_target_out_of_runtime(tmp_path):
    source = tmp_path / "anes.csv"
    pd.DataFrame(
        {
            "caseid": [1, 2, 3, 4],
            "pid_x": [1, 4, 7, -9],
            "libcpre_self": [1, 4, 7, 4],
            "presvote2012_x": [1, 1, 2, -2],
        }
    ).to_csv(source, index=False)
    prepared = prepare_anes_split(
        source,
        _spec(),
        tmp_path / "run",
        evaluation_root=tmp_path / "vault",
    )
    runtime_text = (tmp_path / "run" / "runtime" / "profiles.jsonl").read_text()
    assert "presvote2012_x" not in runtime_text
    first = json.loads(runtime_text.splitlines()[0])
    assert first["synthetic_person_id"].startswith("anes12-")
    assert first["profile"] == {"pid_x": 1, "libcpre_self": 1}
    assert prepared.weighting_status == "uniform_unweighted_validation_only"
    timing_audit = json.loads(
        (tmp_path / "run" / "conditioning-field-timing-audit.json").read_text()
    )
    assert timing_audit["strict_pre_election_eligible"] is True
    assert timing_audit["post_election_fields"] == []
    targets = pd.read_csv(prepared.evaluation_targets)
    assert "presvote2012_x" in targets
    assert "pid_x" not in targets


def test_runtime_audit_rejects_nested_target_key():
    with pytest.raises(ValueError, match="leaked"):
        audit_runtime_payload({"profile": {"presvote2012_x": 1}}, {"presvote2012_x"})


def test_study2_profile_renderer_preserves_reported_variable_order():
    rendered = render_anes_2012_profile(
        {
            "profile": {
                "dem_raceeth_x": 1,
                "gender_respondent_x": 2,
                "dem_age_r_x": 42,
                "libcpre_self": 4,
                "pid_x": 4,
                "paprofile_interestpolit": 2,
                "relig_church": 2,
                "discuss_disc": 1,
                "patriot_flag": 1,
                "sample_stfips": 6,
            }
        }
    )
    ordered_phrases = [
        "White, non-Hispanic",
        "female",
        "42 years old",
        "moderate",
        "independent",
        "somewhat interested",
        "religious services",
        "discuss politics",
        "American flag",
        "FIPS code is 06",
    ]
    offsets = [rendered.index(phrase) for phrase in ordered_phrases]
    assert offsets == sorted(offsets)


def test_provider_free_society_is_sealed_before_evaluation(tmp_path):
    source = tmp_path / "anes.csv"
    pd.DataFrame(
        {
            "caseid": list(range(1, 9)),
            "pid_x": [1, 2, 3, 4, 5, 6, 7, 4],
            "libcpre_self": [1, 2, 3, 4, 5, 6, 7, 4],
            "presvote2012_x": [1, 1, 1, 1, 2, 2, 2, 2],
        }
    ).to_csv(source, index=False)
    prepared = prepare_anes_split(
        source,
        _spec(),
        tmp_path / "run",
        evaluation_root=tmp_path / "vault",
    )
    simulated = run_provider_free_society(
        prepared.runtime_profiles,
        tmp_path / "output",
        seed=10,
        replications=2,
        max_agents=4,
        group_size=2,
        rounds=2,
    )
    assert simulated["n_prediction_rows"] == 16
    report = evaluate_vote_predictions(
        simulated["predictions"],
        prepared.evaluation_targets,
        tmp_path / "evaluation.json",
    )
    assert report["scientific_result"] is False
    assert {row["treatment"] for row in report["summary"]} == {
        "independent",
        "society",
    }
    predictions = pd.read_json(simulated["predictions"], lines=True)
    assert "presvote2012_x" not in predictions


def test_provider_free_sampling_does_not_apply_survey_weights_twice(tmp_path):
    profiles = tmp_path / "profiles.jsonl"
    rows = [
        {
            "synthetic_person_id": f"person-{index}",
            "population_weight": 1000.0 if index == 0 else 1.0,
            "profile": {"pid_x": 4, "libcpre_self": 4},
        }
        for index in range(4)
    ]
    profiles.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = run_provider_free_society(
        profiles,
        tmp_path / "output",
        seed=0,
        replications=1,
        max_agents=2,
        group_size=2,
        rounds=1,
    )
    predictions = pd.read_json(result["predictions"], lines=True)
    assert set(predictions["synthetic_person_id"]) == {"person-2", "person-3"}
    seal = json.loads((tmp_path / "output" / "prediction-seal.json").read_text())
    assert seal["profile_sampling"] == "simple_random_without_replacement"
    assert seal["survey_weight_application"] == "evaluation_only"


def test_evaluation_trusts_vault_weights_not_prediction_weights(tmp_path):
    profiles = tmp_path / "profiles.jsonl"
    runtime_rows = [
        {
            "synthetic_person_id": "person-dem",
            "population_weight": 1000.0,
            "profile": {"pid_x": 4, "libcpre_self": 4},
        },
        {
            "synthetic_person_id": "person-rep",
            "population_weight": 1.0,
            "profile": {"pid_x": 4, "libcpre_self": 4},
        },
    ]
    profiles.write_text("".join(json.dumps(row) + "\n" for row in runtime_rows), encoding="utf-8")
    result = run_provider_free_society(
        profiles,
        tmp_path / "output",
        seed=0,
        replications=1,
        max_agents=2,
        group_size=2,
        rounds=1,
    )
    targets = tmp_path / "targets.csv"
    pd.DataFrame(
        {
            "synthetic_person_id": ["person-dem", "person-rep"],
            "population_weight": [1.0, 9.0],
            "presvote2012_x": [1, 2],
        }
    ).to_csv(targets, index=False)
    report = evaluate_vote_predictions(result["predictions"], targets, tmp_path / "evaluation.json")
    assert report["target_population_reference"] == {
        "n_valid_two_party": 2,
        "weighted_observed_republican_share": pytest.approx(0.9),
        "weight_source": "evaluation_vault",
    }
    assert all(
        row["observed_republican_share"] == pytest.approx(0.9) for row in report["per_replication"]
    )


def test_public_paper_baseline_metrics(tmp_path):
    source = tmp_path / "paper.csv"
    pd.DataFrame(
        {
            "p_romney": [0.1, 0.8, 0.6, 0.2],
            "p_obama": [0.9, 0.2, 0.4, 0.8],
            "presvote2012_x": [1, 2, 1, -2],
        }
    ).to_csv(source, index=False)
    report = evaluate_paper_study2_replication(source)
    assert report["n_two_party_comparison"] == 3
    assert report["agreement"] == pytest.approx(2 / 3)
    assert report["observed_two_party_romney_share"] == pytest.approx(1 / 3)


def test_container_plan_is_no_network_and_never_mounts_vault(tmp_path):
    profiles = tmp_path / "profiles.jsonl"
    profiles.write_text("{}\n", encoding="utf-8")
    command = sealed_container_command(profiles, tmp_path / "output")
    rendered = " ".join(command)
    assert "--network none" in rendered
    assert "--read-only" in command
    assert "data/evaluation-vault" not in rendered


def test_cutoff_world_rejects_future_documents(tmp_path):
    source = tmp_path / "world.json"
    source.write_text(
        json.dumps(
            {
                "cutoff_date": "2012-11-05",
                "documents": [
                    {
                        "id": "future",
                        "published_at": "2012-11-06",
                        "title": "Election result",
                        "text": "Later outcome",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="post-cutoff"):
        load_cutoff_world(source, date(2012, 11, 5))


def test_live_conversation_protocol_uses_private_final_ballots(tmp_path):
    source = tmp_path / "anes.csv"
    pd.DataFrame(
        {
            "caseid": [1, 2],
            "pid_x": [1, 7],
            "libcpre_self": [1, 7],
            "presvote2012_x": [1, 2],
        }
    ).to_csv(source, index=False)
    prepared = prepare_anes_split(
        source,
        _spec(run_id="live-prepared"),
        tmp_path / "prepared",
        evaluation_root=tmp_path / "vault",
    )
    workers = [SimpleNamespace(id="model-a"), SimpleNamespace(id="model-b")]

    def fake_completion(model, messages, *, system, tools):
        del model, system
        assert tools is False
        prompt = messages[-1]["content"]
        if 'Return only {"message"' in prompt:
            return SimpleNamespace(text='{"message":"I am weighing party and current events."}')
        return SimpleNamespace(text='{"probability_romney":0.6,"choice":"Romney"}')

    result = run_live_llm_vote_society(
        prepared.runtime_profiles,
        tmp_path / "live",
        run_id="live-test",
        replications=1,
        max_agents=2,
        group_size=2,
        rounds=1,
        _completion=fake_completion,
        _workers=workers,
    )
    assert result["n_prediction_rows"] == 4
    assert result["n_conversation_rows"] == 4
    predictions = pd.read_json(result["predictions"], lines=True)
    assert set(predictions["treatment"]) == {"independent", "society"}
    transcript = pd.read_json(result["conversation"], lines=True)
    assert set(transcript["visibility"]) == {
        "private_deliberation",
        "public_peer_message",
    }
    seal = json.loads((tmp_path / "live" / "prediction-seal.json").read_text())
    assert seal["full_process_container_isolation"] is False
    assert seal["model_weight_temporal_isolation"] is False
    assert seal["profile_sampling"] == "simple_random_without_replacement"
    assert seal["survey_weight_application"] == "evaluation_only"
    assert seal["protocol"] == "matched_private_deliberation_control_v1"
    assert seal["balanced_profile_coverage"]["balanced"] is True


def test_live_runner_rejects_unsealed_profile_file(tmp_path):
    profiles = tmp_path / "profiles.jsonl"
    profiles.write_text(
        json.dumps(
            {
                "synthetic_person_id": "person-1",
                "population_weight": 1.0,
                "profile": {"pid_x": 1, "libcpre_self": 1},
                "information_cutoff": "2012-11-05",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest and parent split seal"):
        run_live_llm_vote_society(
            profiles,
            tmp_path / "live",
            run_id="unsealed-live",
            _completion=lambda *args, **kwargs: None,
            _workers=[SimpleNamespace(id="a"), SimpleNamespace(id="b")],
        )


def test_prepared_runtime_verification_rejects_changed_profile_bytes(tmp_path):
    source = tmp_path / "anes.csv"
    pd.DataFrame(
        {
            "caseid": [1, 2],
            "pid_x": [1, 7],
            "libcpre_self": [1, 7],
            "presvote2012_x": [1, 2],
        }
    ).to_csv(source, index=False)
    prepared = prepare_anes_split(
        source,
        _spec(run_id="sealed-live"),
        tmp_path / "prepared",
        evaluation_root=tmp_path / "vault",
    )
    verified = verify_prepared_runtime_profiles(
        prepared.runtime_profiles,
        cutoff=date(2012, 11, 5),
    )
    assert verified["n_profiles"] == 2
    profiles = tmp_path / "prepared" / "runtime" / "profiles.jsonl"
    profiles.write_text(profiles.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash does not match"):
        verify_prepared_runtime_profiles(profiles, cutoff=date(2012, 11, 5))


def test_live_runner_resumes_completed_calls_without_repeating_them(tmp_path):
    source = tmp_path / "anes.csv"
    pd.DataFrame(
        {
            "caseid": [1, 2],
            "pid_x": [1, 7],
            "libcpre_self": [1, 7],
            "presvote2012_x": [1, 2],
        }
    ).to_csv(source, index=False)
    prepared = prepare_anes_split(
        source,
        _spec(run_id="resume-prepared"),
        tmp_path / "prepared",
        evaluation_root=tmp_path / "vault",
    )
    workers = [SimpleNamespace(id="model-a"), SimpleNamespace(id="model-b")]
    first_attempts = []

    def flaky_completion(model, messages, *, system, tools):
        del model, system, tools
        first_attempts.append(messages[-1]["content"])
        if len(first_attempts) == 3:
            raise RuntimeError("injected interruption")
        if 'Return only {"message"' in messages[-1]["content"]:
            return SimpleNamespace(text='{"message":"private or public thought"}')
        return SimpleNamespace(text='{"probability_romney":0.4,"choice":"Obama"}')

    output = tmp_path / "live"
    with pytest.raises(RuntimeError, match="injected interruption"):
        run_live_llm_vote_society(
            prepared.runtime_profiles,
            output,
            run_id="resume-live",
            replications=1,
            max_agents=2,
            group_size=2,
            rounds=1,
            _completion=flaky_completion,
            _workers=workers,
        )
    checkpoint_lines = (output / "call-checkpoints.jsonl").read_text().splitlines()
    events = [json.loads(line) for line in checkpoint_lines]
    assert [event["status"] for event in events] == ["completed", "completed", "failed"]
    resumed_provider_calls = []

    def resumed_completion(model, messages, *, system, tools):
        del model, system, tools
        resumed_provider_calls.append(messages[-1]["content"])
        if 'Return only {"message"' in messages[-1]["content"]:
            return SimpleNamespace(text='{"message":"private or public thought"}')
        return SimpleNamespace(text='{"probability_romney":0.4,"choice":"Obama"}')

    result = run_live_llm_vote_society(
        prepared.runtime_profiles,
        output,
        run_id="resume-live",
        replications=1,
        max_agents=2,
        group_size=2,
        rounds=1,
        _completion=resumed_completion,
        _workers=workers,
    )
    assert result["resumed_logical_calls"] == 2
    assert len(resumed_provider_calls) == 6
    assert result["n_prediction_rows"] == 4
    assert result["balanced_profile_coverage"]["balanced"] is True


def test_balanced_panel_rejects_missing_treatment_profile():
    predictions = pd.DataFrame(
        [
            {
                "treatment": "independent",
                "replication": 0,
                "synthetic_person_id": "a",
                "model_id": "m",
                "predicted_probability": 0.4,
            },
            {
                "treatment": "independent",
                "replication": 0,
                "synthetic_person_id": "b",
                "model_id": "m",
                "predicted_probability": 0.6,
            },
            {
                "treatment": "society",
                "replication": 0,
                "synthetic_person_id": "a",
                "model_id": "m",
                "predicted_probability": 0.5,
            },
        ]
    )
    with pytest.raises(ValueError, match="exact matched profile coverage"):
        _require_balanced_prediction_panel(predictions)


def test_sandbox_doctor_does_not_overclaim():
    report = sandbox_doctor()
    assert report["existing_container_mode_scope"] == "frozen_retrieval_sidecar_only"
    assert report["existing_full_swarm_isolation"] is False
    assert report["hosted_model_weight_temporal_isolation_supported"] is False


@pytest.mark.parametrize("engine", ["provider_free_structural_mock", "live_llm_no_tools_host"])
def test_evaluation_seals_provenance_and_uses_verified_engine(tmp_path, engine):
    from pathlib import Path

    from psbx.experiments.anes_society import _canonical_json_sha256, _sha256_file

    profiles = tmp_path / "profiles.jsonl"
    profiles.write_text("".join(json.dumps({
        "synthetic_person_id": f"p{i}", "population_weight": 1,
        "profile": {"pid_x": 1 if i == 0 else 7, "libcpre_self": 4},
    }) + "\n" for i in range(2)))
    result = run_provider_free_society(
        profiles, tmp_path / "output", seed=1, replications=1,
        max_agents=2, group_size=2, rounds=1,
    )
    predictions = Path(result["predictions"])
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    for row in rows:
        row["engine"] = engine
    predictions.write_text("".join(json.dumps(row) + "\n" for row in rows))
    seal_path = Path(result["prediction_seal"])
    seal = json.loads(seal_path.read_text())
    seal.update(engine=engine, predictions_sha256=_sha256_file(predictions))
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path.write_text(json.dumps(seal))
    targets = tmp_path / "targets.csv"
    pd.DataFrame({"synthetic_person_id": ["p0", "p1"], "population_weight": [1, 1],
                  "presvote2012_x": [1, 2]}).to_csv(targets, index=False)
    destination = tmp_path / "evaluation.json"
    report = evaluate_vote_predictions(predictions, targets, destination)
    assert report["engine"] == engine
    assert report["warning"].startswith("Live" if engine.startswith("live") else "Provider-free")
    evaluation_seal = json.loads(destination.with_suffix(".seal.json").read_text())
    assert evaluation_seal["report_sha256"] == _sha256_file(destination)
    assert evaluation_seal["targets_sha256"] == _sha256_file(targets)
    assert evaluation_seal["prediction_seal_sha256"] == _sha256_file(seal_path)
    # Valid hashes alone cannot excuse conflicting engine claims.
    seal["engine"] = "conflicting_engine"
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path.write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="engine does not match"):
        evaluate_vote_predictions(predictions, targets, destination)
    seal["engine"] = engine  # Tampering without resealing must also fail.
    seal_path.write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="seal checksum"):
        evaluate_vote_predictions(predictions, targets, destination)
