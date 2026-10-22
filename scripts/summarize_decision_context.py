"""Aggregate sealed context comparisons and repeated-prediction stability diagnostics."""

import argparse
import json
from pathlib import Path

import numpy as np

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.paths import resolve, validate_run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="anes2012-decision-context-20261011")
    args = parser.parse_args()
    root = resolve("data/runs") / validate_run_id(args.run_id)
    reports, bindings = {}, {}
    for phase in ["independent", "interactions"]:
        report_path = root / f"{phase}-evaluation.json"
        report_seal_path = root / f"{phase}-evaluation-seal.json"
        report_seal = json.loads(report_seal_path.read_text())
        check_seal(report_seal)
        assert report_seal["report_sha256"] == _sha256_file(report_path)
        prediction_seal_path = root / f"{phase}-prediction-seal.json"
        assert report_seal["prediction_seal_sha256"] == _sha256_file(prediction_seal_path)
        prediction_seal = json.loads(prediction_seal_path.read_text())
        check_seal(prediction_seal)
        assert prediction_seal["predictions_sha256"] == _sha256_file(
            root / f"{phase}-predictions.json"
        )
        reports[phase] = json.loads(report_path.read_text())
        bindings[report_seal_path.name] = _sha256_file(report_seal_path)
    predictions = json.loads((root / "independent-predictions.json").read_text())
    repeated = {}
    for row in predictions:
        repeated.setdefault((row["synthetic_person_id"], row["arm"]), {})[row["repetition"]] = row[
            "probabilities"
        ]
    diagnostics = []
    for arm in sorted({row["arm"] for row in predictions}):
        pairs = [
            rows
            for (_, condition), rows in repeated.items()
            if condition == arm
            and len(rows) == 2
            and all(value is not None for value in rows.values())
        ]
        for task in TARGETS:
            first = np.array([rows[0][task] for rows in pairs])
            second = np.array([rows[1][task] for rows in pairs])
            diagnostics.append(
                {
                    "arm": arm,
                    "task": task,
                    "n": len(pairs),
                    "repeat_total_variation_mean": float(
                        np.mean(0.5 * abs(first - second).sum(axis=1))
                    ),
                    "repeat_modal_answer_disagreement": float(
                        np.mean(first.argmax(axis=1) != second.argmax(axis=1))
                    ),
                }
            )
    transcripts_path = root / "interaction-transcripts.json"
    transcripts = json.loads(transcripts_path.read_text())
    ledger_path = root / "spend_ledger.json"
    ledger = json.loads(ledger_path.read_text())
    result = {
        "scientific_result": False,
        "reports": reports,
        "repeat_stability": diagnostics,
        "public_messages": sum(r["arm"] == "limited_network" for r in transcripts),
        "private_reflections": sum(r["arm"] == "private_matched" for r in transcripts),
        "public_turns_receiving_peer_messages": sum(
            r["arm"] == "limited_network" and bool(r["received_peer_ids"]) for r in transcripts
        ),
        "request_reservations": ledger["reserved_requests"],
        "provider_reported_cost_usd": sum(
            (r.get("reported_usage") or {}).get("provider_cost_usd", 0) or 0
            for r in ledger["entries"]
        ),
        "unreconciled_requests": sum(r.get("reported_usage") is None for r in ledger["entries"]),
    }
    dump(root / "summary.json", result)
    dump(
        root / "summary-seal.json",
        seal(
            {
                "summary_sha256": _sha256_file(root / "summary.json"),
                "bindings": bindings,
                "transcripts_sha256": _sha256_file(transcripts_path),
                "ledger_sha256": _sha256_file(ledger_path),
                "source_sha256": _sha256_file(Path(__file__)),
            }
        ),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
