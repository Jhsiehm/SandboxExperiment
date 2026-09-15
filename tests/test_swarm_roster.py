import json
from datetime import date, datetime

import pytest
from typer.testing import CliRunner

from psbx.agents.runner import skip_reason
from psbx.agents.swarm import (
    FLASH_LITE_VOICE,
    HAIKU_VOICE,
    MINI_VOICE,
    OPEN_WEIGHT_VOICE,
    SWARM_MEDIAN_ID,
    _voice_for,
    expand_bodies,
    load_roster,
    median_probability,
    parse_swarm_json,
    require_swarm_ready,
    run_swarm,
    worker_models,
)
from psbx.config import load_models, load_run, load_swarm
from psbx.schemas import (
    Epoch,
    ModelConfig,
    Question,
    SearchHit,
    SwarmRoster,
    SwarmSpecies,
)


def _question() -> Question:
    return Question(
        id="q1",
        epoch_id="e2012",
        category="economic",
        text="Will unemployment stay above 7 percent by 2012-12-31?",
        resolution_criteria="BLS",
        cutoff_date="2012-06-30",
        resolution_date="2012-12-31",
        ground_truth=True,
        generator="test",
    )


def _epoch() -> Epoch:
    return Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2012, 12, 31),
        corpus_index_path="data/corpus/e2012",
    )


class FakeClient:
    def __init__(self):
        self.n_calls = 0
        self._queries: list[str] = []

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    def search(self, query, k=10, min_prominence=0.0, source_types=None):
        del k, min_prominence
        self.n_calls += 1
        self._queries.append(query)
        if source_types:
            return []
        return [
            SearchHit(
                document_id="d1",
                title="Jobs",
                outlet="wire",
                published_at=datetime(2012, 1, 15),
                snippet="unemployment remains elevated and widely expected to stay high",
                prominence=0.8,
            )
        ]

    def fetch(self, document_id):
        self.n_calls += 1
        return {
            "id": document_id,
            "title": "Jobs",
            "published_at": "2012-01-15T00:00:00",
            "text": (
                "Unemployment remains elevated and widely expected to stay high "
                "through the year according to the BLS outlook."
            ),
        }


def test_swarm_roster_is_planned_cheap_mix():
    roster = load_swarm()
    assert roster.n_agents == 12
    assert roster.n_questions_default == 1
    assert roster.serialize_openrouter is True
    counts = {b.model_id: b.count for b in roster.bodies}
    assert counts == {
        "openrouter-gpt-4.1-mini": 2,
        "openrouter-gpt-4o-mini": 2,
        "openrouter-haiku": 2,
        "openrouter-gemini-flash-lite": 2,
        "openrouter-llama-3.1-8b": 2,
        "openrouter-qwen-2.5-7b": 2,
    }
    assert all(b.json_forecast and not b.chain_of_thought for b in roster.bodies)
    assert all(b.max_tokens == 256 and b.temperature == 0.8 for b in roster.bodies)
    assert roster.optional_scale_up == []
    local = {b.model_id for b in roster.local_scale_up}
    assert local == {"local-llama-3.1-8b", "local-qwen-2.5-7b"}
    default_ids = {b.model_id for b in roster.bodies}
    assert default_ids == {
        "openrouter-gpt-4.1-mini",
        "openrouter-gpt-4o-mini",
        "openrouter-haiku",
        "openrouter-gemini-flash-lite",
        "openrouter-llama-3.1-8b",
        "openrouter-qwen-2.5-7b",
    }
    assert not (local & default_ids)


def test_expand_bodies_twelve_and_no_local():
    expanded = expand_bodies()
    assert len(expanded) == 12
    assert sum(1 for b in expanded if b.model_id == "openrouter-gpt-4.1-mini") == 2
    assert sum(1 for b in expanded if b.model_id == "openrouter-gpt-4o-mini") == 2
    assert sum(1 for b in expanded if b.model_id == "openrouter-haiku") == 2
    assert sum(1 for b in expanded if b.model_id == "openrouter-gemini-flash-lite") == 2
    assert sum(1 for b in expanded if b.model_id == "openrouter-llama-3.1-8b") == 2
    assert sum(1 for b in expanded if b.model_id == "openrouter-qwen-2.5-7b") == 2
    workers = worker_models()
    assert len(workers) == 12
    assert all(not m.needs_endpoint for m in workers)
    assert all(m.provider == "openrouter" for m in workers)
    assert SWARM_MEDIAN_ID not in {m.id for m in workers}


