"""Bounded, aggregate-only inventory for the research workspace.

This reads saved metadata, never respondent rows or provider/process state.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

import yaml

from psbx.paths import repo_root

HISTORY = "reports/experiment-history-20261022/experiment-ledger.json"
FEASIBILITY = "reports/behavior-feasibility-20261022"
PLAN = "config/behavior-event-study-plan.yaml"
MAX_BYTES = 8_000_000


def _read(base, relative):
    try:
        path = base / relative
        if path.stat().st_size > MAX_BYTES:
            return {}
        text = path.read_text(encoding="utf-8")
        value = yaml.safe_load(text) if path.suffix == ".yaml" else json.loads(text)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError, yaml.YAMLError):
        return {}


def _num(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _obj(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _count(base, pattern):
    try:
        # A capped inventory is unknown rather than a misleading exact count.
        n = sum(1 for _ in islice(base.glob(pattern), 10001))
        return n if n <= 10000 else None
    except OSError:
        return None


def _measure(label, value):
    return {"label": label, "value": _num(value)}


LOCAL_COMPARISON = "data/local-mlx-pilot/matched-comparison-20261023"
RESIDUAL_CALIBRATION = "data/local-mlx-pilot/residual-calibration-v1-20261023"


def _saved_score_count(path):
    # Count complete records only. Never deserialize row-level scores or identities.
    try:
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes().count(b"\n")
    except OSError:
        return None


def panel_development_progress(base):
    reference = _read(base, "reports/statistical-reference-20261023/manifest.json")
    quality = _read(base, "reports/statistical-reference-20261023/data-quality.json")
    readiness = _read(base, "reports/anes-panel-readiness-20261023/readiness.json")
    if not reference and not readiness:
        return None
    def count(value):
        return value if type(value) is int and value >= 0 else None
    retained = reference.get("status") == "frozen_statistical_reference_development_only"
    return {
        "reference_retained": retained,
        "quality": {key: count(quality.get(key)) if retained else None for key in
                    ("unique_people", "unique_groups", "changed_count", "unchanged_count")},
        "status": "blocked_on_source_metadata" if readiness.get("status") == "blocked_on_source_metadata" else "unverified",
        "development_export_tool_ready": readiness.get("development_export_tool_ready") is True,
        "source_blocker_count": count(readiness.get("source_blocker_count")),
        "real_panel_records_audited": count(readiness.get("real_panel_records_audited")),
        "model_training_enabled": readiness.get("model_training_enabled") if type(readiness.get("model_training_enabled")) is bool else None,
        "later_wave_readout_enabled": readiness.get("later_wave_readout_enabled") if type(readiness.get("later_wave_readout_enabled")) is bool else None,
        "ready_for_development_ingestion": readiness.get("ready_for_development_ingestion") is True,
    }


def residual_calibration_progress(base):
    """Expose only whitelisted aggregates; do not open row prediction files."""
    if not _read(base, RESIDUAL_CALIBRATION + "/contract.json"):
        return None
    summary = _read(base, RESIDUAL_CALIBRATION + "/base-fit/summary.json")
    watchdog = _read(base, RESIDUAL_CALIBRATION + "/watchdog-base-fit/summary.json")
    oof = _read(base, RESIDUAL_CALIBRATION + "/oof-evaluation.json")
    internal = _read(base, RESIDUAL_CALIBRATION + "/internal-calibration-evaluation.json")
    decision = _read(base, RESIDUAL_CALIBRATION + "/decision.json")
    failure = _read(base, RESIDUAL_CALIBRATION + "/calibration-failure.json")
    count = summary.get("completed")
    count = count if type(count) is int and 0 <= count <= 92 else None
    exit_code = _num(watchdog.get("exit_code"))
    verified = (summary.get("status") == "completed" and count == 92 and
                type(watchdog.get("exit_code")) is int and watchdog["exit_code"] == 0 and
                type(watchdog.get("child_returncode")) is int and watchdog["child_returncode"] == 0 and
                watchdog.get("stop_reason") is None and watchdog.get("error") is None)
    gate = _obj(oof.get("gate"))
    passed = gate.get("passed") if type(gate.get("passed")) is bool else None
    safe_oof = None
    if oof.get("status") == "completed":
        means = {name: _num(_obj(gate.get("mean_rps")).get(name)) for name in ("transition", "control", "extension")}
        means = {name: value if value is not None and 0 <= value <= 1 else None for name, value in means.items()}
        gains = {name: _num(_obj(gate.get("extension_gain")).get(name)) for name in ("transition", "control")}
        gains = {name: value if value is not None and -1 <= value <= 1 else None for name, value in gains.items()}
        safe_oof = dict(mean_rps=means, extension_gain=gains, passed=passed)
    safe_internal = None
    if verified and safe_oof is not None and passed is True and internal.get("status") == "completed":
        means = {name: _num(_obj(internal.get("mean_rps")).get(name)) for name in ("transition", "control", "extension")}
        safe_internal = dict(mean_rps={name: value if value is not None and 0 <= value <= 1 else None for name, value in means.items()},
                             direction_retained=internal.get("direction_retained") if type(internal.get("direction_retained")) is bool else None)
    if (exit_code is not None and exit_code != 0) or summary.get("status") == "failed":
        status = "forward_stopped"
    elif failure.get("status") == "failed":
        status = "calibration_failed"
    elif safe_oof is not None and not verified:
        status = "results_saved_unverified"
    elif safe_oof is not None and passed is False:
        status = "oof_gate_failed"
    elif safe_internal is not None and safe_internal["direction_retained"] is False:
        status = "internal_direction_failed"
    elif safe_internal is not None and safe_internal["direction_retained"] is True:
        status = "gates_passed_review_required"
    elif safe_oof is not None and passed is True:
        status = "oof_passed_internal_pending"
    elif verified:
        status = "forwards_completed"
    elif summary:
        status = "summary_saved_unverified"
    else:
        status = "prepared_or_running_unverified"
    decision_status = decision.get("status")
    return dict(source=RESIDUAL_CALIBRATION, status=status, completed=count, total=92,
                forward_completed=verified, elapsed_seconds=_num(summary.get("elapsed_seconds")),
                peak_allocated_bytes=_num(summary.get("peak_allocated_bytes")), exit_code=exit_code,
                oof=safe_oof, internal=safe_internal,
                decision_status=decision_status if decision_status in ("oof_gate_failed", "gates_passed", "internal_direction_failed") else None,
                internal_readout=decision.get("internal_readout") if type(decision.get("internal_readout")) is bool else None,
                outer_validation=decision.get("outer_validation") if type(decision.get("outer_validation")) is bool else None)


def local_comparison_progress(base):
    protocol = _read(base, LOCAL_COMPARISON + "/protocol.json")
    calibration = residual_calibration_progress(base)
    panel_development = panel_development_progress(base)
    if not protocol and calibration is None and panel_development is None:
        return None
    stage = next((row for row in _rows(protocol.get("stages"))
                  if row.get("id") == "A_observed_history_message_loss"), {})
    total = _num(stage.get("examples"))
    arms = []
    for arm, label, watchdog in [
        ("base", "Base model", "watchdog-nll-base"),
        ("pilot_adapter", "Pilot adapter", "watchdog-nll-adapter"),
    ]:
        summary = _read(base, f"{LOCAL_COMPARISON}/{arm}/summary.json")
        supervisor = _read(base, f"{LOCAL_COMPARISON}/{watchdog}/summary.json")
        count = _saved_score_count(base / LOCAL_COMPARISON / arm / "scores.jsonl")
        completed = _num(summary.get("examples")) if summary else count
        exit_code = _num(supervisor.get("exit_code"))
        if exit_code is not None and exit_code != 0:
            status = "stopped"
        elif summary.get("status") == "completed" and exit_code == 0 and completed == total and total is not None:
            status = "completed"
        elif summary:
            status = "summary_saved_unverified"
        elif count is not None:
            status = "progress_saved_unverified"
        else:
            status = "not_recorded"
        arms.append(dict(id=arm, label=label, status=status, completed=completed,
                         total=total, elapsed_seconds=_num(summary.get("elapsed_seconds")),
                         token_weighted_nll=_num(summary.get("token_weighted_nll")),
                         exit_code=exit_code))
    decision = _read(base, LOCAL_COMPARISON + "/stage-decision.json")
    safe_decision = None
    if decision:
        # Never pass through free text, model outputs, row lists or unknown fields.
        safe_decision = {
            "status": decision.get("status") if decision.get("status") in ("stopped", "completed", "deferred") else "unknown",
            "stage": decision.get("stage") if decision.get("stage") in ("A_observed_history_message_loss", "B1_direct_belief_transfer", "B2_private_and_swarm_diagnostic") else "unknown",
            "reason": "pilot_adapter_first_prediction_invalid_json" if decision.get("reason") == "pilot_adapter_first_prediction_invalid_json" else "unspecified",
            "B2": "not_started_format_gate_failed" if decision.get("B2") == "not_started_format_gate_failed" else "unknown",
            "outcome_scoring_performed": decision.get("outcome_scoring_performed") if type(decision.get("outcome_scoring_performed")) is bool else None,
        }
        for field in ("base_valid", "base_planned", "adapter_attempted", "adapter_valid", "adapter_planned", "retries", "repairs", "new_paid_calls"):
            value = decision.get(field)
            safe_decision[field] = value if type(value) is int and value >= 0 else None
    format_result = _read(base, "data/local-mlx-pilot/format-smoke-v1-20261023/format-evaluation.json")
    format_summary = None
    if format_result.get("status") == "completed":
        counts = {}
        for model in ("base", "pilot_adapter"):
            counts[model] = {}
            for condition in ("original", "assistant_prefill"):
                row = _obj(_obj(_obj(format_result.get("results")).get(model)).get(condition))
                value = row.get("valid")
                counts[model][condition] = value if type(value) is int and 0 <= value <= 4 else None
        format_summary = dict(counts=counts,
            passed=format_result.get("prefill_all_models_all_cases_valid") is True)
    classifier_path = "data/local-mlx-pilot/outcome-classifier-v1-20261023"
    classifier = None
    if _read(base, classifier_path + "/contract.json"):
        train = _read(base, classifier_path + "/training/summary.json")
        watchdog = _read(base, classifier_path + "/watchdog-train/summary.json")
        evaluation = _read(base, classifier_path + "/internal-evaluation.json")
        classifier = dict(training_completed=train.get("status") == "completed" and watchdog.get("exit_code") == 0,
                          steps=_saved_score_count(base / classifier_path / "training/metrics.jsonl"),
                          internal_completed=evaluation.get("status") == "completed")
        if classifier["internal_completed"]:
            classifier.update(base_rps=_num(_obj(_obj(evaluation.get("arms")).get("base")).get("rps")),
                candidate_rps=_num(_obj(_obj(evaluation.get("arms")).get("pilot_classifier")).get("rps")),
                persistence_rps=_num(_obj(_obj(evaluation.get("arms")).get("persistence")).get("rps")),
                transition_rps=_num(_obj(_obj(evaluation.get("arms")).get("transition")).get("rps")),
                gate_passed=evaluation.get("numerical_nonworsening_gate") is True)
    investigation = _read(base, classifier_path + "/investigation-summary.json")
    safe_investigation = None
    if investigation.get("status") == "completed":
        safe_investigation = {key: _num(investigation.get(key)) for key in (
            "candidate_category4_count", "people", "unchanged_count", "unchanged_gap_fraction",
            "reconstructed_exposed_rows", "fit_rows", "sampled_baseline_rps")}
    return dict(source=LOCAL_COMPARISON, arms=arms, stage_decision=safe_decision, format_smoke=format_summary, classifier=classifier, investigation=safe_investigation, residual_calibration=calibration, panel_development=panel_development,
                description="Local research experiments · development only" if calibration else "Local observed-history message scoring · development only",
                limitation="Saved progress is not proof of a running process. Message likelihood does not establish belief accuracy. This job has no social-action replay.")


def build_research_overview(root: Path | None = None):
    base = root or repo_root()
    plan = _read(base, PLAN)
    execution = _obj(plan.get("execution"))
    decision = _read(base, FEASIBILITY + "/integration/decision-summary.json")
    verification = _read(base, FEASIBILITY + "/integration/verification.json")
    oregon = _read(base, FEASIBILITY + "/baseline/oregon-results.json")
    history = _read(base, HISTORY)
    records = _rows(history.get("records"))
    studies = []

    def add(
        id,
        title,
        summary,
        source,
        *,
        available=False,
        status=None,
        completed=None,
        total=None,
        unit="saved calls",
        metricLabel="Recorded results",
        metricValue=None,
        kind="live_model_record",
        measures=None,
        limitations=None,
        detailView=None,
    ):
        studies.append(
            dict(
                id=id,
                title=title,
                summary=summary,
                source=source,
                status=status or ("saved_results" if available else "missing"),
                completed=completed,
                total=total,
                unit=unit,
                metricLabel=metricLabel,
                metricValue=_num(metricValue),
                kind=kind,
                measures=measures or [],
                limitations=limitations or [],
                detailView=detailView,
            )
        )

    for id, run, title, description in [
        (
            "individual",
            "anes2012-ohio-individual-development-20261020",
            "ANES · individual development",
            "Focused profiles and private review, compared with sparse, rich and "
            "statistical baselines.",
        ),
        (
            "ablation",
            "anes2012-ohio-profile-ablation-development-v1",
            "ANES · profile ablation",
            "Four profile arms, repeated forecasts and cross-fitted calibration "
            "on inspected development people.",
        ),
        (
            "debate",
            "debate-isolated-social-pilot-20261014",
            "DEBATE · social update",
            "Generated conversation, private reflection, persistence and incoming-message replay.",
        ),
    ]:
        folder = "data/runs/" + run
        report = _read(base, folder + "/evaluation.json")
        contract = _obj(_read(base, folder + "/contract.json").get("config"))
        audit = _read(base, folder + "/audit.json")
        completed = _num(audit.get("completed_checkpoints", audit.get("checkpoints")))
        if completed is None and contract:
            completed = _count(base / folder, "checkpoints/*.json")
        measures = [
            _measure("People", contract.get("people")),
            _measure("Planned calls", contract.get("planned_calls")),
        ]
        if id == "individual":
            measures += [
                _measure(k.replace("_", " "), v) for k, v in _obj(report.get("macro_brier")).items()
            ]
            label, metric = (
                "Focused weighted half-Brier",
                _obj(report.get("macro_brier")).get("focused_direct"),
            )
            limits = [
                "Development evidence; no demonstrated advantage over the party baseline.",
                "Scores are not directly comparable to the later ablation aggregation.",
            ]
        elif id == "ablation":
            for arm in [
                "original_sparse",
                "original_rich",
                "reduced_existing",
                "reduced_plus_observed",
            ]:
                values = [
                    _num(_obj(r.get("weighted")).get("brier"))
                    for r in _rows(report.get("metrics"))
                    if r.get("arm") == arm and r.get("variant") == "direct"
                ]
                values = [v for v in values if v is not None]
                measures.append(
                    _measure(
                        arm.replace("_", " ") + " · direct half-Brier",
                        sum(values) / len(values) if len(values) == 3 else None,
                    )
                )
            label, metric = "Reduced + observed half-Brier", measures[-1]["value"]
            limits = [
                "Previously inspected development people; no fresh holdout claim.",
                "No arm promoted; conditional intervals omit calibration-refitting uncertainty.",
            ]
        else:
            measures += [
                _measure(str(r.get("arm")) + " · RPS", r.get("rps"))
                for r in _rows(report.get("metrics"))
            ]
            label, metric = (
                "Conversation RPS",
                next(
                    (r.get("rps") for r in _rows(report.get("metrics")) if r.get("arm") == "swarm"),
                    None,
                ),
            )
            measures.append(_measure("Conversation groups", report.get("groups")))
            limits = [
                "Small selected pilot; superiority to persistence remains uncertain.",
                "Research-only dataset. Replay is a conditional diagnostic, not "
                "a time-zero forecast.",
            ]
        add(
            id,
            title,
            description,
            folder + "/evaluation.json",
            available=bool(report),
            status="saved_results" if report else ("saved_progress" if completed else "missing"),
            completed=completed,
            total=_num(contract.get("planned_calls")),
            metricLabel=label,
            metricValue=metric,
            measures=measures,
            limitations=limits,
            detailView="anes" if id != "debate" else None,
        )

    debate_admission = _obj(decision.get("debate"))
    debate_study = next(s for s in studies if s["id"] == "debate")
    debate_study["measures"] += [
        _measure(
            "Structure-passing audited sessions", debate_admission.get("strict_structure_pass")
        ),
        _measure("Audited sessions", debate_admission.get("masked_audited_sessions")),
        _measure(
            "Passing confirmation candidates",
            debate_admission.get("confirmation_candidates_passing"),
        ),
        _measure(
            "Proposed confirmation candidates",
            debate_admission.get("confirmation_candidates_proposed"),
        ),
    ]
    debate_study["admission"] = {
        "passed": _num(debate_admission.get("strict_structure_pass")),
        "total": _num(debate_admission.get("masked_audited_sessions")),
        "confirmationPassed": _num(debate_admission.get("confirmation_candidates_passing")),
        "confirmationTotal": _num(debate_admission.get("confirmation_candidates_proposed")),
        "source": FEASIBILITY + "/integration/decision-summary.json",
        "status": "admission_audit" if debate_admission else "missing",
    }
    metrics = _obj(oregon.get("historical_oof_metrics"))
    add(
        "oregon",
        "Oregon · observed enrollment",
        "Historical administrative enrollment reference reproduced; paid-agent "
        "admission remains pending.",
        FEASIBILITY + "/baseline/oregon-results.json",
        available=bool(oregon),
        kind="offline_reference",
        completed=None,
        total=None,
        unit="people in historical source",
        metricLabel="Logistic historical OOF Brier",
        metricValue=_obj(metrics.get("same_information_logistic")).get("brier"),
        measures=[
            _measure("People", oregon.get("n_people")),
            _measure("Households", oregon.get("n_households")),
            _measure("Assignment-only Brier", _obj(metrics.get("assignment_only")).get("brier")),
            _measure("Provider calls", oregon.get("provider_calls")),
            _measure(
                "Published reference checks passed",
                verification.get("published_reference_checks_passed"),
            ),
        ],
        limitations=[
            "Historical development reproduction; not fresh confirmation or agent performance.",
            "Sparse measured inputs; no observed social network or invented individual trajectory.",
        ],
    )
    checks = [
        check
        for endpoint in _obj(oregon.get("published_rounding_checks")).values()
        for check in _obj(endpoint).values()
        if isinstance(check, dict)
    ]
    studies[-1]["referenceChecks"] = {
        "passed": sum(check.get("passed") is True for check in checks) if checks else None,
        "total": len(checks) if checks else None,
        "source": FEASIBILITY + "/baseline/oregon-results.json",
    }
    historical = [r for r in records if r.get("family") == "historical_forecast"]
    add(
        "forecast",
        "Historical forecasting",
        "Cutoff-constrained event forecasts and retrieval experiments; archive "
        "includes mock and live records.",
        HISTORY,
        available=bool(historical),
        kind="mixed_archive",
        unit="history records",
        metricLabel="Historical forecast records",
        metricValue=len(historical) if history else None,
        limitations=[
            "Records are not independent studies. Mock runs do not establish predictive validity."
        ],
        detailView="runs",
    )
    reserve = _num(
        _obj(_obj(plan.get("existing_evidence")).get("anes")).get("protected_reserve_people")
    )
    add(
        "reserve",
        "Reserved validation",
        "Protected ANES reserve remains outside development fitting and scoring.",
        PLAN,
        status="protected" if reserve is not None else "missing",
        kind="protected",
        metricLabel="Reserved people",
        metricValue=reserve,
        limitations=[
            "No respondent content is read by this view. Reserve size comes from planning metadata."
        ],
    )

    studies[-1]["reserveAccessed"] = (
        decision.get("anes_reserve_accessed")
        if type(decision.get("anes_reserve_accessed")) is bool
        else None
    )
    studies[-1]["auditSource"] = (
        FEASIBILITY + "/integration/decision-summary.json" if decision else None
    )
    if studies[-1]["reserveAccessed"] is False:
        studies[-1]["summary"] = "Latest saved feasibility audit reports no ANES reserve access."
        studies[-1]["limitations"].append(
            "Audit covers the saved feasibility work, not live access monitoring."
        )

    library = []

    def item(id, title, source, summary, count=None, unit="items", runtime="Metadata only"):
        library.append(
            dict(
                id=id,
                title=title,
                source=source,
                summary=summary,
                count=_num(count),
                unit=unit,
                available=(base / source).exists(),
                runtimeAccess=runtime,
            )
        )

    meta = _read(base, "data/corpus/e2012/meta.json")
    item(
        "corpus",
        "Historical evidence corpus",
        "data/corpus/e2012/meta.json",
        "Cutoff-controlled retrieval index includes reconstructed fixtures; "
        "public documents do not imply personal exposure.",
        meta.get("n_docs", meta.get("n_documents", meta.get("document_count"))),
        "documents",
        "Cutoff-filtered retrieval",
    )
    library[-1]["measures"] = [
        _measure(
            "Authenticated artifacts",
            _obj(meta.get("authenticity_counts")).get("authenticated_artifact"),
        ),
        _measure(
            "Reconstructed fixtures",
            _obj(meta.get("authenticity_counts")).get("reconstructed_fixture"),
        ),
        _measure("Research-eligible documents", meta.get("research_eligible_documents")),
    ]
    bank = _read(base, "data/survey-microdata/anes/2012/derived/question_bank.jsonl.manifest.json")
    item(
        "anes",
        "ANES question inventory",
        "data/survey-microdata/anes/2012/derived/question_bank.jsonl.manifest.json",
        "Question specifications only; outcome-bearing microdata remains evaluator-side.",
        _obj(bank.get("counts")).get("total"),
        "question specifications",
        "Approved profile fields only",
    )
    item(
        "population",
        "Synthetic population manifests",
        "data/population",
        "Constructed population bundles, not observed independent human responses.",
        _count(base / "data/population", "*/*/manifest.json")
        if (base / "data/population").exists()
        else None,
        "population bundles",
        "Synthetic construction",
    )
    debate = _obj(decision.get("debate"))
    item(
        "debate",
        "DEBATE source sessions",
        FEASIBILITY + "/integration/decision-summary.json",
        "Research-only source inventory; source pseudonyms are not independently "
        "verified unique humans.",
        debate.get("golden_sessions"),
        "source sessions",
        "Contract-filtered initial profiles and incoming messages",
    )
    item(
        "oregon",
        "Oregon administrative source",
        FEASIBILITY + "/oregon-data/manifest.json",
        "Official archive acquired; model-visible features and cutoff policy await admission.",
        oregon.get("n_people"),
        "source people",
        "Agent admission pending; outcomes evaluator-only",
    )
    item(
        "history",
        "Experiment ledger",
        HISTORY,
        "Includes plans, mocks, reanalyses and live runs; not a count of independent experiments.",
        len(records) if history else None,
        "indexed records",
        "Aggregate research metadata",
    )
    item(
        "reserve",
        "Protected validation boundary",
        PLAN,
        "No reading, fitting, tuning or scoring during this development phase.",
        reserve,
        "reserved people",
        "Excluded from agent runtime",
    )
    for key, title, path, field, access, summary in [
        (
            "elections",
            "Election comparison registry",
            "config/election_sources.yaml",
            "sources",
            "Release checks required; comparison outcomes evaluator-only",
            "Registered comparison sources, not a count of downloaded or "
            "runtime-admitted datasets.",
        ),
        (
            "surveys",
            "Survey source registry",
            "config/survey_sources.yaml",
            "artifacts",
            "Only verified cutoff-safe public artifacts; gated sources require manual access",
            "Registered survey artifact versions, not necessarily downloaded or "
            "approved for the epoch.",
        ),
    ]:
        registry = _read(base, path)
        item(
            key,
            title,
            path,
            summary,
            len(_rows(registry.get(field))) if registry else None,
            "registered sources" if field == "sources" else "registered artifact versions",
            access,
        )

    tracks = []
    titles = {
        "individual": "Individual prediction",
        "social_update": "Social updating",
        "behavior_event": "Observed behavior",
    }
    for key, value in _obj(plan.get("tracks")).items():
        if key not in titles:
            continue
        value = _obj(value)
        tracks.append(
            dict(
                id=key,
                title=titles[key],
                summary=value.get("design")
                or value.get("primary_contrast")
                or value.get("proposed_primary_outcome"),
                status="planned",
            )
        )
    return dict(
        schema_version=1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        studies=studies,
        local_comparison=local_comparison_progress(base),
        library=library,
        plan=dict(
            summary=plan.get("purpose"),
            status=plan.get("status", "missing"),
            paidCallsStarted=execution.get("paid_calls_started"),
            usdCap=_num(execution.get("proposed_pilot_usd_cap")),
            requestCap=_num(execution.get("proposed_pilot_request_cap")),
            tracks=tracks,
            source=PLAN,
        ),
        caveats=[
            "Saved counts are not process liveness; this view does not launch experiments.",
            "Pixel scenes are symbolic aggregate illustrations, not observed "
            "social networks or individual trajectories.",
            "Missing values mean unavailable, not zero. Metrics have different "
            "targets and denominators.",
            "Read-only local artifact summary; aggregate reports are not "
            "independently re-audited on each refresh.",
        ],
    )
