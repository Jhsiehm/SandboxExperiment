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


def test_local_comparison_progress_is_aggregate_and_not_liveness(tmp_path):
    prefix = "data/local-mlx-pilot/matched-comparison-20261023/"
    write(tmp_path, prefix + "protocol.json", {"stages": [
        {"id": "A_observed_history_message_loss", "examples": 133}]})
    scores = tmp_path / prefix / "base/scores.jsonl"
    scores.parent.mkdir()
    scores.write_text('{"participant":"SECRET","nll":1}\n{"partial":')
    progress = build_research_overview(tmp_path)["local_comparison"]
    assert progress["arms"][0]["completed"] == 1
    assert progress["arms"][0]["status"] == "progress_saved_unverified"
    assert "SECRET" not in json.dumps(progress)
    assert progress["arms"][1]["completed"] is None
    write(tmp_path, prefix + "base/summary.json", {
        "status": "completed", "examples": 133, "groups": {"SECRET": 0.5},
        "token_weighted_nll": 3.6})
    assert build_research_overview(tmp_path)["local_comparison"]["arms"][0]["status"] == "summary_saved_unverified"
    write(tmp_path, prefix + "watchdog-nll-base/summary.json", {"exit_code": 0})
    arm = build_research_overview(tmp_path)["local_comparison"]["arms"][0]
    assert arm["status"] == "completed"
    assert arm["token_weighted_nll"] == 3.6
    assert "SECRET" not in json.dumps(arm)
    write(tmp_path, prefix + "watchdog-nll-base/summary.json", {"exit_code": 124})
    assert build_research_overview(tmp_path)["local_comparison"]["arms"][0]["status"] == "stopped"


def test_local_stage_decision_whitelist_separates_format_failure(tmp_path):
    prefix = "data/local-mlx-pilot/matched-comparison-20261023/"
    write(tmp_path, prefix + "protocol.json", {"stages": []})
    write(tmp_path, prefix + "stage-decision.json", {
        "status": "stopped", "stage": "B1_direct_belief_transfer",
        "reason": "pilot_adapter_first_prediction_invalid_json",
        "base_valid": 16, "base_planned": 16, "adapter_attempted": 1,
        "adapter_valid": 0, "adapter_planned": 16,
        "outcome_scoring_performed": False,
        "B2": "not_started_format_gate_failed", "retries": 0, "repairs": 0,
        "new_paid_calls": 0, "interpretation": "SECRET", "targets": ["SECRET"],
        "raw_prediction": "SECRET", "credentials": "SECRET"})
    decision = build_research_overview(tmp_path)["local_comparison"]["stage_decision"]
    assert decision["status"] == "stopped"
    assert decision["base_valid"] == 16
    assert decision["adapter_valid"] == 0
    assert decision["outcome_scoring_performed"] is False
    assert decision["B2"] == "not_started_format_gate_failed"
    assert "SECRET" not in json.dumps(decision)
    write(tmp_path, prefix + "stage-decision.json", {
        "status": "SECRET", "stage": "SECRET", "reason": "SECRET", "B2": "SECRET",
        "base_valid": "SECRET", "adapter_valid": True, "retries": -1,
        "outcome_scoring_performed": "SECRET"})
    decision = build_research_overview(tmp_path)["local_comparison"]["stage_decision"]
    assert "SECRET" not in json.dumps(decision)
    assert decision["base_valid"] is None
    assert decision["adapter_valid"] is None
    assert decision["retries"] is None


def test_training_format_summary_exposes_only_counts(tmp_path):
    write(tmp_path, "data/local-mlx-pilot/matched-comparison-20261023/protocol.json", {"stages": []})
    write(tmp_path, "data/local-mlx-pilot/format-smoke-v1-20261023/format-evaluation.json", {
        "status": "completed", "prefill_all_models_all_cases_valid": False,
        "paired_statuses": ["SECRET"], "results": {
            "base": {"original": {"valid": 4}, "assistant_prefill": {"valid": 3}},
            "pilot_adapter": {"original": {"valid": 0}, "assistant_prefill": {"valid": 0, "raw": "SECRET"}}}})
    result = build_research_overview(tmp_path)["local_comparison"]["format_smoke"]
    assert result["passed"] is False
    assert result["counts"]["base"]["original"] == 4
    assert result["counts"]["pilot_adapter"]["assistant_prefill"] == 0
    assert "SECRET" not in json.dumps(result)


