from __future__ import annotations

from psbx.schemas import Prediction, Question
from psbx.scoring.brier import brier_one


def baseline_scores(qs: list[Question]) -> dict[str, float]:
    """Baselines computed on the question set (no model required)."""
    if not qs:
        return {}
    n = len(qs)
    always_half = sum(brier_one(0.5, q.ground_truth) for q in qs) / n
    status_quo = sum(brier_one(0.0, q.ground_truth) for q in qs) / n
    priors = [q.prior_signal.probability if q.prior_signal else 0.5 for q in qs]
    mean_prior = sum(priors) / n
    always_base_rate = sum(brier_one(mean_prior, q.ground_truth) for q in qs) / n
    per_question_prior = sum(brier_one(p, q.ground_truth) for p, q in zip(priors, qs)) / n
    return {
        "always_0.5": always_half,
        "status_quo_persistence": status_quo,
        "always_base_rate": always_base_rate,
        "prior_signal": per_question_prior,
    }


def as_predictions(qs: list[Question], run_id: str, name: str, probability_fn) -> list[Prediction]:
    dummy_cite = {
        "document_id": "baseline",
        "quoted_span": "baseline does not retrieve",
        "supports": "context",
    }
    preds: list[Prediction] = []
    for q in qs:
        preds.append(
            Prediction(
                run_id=run_id,
                question_id=q.id,
                model_id=name,
                probability=float(probability_fn(q)),
                reasoning=name,
                citations=[dummy_cite],
            )
        )
    return preds
