from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psbx.io import read_jsonl
from psbx.paths import resolve
from psbx.schemas import CalibrationResult, ContaminationResult, ModelConfig, Prediction, Question, ScoreReport
from psbx.scoring.baselines import baseline_scores
from psbx.scoring.brier import brier, brier_by_category, brier_by_model, brier_index
from psbx.scoring.calibration import calibration_curve
from psbx.scoring.contamination import contamination_curve

PHASE1_HEURISTIC_RUN = "phase1-e2012-smoke"


def score_run(
    preds: list[Prediction],
    questions: list[Question],
    models: list[ModelConfig],
    run_id: str,
) -> ScoreReport:
    qs = {q.id: q for q in questions}
    by_model = brier_by_model(preds, qs)
    calib = {}
    contam = []
    for model in models:
        subset = [p for p in preds if p.model_id == model.id]
        if not subset:
            continue
        calib[model.id] = calibration_curve(subset, qs)
        contam.append(contamination_curve(subset, qs, model))
    cat: dict[str, dict[str, float]] = {}
    for model in models:
        subset = [p for p in preds if p.model_id == model.id]
        if subset:
            cat[model.id] = brier_by_category(subset, qs)
    bases = baseline_scores(questions)
    heuristic = _phase1_heuristic_brier(questions)
    if heuristic is not None:
        bases["phase1_heuristic"] = heuristic
    base = bases.get("always_base_rate", 0.25)
    prior = bases.get("prior_signal", 0.25)
    beating = [mid for mid, score in by_model.items() if score < base]
    beating_prior = [mid for mid, score in by_model.items() if score < prior]
    return ScoreReport(
        run_id=run_id,
        n_predictions=len(preds),
        brier_by_model=by_model,
        brier_index_by_model={k: brier_index(v) for k, v in by_model.items()},
        brier_by_category=cat,
        baselines=bases,
        models_beating_base_rate=beating,
        models_beating_prior_signal=beating_prior,
        calibration=calib,
        contamination=contam,
        n_flagged=sum(1 for p in preds if p.flagged_for_contamination_review),
    )


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
