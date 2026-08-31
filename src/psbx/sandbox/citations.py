from __future__ import annotations

from psbx.corpus.index import HybridIndex
from psbx.schemas import Citation, Prediction


def validate_citations(pred: Prediction, index: HybridIndex) -> Prediction:
    reasons: list[str] = []
    if not pred.citations:
        reasons.append("empty_citations")
    for cite in pred.citations:
        try:
            doc = index.get(cite.document_id)
        except KeyError:
            reasons.append(f"unknown_document:{cite.document_id}")
            continue
        if cite.quoted_span not in doc.text:
            reasons.append(f"span_not_verbatim:{cite.document_id}")
    flagged = bool(reasons)
    return pred.model_copy(
        update={
            "flagged_for_contamination_review": flagged,
            "flag_reasons": reasons,
        }
    )


def citation_ok(cite: Citation, index: HybridIndex) -> bool:
    try:
        doc = index.get(cite.document_id)
    except KeyError:
        return False
    return cite.quoted_span in doc.text