def test_registered_openrouter_slugs_and_local_guard():
    models = load_models()
    assert models["openrouter-gpt-4.1-mini"].model_name == "openai/gpt-4.1-mini"
    assert models["openrouter-gpt-4o-mini"].model_name == "openai/gpt-4o-mini"
    assert models["openrouter-haiku"].model_name == "anthropic/claude-3-haiku"
    assert models["openrouter-gemini-flash-lite"].model_name == "google/gemini-2.5-flash-lite"
    assert models["openrouter-llama-3.1-8b"].model_name == "meta-llama/llama-3.1-8b-instruct"
    assert models["openrouter-qwen-2.5-7b"].model_name == "qwen/qwen-2.5-7b-instruct"
    assert models["openrouter-llama-3.1-8b"].provider == "openrouter"
    assert models["openrouter-qwen-2.5-7b"].needs_endpoint is False
    assert models[SWARM_MEDIAN_ID].model_name == "swarm-median"
    llama = models["local-llama-3.1-8b"]
    qwen = models["local-qwen-2.5-7b"]
    assert llama.provider == "local_vllm"
    assert qwen.provider == "local_vllm"
    assert llama.needs_endpoint and qwen.needs_endpoint
    assert llama.openrouter_fallback == "meta-llama/llama-3.1-8b-instruct"
    assert qwen.openrouter_fallback == "qwen/qwen-2.5-7b-instruct"
    assert models["openrouter-gpt-4.1-mini"].label.startswith("swarm worker")
    assert models["openrouter-haiku"].label.startswith("swarm species")
    assert models["openrouter-gemini-flash-lite"].label.startswith("swarm species")
    assert models[SWARM_MEDIAN_ID].label.startswith("swarm")


def test_swarm_voices_split_species():
    models = load_models()
    assert _voice_for(models["openrouter-gpt-4.1-mini"]) == MINI_VOICE
    assert _voice_for(models["openrouter-gpt-4o-mini"]) == MINI_VOICE
    assert _voice_for(models["openrouter-haiku"]) == HAIKU_VOICE
    assert _voice_for(models["openrouter-gemini-flash-lite"]) == FLASH_LITE_VOICE
    assert _voice_for(models["openrouter-llama-3.1-8b"]) == OPEN_WEIGHT_VOICE
    assert _voice_for(models["openrouter-qwen-2.5-7b"]) == OPEN_WEIGHT_VOICE


