"""Exploratory calibration and missing-profile diagnostics after sealed evaluation.

These secondary diagnostics do not change the predeclared comparison or gate.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.reserved_validation import read, verify_contract
from psbx.paths import resolve, validate_run_id


def confidence_bins(p, y, w):
    p, y, w = np.asarray(p), np.asarray(y), np.asarray(w)
    confidence = p.max(axis=1)
    correct = p.argmax(axis=1) == y
    groups = []
    for lo, hi in [(1 / 3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.00000001)]:
        selected = (confidence >= lo - 1e-10) & (confidence < hi)
        if selected.any():
            groups.append(
                dict(
                    lower=lo,
                    upper=min(hi, 1),
                    rows=int(selected.sum()),
                    weight_share=float(w[selected].sum() / w.sum()),
                    mean_confidence=float(np.average(confidence[selected], weights=w[selected])),
                    answer_agreement=float(np.average(correct[selected], weights=w[selected])),
                )
            )
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="anes2012-ohio-reserved-validation-20261012")
    args = parser.parse_args()
    root = resolve("data/runs") / validate_run_id(args.run_id)
    contract = verify_contract(root)
    evaluation_seal = read(root / "evaluation-seal.json")
    check_seal(evaluation_seal)
    if evaluation_seal["report_sha256"] != _sha256_file(root / "evaluation.json"):
        raise ValueError("Evaluation changed")
    prediction_seal = read(root / "output/prediction-seal.json")
    check_seal(prediction_seal)
    if prediction_seal["predictions_sha256"] != _sha256_file(root / "output/predictions.json"):
        raise ValueError("Predictions changed")
    manifest = read(contract["targets_manifest"])
    check_seal(manifest)
    if _sha256_file(Path(manifest["targets_path"])) != evaluation_seal["targets_sha256"]:
        raise ValueError("Target bytes changed")
    target = {r["synthetic_person_id"]: r for r in read(manifest["targets_path"])}
    rows = read(root / "output/predictions.json")
    profiles = read(root / "input/cohort.json")
    diagnostic = []
    for task, spec in TARGETS.items():
        for arm in ["sparse", "rich"]:
            selected = [
                r
                for r in rows
                if r["metadata"]["arm"] == arm
                and r["probabilities"] is not None
                and target[r["metadata"]["synthetic_person_id"]][task] in spec["codes"]
            ]
            p = np.array([r["probabilities"][task] for r in selected])
            y = [
                spec["codes"].index(target[r["metadata"]["synthetic_person_id"]][task])
                for r in selected
            ]
            w = [target[r["metadata"]["synthetic_person_id"]]["weight"] for r in selected]
            bins = confidence_bins(p, y, w)
            diagnostic.append(
                dict(
                    task=task,
                    arm=arm,
                    bins=bins,
                    top_label_ece=sum(
                        b["weight_share"] * abs(b["mean_confidence"] - b["answer_agreement"])
                        for b in bins
                    ),
                    weighted_mean_entropy=float(
                        np.average(-(p * np.log(np.clip(p, 1e-12, 1))).sum(axis=1), weights=w)
                    ),
                )
            )
    result = dict(
        scope="Exploratory secondary diagnostics; no inferential intervals. "
        "Calibration bins are descriptive; repetitions are dependent. "
        "Higher entropy is neither automatically better nor worse fidelity.",
        calibration=diagnostic,
        profile_missing_counts={
            f: sum(p["observed"][f]["code"] is None for p in profiles)
            for f in profiles[0]["observed"]
        },
        cohort_n=len(profiles),
    )
    dump(root / "diagnostics.json", result)
    dump(
        root / "diagnostics-seal.json",
        seal(
            dict(
                diagnostics_sha256=_sha256_file(root / "diagnostics.json"),
                evaluation_seal_sha256=_sha256_file(root / "evaluation-seal.json"),
                source_sha256=_sha256_file(Path(__file__)),
            )
        ),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
