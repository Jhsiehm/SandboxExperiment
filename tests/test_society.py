from datetime import date

from typer.testing import CliRunner

from psbx.cli import app
from psbx.paths import resolve
from psbx.society.adapters import EnvSearchClient
from psbx.society.experiment import agent_specs_for_models, bind_frozen_env, try_as2_router
from psbx.society.shim import load_as2


def _ensure_e2012_index() -> None:
    from psbx.config import load_epochs
    from psbx.corpus.build_index import build_index
    from psbx.corpus.index import load_index

    epoch = load_epochs()["e2012"]
    dest = resolve(epoch.corpus_index_path)
    if (dest / "documents.jsonl").exists():
        load_index(epoch)
        return
    build_index(epoch, live=False)


def test_frozen_epoch_env_cutoff_and_tools():
    _ensure_e2012_index()
    env, epoch, index = bind_frozen_env("e2012")
    clock = env.epoch_clock(1)
    assert clock["now"] == epoch.cutoff_date.isoformat()
    rows = env.search(1, "unemployment", k=3)
    assert rows
    for row in rows:
        published = date.fromisoformat(str(row["published_at"])[:10])
        assert published <= epoch.cutoff_date
    doc = env.fetch(1, rows[0]["document_id"])
    assert "text" in doc
    assert "embedding" not in doc
    client = EnvSearchClient(env)
    hits = client.search("NDAA", k=2)
    assert hits
    fetched = client.fetch(hits[0].document_id)
    assert fetched["id"] == hits[0].document_id
    del index


def test_as2_module_contract():
    EnvBase, tool, AgentBase = load_as2()
    from custom.agents.forecaster_agent import ForecasterAgent
    from custom.envs.frozen_epoch_env import FrozenEpochEnv

    assert issubclass(FrozenEpochEnv, EnvBase)
    assert issubclass(ForecasterAgent, AgentBase)
    assert getattr(FrozenEpochEnv.search, "_as2_tool", True)
    assert FrozenEpochEnv.mcp_description()
    specs = agent_specs_for_models(["frontier-a"])
    assert specs[0]["config"]["agent_class"] == "ForecasterAgent"
    assert try_as2_router(FrozenEpochEnv()) in {"shim", "agentsociety2"}


def test_society_cli_mock_does_not_clobber_smoke(monkeypatch) -> None:
    _ensure_e2012_index()
    smoke = resolve("data/runs/phase1-e2012-smoke/predictions.jsonl")
    before = (smoke.stat().st_mtime_ns, smoke.stat().st_size) if smoke.exists() else None
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["society", "run", "--config", "config/run-society.yaml", "--limit", "1"],
    )
    assert result.exit_code == 0, result.output
    dest = resolve("data/runs/phase1-e2012-society/predictions.jsonl")
    assert dest.exists()
    assert dest != smoke
    if before is not None:
        after = (smoke.stat().st_mtime_ns, smoke.stat().st_size)
        assert after == before
