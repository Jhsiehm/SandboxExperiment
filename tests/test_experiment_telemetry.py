import json
import os
from types import SimpleNamespace

import pytest

from psbx.experiments import individual_validation as individual
from psbx.experiments import telemetry
from psbx.experiments.individual_worker import SPARSE
from psbx.schemas import ModelConfig


def events(root):
    return [json.loads(line) for line in (root / "visual_events.jsonl").read_text().splitlines()]


def test_content_free_events_and_lease(tmp_path):
    @telemetry.observed_run
    def runner(root):
        telemetry.observe("agent_started", agent_key="PRIVATE_RESPONDENT", phase="final")
        telemetry.observe("model_requested", agent_key="PRIVATE_RESPONDENT", phase="final")
        telemetry.observe("not_allowed", agent_key="OTHER_SECRET")
        telemetry.observe("response_received", agent_key="OTHER_SECRET", phase="SECRET_PHASE")
        status = json.loads((root / "visual_status.json").read_text())
        assert status["status"] == "running"
        assert status["pid"] == os.getpid()
        assert status["process_start"] == telemetry.process_identity(os.getpid())
        return 42

    assert runner(tmp_path) == 42
    rows = events(tmp_path)
    assert [r["kind"] for r in rows] == [
        "run_started", "agent_started", "model_requested", "evaluation_ready", "run_completed"
    ]
    assert [r["seq"] for r in rows] == list(range(1, 6))
    assert rows[1]["agent"] == rows[2]["agent"] == 1
    assert "PRIVATE" not in (tmp_path / "visual_events.jsonl").read_text()
    assert "SECRET" not in (tmp_path / "visual_events.jsonl").read_text()
    assert json.loads((tmp_path / "visual_status.json").read_text())["status"] == "completed"
    runner(tmp_path)
    assert len(events(tmp_path)) == 10
    assert events(tmp_path)[0]["session_id"] != events(tmp_path)[5]["session_id"]


def test_failure_keeps_original_exception_without_exception_text(tmp_path):
    failure = ValueError("sensitive provider detail")

    @telemetry.observed_run
    def runner(root):
        raise failure

    with pytest.raises(ValueError) as caught:
        runner(tmp_path)
    assert caught.value is failure
    assert [r["kind"] for r in events(tmp_path)] == ["run_started", "run_failed"]
    assert "sensitive" not in (tmp_path / "visual_events.jsonl").read_text()
    assert json.loads((tmp_path / "visual_status.json").read_text())["status"] == "failed"


def test_unwritable_telemetry_does_not_change_result(tmp_path):
    # A directory in place of each file reliably rejects writing even as root.
    (tmp_path / "visual_events.jsonl").mkdir()
    (tmp_path / "visual_status.json").mkdir()

    @telemetry.observed_run
    def runner(root):
        telemetry.observe("checkpoint_saved", agent_key="secret", phase="final")
        return "unchanged"

    assert runner(tmp_path) == "unchanged"
    assert not list(tmp_path.glob(".visual-status-*.tmp"))


def test_request_checkpoint_and_resume_observations(tmp_path, monkeypatch):
    (tmp_path / "checkpoints").mkdir()
    data = dict(
        arm="sparse_direct", stage="final", review="", baseline_date="2012-09-01",
        observations={f: dict(label=f, answer="PRIVATE_VALUE", status="observed_pre_election")
                      for f in SPARSE},
    )
    model = ModelConfig(id="test", provider="openrouter", model_name="test",
                        declared_pretraining_cutoff="2020-01-01", is_instruction_tuned=True)
    calls = []
    monkeypatch.setattr(individual, "docker_job", lambda *a: {
        "user": "PRIVATE_PROMPT", "system": "PRIVATE_SYSTEM", "isolation": {},
    })

    def complete(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(text='{"vote":[1,0,0],"health_law":[0,1,0],"gun_policy":[0,0,1]}')

    monkeypatch.setattr(individual, "complete_turn", complete)

    @telemetry.observed_run
    def runner(root):
        meta = dict(person="PRIVATE_ID", arm="sparse_direct", stage="final")
        first = individual.call(root, {"image_id": "fake"}, model, data, meta)
        assert individual.call(root, {"image_id": "fake"}, model, data, meta) == first

    runner(tmp_path)
    assert len(calls) == 1
    assert [r["kind"] for r in events(tmp_path)] == [
        "run_started", "agent_started", "model_requested", "response_received",
        "checkpoint_saved", "evaluation_ready", "run_completed",
    ]
    serialized = (tmp_path / "visual_events.jsonl").read_text()
    assert "PRIVATE" not in serialized
    assert "vote" not in serialized


def test_process_identity_rejects_non_process():
    assert telemetry.process_identity(-1) is None
    assert telemetry.process_identity(True) is None
    assert telemetry.process_identity(999999999) is None
