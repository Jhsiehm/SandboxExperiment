"""ForecastBench-compatible binary Brier: (f - o)^2. Lower is better."""

from __future__ import annotations

import math

from psbx.schemas import Prediction, Question


def brier_one(probability: float, outcome: bool) -> float:
    return (probability - (1.0 if outcome else 0.0)) ** 2


def brier(preds: list[Prediction], qs: dict[str, Question]) -> float:
    if not preds:
        raise ValueError("no predictions")
    return sum(brier_one(p.probability, qs[p.question_id].ground_truth) for p in preds) / len(preds)


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