def test_needs_endpoint_refuses_openrouter_rewrite(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    hijacked = ModelConfig(
        id="local-llama-3.1-8b",
        provider="openrouter",
        model_name="meta-llama/llama-3.1-8b-instruct",
        declared_pretraining_cutoff="2023-12-01",
        is_instruction_tuned=True,
        needs_endpoint=True,
    )
    reason = skip_reason(hijacked)
    assert reason is not None
    assert "OPENROUTER_API_KEY" in reason
    assert "sk-test" not in reason


def test_skip_reason_swarm_median_is_aggregate():
    models = load_models()
    reason = skip_reason(models[SWARM_MEDIAN_ID])
    assert reason is not None
    assert "aggregate" in reason
    assert "use_swarm" in reason


def test_median_and_parse_swarm_json():
    assert median_probability([0.1, 0.9]) == 0.5
    assert median_probability([0.2, 0.4, 0.9]) == 0.4
    parsed = parse_swarm_json('{"p": 0.42, "rationale": "pack points yes"}')
    assert parsed["probability"] == 0.42
    long = "word " * 50
    parsed = parse_swarm_json(json.dumps({"probability": 0.3, "reasoning": long}))
    assert len(parsed["rationale"].split()) == 40
    with pytest.raises(Exception, match="missing p"):
        parse_swarm_json('{"rationale": "no p"}')


def test_require_swarm_ready_fails_without_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        require_swarm_ready()


def test_run_swarm_shared_pack_and_median(monkeypatch):
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    ps = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.15, 0.25, 0.35, 0.45]
    n = {"i": 0}

    def fake_complete(model, messages, *, system, tools=True):
        del system
        assert tools is False
        assert model.needs_endpoint is False
        assert model.id != SWARM_MEDIAN_ID
        assert model.model_name != "swarm-median"
        assert any(m.get("role") == "system" for m in messages)
        n["i"] += 1
        p = ps[n["i"] - 1]
        from psbx.agents.runner import Turn

        return Turn(text=json.dumps({"p": p, "rationale": "from the shared pack"}))

    monkeypatch.setattr("psbx.agents.swarm.complete_turn", fake_complete)
    client = FakeClient()
    result = run_swarm(_question(), _epoch(), "phase2-e2012-swarm-probe", client)
    assert n["i"] == 12
    assert client.n_calls == 3
    assert result.prediction.model_id == SWARM_MEDIAN_ID
    assert result.prediction.probability == pytest.approx(0.375)
    assert len(result.votes) == 12
    assert {v.model_id for v in result.votes} == {
        "openrouter-gpt-4.1-mini",
        "openrouter-gpt-4o-mini",
        "openrouter-haiku",
        "openrouter-gemini-flash-lite",
        "openrouter-llama-3.1-8b",
        "openrouter-qwen-2.5-7b",
    }
    slugs = {v.model_slug for v in result.votes}
    assert slugs == {
        "openai/gpt-4.1-mini",
        "openai/gpt-4o-mini",
        "anthropic/claude-3-haiku",
        "google/gemini-2.5-flash-lite",
        "meta-llama/llama-3.1-8b-instruct",
        "qwen/qwen-2.5-7b-instruct",
    }
    assert all(v.system_prompt for v in result.votes)
    assert result.prediction.n_tool_calls == 3
    assert result.prediction.search_queries
    assert {v.perspective_id for v in result.votes}


def test_run_swarm_mock_heuristic_does_not_call_openrouter(monkeypatch):
    monkeypatch.setenv("PSBX_MOCK_LLM", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    def boom(*args, **kwargs):
        raise AssertionError("OpenRouter must not be called in mock swarm")

    monkeypatch.setattr("psbx.agents.swarm.complete_turn", boom)
    client = FakeClient()
    result = run_swarm(_question(), _epoch(), "mock-swarm", client)
    assert result.prediction.model_id == SWARM_MEDIAN_ID
    assert 0.0 <= result.prediction.probability <= 1.0
    assert len(result.votes) == 12
    assert client.n_calls == 3
    assert all(v.perspective_id for v in result.votes)


def test_worker_models_skips_local_even_if_on_roster():
    roster = SwarmRoster(
        name="sneak-local",
        n_agents=2,
        bodies=[
            SwarmSpecies(model_id="openrouter-gpt-4.1-mini", count=1),
            SwarmSpecies(model_id="local-llama-3.1-8b", count=1),
        ],
    )
    workers = worker_models(roster)
    assert [w.id for w in workers] == ["openrouter-gpt-4.1-mini"]


CHEAP_OPENROUTER_PROBE = [
    "openrouter-gpt-4.1-mini",
    "openrouter-gpt-4o-mini",
    "openrouter-haiku",
    "openrouter-gemini-flash-lite",
    "openrouter-llama-3.1-8b",
    "openrouter-qwen-2.5-7b",
]


def test_openrouter_probe_stays_cheap_and_swarm_run_is_median():
    probe = load_run("config/run-openrouter.yaml")
    assert probe.n_questions == 1
    assert probe.models == CHEAP_OPENROUTER_PROBE
    assert probe.use_swarm is False
    assert probe.swarm_roster == "config/swarm.yaml"
    assert probe.allow_mock is False
    mix = load_run("config/run-swarm.yaml")
    assert mix.n_questions == 1
    assert mix.models == [SWARM_MEDIAN_ID]
    assert mix.use_swarm is True
    assert mix.swarm_roster == "config/swarm.yaml"
    assert mix.allow_mock is False
    assert load_roster().n_agents == 12


def test_swarm_cli_fails_without_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    runner = CliRunner()
    from psbx.cli import app

    result = runner.invoke(app, ["run", "--config", "config/run-swarm.yaml", "--limit", "1"])
    assert result.exit_code != 0
    combined = (result.output or "") + str(result.exception)
    assert "OPENROUTER_API_KEY" in combined
    assert "sk-" not in combined
