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
