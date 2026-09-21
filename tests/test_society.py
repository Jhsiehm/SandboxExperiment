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
        assert row["authenticity"] in {
            "reconstructed_fixture",
            "unverified",
            "authenticated_capture",
            "authenticated_artifact",
        }
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
    empty = env.evidence_pack(1)
    assert empty["available"] is False
    env.bind_evidence({"queries": ["unemployment"], "hits_text": "jobs"})
    packed = env.evidence_pack(1)
    assert packed["available"] is True
    assert packed["queries"] == ["unemployment"]
    kinds = env.list_source_types(1)
    assert kinds["counts"]
    assert "conditioners" in kinds
    empty_persona = env.persona_card(1)
    assert empty_persona["available"] is False
    from psbx.society.perspectives import load_perspectives

    env.bind_personas(load_perspectives().assigned(12))
    card = env.persona_card(1)
    assert card["available"] is True
    assert card["id"]
    rows = env.search(1, "gallup poll", k=5, source_types="survey")
    for row in rows:
        published = date.fromisoformat(str(row["published_at"])[:10])
        assert published <= epoch.cutoff_date
        if row.get("source_type"):
            assert row["source_type"] == "survey"
    del index


def test_as2_module_contract():
    EnvBase, tool, AgentBase = load_as2()
    from custom.agents.forecaster_agent import ForecasterAgent
    from custom.envs.frozen_epoch_env import FrozenEpochEnv

    assert issubclass(FrozenEpochEnv, EnvBase)
    assert issubclass(ForecasterAgent, AgentBase)
    assert getattr(FrozenEpochEnv.search, "_as2_tool", True)
    assert FrozenEpochEnv.mcp_description()
    assert FrozenEpochEnv.init_description()
    assert FrozenEpochEnv.is_concurrency_safe() is False
    assert ForecasterAgent.init_description()
    specs = agent_specs_for_models(["frontier-a"])
    assert specs[0]["config"]["agent_class"] == "ForecasterAgent"
    assert try_as2_router(FrozenEpochEnv()) in {"shim", "agentsociety2"}


def test_society_cli_mock_does_not_clobber_smoke(tmp_path, monkeypatch) -> None:
    _ensure_e2012_index()
    smoke = resolve("data/runs/phase1-e2012-smoke/predictions.jsonl")
    before = (smoke.stat().st_mtime_ns, smoke.stat().st_size) if smoke.exists() else None
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    def isolated_run_dir(run_id):
        return tmp_path / "runs" / run_id

    monkeypatch.setattr("psbx.cli.run_dir", isolated_run_dir)
    monkeypatch.setattr("psbx.society.experiment.resolve_run_dir", isolated_run_dir)
    monkeypatch.setattr("psbx.run_provenance.run_dir", isolated_run_dir)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["society", "run", "--config", "config/run-society.yaml", "--limit", "1"],
    )
    assert result.exit_code == 0, result.output
    dest = isolated_run_dir("phase1-e2012-society") / "predictions.jsonl"
    assert dest.exists()
    assert dest != smoke
    if before is not None:
        after = (smoke.stat().st_mtime_ns, smoke.stat().st_size)
        assert after == before


def test_as2_swarm_export_matches_roster_and_cli_contract(tmp_path):
    from psbx.config import load_run, load_swarm
    from psbx.io import read_jsonl
    from psbx.paths import agentsociety_root
    from psbx.schemas import Question
    from psbx.society.as2_config import (
        export_society_bundle,
        init_config_payload,
        swarm_agent_specs,
    )

    roster = load_swarm()
    specs = swarm_agent_specs(roster)
    assert len(specs) == 12
    assert {s["profile"]["model_id"] for s in specs} == {
        "openrouter-gpt-4.1-mini",
        "openrouter-gpt-4o-mini",
        "openrouter-haiku",
        "openrouter-gemini-flash-lite",
        "openrouter-llama-3.1-8b",
        "openrouter-qwen-2.5-7b",
    }
    payload = init_config_payload(roster=roster)
    assert payload["env_modules"][0]["module_type"] == "FrozenEpochEnv"
    assert payload["psbx"]["agentsociety_root"] in {None, "../AgentSociety"}
    assert len(payload["agents"]) == 12
    assert all(a["agent_type"] == "ForecasterAgent" for a in payload["agents"])
    assert all("id" in a["kwargs"] for a in payload["agents"])
    sibling = agentsociety_root()
    if sibling is not None:
        assert sibling.name == "AgentSociety"
        assert (sibling / "packages" / "agentsociety2").is_dir()
    run = load_run("config/run-society-swarm.yaml")
    qs = read_jsonl(run.question_set, Question)[:1]
    paths = export_society_bundle(run, qs, tmp_path)
    init = (tmp_path / "init_config.json").read_text(encoding="utf-8")
    assert "ForecasterAgent" in init
    assert "FrozenEpochEnv" in init
    assert (tmp_path / "agents" / "agent_0001" / "AGENT.json").exists()
    assert (tmp_path / "agents" / "agent_0012" / "config.json").exists()
    assert "questionnaire" in paths["steps"].read_text(encoding="utf-8")
    assert '"schema_version": 1' in (tmp_path / "SOCIETY.json").read_text(encoding="utf-8")


def test_society_swarm_mock_writes_workspaces(tmp_path, monkeypatch) -> None:
    _ensure_e2012_index()
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    from psbx.config import load_run
    from psbx.society.experiment import run_society

    def isolated_run_dir(run_id):
        return tmp_path / "runs" / run_id

    monkeypatch.setattr("psbx.society.experiment.resolve_run_dir", isolated_run_dir)
    monkeypatch.setattr("psbx.run_provenance.run_dir", isolated_run_dir)
    run = load_run("config/run-society-swarm-mock.yaml")
    run = run.model_copy(
        update={
            "run_id": "test-society-swarm",
            "n_questions": 1,
            "sandbox_mode": "host",
        }
    )
    preds = run_society(run, limit=1)
    assert preds
    assert preds[0].model_id == "swarm-median"
    society = isolated_run_dir("test-society-swarm") / "society"
    assert (society / "init_config.json").exists()
    assert (society / "agents" / "agent_0006" / "AGENT.json").exists()
    votes = isolated_run_dir("test-society-swarm") / "swarm_votes.jsonl"
    assert votes.exists()


def test_society_export_cli(tmp_path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "society",
            "export",
            "--config",
            "config/run-society-swarm.yaml",
            "--dest",
            str(tmp_path),
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "init_config.json").exists()
    assert (tmp_path / "steps.yaml").exists()
