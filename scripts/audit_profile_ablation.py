"""Independently check the new profile comparison's boundaries and direct scores."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.profile_ablation import RUN, payload, verify
from psbx.experiments.profile_ablation_worker import ARMS
from psbx.paths import resolve


def read(path):
    return json.loads(Path(path).read_text())


def main():
    root = resolve("data/runs") / RUN
    contract = verify(root)
    for name in ["prediction-seal.json", "evaluation-seal.json"]:
        check_seal(read(root / name))
    boundary = read(root / "prediction-seal.json")
    for name, expected_hash in boundary["bindings"].items():
        assert _sha256_file(Path(name)) == expected_hash, name
    evaluation_seal = read(root / "evaluation-seal.json")
    assert evaluation_seal["report_sha256"] == _sha256_file(root / "evaluation.json")
    assert evaluation_seal["prediction_seal_sha256"] == _sha256_file(root / "prediction-seal.json")
    people = read(root / "cohort.json")
    by_id = {person["synthetic_person_id"]: person for person in people}
    assert len(by_id) == len(people) == 120
    reserve = set(read(contract["reserve_ids"]))
    assert len(reserve) == 50 and not reserve & set(by_id)
    outer = read(root / "folds.json")
    assert set(outer) == set(by_id)
    checkpoints = [read(path) for path in (root / "checkpoints").glob("*.json")]
    expected = {(person, arm, rep) for person in by_id for arm in ARMS for rep in range(2)}
    checkpoint_index = {}
    for row in checkpoints:
        meta = row["metadata"]
        key = meta["person"], meta["arm"], meta["repetition"]
        assert key not in checkpoint_index
        checkpoint_index[key] = row
        assert row["payload"] == payload(by_id[key[0]], key[1])
        iso = row["isolation"]
        assert iso["uid"] == 10001 and iso["root_readonly"] and iso["no_new_privileges"]
        assert not iso["active_external_interfaces"] and int(iso["effective_capabilities"], 16) == 0
        assert not iso["provider_key_present"] and not iso["forbidden_paths_present"]
    assert set(checkpoint_index) == expected and len(checkpoints) == 960
    predictions = read(root / "predictions.json")
    assert len(predictions) == len(expected)
    seen = set()
    for prediction in predictions:
        meta = prediction["metadata"]
        key = meta["person"], meta["arm"], meta["repetition"]
        assert key not in seen
        seen.add(key)
        assert prediction["probabilities"] == checkpoint_index[key]["probabilities"]
    assert seen == expected
    report = read(root / "evaluation.json")
    assert report["reserved_respondents_used"] == 0 and report["promotion"] is False
    for task_arm in report["fitting_audit"]:
        all_test_ids = []
        for fold in task_arm["folds"]:
            train, test = set(fold["training_ids"]), set(fold["evaluation_ids"])
            assert not train & test and not (train | test) & reserve
            assert train | test <= set(by_id)
            assert all(outer[person] == fold["outer_fold"] for person in test)
            assert all(outer[person] != fold["outer_fold"] for person in train)
            all_test_ids.extend(test)
        assert len(all_test_ids) == len(set(all_test_ids))
    # Outcome values are opened only after sealed prediction and panel checks pass.
    manifest = read(contract["target_manifest"])
    check_seal(manifest)
    assert _sha256_file(Path(manifest["targets_path"])) == manifest["targets_sha256"]
    targets = {
        p["synthetic_person_id"]: p
        for p in read(manifest["targets_path"])
        if p["synthetic_person_id"] in by_id
    }
    direct_scores = {}
    for arm in ARMS:
        for task, spec in TARGETS.items():
            losses, weights = [], []
            for person_id, person in by_id.items():
                target = targets[person_id][task]
                if target not in spec["codes"]:
                    continue
                probability = np.mean(
                    [
                        checkpoint_index[person_id, arm, rep]["probabilities"][task]
                        for rep in range(2)
                    ],
                    axis=0,
                )
                truth = np.eye(3)[spec["codes"].index(target)]
                losses.append(float(np.square(probability - truth).sum() / 2))
                weights.append(person["weight"])
            value = float(np.average(losses, weights=weights))
            reported = next(
                row["weighted"]["brier"]
                for row in report["metrics"]
                if row["arm"] == arm and row["task"] == task and row["variant"] == "direct"
            )
            assert abs(value - reported) < 1e-12
            direct_scores[f"{arm}:{task}"] = value
    audit = seal(
        dict(
            verified=True,
            checkpoints=960,
            people=120,
            reserve_overlap=0,
            exact_payloads_and_isolation_checked=True,
            outer_fitting_boundaries_checked=True,
            direct_scores=direct_scores,
            evaluation_seal_sha256=_sha256_file(root / "evaluation-seal.json"),
            audit_source_sha256=_sha256_file(Path(__file__)),
            limitation="Direct scores independently recomputed. Statistical/hybrid "
            "fitting checked by adversarial label tests, not a second implementation.",
        )
    )
    dump(root / "independent-audit.json", audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
