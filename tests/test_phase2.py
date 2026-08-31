import os
from datetime import date

from typer.testing import CliRunner

from psbx.agents.runner import execute_tool, parse_prediction_json, skip_reason
from psbx.cli import app
from psbx.config import load_run
from psbx.io import write_jsonl
from psbx.paths import resolve
from psbx.sandbox.harness import run_set
from psbx.schemas import Citation, ModelConfig, Prediction, Question
from psbx.scoring.report import score_run


def test_phase2_config_disallows_mock():
    cfg = load_run("config/run-phase2.yaml")
    assert cfg.run_id == "phase2-e2012-real"
    assert cfg.allow_mock is False
    assert cfg.models == ["frontier-a", "frontier-b"]
    assert cfg.max_tool_calls == 8


def test_live_run_fails_loud_without_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--config", "config/run-phase2.yaml", "--limit", "1"])
    assert result.exit_code != 0
    combined = (result.output or "") + str(result.exception)
    assert "ANTHROPIC_API_KEY" in combined or "OPENAI_API_KEY" in combined


def test_skip_reason_and_parse():
    model = ModelConfig(
        id="frontier-a",
        provider="anthropic",
        model_name="x",
        declared_pretraining_cutoff=date(2025, 1, 1),
        is_instruction_tuned=True,
    )
    os.environ["ANTHROPIC_API_KEY"] = ""
    assert skip_reason(model)
    parsed = parse_prediction_json(
        '{"probability": 0.4, "reasoning": "x", "citations": '
        '[{"document_id": "d", "quoted_span": "hello world span", "supports": "context"}]}'
    )
    assert parsed["probability"] == 0.4


def test_execute_tool_against_index():
    import pytest

    from psbx.config import load_epochs
    from psbx.corpus.index import load_index
    from psbx.paths import resolve as repo_resolve
    from psbx.sandbox.client import LocalSearchClient

    if not repo_resolve("data/corpus/e2012/documents.jsonl").exists():
        pytest.skip("corpus index not built")

    epoch = load_epochs()["e2012"]
    index = load_index(epoch)
    client = LocalSearchClient(index)
    blob = execute_tool(client, "search", {"query": "unemployment", "k": 3})
    assert "NO HITS" not in blob
    doc_id = blob.split(" | ", 1)[0].strip()
    fetched = execute_tool(client, "fetch", {"document_id": doc_id})
    assert fetched.startswith("id=")


def test_resume_skips_existing_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    from psbx.config import load_epochs, load_models
    from psbx.io import read_jsonl
    from psbx.schemas import Question as Q

    epoch = load_epochs()["e2012"]
    qs = read_jsonl("data/questions/e2012.jsonl", Q)[:2]
    model = load_models()["frontier-a"]
    run = load_run("config/run.yaml").model_copy(
        update={"run_id": "phase2-resume-test", "n_questions": 2, "models": ["frontier-a"]}
    )
    dest = resolve(f"data/runs/{run.run_id}/predictions.jsonl")
    if dest.exists():
        dest.unlink()
    first = Prediction(
        run_id=run.run_id,
        question_id=qs[0].id,
        model_id=model.id,
        probability=0.4,
        reasoning="preexisting",
        citations=[Citation(document_id="d", quoted_span="preexisting span text here", supports="context")],
    )
    write_jsonl(dest, [first])
    preds = run_set(qs, [model], epoch, run)
    assert len(preds) == 2
    kept = [p for p in preds if p.question_id == qs[0].id]
    assert kept[0].reasoning == "preexisting"
    dest.unlink(missing_ok=True)


def test_score_includes_heuristic_and_prior(monkeypatch):
    from psbx.config import load_epochs
    from psbx.io import read_jsonl
    from psbx.schemas import Question as Q

    qs = read_jsonl("data/questions/e2012.jsonl", Q)[:5]
    models = [
        ModelConfig(
            id="frontier-a",
            provider="anthropic",
            model_name="x",
            declared_pretraining_cutoff=date(2025, 1, 1),
            is_instruction_tuned=True,
        )
    ]
    preds = [
        Prediction(
            run_id="phase2-e2012-real",
            question_id=q.id,
            model_id="frontier-a",
            probability=0.5,
            reasoning="t",
            citations=[Citation(document_id="d", quoted_span="span text for cite", supports="context")],
        )
        for q in qs
    ]
    report = score_run(preds, qs, models, "phase2-e2012-real")
    assert "prior_signal" in report.baselines
    assert "always_base_rate" in report.baselines
    smoke = resolve("data/runs/phase1-e2012-smoke/predictions.jsonl")
    if smoke.exists():
        assert "phase1_heuristic" in report.baselines
    assert report.models_beating_prior_signal is not None
