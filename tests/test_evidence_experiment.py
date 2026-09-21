from datetime import date, datetime, timezone

import pytest

from psbx.corpus.embed import embed_texts
from psbx.corpus.index import HybridIndex
from psbx.experiments import evidence_ablation as evidence_ablation_module
from psbx.experiments.evidence_ablation import (
    CONDITIONS,
    EvidenceAssignment,
    EvidenceExperimentSpec,
    EvidenceFailure,
    EvidenceObservation,
    analyze_evidence_experiment,
    run_evidence_experiment,
)
from psbx.io import read_json, read_jsonl
from psbx.schemas import Document, Epoch, ModelConfig, Question

UTC = timezone.utc


def _question(question_id: str, token: str, truth: bool) -> Question:
    return Question(
        id=question_id,
        epoch_id="e2012",
        category="economic",
        text=f"Will the {token} event occur by December 31, 2012?",
        resolution_criteria="Fixture outcome.",
        cutoff_date=date(2012, 6, 30),
        resolution_date=date(2012, 12, 31),
        ground_truth=truth,
        generator="test",
    )


def _document(document_id: str, token: str, cue: str) -> Document:
    captured = datetime(2012, 6, 1, tzinfo=UTC)
    text = f"The {token} event is {cue}. This authenticated fixture has enough literal text."
    return Document(
        id=document_id,
        url=f"https://example.com/{document_id}",
        outlet="Archive fixture",
        published_at=captured,
        title=f"{token} outlook",
        text=text,
        source_type="news",
        authenticity="authenticated_capture",
        timestamp_basis="archive_capture",
        captured_at=captured,
        source_reference=(
            f"https://web.archive.org/web/20120601000000id_/https://example.com/{document_id}"
        ),
        capture_verified=True,
    )


def _model() -> ModelConfig:
    return ModelConfig(
        id="fixture-model",
        provider="openai",
        model_name="fixture",
        declared_pretraining_cutoff=date(2011, 1, 1),
        is_instruction_tuned=True,
    )


def test_bounded_evidence_experiment_persists_complete_paired_design(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "0")
    questions = [
        _question("alpha-question", "alpha", True),
        _question("beta-question", "beta", False),
    ]
    documents = [
        _document("alpha-evidence", "alpha", "widely expected"),
        _document("beta-evidence", "beta", "not scheduled"),
        _document("gamma-evidence", "gamma", "faces an uncertain"),
    ]
    epoch = Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2013, 6, 30),
        corpus_index_path="unused",
    )
    index = HybridIndex(
        documents,
        embed_texts([f"{document.title} {document.text}" for document in documents]),
        epoch.cutoff_date,
    )
    spec = EvidenceExperimentSpec(
        experiment_id="offline-evidence-ablation",
        epoch="e2012",
        models=["fixture-model"],
        question_set="unused.jsonl",
        n_questions=2,
        evidence_documents=1,
        max_tool_calls=2,
        max_tokens=128,
        bootstrap_replicates=200,
        random_seed=42,
    )

    report = run_evidence_experiment(
        spec,
        questions,
        [_model()],
        epoch,
        index,
        destination=tmp_path,
    )
    assignments = read_jsonl(tmp_path / "assignments.jsonl", EvidenceAssignment)
    observations = read_jsonl(tmp_path / "observations.jsonl", EvidenceObservation)

    assert len(assignments) == len(observations) == 6
    assert {assignment.condition for assignment in assignments} == set(CONDITIONS)
    for unit_id in {assignment.unit_id for assignment in assignments}:
        unit = [assignment for assignment in assignments if assignment.unit_id == unit_id]
        assert sorted(assignment.condition_order for assignment in unit) == [0, 1, 2]
        assert {assignment.condition for assignment in unit} == set(CONDITIONS)
    shuffled = [
        assignment for assignment in assignments if assignment.condition == "shuffled_eligible"
    ]
    assert all(row.source_question_id != row.question_id for row in shuffled)
    assert report["status"] == "complete"
    assert report["common_budget"] == {
        "max_tool_calls": 2,
        "max_tokens": 128,
        "temperature": 0.2,
    }
    assert report["by_condition"]["matched_authenticated"]["mean_brier"] < 0.25
    assert report["by_condition"]["shuffled_eligible"]["mean_brier"] > 0.25
    assert all(
        contrast["n_paired_units"] == 2
        and contrast["n_question_clusters"] == 2
        and contrast["uncertainty_method"] == "question-cluster bootstrap"
        for contrast in report["paired_contrasts"]
    )
    manifest = read_json(tmp_path / "experiment_manifest.json")
    assert manifest["fingerprint"]
    assert manifest["schema_version"] == 2
    assert manifest["prompt_protocol"]["system_prompt"]
    assert set(manifest["prompt_protocol"]["user_prompts_by_question"]) == {
        "alpha-question",
        "beta-question",
    }
    assert len(manifest["prompt_protocol"]["implementation_sha256"]) == 64
    assert read_json(tmp_path / "evidence_packs.json")

    resumed = run_evidence_experiment(
        spec,
        questions,
        [_model()],
        epoch,
        index,
        destination=tmp_path,
    )
    assert resumed == report
    assert len(read_jsonl(tmp_path / "observations.jsonl", EvidenceObservation)) == 6

    original_system_prompt = evidence_ablation_module.system_prompt
    monkeypatch.setattr(
        evidence_ablation_module,
        "system_prompt",
        lambda cutoff: original_system_prompt(cutoff) + "\nProtocol revision.",
    )
    with pytest.raises(RuntimeError, match="different inputs, assignments, or execution"):
        run_evidence_experiment(
            spec,
            questions,
            [_model()],
            epoch,
            index,
            destination=tmp_path,
        )


