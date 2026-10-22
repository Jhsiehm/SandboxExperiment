import json
from types import SimpleNamespace

import numpy as np
import pytest

from psbx.experiments import social_confirmation as sc
from psbx.experiments.social_worker import build_prompt


def setup_broker(tmp_path, monkeypatch, outputs):
    model = sc.load_models()["openrouter-gpt-4.1-mini"]
    sc.dump(tmp_path / "worker.json", model.model_dump(mode="json"))
    counts = dict(docker=0, paid=0)

    def docker(payload, image):
        counts["docker"] += 1
        return {**build_prompt(payload), "isolation": {"uid": 10001}}

    def paid(*args, **kwargs):
        counts["paid"] += 1
        item = next(outputs)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item)

    monkeypatch.setattr(sc, "docker_job", docker)
    monkeypatch.setattr(sc, "complete_turn", paid)
    return sc.Broker(tmp_path, {"image_id": "test"}), counts


def payload():
    return dict(
        profile=dict(
            agent_id="a",
            topic="t",
            initial_score=3,
            initial_text="initial",
            partners={"1": "b", "2": "c", "3": "d"},
        ),
        arm="private",
        stage="final",
        round=3,
        history=[],
    )


def test_completed_resume_never_calls_provider_or_worker(tmp_path, monkeypatch):
    broker, counts = setup_broker(tmp_path, monkeypatch, iter(['{"probabilities":[0,0,1,0,0,0]}']))
    meta = dict(group="g", arm="direct", agent="a")
    first = broker.call(payload(), meta)
    assert broker.call(payload(), meta) == first
    assert counts == {"paid": 1, "docker": 1}
    changed = payload()
    changed["profile"]["initial_score"] = 4
    with pytest.raises(ValueError, match="Resume payload"):
        broker.call(changed, meta)


def test_repair_fresh_worker_and_ambiguous_attempt_blocks(tmp_path, monkeypatch):
    broker, counts = setup_broker(
        tmp_path, monkeypatch, iter(["bad", '{"probabilities":[0,0,1,0,0,0]}'])
    )
    broker.call(payload(), dict(group="g", arm="direct", agent="a"))
    assert counts == {"paid": 2, "docker": 2}
    broker, counts = setup_broker(tmp_path, monkeypatch, iter([RuntimeError("timeout")]))
    meta = dict(group="other", arm="direct", agent="a")
    with pytest.raises(RuntimeError, match="timeout"):
        broker.call(payload(), meta)
    with pytest.raises(RuntimeError, match="Ambiguous"):
        broker.call(payload(), meta)
    assert counts["paid"] == 1


def test_returned_attempt_recovers_without_duplicate_paid_call(tmp_path, monkeypatch):
    broker, counts = setup_broker(tmp_path, monkeypatch, iter(['{"probabilities":[0,0,1,0,0,0]}']))
    meta = dict(group="g", arm="direct", agent="a")
    broker.call(payload(), meta)
    (broker.directory / (sc._canonical_json_sha256(meta) + ".json")).unlink()
    broker.call(payload(), meta)
    assert counts["paid"] == 1


def test_run_direct_has_no_replay_or_private_history(tmp_path, monkeypatch):
    cases = []
    for i in range(4):
        p = payload()["profile"]
        p["agent_id"] = str(i)
        p["partners"] = {str(r): str(i ^ r) for r in range(1, 4)}
        cases.append(
            dict(
                group_id="g",
                profile=p,
                real_incoming=[
                    dict(speaker=str(i ^ 1), direction="received", round=1, text="REPLAYSECRET")
                ],
            )
        )
    sc.dump(tmp_path / "cases.json", cases)
    sc.dump(tmp_path / "contract.json", {})
    config = dict(seed=42, max_requests=2000, max_usd=30)
    monkeypatch.setattr(sc, "verify", lambda root: {"config": config})
    monkeypatch.setattr(sc, "load_dotenv", lambda: None)
    monkeypatch.setattr(sc, "configure_runtime", lambda config: None)
    monkeypatch.setattr(sc, "begin_spend_run", lambda name: None)
    monkeypatch.setattr(sc, "preflight_paid_requests", lambda requests: {})
    observed = []

    class FakeBroker:
        def __init__(self, *args):
            self.model = None
            (tmp_path / "checkpoints").mkdir()

        def call(self, p, m):
            observed.append((json.loads(json.dumps(p)), m))
            if p["stage"] == "message":
                expected = (m["round"] - 1) * 2 + m["pass_index"]
                assert len(p["history"]) == expected * (2 if m["arm"] == "swarm" else 1)
            return (
                {"message": "generated"}
                if p["stage"] == "message"
                else {"probabilities": [0, 0, 1, 0, 0, 0]}
            )

    monkeypatch.setattr(sc, "Broker", FakeBroker)
    sc.run(tmp_path)
    assert len(observed) == 64
    for p, m in observed:
        if m["arm"] == "direct":
            assert p["arm"] == "private" and p["history"] == []
        if m["arm"] != "replay":
            assert "REPLAYSECRET" not in json.dumps(p)
    assert len(sc.read(tmp_path / "predictions.json")) == 16


def test_probability_score_is_proper_cumulative_score():
    p = np.array([[0, 0, 1, 0, 0, 0]])
    assert sc.scores(p, [3], [3])["rps"][0] == 0
    assert sc.scores(p, [3], [4])["rps"][0] == pytest.approx(0.2)


def test_runtime_disables_uncounted_retries_and_restores_large_ledger(tmp_path, monkeypatch):
    from psbx import spending

    monkeypatch.setattr(spending, "run_dir", lambda _: tmp_path)
    monkeypatch.setattr(spending, "_LEDGER_MAX_BYTES", 1_000_000)
    monkeypatch.setattr(sc.openrouter, "_MAX_429_RETRIES", 2)
    sc.configure_runtime(dict(max_usd=30, max_requests=2000))
    assert sc.openrouter._MAX_429_RETRIES == 0
    sc.dump(
        tmp_path / "spend_ledger.json",
        dict(
            run_id="r",
            reserved_requests=1856,
            reserved_usd=12.34,
            entries=[dict(padding="x" * 600) for _ in range(1856)],
        ),
    )
    guard = spending._SpendGuard()
    guard.begin_run("r")
    assert guard._request_count == 1856 and guard._reserved_usd == 12.34
