from datetime import datetime, timezone

import numpy as np
import pytest

from psbx.config import load_epochs
from psbx.corpus.build_index import build_index, collect_documents
from psbx.corpus.index import HybridIndex
from psbx.schemas import Document


def test_every_seed_document_respects_cutoff():
    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    assert docs
    for doc in docs:
        assert doc.published_at.date() <= epoch.cutoff_date


def test_index_rejects_future_document():
    epoch = load_epochs()["e2012"]
    future = Document(
        id="future",
        url="https://example.com/future",
        outlet="Reuters",
        published_at=datetime(2012, 7, 1, tzinfo=timezone.utc),
        title="after cutoff",
        text="this document is from July 2012 and must not enter the index",
        source_type="wire",
        prominence=0.1,
    )
    with pytest.raises(AssertionError):
        HybridIndex([future], np.zeros((1, 8), dtype=np.float32), epoch.cutoff_date)


def test_build_index_roundtrip(tmp_path, monkeypatch):
    epoch = load_epochs()["e2012"]
    monkeypatch.setattr(epoch, "corpus_index_path", str(tmp_path / "idx"))
    index = build_index(epoch)
    hits = index.search("unemployment rate May", k=5)
    assert hits
    for hit in hits:
        assert hit.published_at.date() <= epoch.cutoff_date
