from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psbx.io import read_jsonl
from psbx.paths import resolve
from psbx.schemas import (
    CalibrationResult,
    ContaminationResult,
    ModelConfig,
    Prediction,
    Question,
    ScoreCoverage,
    ScoreReport,
)
from psbx.scoring.baselines import as_predictions, baseline_scores
from psbx.scoring.brier import brier, brier_by_category, brier_index
from psbx.scoring.calibration import calibration_curve
from psbx.scoring.concordance import concordance_index
from psbx.scoring.contamination import contamination_curve

PHASE1_HEURISTIC_RUN = "phase1-e2012-smoke"


def score_run(
    preds: list[Prediction],
    questions: list[Question],
    models: list[ModelConfig],
    run_id: str,
) -> ScoreReport:
    _validate_scoring_inputs(preds, questions, models)
    qs = {q.id: q for q in questions}
    configured = {model.id: model for model in models}
    model_ids = list(configured)
    model_ids.extend(sorted({p.model_id for p in preds} - set(model_ids)))
    subsets = {mid: [p for p in preds if p.model_id == mid] for mid in model_ids}
    answered_ids = {
        mid: {prediction.question_id for prediction in subset}
        for mid, subset in subsets.items()
    }
    by_model = {
        mid: (brier(subset, qs) if subset else None)
        for mid, subset in subsets.items()
    }
    calib = {
        mid: calibration_curve(subset, qs)
        for mid, subset in subsets.items()
        if subset
    }
    contam = [
        contamination_curve(subsets[model.id], qs, model)
        for model in models
        if subsets[model.id]
    ]
    cat: dict[str, dict[str, float]] = {}
    for mid, subset in subsets.items():
        if subset:
            cat[mid] = brier_by_category(subset, qs)

    baselines_by_model: dict[str, dict[str, float]] = {}
    c_baselines_by_model: dict[str, dict[str, float | None]] = {}
    coverage: dict[str, ScoreCoverage] = {}
    ordered_ids = [question.id for question in questions]
    for mid in model_ids:
        answered_questions = [q for q in questions if q.id in answered_ids[mid]]
        model_baselines = baseline_scores(answered_questions)
        heuristic = _phase1_heuristic_brier(answered_questions)
        if heuristic is not None:
            model_baselines["phase1_heuristic"] = heuristic
        baselines_by_model[mid] = model_baselines
        c_baselines_by_model[mid] = _baseline_c_index(answered_questions)
        answered = [
            question_id for question_id in ordered_ids if question_id in answered_ids[mid]
        ]
        missing = [
            question_id for question_id in ordered_ids if question_id not in answered_ids[mid]
        ]
        coverage[mid] = ScoreCoverage(
            expected_questions=len(questions),
            answered_questions=len(answered),
            coverage_fraction=(len(answered) / len(questions) if questions else None),
            answered_question_ids=answered,
            missing_question_ids=missing,
            failed_question_ids=None,
            failure_history_available=False,
        )

    bases = baseline_scores(questions)
    heuristic = _phase1_heuristic_brier(questions)
    if heuristic is not None:
        bases["phase1_heuristic"] = heuristic
    beating = [
        mid
        for mid, score in by_model.items()
        if score is not None
        and score < baselines_by_model[mid].get("always_base_rate", float("-inf"))
    ]
    beating_prior = [
        mid
        for mid, score in by_model.items()
        if score is not None
        and score < baselines_by_model[mid].get("prior_signal", float("-inf"))
    ]
    c_by_model: dict[str, float | None] = {}
    c_pairs: dict[str, int] = {}
    for mid, subset in subsets.items():
        c_value, pair_count = concordance_index(subset, qs)
        c_by_model[mid] = None if c_value is None else round(c_value, 6)
        c_pairs[mid] = pair_count
    c_baselines = _baseline_c_index(questions)

    active_sets = [ids for ids in answered_ids.values() if ids]
    matched_ids = set.intersection(*active_sets) if active_sets else set()
    ordered_matched_ids = [question_id for question_id in ordered_ids if question_id in matched_ids]
    matched_brier: dict[str, float | None] = {}
    matched_c: dict[str, float | None] = {}
    matched_pairs: dict[str, int] = {}
    for mid, subset in subsets.items():
        matched_subset = [p for p in subset if p.question_id in matched_ids]
        matched_brier[mid] = brier(matched_subset, qs) if matched_subset else None
        c_value, pair_count = concordance_index(matched_subset, qs)
        matched_c[mid] = None if c_value is None else round(c_value, 6)
        matched_pairs[mid] = pair_count

    return ScoreReport(
        run_id=run_id,
        n_predictions=len(preds),
        question_count=len(questions),
        brier_by_model=by_model,
        brier_index_by_model={
            key: (None if value is None else brier_index(value))
            for key, value in by_model.items()
        },
        brier_by_category=cat,
        baselines=bases,
        baselines_by_model=baselines_by_model,
        models_beating_base_rate=beating,
        models_beating_prior_signal=beating_prior,
        coverage_by_model=coverage,
        matched_question_ids=ordered_matched_ids,
        matched_brier_by_model=matched_brier,
        matched_c_index_by_model=matched_c,
        matched_c_index_pairs_by_model=matched_pairs,
        calibration=calib,
        contamination=contam,
        n_flagged=sum(1 for p in preds if p.flagged_for_contamination_review),
        c_index_by_model=c_by_model,
        c_index_pairs_by_model=c_pairs,
        c_index_baselines=c_baselines,
        c_index_baselines_by_model=c_baselines_by_model,
    )


