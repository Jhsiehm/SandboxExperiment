from __future__ import annotations

from dataclasses import dataclass, field

from psbx.config import load_sources
from psbx.schemas import Document


@dataclass
class ProminenceContext:
    outlet_weights: dict[str, float] = field(default_factory=dict)
    front_page_minutes: dict[str, float] = field(default_factory=dict)
    gdelt_mention_count: dict[str, int] = field(default_factory=dict)
    mix: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls) -> ProminenceContext:
        src = load_sources()
        weights = {row["name"]: float(row["outlet_weight"]) for row in src["outlets"]}
        weights.update({row["domain"]: float(row["outlet_weight"]) for row in src["outlets"]})
        return cls(outlet_weights=weights, mix=dict(src["prominence_weights"]))


def score_prominence(doc: Document, ctx: ProminenceContext) -> float:
    """Weighted combination, normalized to 0..1.

    Do not use raw document count as a reach proxy. Wire copy inflates it,
    and broadcast segments with huge audiences leave almost no text footprint.
    """
    outlet_w = ctx.outlet_weights.get(doc.outlet, 0.15)
    fp = ctx.front_page_minutes.get(doc.url, doc.front_page_minutes)
    synd = float(doc.syndication_count)
    gdelt = float(ctx.gdelt_mention_count.get(doc.id, doc.gdelt_mention_count))
    mix = ctx.mix or {
        "outlet_weight": 0.4,
        "front_page_minutes": 0.2,
        "syndication_count": 0.2,
        "gdelt_mention_count": 0.2,
    }

    def squash(x: float, cap: float) -> float:
        return min(1.0, x / cap)

    score = (
        mix["outlet_weight"] * min(1.0, outlet_w)
        + mix["front_page_minutes"] * squash(fp, 300.0)
        + mix["syndication_count"] * squash(synd, 60.0)
        + mix["gdelt_mention_count"] * squash(gdelt, 300.0)
    )
    return float(min(1.0, max(0.0, score)))


def apply_prominence(docs: list[Document], ctx: ProminenceContext | None = None) -> list[Document]:
    ctx = ctx or ProminenceContext.from_config()
    return [doc.model_copy(update={"prominence": score_prominence(doc, ctx)}) for doc in docs]
