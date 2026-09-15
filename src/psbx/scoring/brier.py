"""ForecastBench-compatible binary Brier: (f - o)^2. Lower is better."""

from __future__ import annotations

import math

from psbx.schemas import Prediction, Question


def brier_one(probability: float, outcome: bool) -> float:
    return (probability - (1.0 if outcome else 0.0)) ** 2


def brier(preds: list[Prediction], qs: dict[str, Question]) -> float:
    if not preds:
        raise ValueError("no predictions")
    _validate_prediction_keys(preds, qs)
    return sum(brier_one(p.probability, qs[p.question_id].ground_truth) for p in preds) / len(preds)


def _validate_prediction_keys(
    preds: list[Prediction], qs: dict[str, Question]
) -> None:
    unknown = sorted({prediction.question_id for prediction in preds} - set(qs))
    if unknown:
        raise ValueError("predictions reference unknown question IDs: " + ", ".join(unknown))
    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for prediction in preds:
        key = (prediction.model_id, prediction.question_id)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        rendered = ", ".join(
            f"{model_id}/{question_id}" for model_id, question_id in sorted(duplicates)
        )
        raise ValueError("duplicate model/question predictions: " + rendered)


def brier_index(score: float) -> float:
    """(1 - sqrt(Brier)) * 100. ForecastBench secondary scale."""
    return (1.0 - math.sqrt(score)) * 100.0


def brier_by_category(
    preds: list[Prediction], qs: dict[str, Question]
) -> dict[str, float]:
    buckets: dict[str, list[Prediction]] = {}
    for p in preds:
        buckets.setdefault(qs[p.question_id].category, []).append(p)
    return {cat: brier(items, qs) for cat, items in buckets.items()}


def brier_by_model(
    preds: list[Prediction], qs: dict[str, Question]
) -> dict[str, float]:
    buckets: dict[str, list[Prediction]] = {}
    for p in preds:
        buckets.setdefault(p.model_id, []).append(p)
    return {mid: brier(items, qs) for mid, items in buckets.items()}