def _validate_scoring_inputs(
    preds: list[Prediction],
    questions: list[Question],
    models: list[ModelConfig],
) -> None:
    question_ids = [question.id for question in questions]
    duplicate_questions = sorted(
        question_id for question_id, count in Counter(question_ids).items() if count > 1
    )
    if duplicate_questions:
        raise ValueError("duplicate question IDs: " + ", ".join(duplicate_questions))
    model_ids = [model.id for model in models]
    duplicate_models = sorted(
        model_id for model_id, count in Counter(model_ids).items() if count > 1
    )
    if duplicate_models:
        raise ValueError("duplicate model IDs: " + ", ".join(duplicate_models))
    known = set(question_ids)
    unknown = sorted({prediction.question_id for prediction in preds} - known)
    if unknown:
        raise ValueError("predictions reference unknown question IDs: " + ", ".join(unknown))
    pairs = [(prediction.model_id, prediction.question_id) for prediction in preds]
    duplicate_pairs = sorted(pair for pair, count in Counter(pairs).items() if count > 1)
    if duplicate_pairs:
        rendered = ", ".join(
            f"{model_id}/{question_id}" for model_id, question_id in duplicate_pairs
        )
        raise ValueError("duplicate model/question predictions: " + rendered)


def _baseline_c_index(questions: list[Question]) -> dict[str, float | None]:
    qs = {q.id: q for q in questions}
    out: dict[str, float | None] = {}
    specs = {
        "always_0.5": lambda q: 0.5,
        "status_quo_persistence": lambda q: 0.0,
        "always_base_rate": lambda q: (
            sum((x.prior_signal.probability if x.prior_signal else 0.5) for x in questions)
            / max(len(questions), 1)
        ),
        "prior_signal": lambda q: q.prior_signal.probability if q.prior_signal else 0.5,
    }
    for name, fn in specs.items():
        preds = as_predictions(questions, "baseline", name, fn)
        c, _n = concordance_index(preds, qs)
        out[name] = None if c is None else round(c, 6)
    return out


def _phase1_heuristic_brier(questions: list[Question]) -> float | None:
    path = resolve(f"data/runs/{PHASE1_HEURISTIC_RUN}/predictions.jsonl")
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        preds = read_jsonl(path, Prediction)
    except Exception:
        return None
    if not preds:
        return None
    mid = preds[0].model_id
    subset = [p for p in preds if p.model_id == mid]
    qs = {q.id: q for q in questions}
    subset = [p for p in subset if p.question_id in qs]
    if not subset:
        return None
    return brier(subset, qs)


def write_plots(report: ScoreReport, dest_dir: str | Path) -> None:
    dest = resolve(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _calibration_plot(report.calibration, dest / "calibration.png")
    _contamination_plot(report.contamination, dest / "contamination.png")


def _calibration_plot(curves: dict[str, CalibrationResult], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], color="#8A6A2E", linewidth=1, linestyle="--", label="perfect")
    for mid, curve in curves.items():
        xs = [b.mean_forecast for b in curve.bins if b.n]
        ys = [b.mean_outcome for b in curve.bins if b.n]
        ax.plot(xs, ys, marker="o", label=mid, color="#A3392C")
    ax.set_xlabel("forecast")
    ax.set_ylabel("outcome rate")
    ax.set_title("calibration")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _contamination_plot(curves: list[ContaminationResult], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for curve in curves:
        xs = [(b.gap_lo_days + b.gap_hi_days) / 2 for b in curve.buckets if b.n]
        ys = [b.mean_brier for b in curve.buckets if b.n]
        ax.plot(xs, ys, marker="o", label=curve.model_id)
    ax.axvline(0, color="#A3392C", linewidth=1)
    ax.set_xlabel("gap_days (resolution − pretraining cutoff)")
    ax.set_ylabel("mean Brier")
    ax.set_title("contamination curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
