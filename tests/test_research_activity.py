import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from leaderboard import research_activity as activity


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def checkpoint(directory, name, actor="PRIVATE_PERSON", group="PRIVATE_GROUP"):
    put(
        directory / "checkpoints" / name,
        {
            "metadata": {"person": actor, "group": group, "stage": "review"},
            "payload": {"SECRET_PROFILE": "PRIVATE_TEXT"},
            "raw": "PRIVATE_RESPONSE",
            "probabilities": {"PRIVATE_OUTCOME": 0.99},
        },
    )


def telemetry(directory, *, at=None, study="ablation", session="session-one"):
    status = {
        "session_id": session,
        "study_id": study,
        "pid": os.getpid(),
        "process_start": "verified-identity",
        "status": "running",
        "heartbeat_at": at or datetime.now(timezone.utc).isoformat(),
        "lease_seconds": 20,
    }
    put(directory / "visual_status.json", status)
    (directory / "visual_events.jsonl").write_text(
        json.dumps(
            {
                "session_id": session,
                "seq": 1,
                "at": status["heartbeat_at"],
                "kind": "checkpoint_saved",
                "agent": 1,
                "group": 2,
                "phase": "final",
                "summary": "PRIVATE_MESSAGE",
                "model": "PRIVATE_MODEL",
                "payload": "PRIVATE_PROFILE",
            }
        )
        + "\n"
    )
    return status


def test_replay_is_safe_and_never_invents_intermediate_actions(tmp_path):
    directory = tmp_path / "data/runs" / activity.RUNS["individual"]
    checkpoint(directory, "one.json")
    put(directory / "evaluation.json", {"targets": "PRIVATE_TARGET"})
    payload = activity.build_research_activity("individual", tmp_path)
    assert payload["mode"] == "replay"
    assert [e["kind"] for e in payload["events"]] == ["checkpoint_saved", "evaluated"]
    assert payload["events"][0]["actor"] == "Agent 01"
    assert payload["events"][0]["at"] is None
    assert "PRIVATE" not in json.dumps(payload)


def test_replay_cursor_stable_when_earlier_named_checkpoint_arrives(tmp_path):
    directory = tmp_path / "data/runs" / activity.RUNS["individual"]
    checkpoint(directory, "z.json")
    first = activity.build_research_activity("individual", tmp_path)
    checkpoint(directory, "a.json", actor="second")
    second = activity.build_research_activity("individual", tmp_path, first["next_after"])
    assert second["session_id"] == first["session_id"]
    assert [e["seq"] for e in second["events"]] == [2]
    assert second["events"][0]["actor"] == "Agent 02"


def test_bounded_pages_and_missing_states(tmp_path):
    assert activity.build_research_activity("ablation", tmp_path)["mode"] == "idle"
    directory = tmp_path / "data/runs" / activity.RUNS["ablation"]
    for i in range(activity.PAGE_SIZE + 2):
        checkpoint(directory, f"{i:04}.json")
    payload = activity.build_research_activity("ablation", tmp_path)
    assert len(payload["events"]) == activity.PAGE_SIZE
    assert payload["has_more"] is True
    assert (
        len(activity.build_research_activity("ablation", tmp_path, payload["next_after"])["events"])
        == 2
    )


def test_telemetry_filters_session_and_payload_and_requires_live_identity(tmp_path, monkeypatch):
    directory = tmp_path / "data/runs" / activity.RUNS["ablation"]
    telemetry(directory)
    monkeypatch.setattr(activity, "_live", lambda status: False)
    with (directory / "visual_events.jsonl").open("a") as handle:
        handle.write(json.dumps({"session_id": "old", "seq": 2, "kind": "run_started"}) + "\n")
        handle.write("{partial")
    payload = activity.build_research_activity("ablation", tmp_path)
    assert payload["mode"] == "replay"
    assert payload["status"] == "liveness_unconfirmed"
    assert len(payload["events"]) == 1
    assert "PRIVATE" not in json.dumps(payload)


