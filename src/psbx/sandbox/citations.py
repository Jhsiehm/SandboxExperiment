from __future__ import annotations

from psbx.corpus.index import HybridIndex
from psbx.schemas import Citation, EvidenceUse, Prediction


def validate_citations(
    pred: Prediction,
    index: HybridIndex,
    *,
    evidence_use: EvidenceUse | str = "practice",
) -> Prediction:
    """Verify document identity and literal quotation, never semantic entailment."""
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
        if evidence_use == "research" and not doc.research_eligible:
            reasons.append(f"research_ineligible_document:{cite.document_id}")
    flagged = bool(reasons)
    return pred.model_copy(
        update={
            "citation_verification_failed": flagged,
            "citation_verification_reasons": reasons,
        }
    )


def citation_ok(cite: Citation, index: HybridIndex) -> bool:
    try:
        doc = index.get(cite.document_id)
    except KeyError:
        return False
    return cite.quoted_span in doc.text
