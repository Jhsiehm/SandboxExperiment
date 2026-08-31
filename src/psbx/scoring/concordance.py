"""Harrell concordance (C-index) for ranking-style forecasts.

On the current binary question set this is pairwise AUC: among comparable
pairs (one YES, one NO), how often did the model assign the higher
probability to the event that happened?

0.5 is chance, 1.0 is perfect ranking, 0.0 is inverted. Undefined (None)
when every outcome is the same — there are no comparable pairs.

Brier and C-index answer different questions. A model trained after 2012
can rank outcomes almost perfectly (it remembers *what* happened) while
still posting a mediocre Brier (it is overconfident or poorly calibrated).
That split is why a post-cutoff model is still worth running on e2012.

The same pairwise definition extends to sequential / time-to-event items:
a pair is comparable when event times differ, and the predicted score
should order them the same way. Wire that in when the question set grows
beyond binary will-by items.
"""

from __future__ import annotations

from psbx.schemas import Prediction, Question


def concordance_index(preds: list[Prediction], qs: dict[str, Question]) -> tuple[float | None, int]:
    """Return (C-index, n_comparable_pairs). Ties count as 0.5."""
    scored: list[tuple[float, bool]] = []
    for p in preds:
        q = qs.get(p.question_id)
        if q is None:
            continue
        scored.append((p.probability, bool(q.ground_truth)))
    yes = [s for s, y in scored if y]
    no = [s for s, y in scored if not y]
    if not yes or not no:
        return None, 0
    concordant = 0.0
    n = 0
    for yi in yes:
        for nj in no:
            n += 1
            if yi > nj:
                concordant += 1.0
            elif yi == nj:
                concordant += 0.5
    return concordant / n, n


def concordance_by_model(
    preds: list[Prediction], qs: dict[str, Question]
) -> tuple[dict[str, float | None], dict[str, int]]:
    buckets: dict[str, list[Prediction]] = {}
    for p in preds:
        buckets.setdefault(p.model_id, []).append(p)
    scores: dict[str, float | None] = {}
    pairs: dict[str, int] = {}
    for mid, items in buckets.items():
        c, n = concordance_index(items, qs)
        scores[mid] = None if c is None else round(c, 6)
        pairs[mid] = n
    return scores, pairs