def test_classifier_pilot_aggregate_summary(tmp_path):
    write(tmp_path, 'data/local-mlx-pilot/matched-comparison-20261023/protocol.json', {'stages': []})
    prefix='data/local-mlx-pilot/outcome-classifier-v1-20261023/'
    write(tmp_path,prefix+'contract.json',{'status':'frozen_classifier_v1'})
    write(tmp_path,prefix+'training/summary.json',{'status':'completed','SECRET':'hidden'})
    write(tmp_path,prefix+'watchdog-train/summary.json',{'exit_code':0})
    write(tmp_path,prefix+'internal-evaluation.json',{'status':'completed','numerical_nonworsening_gate':False,
        'arms':{'base':{'rps':.1},'pilot_classifier':{'rps':.2},'persistence':{'rps':.15},'transition':{'rps':.12}},
        'predictions':['SECRET']})
    result=build_research_overview(tmp_path)['local_comparison']['classifier']
    assert result['training_completed'] and result['internal_completed']
    assert result['candidate_rps']==.2 and result['gate_passed'] is False
    assert 'SECRET' not in json.dumps(result)


def test_classifier_investigation_excludes_row_data(tmp_path):
    write(tmp_path,'data/local-mlx-pilot/matched-comparison-20261023/protocol.json',{'stages':[]})
    write(tmp_path,'data/local-mlx-pilot/outcome-classifier-v1-20261023/investigation-summary.json',{
        'status':'completed','candidate_category4_count':23,'people':24,'sampled_baseline_rps':.134724,
        'participant_text':'SECRET','row_data':['SECRET'],'cause':'SECRET'})
    result=build_research_overview(tmp_path)['local_comparison']['investigation']
    assert result['candidate_category4_count']==23
    assert result['sampled_baseline_rps']==.134724
    assert 'SECRET' not in json.dumps(result)


RESIDUAL_PREFIX = 'data/local-mlx-pilot/residual-calibration-v1-20261023/'


def residual_fixture(tmp_path, *, verified=True):
    write(tmp_path, RESIDUAL_PREFIX+'contract.json', {'status':'frozen_residual_calibration_v1'})
    write(tmp_path, RESIDUAL_PREFIX+'base-fit/summary.json', {'status':'completed','completed':92,
        'elapsed_seconds':32.56,'peak_allocated_bytes':4930000000,'row_logits':['SECRET']})
    if verified:
        write(tmp_path, RESIDUAL_PREFIX+'watchdog-base-fit/summary.json',
              {'exit_code':0,'child_returncode':0,'stop_reason':None,'error':None})


def test_residual_prepared_does_not_claim_running(tmp_path):
    write(tmp_path, RESIDUAL_PREFIX+'contract.json', {'status':'frozen_residual_calibration_v1','profiles':['SECRET']})
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['status']=='prepared_or_running_unverified'
    assert result['completed'] is None and not result['forward_completed']
    assert result['oof'] is None
    assert 'SECRET' not in json.dumps(result)


def test_residual_gate_failure_whitelists_aggregates(tmp_path):
    residual_fixture(tmp_path)
    write(tmp_path, RESIDUAL_PREFIX+'oof-evaluation.json', {'status':'completed','group_rps':{'SECRET':1},
        'fold_models':[{'coefficients':['SECRET']}], 'gate':{'passed':False,
            'mean_rps':{'transition':.141336,'control':.140186,'extension':.140233,'SECRET':1},
            'extension_gain':{'control':-.000047,'transition':.001103,'SECRET':1},
            'component_differences':{'SECRET':1}}})
    write(tmp_path, RESIDUAL_PREFIX+'decision.json', {'status':'oof_gate_failed','internal_readout':False,
        'outer_validation':False,'reason':'SECRET'})
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['status']=='oof_gate_failed' and result['completed']==92
    assert result['oof']['mean_rps']['control']==.140186
    assert result['oof']['extension_gain']['control']==-.000047
    assert result['internal'] is None and result['internal_readout'] is False
    assert 'SECRET' not in json.dumps(result)


def test_residual_summary_without_supervisor_not_completed(tmp_path):
    residual_fixture(tmp_path,verified=False)
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['status']=='summary_saved_unverified' and not result['forward_completed']
    write(tmp_path, RESIDUAL_PREFIX+'watchdog-base-fit/summary.json',
          {'exit_code':124,'child_returncode':0,'stop_reason':'SECRET'})
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['status']=='forward_stopped'
    assert 'SECRET' not in json.dumps(result)


