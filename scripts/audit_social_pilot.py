"""Independent post-run integrity and scoring audit; never opens targets before seals.

Usage: .venv/bin/python scripts/audit_social_pilot.py
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from psbx.experiments.anes_society import _canonical_json_sha256, _sha256_file
from psbx.experiments.decision_profiles import check_seal, dump, seal
from psbx.experiments.social_benchmark import RUN_ID, verify
from psbx.experiments.social_worker import build_prompt
from psbx.paths import resolve


def read(path):
    return json.loads(Path(path).read_text())


def main():
    root = resolve("data/runs") / RUN_ID
    contract = verify(root)
    pred_seal = read(root / "prediction-seal.json")
    eval_seal = read(root / "evaluation-seal.json")
    check_seal(pred_seal)
    check_seal(eval_seal)
    for field, name in [
        ("contract_sha256", "contract.json"),
        ("predictions_sha256", "predictions.json"),
        ("transcript_sha256", "transcript.json"),
    ]:
        assert pred_seal[field] == _sha256_file(root / name)
    assert eval_seal["report_sha256"] == _sha256_file(root / "evaluation.json")
    assert eval_seal["prediction_seal_sha256"] == _sha256_file(root / "prediction-seal.json")
    assert eval_seal["targets_sha256"] == contract["targets_sha256"]
    assert _sha256_file(Path(contract["targets_path"])) == contract["targets_sha256"]

    cases = read(root / "cases.json")
    by_agent = {c["profile"]["agent_id"]: c for c in cases}
    checkpoints = []
    all_paths = list((root / "checkpoints").glob("*.json"))
    assert len(all_paths) == 480 == len(pred_seal["checkpoints"])
    for path in all_paths:
        assert pred_seal["checkpoints"][path.name] == _sha256_file(path)
        c = read(path)
        assert c["status"] == "completed"
        assert path.stem == _canonical_json_sha256(c["metadata"])
        assert c["fingerprint"] == _canonical_json_sha256(
            dict(payload=c["payload"], worker=read(root / "worker.json"))
        )
        assert c["prompt_sha256"] == _canonical_json_sha256(build_prompt(c["payload"]))
        assert c["payload"]["profile"] == by_agent[c["metadata"]["agent"]]["profile"]
        iso = c["isolation"]
        assert iso["uid"] == 10001 and iso["root_readonly"] and iso["no_new_privileges"]
        assert not iso["active_external_interfaces"] and not int(iso["effective_capabilities"], 16)
        assert not iso["provider_key_present"] and not iso["forbidden_paths_present"]
        checkpoints.append(c)

    index = {
        (
            c["metadata"]["agent"],
            c["metadata"]["arm"],
            c["metadata"]["stage"],
            c["metadata"]["round"],
            c["metadata"]["pass_index"],
        ): c
        for c in checkpoints
    }
    assert len(index) == 480
    lengths = []
    # Independently reconstruct delivered histories, checking no same-pass peeking.
    for case in cases:
        agent = case["profile"]["agent_id"]
        for arm in ["private", "swarm"]:
            history = []
            for round_ in range(1, 4):
                for pass_ in range(2):
                    c = index[agent, arm, "message", round_, pass_]
                    assert c["payload"]["history"] == history
                    message = c["parsed"]["message"]
                    lengths.append(len(message.split()))
                    history.append(
                        dict(
                            speaker=agent,
                            direction="private" if arm == "private" else "own",
                            round=round_,
                            text=message,
                        )
                    )
                    if arm == "swarm":
                        peer = case["profile"]["partners"][str(round_)]
                        received = index[peer, arm, "message", round_, pass_]["parsed"]["message"]
                        history.append(
                            dict(
                                speaker=peer,
                                direction="received",
                                round=round_,
                                text=received,
                            )
                        )
            assert index[agent, arm, "final", 3, 0]["payload"]["history"] == history
        assert index[agent, "replay", "final", 3, 0]["payload"]["history"] == case["real_incoming"]

    predictions = read(root / "predictions.json")
    transcripts = read(root / "transcript.json")
    assert len(predictions) == 96 and len(transcripts) == 384
    for row in predictions + transcripts:
        c = index[row["agent"], row["arm"], row["stage"], row["round"], row["pass_index"]]
        for key, value in c["parsed"].items():
            assert row[key] == value
    # Targets opened only after complete panel and both seals have been verified.
    labels = {v["agent_id"]: v["final_score"] for v in read(contract["targets_path"])}
    report = read(root / "evaluation.json")
    errors = {a: [] for a in ["persistence", "private", "swarm", "replay"]}
    for row in predictions:
        p = row["probabilities"]
        y = labels[row["agent"]]
        errors[row["arm"]].append(sum((sum(p[:k]) - float(y <= k)) ** 2 for k in range(1, 6)) / 5)
    for case in cases:
        agent = case["profile"]["agent_id"]
        errors["persistence"].append(abs(case["profile"]["initial_score"] - labels[agent]) / 5)
    recomputed = {arm: sum(values) / len(values) for arm, values in errors.items()}
    for row in report["metrics"]:
        assert abs(recomputed[row["arm"]] - row["rps"]) < 1e-12
    exploratory_change_calibration = {}
    for arm in ["persistence", "private", "swarm", "replay"]:
        probs, changed, correct = [], [], []
        for case in cases:
            agent = case["profile"]["agent_id"]
            initial = case["profile"]["initial_score"]
            p = (
                [float(k == initial) for k in range(1, 7)]
                if arm == "persistence"
                else index[agent, arm, "final", 3, 0]["parsed"]["probabilities"]
            )
            probs.append(1 - p[initial - 1])
            changed.append(float(labels[agent] != initial))
            correct.append(float(max(range(6), key=lambda k: p[k]) + 1 == labels[agent]))
        exploratory_change_calibration[arm] = dict(
            mean_predicted_change_probability=statistics.mean(probs),
            observed_changed_fraction=statistics.mean(changed),
            binary_change_brier=statistics.mean((p - y) ** 2 for p, y in zip(probs, changed)),
            exact_modal_rating_accuracy=statistics.mean(correct),
        )
    ledger = read(root / "spend_ledger.json")
    attempts = sum(c["attempts"] for c in checkpoints)
    assert ledger["reserved_requests"] >= attempts
    # Exploratory descriptive diagnostic, not a behavioral validity score.
    human_words = [len(h["text"].split()) for c in cases for h in c["real_incoming"]]
    swarm_words = [len(t["message"].split()) for t in transcripts if t["arm"] == "swarm"]
    dialogue_lengths = {}
    for name, lengths_ in [("human_incoming", human_words), ("generated_swarm", swarm_words)]:
        dialogue_lengths[name] = dict(
            messages=len(lengths_),
            mean_words=statistics.mean(lengths_),
            median_words=statistics.median(lengths_),
            empty_messages=lengths_.count(0),
        )
    audit = dict(
        verified=True,
        completed_checkpoints=len(checkpoints),
        predictions=len(predictions),
        generated_messages=len(transcripts),
        isolated_jobs=len(checkpoints),
        exact_history_reconstruction=True,
        source_contract_and_seals_valid=True,
        independent_rps=recomputed,
        attempts=attempts,
        attempt_counts=dict(Counter(c["attempts"] for c in checkpoints)),
        messages_over_60_words=sum(n > 60 for n in lengths),
        maximum_message_words=max(lengths),
        exploratory_message_lengths=dialogue_lengths,
        exploratory_change_calibration=exploratory_change_calibration,
        provider_requests=ledger["reserved_requests"],
        unresolved_usage=sum(e.get("reported_usage") is None for e in ledger["entries"]),
        audit_source_sha256=_sha256_file(Path(__file__)),
        evaluation_seal_sha256=_sha256_file(root / "evaluation-seal.json"),
        caveat="Research pilot; successful integrity checks do not establish behavioral validity.",
    )
    dump(root / "audit.json", seal(audit))
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