def test_fresh_verified_custom_run_is_discovered(tmp_path, monkeypatch):
    directory = tmp_path / "data/runs/custom-ablation"
    telemetry(directory)
    monkeypatch.setattr(
        activity, "_live", lambda status: status.get("process_start") == "verified-identity"
    )
    payload = activity.build_research_activity("ablation", tmp_path)
    assert payload["mode"] == "live"
    assert payload["run_id"] == "custom-ablation"
    assert payload["runs"][0]["id"] == "custom-ablation"
    with pytest.raises(ValueError):
        activity.build_research_activity("individual", tmp_path, run_id="custom-ablation")


def test_heartbeat_timestamp_alone_is_not_live(tmp_path):
    status = telemetry(tmp_path)
    status["heartbeat_at"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    assert activity._live(status) is False
    status["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    status["pid"] = -1
    assert activity._live(status) is False


def test_unknown_paths_protected_studies_and_symlinks(tmp_path):
    for study in ["../other", "unknown"]:
        with pytest.raises(ValueError):
            activity.build_research_activity(study, tmp_path)
    with pytest.raises(ValueError):
        activity.build_research_activity("individual", tmp_path, after=-1)
    for study in ["oregon", "reserve"]:
        assert activity.build_research_activity(study, tmp_path)["mode"] == "unsupported"
    directory = tmp_path / "data/runs" / activity.RUNS["ablation"]
    directory.mkdir(parents=True)
    external = tmp_path / "private.json"
    put(external, {"session_id": "PRIVATE"})
    (directory / "visual_status.json").symlink_to(external)
    assert activity.build_research_activity("ablation", tmp_path)["events"] == []


def test_actual_worker_lease_and_process_identity(tmp_path):
    from psbx.experiments.telemetry import process_identity

    status = telemetry(tmp_path)
    status["at"] = status.pop("heartbeat_at")
    identity = process_identity(os.getpid())
    if identity is None:
        pytest.skip("Platform cannot verify process identity")
    status["process_start"] = identity
    assert activity._live(status) is True
    status["process_start"] = "reused-pid-wrong-birth"
    assert activity._live(status) is False


def test_malformed_event_fields_are_ignored(tmp_path):
    directory = tmp_path / "data/runs" / activity.RUNS["ablation"]
    telemetry(directory)
    with (directory / "visual_events.jsonl").open("a") as handle:
        handle.write(json.dumps({"session_id": "session-one", "seq": 2, "kind": []}) + "\n")
        handle.write(
            json.dumps(
                {"session_id": "session-one", "seq": 3, "kind": "agent_started", "phase": []}
            )
            + "\n"
        )
    payload = activity.build_research_activity("ablation", tmp_path)
    assert [event["seq"] for event in payload["events"]] == [1, 3]
    assert payload["events"][1]["phase"] is None


def test_live_tail_is_bounded_and_historical_replay_starts_at_beginning(tmp_path, monkeypatch):
    directory = tmp_path / "data/runs" / activity.RUNS["ablation"]
    telemetry(directory)
    events = [
        {"session_id": "session-one", "seq": seq, "kind": "checkpoint_saved"}
        for seq in range(1, activity.PAGE_SIZE + 51)
    ]
    (directory / "visual_events.jsonl").write_text(
        "\n".join(json.dumps(row) for row in events) + "\n"
    )
    monkeypatch.setattr(activity, "_live", lambda status: True)
    live = activity.build_research_activity("ablation", tmp_path, tail=True)
    assert len(live["events"]) == activity.PAGE_SIZE
    assert live["events"][0]["seq"] == 51
    assert live["next_after"] == activity.PAGE_SIZE + 50
    assert live["has_more"] is False
    assert live["coverage"]["first_seq"] == 51
    assert live["coverage"]["prior_events"] == 50
    assert live["coverage"]["available_events"] == activity.PAGE_SIZE + 50
    full = activity.build_research_activity("ablation", tmp_path, tail=False)
    assert full["events"][0]["seq"] == 1
    assert full["has_more"] is True
    monkeypatch.setattr(activity, "_live", lambda status: False)
    historical = activity.build_research_activity("ablation", tmp_path, tail=True)
    assert historical["events"][0]["seq"] == 1
    assert historical["has_more"] is True
    assert historical["coverage"]["recent_window"] is False
