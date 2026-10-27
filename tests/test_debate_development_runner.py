"""Check the development runner's information boundaries without API calls."""

import importlib.util
import json
from pathlib import Path


def test_three_arm_runner_preserves_synchronous_private_histories(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts/run_debate_development_test.py"
    spec = importlib.util.spec_from_file_location("development_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    people = [dict(group_id="g", profile=dict(agent_id=f"p{i}", topic="test",
        initial_score=3, initial_text="initial", partners={str(r): f"p{i ^ r}" for r in (1, 2, 3)}))
        for i in range(4)]
    (tmp_path / "cases.json").write_text(json.dumps(people))
    (tmp_path / "contract.json").write_text("{}")
    (tmp_path / "checkpoints").mkdir()
    monkeypatch.setattr(module, "verify", lambda root: {"seed": 20261023})
    monkeypatch.setattr(module, "runtime", lambda: None)
    monkeypatch.setattr(module, "begin_spend_run", lambda run_id: None)
    calls = []

    class FakeBroker:
        def __init__(self, root, contract):
            pass

        def call(self, payload, meta):
            calls.append(meta)
            history = payload["history"]
            agent = payload["profile"]["agent_id"]
            if meta["arm"] == "direct":
                assert history == []
            else:
                previous_passes = (meta["round"] - 1) * 2 + meta["pass_index"]
                if meta["stage"] == "final":
                    previous_passes = 6
                assert len(history) == previous_passes * (2 if meta["arm"] == "swarm" else 1)
                for h in history:
                    assert h["round"] <= payload["round"]
                    if h["direction"] == "received":
                        assert meta["arm"] == "swarm"
                        assert h["speaker"] == payload["profile"]["partners"][str(h["round"])]
                    else:
                        assert h["speaker"] == agent
            return ({"message": agent} if meta["stage"] == "message"
                    else {"probabilities": [0, 0, 1, 0, 0, 0]})

    monkeypatch.setattr(module, "Broker", FakeBroker)
    module.run(tmp_path)
    assert len(calls) == 60
    assert len(json.loads((tmp_path / "predictions.json").read_text())) == 12
    assert (tmp_path / "prediction-seal.json").exists()
    assert not (tmp_path / "evaluation.json").exists()
