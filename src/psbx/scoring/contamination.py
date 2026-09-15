"""Descriptive performance versus distance from declared cutoff metadata.

gap_days = resolution_date - declared_pretraining_cutoff

  gap > 0  event resolves after the model's declared cutoff date
  gap < 0  event resolves before the model's declared cutoff date

These observational buckets do not identify training membership, retrieval use,
leakage, or causal effects. Declared cutoff dates are model metadata, not audited
boundaries. The diagnostic may motivate a controlled follow-up experiment only.
"""

from __future__ import annotations

from psbx.schemas import (
    ContaminationBucket,
    ContaminationResult,
    ModelConfig,
    Prediction,
    Question,
)
from psbx.scoring.brier import brier_one

DEFAULT_EDGES = (-8000, -4000, -2000, -365, 0, 365, 2000, 5000)


def _gap_days(question: Question, model: ModelConfig) -> int:
    return (question.resolution_date - model.declared_pretraining_cutoff).days


def contamination_curve(
    preds: list[Prediction],
    qs: dict[str, Question],
    model: ModelConfig,
    edges: tuple[int, ...] = DEFAULT_EDGES,
) -> ContaminationResult:
    rows = [(p, _gap_days(qs[p.question_id], model)) for p in preds if p.model_id == model.id]
    buckets: list[ContaminationBucket] = []
    for lo, hi in zip(edges, edges[1:]):
        group = [p for p, g in rows if lo <= g < hi]
        buckets.append(_summarize(group, qs, lo, hi))
    pre = [p for p, g in rows if g < 0]
    post = [p for p, g in rows if g >= 0]
    pre_b = _mean_brier(pre, qs) if pre else None
    post_b = _mean_brier(post, qs) if post else None
    delta = None
    if pre_b is not None and post_b is not None:
        # Positive delta is a descriptive difference, not a contamination estimate.
        delta = post_b - pre_b
    return ContaminationResult(
        model_id=model.id,
        declared_pretraining_cutoff=model.declared_pretraining_cutoff,
        buckets=buckets,
        pre_cutoff_mean_brier=pre_b,
        post_cutoff_mean_brier=post_b,
        contamination_delta=delta,
    )


def _mean_brier(preds: list[Prediction], qs: dict[str, Question]) -> float:
    return sum(brier_one(p.probability, qs[p.question_id].ground_truth) for p in preds) / len(preds)


def _summarize(
    group: list[Prediction], qs: dict[str, Question], lo: int, hi: int
) -> ContaminationBucket:
    if not group:
        return ContaminationBucket(
            gap_lo_days=lo, gap_hi_days=hi, n=0, mean_brier=None, mean_accuracy=None
        )
    b = _mean_brier(group, qs)
    acc = sum(
        1.0 if ((p.probability >= 0.5) == qs[p.question_id].ground_truth) else 0.0 for p in group
    ) / len(group)
    return ContaminationBucket(
        gap_lo_days=lo, gap_hi_days=hi, n=len(group), mean_brier=b, mean_accuracy=acc
    )
