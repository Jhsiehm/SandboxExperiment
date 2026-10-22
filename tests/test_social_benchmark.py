import copy
from types import SimpleNamespace

import numpy as np
import pytest

from psbx.experiments.decision_profiles import dump
from psbx.experiments.social_benchmark import (
    Broker,
    parse_group,
    scores,
    validate_coverage,
    validate_result,
)
from psbx.experiments.social_worker import build_prompt


def payload(arm="swarm"):
    return dict(
        profile=dict(
            agent_id="a",
            topic="test",
            initial_score=4,
            initial_text="My measured initial explanation",
            partners={"1": "b", "2": "c", "3": "d"},
        ),
        arm=arm,
        stage="final",
        round=3,
        history=[],
    )


def test_only_own_profile_and_permitted_public_history():
    p = payload()
    build_prompt(p)
    p["history"] = [dict(speaker="b", direction="received", round=1, text="a public message")]
    assert "a public message" in build_prompt(p)["user"]
    p["arm"] = "private"
    with pytest.raises(ValueError, match="peer"):
        build_prompt(p)
    p["arm"] = "swarm"
    p["history"][0]["speaker"] = "c"
    with pytest.raises(ValueError, match="unassigned"):
        build_prompt(p)
    p["history"][0]["speaker"] = "b"
    p["history"][0]["direction"] = "private"
    with pytest.raises(ValueError, match="private state"):
        build_prompt(p)


@pytest.mark.parametrize("key", ["final_score", "other_profiles", "demographics", "targets"])
def test_private_profile_allowlist(key):
    p = payload()
    p["profile"][key] = "forbidden"
    with pytest.raises(ValueError):
        build_prompt(p)


def test_future_history_rejected():
    p = payload()
    p["round"] = 1
    p["history"] = [dict(speaker="c", direction="received", round=2, text="future")]
    with pytest.raises(ValueError, match="future"):
        build_prompt(p)


def test_probability_validation_and_ordinal_score():
    perfect = scores([[0, 0, 0, 0, 0, 1]], [1], [6])
    assert perfect["rps"][0] == 0 and perfect["mae"][0] == 0
    wrong = scores([[1, 0, 0, 0, 0, 0]], [1], [6])
    assert wrong["rps"][0] == 1 and wrong["mae"][0] == 5
    assert wrong["direction"][0] == 0
    with pytest.raises(ValueError):
        validate_result({"probabilities": [np.nan] * 6}, "final")
    with pytest.raises(ValueError):
        validate_result({"probabilities": [1] * 6}, "final")


def test_complete_panel_required():
    cases = [{"group_id": "g", "profile": {"agent_id": "a"}}]
    rows = [
        dict(group="g", agent="a", arm=a, probabilities=[1, 0, 0, 0, 0, 0])
        for a in ["private", "swarm", "replay"]
    ]
    validate_coverage(cases, rows)
    with pytest.raises(ValueError):
        validate_coverage(cases, rows[:-1])
    with pytest.raises(ValueError):
        validate_coverage(cases, rows + [rows[0]])


def test_parser_splits_targets_and_deduplicates_sent_received():
    rows = []
    for i in range(4):
        rows.append(
            dict(event_type="Initial Opinion", worker_id=str(i), sliderValue="3", text="initial")
        )
        rows.append(
            dict(
                event_type="Post Opinion",
                worker_id=str(i),
                sliderValue="6",
                text="SECRET_FINAL",
                event_order="100",
            )
        )
        for round_, xor in [(1, 1), (2, 2), (3, 3)]:
            for event in ["message_sent", "message_received"]:
                rows.append(
                    dict(
                        event_type=event,
                        worker_id=str(i),
                        sender_id=str(i),
                        recipient_id=str(i ^ xor),
                        chat_round_order=f"{round_}.0",
                        text="public",
                        event_order=str(round_ * 10 + i),
                    )
                )
    cases, targets = parse_group(rows, "topic", "g")
    assert len(cases) == 4 and all(len(c["real_incoming"]) == 3 for c in cases)
    assert "SECRET_FINAL" not in str(cases)
    assert all(t["final_score"] == 6 for t in targets)
    rows.append(
        dict(
            event_type="Post Opinion",
            worker_id="0",
            sliderValue="5",
            text="SECRET2",
            event_order="101",
        )
    )
    assert parse_group(rows, "topic", "g")[1][0]["final_score"] == 5


def test_resume_and_provider_failure_are_explicit(tmp_path, monkeypatch):
    from test_decision_context import worker

    dump(tmp_path / "worker.json", worker().model_dump(mode="json"))
    broker = Broker(tmp_path, {"image_id": "fixture"})
    monkeypatch.setattr(
        "psbx.experiments.social_benchmark.docker_job",
        lambda p, i: {**build_prompt(p), "isolation": {}},
    )
    calls = []

    def complete(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(text='{"probabilities":[0,0,0,1,0,0]}')

    monkeypatch.setattr("psbx.experiments.social_benchmark.complete_turn", complete)
    p = payload()
    meta = dict(group="g", arm="swarm", stage="final")
    broker.call(p, meta)
    broker.call(p, meta)
    assert len(calls) == 1
    changed = copy.deepcopy(p)
    changed["profile"]["initial_text"] = "changed"
    with pytest.raises(ValueError):
        broker.call(changed, meta)

    def fail(*args, **kwargs):
        raise TimeoutError("private provider diagnostic")

    monkeypatch.setattr("psbx.experiments.social_benchmark.complete_turn", fail)
    with pytest.raises(TimeoutError):
        broker.call(p, {**meta, "another": True})
    text = (tmp_path / "provider-failures.jsonl").read_text()
    assert "TimeoutError" in text and "private provider diagnostic" not in text
