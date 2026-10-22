"""Aggregate-only view of the independent ANES development comparison."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from psbx.paths import repo_root

RUN_ID = "anes2012-ohio-profile-ablation-development-v1"
ARMS = {"original_sparse", "original_rich", "reduced_existing", "reduced_plus_observed"}
TASKS = {"vote", "health_law", "gun_policy"}


def _read(path):
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def _sealed(value):
    body = {k: v for k, v in value.items() if k != "seal_sha256"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    if value.get("seal_sha256") != digest:
        raise ValueError("Invalid seal")


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def build_individual_payload(root: Path | None = None):
    directory = (root or repo_root()) / "data" / "runs" / RUN_ID
    payload = dict(
        run_id=RUN_ID,
        status="not_prepared",
        people=None,
        planned_calls=None,
        completed_calls=0,
        reserved_respondents_used=None,
        scope="Independent prediction on previously inspected development respondents.",
        metrics=[],
        limitations=[
            "Out-of-fit calibration is not fresh external validation.",
            "This comparison contains no conversation or historical evidence pack.",
            "Completion counts indicate saved responses, not whether a process is running.",
        ],
    )
    if not (directory / "contract.json").exists():
        return payload
    try:
        contract = _read(directory / "contract.json")
        _sealed(contract)
        config = contract["config"]
        payload.update(
            status="prepared",
            people=_number(config.get("people")),
            planned_calls=_number(config.get("planned_calls")),
            completed_calls=len(list((directory / "checkpoints").glob("*.json"))),
        )
        if payload["completed_calls"]:
            payload["status"] = "in_progress"
        if not (directory / "evaluation-seal.json").exists():
            return payload
        boundary = _read(directory / "evaluation-seal.json")
        _sealed(boundary)
        for name, key in [
            ("evaluation.json", "report_sha256"),
            ("prediction-seal.json", "prediction_seal_sha256"),
        ]:
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != boundary[key]:
                raise ValueError("Changed result")
        prediction_seal = _read(directory / "prediction-seal.json")
        _sealed(prediction_seal)
        for name in ["contract.json", "predictions.json"]:
            path = directory / name
            if (
                prediction_seal["bindings"].get(str(path))
                != hashlib.sha256(path.read_bytes()).hexdigest()
            ):
                raise ValueError("Changed prediction inputs")
        report = _read(directory / "evaluation.json")
        if report.get("reserved_respondents_used") != 0 or report.get("promotion") is not False:
            raise ValueError("Unexpected evaluation scope")
        rows = []
        for row in report["metrics"]:
            if row["arm"] not in ARMS or row["task"] not in TASKS:
                raise ValueError("Unknown comparison")
            if row["variant"] not in {"direct", "prevalence", "party", "hybrid"}:
                raise ValueError("Unknown predictor")
            weighted = row["weighted"]
            share_mae = weighted.get("answer_share_mae", weighted.get("share_mae"))
            if share_mae is None and _number(weighted.get("total_variation")) is not None:
                # Every current task has three categories: TV = sum(abs errors) / 2.
                share_mae = 2 * weighted["total_variation"] / 3
            rows.append(
                dict(
                    arm=row["arm"],
                    variant=row["variant"],
                    task=row["task"],
                    **{
                        k: _number(weighted.get(k))
                        for k in ["brier", "total_variation", "accuracy", "n", "effective_n"]
                    },
                    answer_share_mae=_number(share_mae),
                    repeat_agreement=_number(row.get("repeat_agreement")),
                )
            )
        payload.update(status="complete", reserved_respondents_used=0, metrics=rows)
    except (OSError, ValueError, KeyError, TypeError):
        payload.update(status="integrity_error", metrics=[])
    return payload
