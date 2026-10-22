import json

from leaderboard.research import build_research_overview


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value))


def test_empty_checkout_is_unknown_not_running(tmp_path):
    payload = build_research_overview(tmp_path)
    assert payload["plan"]["status"] == "missing"
    assert all(s["status"] == "missing" for s in payload["studies"])
    assert all(s["metricValue"] is None for s in payload["studies"])
    assert all(not x["available"] and x["count"] is None for x in payload["library"])


def test_saved_counts_do_not_claim_process_liveness_or_expose_people(tmp_path):
    folder = "data/runs/debate-isolated-social-pilot-20261014/"
    write(
        tmp_path,
        folder + "contract.json",
        {"config": {"planned_calls": 480, "people": 32}, "targets": ["SECRET_PERSON"]},
    )
    write(tmp_path, folder + "audit.json", {"completed_checkpoints": 480})
    write(
        tmp_path,
        folder + "evaluation.json",
        {
            "people": 32,
            "groups": 8,
            "metrics": [{"arm": "swarm", "rps": 0.12}],
            "individual_rows": ["SECRET_RESPONSE"],
        },
    )
    payload = build_research_overview(tmp_path)
    debate = next(s for s in payload["studies"] if s["id"] == "debate")
    assert debate["completed"] == debate["total"] == 480
    assert debate["status"] == "saved_results"
    assert debate["metricValue"] == 0.12
    assert "SECRET" not in json.dumps(payload)


def test_oregon_offline_reference_and_plan_are_separate(tmp_path):
    write(
        tmp_path,
        "reports/behavior-feasibility-20261022/baseline/oregon-results.json",
        {
            "n_people": 74922,
            "provider_calls": 0,
            "historical_oof_metrics": {"same_information_logistic": {"brier": 0.1642}},
        },
    )
    path = tmp_path / "config/behavior-event-study-plan.yaml"
    path.parent.mkdir()
    path.write_text(
        "status: draft_not_executable\nexecution:\n  paid_calls_started: false\n "
        " proposed_pilot_usd_cap: 30\n  proposed_pilot_request_cap: 2000\n"
    )
    payload = build_research_overview(tmp_path)
    oregon = next(s for s in payload["studies"] if s["id"] == "oregon")
    assert oregon["kind"] == "offline_reference"
    assert oregon["metricValue"] == 0.1642
    assert oregon["completed"] is None
    assert payload["plan"]["paidCallsStarted"] is False
    assert payload["plan"]["requestCap"] == 2000


def test_corrupt_and_wrong_shape_metadata_does_not_crash(tmp_path):
    write(
        tmp_path, "reports/experiment-history-20261022/experiment-ledger.json", {"records": "bad"}
    )
    write(
        tmp_path,
        "config/behavior-event-study-plan.yaml",
        {"tracks": ["bad"], "existing_evidence": "bad"},
    )
    path = tmp_path / "data/corpus/e2012/meta.json"
    path.parent.mkdir(parents=True)
    path.write_text("{partial")
    assert build_research_overview(tmp_path)["plan"]["tracks"] == []


def test_admission_reference_checks_and_reserve_audit(tmp_path):
    prefix = "reports/behavior-feasibility-20261022/"
    write(
        tmp_path,
        prefix + "integration/decision-summary.json",
        {
            "anes_reserve_accessed": False,
            "debate": {
                "strict_structure_pass": 104,
                "masked_audited_sessions": 108,
                "confirmation_candidates_passing": 29,
                "confirmation_candidates_proposed": 30,
            },
        },
    )
    write(
        tmp_path,
        prefix + "baseline/oregon-results.json",
        {
            "published_rounding_checks": {
                "endpoint": {"control_mean": {"passed": True}, "coefficient": {"passed": False}}
            }
        },
    )
    write(tmp_path, "config/election_sources.yaml", {"sources": [{"id": "one"}]})
    write(tmp_path, "config/survey_sources.yaml", {"artifacts": [{"id": "one"}, {"id": "two"}]})
    payload = build_research_overview(tmp_path)
    studies = {s["id"]: s for s in payload["studies"]}
    assert studies["debate"]["admission"]["passed"] == 104
    assert studies["debate"]["admission"]["confirmationTotal"] == 30
    assert studies["oregon"]["referenceChecks"]["passed"] == 1
    assert studies["oregon"]["referenceChecks"]["total"] == 2
    assert studies["reserve"]["reserveAccessed"] is False
    assert all(studies[id]["detailView"] is None for id in ["debate", "oregon", "reserve"])
    library = {s["id"]: s for s in payload["library"]}
    assert library["elections"]["count"] == 1
    assert library["surveys"]["count"] == 2
