"""Agenda-setting check: reach-weighted corpus topics vs next-month Gallup MIP."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.stats import spearmanr

from psbx.corpus.index import HybridIndex
from psbx.io import read_json
from psbx.schemas import Document

TOPIC_CUES = {
    "economy_plus_unemployment": (
        "unemployment",
        "payroll",
        "jobs",
        "labor force",
        "inflation",
        "cpi",
        "housing starts",
        "treasury",
        "recovery",
    ),
    "deficit": ("sequestration", "fiscal", "deficit", "debt", "tax rates", "budget"),
    "war_terrorism": ("syria", "assad", "iran", "nuclear", "mali", "north korea", "ceasefire"),
    "healthcare": ("fda", "vawa", "health care", "medicaid"),
    "immigration": ("immigration", "dream"),
}


def topic_mass(docs: list[Document]) -> dict[str, float]:
    scores = defaultdict(float)
    for doc in docs:
        blob = f"{doc.title} {doc.text}".lower()
        for topic, cues in TOPIC_CUES.items():
            if any(c in blob for c in cues):
                scores[topic] += doc.prominence
    total = sum(scores.values()) or 1.0
    return {k: v / total for k, v in scores.items()}


def monthly_topic_share(index: HybridIndex) -> dict[str, dict[str, float]]:
    by_month: dict[str, list[Document]] = defaultdict(list)
    for doc in index.docs:
        key = doc.published_at.strftime("%Y-%m")
        by_month[key].append(doc)
    return {month: topic_mass(docs) for month, docs in sorted(by_month.items())}


def correlate_gallup(index: HybridIndex, gallup_path: str = "data/sources/gallup_mip_2012.json") -> dict:
    gallup = read_json(gallup_path)
    shares = monthly_topic_share(index)
    pairs_by_topic: dict[str, list[tuple[float, float]]] = defaultdict(list)
    points = gallup["points"]
    by_month = {row["month"]: row for row in points}
    months = sorted(by_month)
    for i, month in enumerate(months[:-1]):
        nxt = months[i + 1]
        if month not in shares:
            continue
        for topic in TOPIC_CUES:
            if topic not in by_month[nxt]:
                continue
            pairs_by_topic[topic].append((shares[month].get(topic, 0.0), float(by_month[nxt][topic])))
    out: dict[str, dict[str, float]] = {}
    for topic, pairs in pairs_by_topic.items():
        if len(pairs) < 3:
            continue
        x = np.array([a for a, _ in pairs])
        y = np.array([b for _, b in pairs])
        rho, p = spearmanr(x, y)
        out[topic] = {
            "spearman_rho": None if np.isnan(rho) else float(rho),
            "p_value": None if np.isnan(p) else float(p),
            "n": len(pairs),
        }
    return out
