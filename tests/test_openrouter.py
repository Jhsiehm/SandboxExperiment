from datetime import date

import httpx
import pytest

from psbx.agents.runner import skip_reason
from psbx.env import live_ready, provider_status
from psbx.openrouter import (
    capped_max_tokens,
    chat_completion,
    reset_gate_for_tests,
)
from psbx.schemas import ModelConfig


@pytest.fixture(autouse=True)
def _isolate_openrouter_env(monkeypatch):
    """Never let tests inherit a real key from .env."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_MIN_INTERVAL_SEC", "0")
    reset_gate_for_tests()
    yield
    reset_gate_for_tests()


def _or_model() -> ModelConfig:
    return ModelConfig(
        id="openrouter-gpt-4.1-mini",
        provider="openrouter",
        model_name="openai/gpt-4.1-mini",
        declared_pretraining_cutoff=date(2024, 6, 1),
        is_instruction_tuned=True,
        max_tokens=256,
    )


def test_live_ready_openrouter_only(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert live_ready() is True
    assert provider_status()["openrouter"] is True
    assert provider_status()["anthropic"] is False


def test_live_ready_dual_native(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert live_ready() is True


def test_live_ready_missing_all(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert live_ready() is False
    # Explicit empty must not be refilled from repo-root .env.
    assert provider_status()["openrouter"] is False


def test_skip_reason_openrouter(monkeypatch):
    model = _or_model()
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert skip_reason(model) == "OPENROUTER_API_KEY is not set"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert skip_reason(model) is None


def test_capped_max_tokens_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MAX_TOKENS", raising=False)
    assert capped_max_tokens(None) == 256
    assert capped_max_tokens(4096) == 256
    assert capped_max_tokens(16) == 16


def test_openrouter_config_is_cheap():
    from psbx.config import load_run

    cfg = load_run("config/run-openrouter.yaml")
    assert cfg.allow_mock is False
    assert cfg.n_questions == 1
    assert cfg.models == [
        "openrouter-gpt-4.1-mini",
        "openrouter-gpt-4o-mini",
        "openrouter-haiku",
        "openrouter-gemini-flash-lite",
        "openrouter-llama-3.1-8b",
        "openrouter-qwen-2.5-7b",
    ]
    assert cfg.swarm_roster == "config/swarm.yaml"


def test_jobs_pick_openrouter_config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from leaderboard.jobs import OPENROUTER_CONFIG, live_config_path, ready

    assert live_config_path() == OPENROUTER_CONFIG
    snap = ready()
    assert snap["live_ready"] is True
    assert snap["live_config"] == OPENROUTER_CONFIG
    assert snap["live_config"] != "config/run-swarm.yaml"
    assert snap["swarm_run_config"] == "config/run-swarm.yaml"
    assert "2 × each" in snap["swarm_roster"]
    assert "Llama 3.1 8B" in snap["swarm_roster"]
    assert "Qwen 2.5 7B" in snap["swarm_roster"]
    assert snap["swarm_run_id"] == "phase2-e2012-swarm-probe-container"
    assert "Three HUD buttons" in snap["swarm_note"]
    assert "sk-test" not in str(snap)


def test_live_mix_prefers_openrouter_even_with_native_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")
    from leaderboard.jobs import (
        LIVE_CONFIG,
        MOCK_CONFIG,
        OPENROUTER_CONFIG,
        SWARM_CONFIG,
        config_for_kind,
        live_config_path,
    )

    assert live_config_path() == OPENROUTER_CONFIG
    assert live_config_path() != LIVE_CONFIG
    assert config_for_kind("mock") == MOCK_CONFIG
    assert config_for_kind("live") == OPENROUTER_CONFIG
    assert config_for_kind("swarm") == SWARM_CONFIG
    assert config_for_kind("swarm") != OPENROUTER_CONFIG


def test_chat_completion_headers_and_429(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENROUTER_MIN_INTERVAL_SEC", "0")
    monkeypatch.setenv("OPENROUTER_MAX_PER_MINUTE", "20")
    monkeypatch.setenv("OPENROUTER_MAX_CONCURRENCY", "1")
    reset_gate_for_tests()
    sleeps: list[float] = []
    monkeypatch.setattr("psbx.openrouter.time.sleep", lambda s: sleeps.append(s))

    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        assert "openrouter.ai" in url
        assert headers["HTTP-Referer"] == "http://127.0.0.1:8765"
        assert headers["X-Title"] == "Prediction Sandbox"
        assert headers["authorization"].startswith("Bearer ")
        assert json["max_tokens"] == 16
        req = httpx.Request("POST", url)
        if calls["n"] < 3:
            return httpx.Response(429, request=req, text="rate limited")
        return httpx.Response(
            200,
            request=req,
            json={"choices": [{"message": {"content": "ok", "tool_calls": []}}]},
        )

    monkeypatch.setattr("psbx.openrouter.httpx.post", fake_post)
    data = chat_completion(
        model="openai/gpt-4.1-mini",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
    )
    assert data["choices"][0]["message"]["content"] == "ok"
    assert calls["n"] == 3
    assert 15.0 in sleeps
    assert 30.0 in sleeps


def test_sanitize_openai_message_strips_400_bait():
    from psbx.agents.runner import sanitize_openai_message

    empty_calls = sanitize_openai_message(
        {"role": "assistant", "content": None, "tool_calls": [], "refusal": None}
    )
    assert empty_calls == {"role": "assistant", "content": ""}
    assert "tool_calls" not in empty_calls
    assert "refusal" not in empty_calls

    with_tools = sanitize_openai_message(
        {
            "role": "assistant",
            "content": None,
            "refusal": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"},
                }
            ],
        }
    )
    assert "content" not in with_tools
    assert len(with_tools["tool_calls"]) == 1


def test_chat_completion_includes_400_body(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENROUTER_MIN_INTERVAL_SEC", "0")
    reset_gate_for_tests()

    def bad(url, headers=None, json=None, timeout=None):
        req = httpx.Request("POST", url)
        return httpx.Response(
            400,
            request=req,
            text='{"error":{"message":"unmatched tool_calls"}}',
        )

    monkeypatch.setattr("psbx.openrouter.httpx.post", bad)
    with pytest.raises(RuntimeError, match="unmatched tool_calls"):
        chat_completion(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
        )


def test_chat_completion_surfaces_expired_key_message(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENROUTER_MIN_INTERVAL_SEC", "0")
    reset_gate_for_tests()

    def expired(url, headers=None, json=None, timeout=None):
        req = httpx.Request("POST", url)
        return httpx.Response(
            401,
            request=req,
            text=(
                '{"error":{"message":"API key expired.","code":401,'
                '"metadata":{"headers":{"WWW-Authenticate":"Bearer realm=\\"api\\""}}}}'
            ),
        )

    monkeypatch.setattr("psbx.openrouter.httpx.post", expired)
    with pytest.raises(RuntimeError, match="API key expired"):
        chat_completion(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
        )


def test_live_loop_does_not_replay_unmatched_tool_calls(monkeypatch):
    from psbx.agents.runner import ToolCall, Turn
    from psbx.agents.single_agent import run_single_agent
    from psbx.schemas import Epoch, Question

    class FakeClient:
        def __init__(self):
            self.n_calls = 0
            self.queries: list[str] = []

        def search(self, query, k=10, min_prominence=0.0):
            del k, min_prominence
            self.n_calls += 1
            self.queries.append(query)
            return []

        def fetch(self, document_id):
            self.n_calls += 1
            return {
                "id": document_id,
                "title": "t",
                "published_at": "2012-01-01T00:00:00",
                "text": "hello world span from the wire",
            }

    n = {"i": 0}

    def fake_complete(model, messages, *, system, tools=True):
        del model, system
        pending: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                pending = {c.get("id") for c in msg["tool_calls"]}
            elif msg.get("role") == "tool":
                pending.discard(msg.get("tool_call_id"))
            elif msg.get("role") == "assistant":
                pending = set()
        assert not pending, messages
        n["i"] += 1
        if n["i"] <= 2:
            assert tools is True
            cid = f"call_{n['i']}"
            return Turn(
                text="",
                tool_calls=[ToolCall(id=cid, name="search", arguments={"query": "jobs"})],
                openai_message={
                    "role": "assistant",
                    "content": None,
                    "refusal": None,
                    "tool_calls": [
                        {
                            "id": cid,
                            "type": "function",
                            "function": {"name": "search", "arguments": '{"query":"jobs"}'},
                        }
                    ],
                },
            )
        assert tools is False
        return Turn(
            text=(
                '{"probability": 0.4, "reasoning": "x", "citations": '
                '[{"document_id": "d", "quoted_span": "hello world span", "supports": "context"}]}'
            )
        )

    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    monkeypatch.setattr("psbx.agents.single_agent.complete_turn", fake_complete)
    model = _or_model()
    question = Question.model_validate(
        {
            "id": "q1",
            "epoch_id": "e2012",
            "category": "economic",
            "text": "Will unemployment stay above 7 percent by 2012-12-31?",
            "resolution_criteria": "BLS",
            "cutoff_date": "2012-06-30",
            "resolution_date": "2012-12-31",
            "ground_truth": True,
            "generator": "test",
        }
    )
    epoch = Epoch(
        id="e2012",
        cutoff_date=date(2012, 6, 30),
        resolution_window_end=date(2012, 12, 31),
        corpus_index_path="data/corpus/e2012",
    )
    pred = run_single_agent(
        question, model, epoch, "phase2-e2012-openrouter", FakeClient(), max_tool_calls=2
    )
    assert pred.probability == 0.4
    assert pred.n_tool_calls == 2


def test_chat_completion_gives_up_after_two_429_retries(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENROUTER_MIN_INTERVAL_SEC", "0")
    reset_gate_for_tests()
    monkeypatch.setattr("psbx.openrouter.time.sleep", lambda s: None)

    def always_429(url, headers=None, json=None, timeout=None):
        req = httpx.Request("POST", url)
        return httpx.Response(429, request=req, text="rate limited")

    monkeypatch.setattr("psbx.openrouter.httpx.post", always_429)
    with pytest.raises(RuntimeError, match="openrouter status=429"):
        chat_completion(
            model="openai/gpt-4.1-mini",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
        )
