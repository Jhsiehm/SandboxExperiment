from datetime import date, datetime, timezone

import numpy as np
import pytest

from psbx.config import load_epochs
from psbx.corpus.aggregate_sources import ingest_aggregate_sources
from psbx.corpus.fetch_wikipedia import ingest_wikipedia
from psbx.corpus.index import HybridIndex
from psbx.corpus.seed_documents import seed_documents
from psbx.sandbox.citations import validate_citations
from psbx.sandbox.client import (
    EvidencePolicySearchClient,
    EvidencePolicyViolation,
    LocalSearchClient,
)
from psbx.sandbox.harness import search_client_for
from psbx.schemas import Citation, Document, Prediction, RunConfig

UTC = timezone.utc


def _document(document_id: str, *, authenticated: bool = False) -> Document:
    fields = {}
    if authenticated:
        fields = {
            "authenticity": "authenticated_capture",
            "timestamp_basis": "archive_capture",
            "captured_at": datetime(2012, 6, 1, tzinfo=UTC),
            "source_reference": "https://web.archive.org/web/20120601000000id_/https://example.com",
            "capture_verified": True,
        }
    return Document(
        id=document_id,
        url=f"https://example.com/{document_id}",
        outlet="Example",
        published_at=datetime(2012, 6, 1, tzinfo=UTC),
        title=f"Evidence {document_id}",
        text=f"Literal text for {document_id} about a historical question.",
        source_type="news",
        **fields,
    )


def _index(*documents: Document) -> HybridIndex:
    return HybridIndex(
        list(documents),
        np.zeros((len(documents), 256), dtype=np.float32),
        date(2012, 6, 30),
    )


def test_legacy_document_defaults_to_unverified_and_hashes_exact_text():
    document = _document("legacy")
    assert document.authenticity == "unverified"
    assert document.timestamp_basis == "unknown"
    assert not document.research_eligible
    assert len(document.content_sha256 or "") == 64

    with pytest.raises(ValueError, match="content_sha256 does not match"):
        Document(
            id="bad",
            url="https://example.com/bad",
            outlet="Example",
            published_at=datetime(2012, 6, 1, tzinfo=UTC),
            title="Bad hash",
            text="The content does not match the claimed hash.",
            source_type="news",
            content_sha256="0" * 64,
        )


def test_authenticated_capture_requires_complete_capture_chain():
    with pytest.raises(ValueError, match="authenticated_capture requires"):
        Document(
            id="claimed",
            url="https://example.com/old",
            outlet="Example",
            published_at=datetime(2012, 1, 1, tzinfo=UTC),
            title="Old-looking URL and date",
            text="An old-looking timestamp and URL do not authenticate this text.",
            source_type="news",
            authenticity="authenticated_capture",
        )
    assert _document("captured", authenticated=True).research_eligible


def test_offline_seed_and_summary_fixtures_are_explicit_reconstructions():
    epoch = load_epochs()["e2012"]
    documents = [
        *seed_documents(),
        *ingest_wikipedia(epoch),
        *ingest_aggregate_sources(epoch),
    ]
    assert documents
    assert {document.authenticity for document in documents} == {
        "reconstructed_fixture"
    }
    assert all(not document.research_eligible for document in documents)


def test_research_policy_filters_search_and_refuses_unverified_fetch():
    unverified = _document("unverified")
    authenticated = _document("authenticated", authenticated=True)
    policy = EvidencePolicySearchClient(
        LocalSearchClient(_index(unverified, authenticated)), "research"
    )
    hits = policy.search("historical question", k=10)
    assert [hit.document_id for hit in hits] == ["authenticated"]
    assert hits[0].authenticity == "authenticated_capture"
    with pytest.raises(EvidencePolicyViolation, match="not eligible"):
        policy.fetch("unverified")
    assert policy.fetch("authenticated")["content_sha256"] == authenticated.content_sha256


def test_research_run_fails_before_search_when_corpus_has_no_eligible_evidence():
    run = RunConfig(
        run_id="research-without-authenticated-evidence",
        epoch="e2012",
        models=["fixture"],
        question_set="unused.jsonl",
        evidence_use="research",
    )
    with pytest.raises(RuntimeError, match="no authenticated"):
        search_client_for(run, _index(_document("unverified")))


def test_citation_check_is_document_and_quotation_verification_only():
    document = _document("citation")
    prediction = Prediction(
        run_id="run",
        question_id="q",
        model_id="m",
        probability=0.5,
        reasoning="The supports label is the forecaster's assertion.",
        citations=[
            Citation(
                document_id=document.id,
                quoted_span="Literal text",
                supports="yes",
            )
        ],
    )
    practice = validate_citations(prediction, _index(document))
    assert not practice.citation_verification_failed
    assert not practice.flagged_for_contamination_review

    research = validate_citations(
        prediction,
        _index(document),
        evidence_use="research",
    )
    assert research.citation_verification_failed
    assert research.citation_verification_reasons == [
        "research_ineligible_document:citation"
    ]
    assert not research.flagged_for_contamination_review
    assert research.flag_reasons == []
