"""Historical human-baseline eval: media-stimulus track + demographic swarm track."""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from psbx.config import load_epochs, load_yaml
from psbx.eval.stimulus import items_from_questions
from psbx.io import read_jsonl, write_json
from psbx.paths import resolve
from psbx.schemas import (
    HumanBaselineReport,
    Prediction,
    Question,
    SwarmVote,
    TrackScore,
)
from psbx.scoring.agenda import correlate_gallup
from psbx.scoring.brier import brier, brier_by_model
from psbx.scoring.report import score_run
from psbx.society.perspectives import load_perspectives


def load_eval_config(path: str | Path = "config/eval-baseline.yaml") -> dict[str, Any]:
    return load_yaml(path)


def mae_vs_prior_signal(preds: list[Prediction], questions: list[Question]) -> float | None:
    by_id = {q.id: q for q in questions}
    errors: list[float] = []
    for pred in preds:
        question = by_id.get(pred.question_id)
        if question is None or question.prior_signal is None:
            continue
        errors.append(abs(pred.probability - question.prior_signal.probability))
    if not errors:
        return None
    return float(sum(errors) / len(errors))


def vote_spread(votes: list[SwarmVote]) -> float | None:
    if len(votes) < 2:
        return None
    by_q: dict[str, list[float]] = defaultdict(list)
    for vote in votes:
        by_q[vote.question_id].append(vote.probability)
    spreads = [statistics.pstdev(ps) for ps in by_q.values() if len(ps) >= 2]
    if not spreads:
        return None
    return float(sum(spreads) / len(spreads))


def evaluate_human_baseline(
    run_id: str,
    *,
    eval_config: str | Path = "config/eval-baseline.yaml",
    predictions: list[Prediction] | None = None,
    questions: list[Question] | None = None,
    votes: list[SwarmVote] | None = None,
) -> HumanBaselineReport:
    """Score closeness to historical human/public response on both tracks."""
    cfg = load_eval_config(eval_config)
    epoch_id = str(cfg.get("epoch") or "e2012")
    qpath = str(cfg.get("question_set") or "data/questions/e2012.jsonl")
    qs = questions if questions is not None else read_jsonl(qpath, Question)
    items = items_from_questions(qs, epoch_id=epoch_id)
    pred_path = resolve(f"data/runs/{run_id}/predictions.jsonl")
    preds = predictions
    if preds is None and pred_path.exists() and pred_path.stat().st_size > 0:
        preds = read_jsonl(pred_path, Prediction)
    preds = preds or []
    vote_path = resolve(f"data/runs/{run_id}/swarm_votes.jsonl")
    loaded_votes = votes
    if loaded_votes is None and vote_path.exists() and vote_path.stat().st_size > 0:
        loaded_votes = read_jsonl(vote_path, SwarmVote)
    loaded_votes = loaded_votes or []

    qs_map = {q.id: q for q in qs}
    item_ids = {item.question_id for item in items}
    track_preds = [p for p in preds if p.question_id in item_ids]
    brier_later = brier(track_preds, qs_map) if track_preds else None
    mae_prior = mae_vs_prior_signal(track_preds, qs) if track_preds else None
    spread = vote_spread(loaded_votes)

    catalog = load_perspectives(str(cfg.get("perspectives") or "config/perspectives.yaml"))
    n_assigned = len(catalog.assigned(12)) if catalog.personas else 0

    tracks = {
        "A_media_stimulus": TrackScore(
            track_id="A",
            label="media stimulus → predicted public response vs later history",
            n=len(track_preds),
            brier_vs_later_outcomes=brier_later,
            mae_vs_prior_signal=mae_prior,
            note=(
                "Headlines/outlets with published_at ≤ cutoff are the stimulus. "
                "Brier vs e2012 ground_truth; MAE vs contemporaneous prior_signal "
                "(human/analyst thinking at cutoff). Lower is closer."
            ),
        ),
        "B_demographic_swarm": TrackScore(
            track_id="B",
            label="survey/ad/academic-conditioned demographic swarm",
            n=len(loaded_votes),
            brier_vs_later_outcomes=brier_later,
            mae_vs_prior_signal=mae_prior,
            vote_spread=spread,
            note=(
                f"{n_assigned} slotted simulation personas; "
                f"{len(catalog.catalog_only())} catalog-only extras. "
                "Same media pack; conditioners are survey/ad/academic. "
                "Vote spread is necessary but not sufficient for demographic fidelity. "
                "Do not infer protected class into scoring."
            ),
        ),
    }
    by_model = brier_by_model(track_preds, qs_map) if track_preds else {}
    note = (
        "Phase 1 human-baseline eval. Track A uses time-locked media as stimulus. "
        "Track B is the demographic swarm conditioned on surveys/ads/studies. "
        "They share the frozen corpus and scoring. PolicySim is later. "
        "Closeness to historical human/public response is the metric, not impressiveness."
    )
    return HumanBaselineReport(
        run_id=run_id,
        epoch_id=epoch_id,
        n_questions=len(qs),
        tracks=tracks,
        brier_by_model=by_model,
        note=note,
    )


def write_human_baseline(
    report: HumanBaselineReport,
    run_id: str | None = None,
) -> Path:
    dest = resolve(f"data/runs/{run_id or report.run_id}/human_baseline.json")
    write_json(dest, report)
    return dest


def optional_gallup_agenda(epoch_id: str = "e2012") -> dict[str, Any] | None:
    """Existing next-month Gallup MIP check. Eval only; not agent search."""
    try:
        from psbx.corpus.index import load_index

        epoch = load_epochs()[epoch_id]
        index = load_index(epoch)
        return correlate_gallup(index)
    except Exception:
        return None


def score_and_baseline(
    run_id: str,
    questions: list[Question],
    preds: list[Prediction],
    models: list,
):
    """Convenience: ForecastBench score_run plus human-baseline tracks."""
    scored = score_run(preds, questions, models, run_id)
    baseline = evaluate_human_baseline(
        run_id, predictions=preds, questions=questions
    )
    return scored, baseline
