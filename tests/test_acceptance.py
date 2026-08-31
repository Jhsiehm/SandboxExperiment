import os

from typer.testing import CliRunner

from psbx.cli import app
from psbx.config import load_epochs, load_models, load_run
from psbx.corpus.index import load_index
from psbx.io import read_json, read_jsonl
from psbx.sandbox.citations import validate_citations
from psbx.sandbox.harness import run_set
from psbx.schemas import Prediction, Question

runner = CliRunner()


def test_phase1_cli_and_citations(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    result = runner.invoke(app, ["questions", "build", "--epoch", "e2012", "--limit", "50"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["corpus", "build", "--epoch", "e2012"])
    assert result.exit_code == 0, result.output
    epoch = load_epochs()["e2012"]
    index = load_index(epoch)
    assert index.docs
    for doc in index.docs:
        assert doc.published_at.date() <= epoch.cutoff_date

    qs = read_jsonl("data/questions/e2012.jsonl", Question)
    assert len(qs) == 50
    run = load_run()
    models = [load_models()[mid] for mid in run.models]
    os.environ["PSBX_MOCK_LLM"] = "1"
    preds = run_set(qs, models, epoch, run)
    assert len(preds) == 50 * len(models)
    for pred in preds:
        checked = validate_citations(pred, index)
        assert checked.citations
        assert not checked.flagged_for_contamination_review, checked.flag_reasons

    from psbx.io import write_jsonl
    from psbx.paths import resolve
    from psbx.scoring.report import score_run, write_plots

    write_jsonl(resolve(f"data/runs/{run.run_id}/predictions.jsonl"), preds)
    report = score_run(preds, qs, models, run.run_id)
    write_plots(report, f"data/runs/{run.run_id}")
    from psbx.io import write_json

    write_json(f"data/runs/{run.run_id}/results.json", report)
    assert report.n_predictions == len(preds)
    assert report.brier_by_model
    assert report.contamination
    payload = read_json(f"data/runs/{run.run_id}/results.json")
    assert payload["run_id"] == run.run_id
