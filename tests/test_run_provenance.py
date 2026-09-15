from datetime import date, datetime, timezone

import numpy as np
import pytest

from psbx.corpus.index import HybridIndex
from psbx.paths import run_dir
from psbx.run_provenance import RunProvenanceMismatch, ensure_run_provenance
from psbx.schemas import Document, Epoch, Question, RunConfig


def _contract():
    epoch = Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2013, 6, 30),
        corpus_index_path="data/corpus/e2012",
    )
    document = Document(
        id="doc-1",
        url="https://example.com/2012",
        outlet="Example",
        published_at=datetime(2012, 6, 1, tzinfo=timezone.utc),
        title="Contemporaneous evidence",
        text="Evidence available before the frozen cutoff.",
        source_type="news",
    )
    question = Question(
        id="question-1",
        epoch_id="e2012",
        category="economic",
        text="Will the event happen?",
        resolution_criteria="Resolves from the later published outcome.",
        cutoff_date=date(2012, 6, 30),
        resolution_date=date(2012, 7, 31),
        ground_truth=True,
        generator="test",
    )
    index = HybridIndex([document], np.zeros((1, 8), dtype=np.float32), epoch.cutoff_date)
    run = RunConfig(
        run_id="sealed-test",
        epoch="e2012",
        models=["gpt-oss-2012ish"],
        question_set="data/questions/e2012.jsonl",
        sandbox_mode="container",
    )
    return run, epoch, index, [question]


def test_isolated_resume_requires_matching_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_ROOT", str(tmp_path))
    run, epoch, index, questions = _contract()
    output = run_dir(run.run_id) / "predictions.jsonl"

    provenance = ensure_run_provenance(run, epoch, index, questions, [output])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("saved output\n", encoding="utf-8")
    assert ensure_run_provenance(run, epoch, index, questions, [output]) == provenance

    changed = run.model_copy(update={"source_type": "news"})
    with pytest.raises(RunProvenanceMismatch, match="different config"):
        ensure_run_provenance(changed, epoch, index, questions, [output])


def test_isolated_resume_rejects_legacy_outputs_without_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_ROOT", str(tmp_path))
    run, epoch, index, questions = _contract()
    output = run_dir(run.run_id) / "predictions.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("legacy output\n", encoding="utf-8")

    with pytest.raises(RunProvenanceMismatch, match="without provenance"):
        ensure_run_provenance(run, epoch, index, questions, [output])


def test_run_paths_reject_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="run_id"):
        run_dir("../../outside")
    with pytest.raises(ValueError, match="run_id"):
        RunConfig(
            run_id="../outside",
            epoch="e2012",
            models=["gpt-oss-2012ish"],
            question_set="data/questions/e2012.jsonl",
        )