def test_failed_trial_is_audited_and_resolved_on_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-fixture-token")
    questions = [
        _question("alpha-question", "alpha", True),
        _question("beta-question", "beta", False),
    ]
    documents = [
        _document("alpha-evidence", "alpha", "widely expected"),
        _document("beta-evidence", "beta", "not scheduled"),
    ]
    epoch = Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2013, 6, 30),
        corpus_index_path="unused",
    )
    index = HybridIndex(
        documents,
        embed_texts([f"{document.title} {document.text}" for document in documents]),
        epoch.cutoff_date,
    )
    spec = EvidenceExperimentSpec(
        experiment_id="failure-audit",
        epoch="e2012",
        models=["fixture-model"],
        question_set="unused.jsonl",
        n_questions=2,
        evidence_documents=1,
        max_tool_calls=2,
        max_tokens=128,
        bootstrap_replicates=100,
    )
    original_run_single_agent = evidence_ablation_module.run_single_agent

    def fail_trial(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("provider fixture failed: secret-fixture-token")

    monkeypatch.setattr(evidence_ablation_module, "run_single_agent", fail_trial)
    with pytest.raises(RuntimeError, match="provider fixture failed"):
        run_evidence_experiment(
            spec,
            questions,
            [_model()],
            epoch,
            index,
            destination=tmp_path,
        )

    failures = read_jsonl(tmp_path / "failures.jsonl", EvidenceFailure)
    assert len(failures) == 1
    assert failures[0].attempt == 1
    assert failures[0].error_type == "RuntimeError"
    assert failures[0].error_message == "provider fixture failed: [redacted]"

    monkeypatch.setattr(
        evidence_ablation_module,
        "run_single_agent",
        original_run_single_agent,
    )
    report = run_evidence_experiment(
        spec,
        questions,
        [_model()],
        epoch,
        index,
        destination=tmp_path,
    )
    assert report["status"] == "complete"
    assert report["failure_history"]["n_failed_attempts"] == 1
    assert report["failure_history"]["resolved_trial_ids"] == [failures[0].trial_id]
    assert report["failure_history"]["unresolved_trial_ids"] == []
    assert "provider sampling is not claimed deterministic" in report["random_seed_scope"]


def test_evidence_experiment_rejects_mixed_design_without_multiple_models():
    with pytest.raises(ValueError, match="mixed design requires"):
        EvidenceExperimentSpec(
            experiment_id="bad-mixed",
            epoch="e2012",
            models=["only-one"],
            model_design="mixed",
            question_set="unused.jsonl",
        )


def test_analysis_refuses_incomplete_paired_units():
    spec = EvidenceExperimentSpec(
        experiment_id="incomplete",
        epoch="e2012",
        models=["fixture-model"],
        question_set="unused.jsonl",
    )
    observation = EvidenceObservation(
        trial_id="trial",
        unit_id="unit",
        question_id="q",
        model_id="fixture-model",
        replication=0,
        condition="no_evidence",
        condition_order=0,
        probability=0.5,
        ground_truth=True,
        brier=0.25,
        n_tool_calls=2,
        search_queries=["q"],
        evidence_document_ids=[],
        citation_document_ids=["protocol"],
        citation_verification_failed=False,
        raw_prediction={},
    )
    with pytest.raises(ValueError, match="incomplete paired"):
        analyze_evidence_experiment(spec, [observation])
