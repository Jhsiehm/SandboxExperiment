import hashlib
import json

from leaderboard.individual import RUN_ID, build_individual_payload
from psbx.experiments.decision_profiles import seal


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def bundle(tmp_path):
    root = tmp_path / "data/runs" / RUN_ID
    write(root / "contract.json", seal(dict(config=dict(people=120, planned_calls=960))))
    write(root / "predictions.json", {})
    write(
        root / "prediction-seal.json",
        seal(
            dict(
                bindings={
                    str(root / name): hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in ["contract.json", "predictions.json"]
                }
            )
        ),
    )
    report = dict(
        promotion=False,
        reserved_respondents_used=0,
        fitting_audit=[dict(training_ids=["private-person"], path="/private/file")],
        metrics=[
            dict(
                arm="original_sparse",
                task="vote",
                variant="direct",
                weighted=dict(brier=0.2, n=100, total_variation=0.1, share_mae=0.03),
                raw="private-response",
                repeat_agreement=0.8,
            )
        ],
    )
    write(root / "evaluation.json", report)
    write(
        root / "evaluation-seal.json",
        seal(
            dict(
                report_sha256=hashlib.sha256((root / "evaluation.json").read_bytes()).hexdigest(),
                prediction_seal_sha256=hashlib.sha256(
                    (root / "prediction-seal.json").read_bytes()
                ).hexdigest(),
            )
        ),
    )
    return root


def test_missing_and_progress_never_claim_reserve_verification(tmp_path):
    assert build_individual_payload(tmp_path)["status"] == "not_prepared"
    root = tmp_path / "data/runs" / RUN_ID
    write(root / "contract.json", seal(dict(config=dict(people=120, planned_calls=960))))
    assert build_individual_payload(tmp_path)["status"] == "prepared"
    write(root / "checkpoints/one.json", {})
    result = build_individual_payload(tmp_path)
    assert result["status"] == "in_progress"
    assert result["completed_calls"] == 1
    assert result["reserved_respondents_used"] is None


def test_only_aggregates_are_exposed(tmp_path):
    bundle(tmp_path)
    result = build_individual_payload(tmp_path)
    assert result["status"] == "complete"
    assert result["metrics"][0]["brier"] == 0.2
    assert result["metrics"][0]["answer_share_mae"] == 0.03
    serialized = json.dumps(result)
    for secret in [str(tmp_path), "private-person", "private-response", "/private/file"]:
        assert secret not in serialized


def test_changed_report_or_predictions_suppresses_scores(tmp_path):
    root = bundle(tmp_path)
    write(root / "predictions.json", {"changed": True})
    assert build_individual_payload(tmp_path)["status"] == "integrity_error"
    root = bundle(tmp_path)
    write(root / "evaluation.json", {"changed": True})
    result = build_individual_payload(tmp_path)
    assert result["status"] == "integrity_error"
    assert result["metrics"] == []
