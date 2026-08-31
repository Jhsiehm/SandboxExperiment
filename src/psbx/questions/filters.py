from __future__ import annotations

import re
from collections.abc import Iterable

import numpy as np

from psbx.corpus.embed import embed_texts
from psbx.schemas import Question

PRIOR_LO = 0.15
PRIOR_HI = 0.85
DUP_COSINE = 0.95
AMBIGUOUS = re.compile(
    r"\b(maybe|unclear| somehow|tbd|to be determined|various|etc\.?)\b",
    re.IGNORECASE,
)
HINDSIGHT = re.compile(r"\b(did|was|were|had already)\b", re.IGNORECASE)


def filter_questions(
    qs: Iterable[Question],
    *,
    resolution_window_end=None,
    category_balance: dict[str, int] | None = None,
) -> list[Question]:
    """Drop non-discriminative, unresolvable, hindsight, or near-duplicate items."""
    kept: list[Question] = []
    for q in qs:
        if q.prior_signal is None:
            continue
        if not PRIOR_LO <= q.prior_signal.probability <= PRIOR_HI:
            continue
        if resolution_window_end is not None and q.resolution_date > resolution_window_end:
            continue
        if AMBIGUOUS.search(q.resolution_criteria):
            continue
        if HINDSIGHT.search(q.text) and not q.text.lower().startswith("will "):
            continue
        if not q.text.lower().startswith("will "):
            continue
        kept.append(q)
    kept = _drop_near_duplicates(kept)
    if category_balance:
        kept = _balance(kept, category_balance)
    return kept


def _drop_near_duplicates(qs: list[Question]) -> list[Question]:
    if len(qs) < 2:
        return qs
    mat = embed_texts([q.text for q in qs], backend="hashing")
    drop: set[int] = set()
    nums = [set(re.findall(r"\d+", q.text)) for q in qs]
    for i in range(len(qs)):
        if i in drop:
            continue
        for j in range(i + 1, len(qs)):
            if j in drop:
                continue
            # Different dates/thresholds are distinct questions, not paraphrases.
            if nums[i] != nums[j]:
                continue
            if float(mat[i] @ mat[j]) > DUP_COSINE:
                drop.add(j)
    return [q for i, q in enumerate(qs) if i not in drop]


def _balance(qs: list[Question], targets: dict[str, int]) -> list[Question]:
    buckets: dict[str, list[Question]] = {}
    for q in qs:
        buckets.setdefault(q.category, []).append(q)
    out: list[Question] = []
    for cat, n in targets.items():
        out.extend(buckets.get(cat, [])[:n])
    return out