def test_residual_malformed_values_and_unknown_fields_hidden(tmp_path):
    residual_fixture(tmp_path)
    write(tmp_path, RESIDUAL_PREFIX+'oof-evaluation.json', {'status':'completed', 'gate':{
        'passed':'SECRET','mean_rps':{'control':float('nan'),'extension':True,'transition':-1},
        'extension_gain':{'control':'SECRET','transition':float('inf')}}})
    write(tmp_path, RESIDUAL_PREFIX+'decision.json', {'status':'SECRET','internal_readout':'SECRET','outer_validation':'SECRET'})
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert all(value is None for value in result['oof']['mean_rps'].values())
    assert all(value is None for value in result['oof']['extension_gain'].values())
    assert result['oof']['passed'] is None and result['decision_status'] is None
    assert 'SECRET' not in json.dumps(result)


def test_residual_internal_scores_require_oof_pass(tmp_path):
    residual_fixture(tmp_path)
    write(tmp_path, RESIDUAL_PREFIX+'internal-calibration-evaluation.json', {'status':'completed',
        'mean_rps':{'transition':.15,'control':.14,'extension':.13},'direction_retained':True,
        'group_rps':{'SECRET':.1}})
    write(tmp_path, RESIDUAL_PREFIX+'oof-evaluation.json', {'status':'completed','gate':{'passed':False}})
    assert build_research_overview(tmp_path)['local_comparison']['residual_calibration']['internal'] is None
    write(tmp_path, RESIDUAL_PREFIX+'oof-evaluation.json', {'status':'completed','gate':{'passed':True}})
    result=build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['status']=='gates_passed_review_required'
    assert result['internal']['mean_rps']['extension']==.13
    assert 'SECRET' not in json.dumps(result)


def test_residual_reader_never_opens_row_predictions(tmp_path,monkeypatch):
    import leaderboard.research as research
    residual_fixture(tmp_path)
    original=research._read
    def guard(base,relative):
        assert not relative.endswith(('predictions.jsonl','oof-predictions.json','final-calibrators.json'))
        return original(base,relative)
    monkeypatch.setattr(research,'_read',guard)
    result=research.build_research_overview(tmp_path)['local_comparison']['residual_calibration']
    assert result['forward_completed']


def test_panel_preparation_whitelists_aggregates(tmp_path):
    write(tmp_path, 'reports/statistical-reference-20261023/manifest.json', {'status': 'frozen_statistical_reference_development_only', 'bindings': {'SECRET': 'SECRET'}})
    write(tmp_path, 'reports/statistical-reference-20261023/data-quality.json', {'unique_people':92, 'unique_groups':23, 'changed_count':44, 'unchanged_count':48, 'row_ids':['SECRET']})
    write(tmp_path, 'reports/anes-panel-readiness-20261023/readiness.json', {'status':'blocked_on_source_metadata', 'development_export_tool_ready':True, 'source_blocker_count':5, 'real_panel_records_audited':0, 'model_training_enabled':False, 'later_wave_readout_enabled':False, 'ready_for_development_ingestion':False, 'blockers':[{'id':'SECRET', 'text':'SECRET'}]})
    result=build_research_overview(tmp_path)['local_comparison']['panel_development']
    assert result['reference_retained'] is True
    assert result['quality']['unchanged_count']==48
    assert result['source_blocker_count']==5
    assert result['real_panel_records_audited']==0
    assert result['model_training_enabled'] is False
    assert 'SECRET' not in json.dumps(result)


def test_panel_preparation_rejects_wrong_types_and_unknown_status(tmp_path):
    write(tmp_path, 'reports/statistical-reference-20261023/manifest.json', {'status':'forged'})
    write(tmp_path, 'reports/statistical-reference-20261023/data-quality.json', {'unique_people':92})
    write(tmp_path, 'reports/anes-panel-readiness-20261023/readiness.json', {'status':'SECRET', 'source_blocker_count':True, 'real_panel_records_audited':-1, 'model_training_enabled':'false', 'development_export_tool_ready':'true'})
    result=build_research_overview(tmp_path)['local_comparison']['panel_development']
    assert result['status']=='unverified'
    assert result['reference_retained'] is False
    assert result['quality']['unique_people'] is None
    assert result['source_blocker_count'] is None
    assert result['real_panel_records_audited'] is None
    assert result['model_training_enabled'] is None
    assert result['development_export_tool_ready'] is False
