from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from psbx.schemas import ModelConfig
from psbx.security import allowlisted_subprocess_env, require_loopback_host
from psbx.spending import SpendGuardError, preflight_paid_requests


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.9.8.7", "::1", "[::1]"])
def test_viewer_accepts_only_loopback_hosts(host):
    assert require_loopback_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "example.com", "::"])
def test_viewer_rejects_remote_or_wildcard_hosts(host):
    with pytest.raises(ValueError, match="local-only|remote binds"):
        require_loopback_host(host)


def test_child_environment_is_explicitly_allowlisted():
    source = {
        "PATH": "/usr/bin",
        "HOME": "/tmp/home",
        "OPENROUTER_API_KEY": "model-secret",
        "PSBX_MAX_RUN_USD": "0.50",
        "AWS_SECRET_ACCESS_KEY": "unrelated-secret",
        "RANDOM_TOKEN": "another-secret",
    }
    search_env = allowlisted_subprocess_env(include_model_access=False, source=source)
    assert search_env == {"HOME": "/tmp/home", "PATH": "/usr/bin"}

    model_env = allowlisted_subprocess_env(include_model_access=True, source=source)
    assert model_env["OPENROUTER_API_KEY"] == "model-secret"
    assert model_env["PSBX_MAX_RUN_USD"] == "0.50"
    assert "AWS_SECRET_ACCESS_KEY" not in model_env
    assert "RANDOM_TOKEN" not in model_env


def test_viewer_mutations_require_non_simple_same_origin_request():
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)
    )
    body = {"epoch_id": "does-not-exist"}

    missing = client.post("/api/sandbox/select", json=body)
    assert missing.status_code == 403

    cross_origin = client.post(
        "/api/sandbox/select",
        json=body,
        headers={"X-PSBX-CSRF": "1", "Origin": "https://attacker.example"},
    )
    assert cross_origin.status_code == 403

    same_origin = client.post(
        "/api/sandbox/select",
        json=body,
        headers={"X-PSBX-CSRF": "1", "Origin": "http://127.0.0.1:8765"},
    )
    assert same_origin.status_code == 404


def test_viewer_rejects_dns_rebinding_host_for_reads_and_mutations():
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(), base_url="http://attacker.example:8765", client=("127.0.0.1", 50000)
    )
    assert client.get("/api/questions").status_code == 403
    response = client.post(
        "/api/sandbox/select",
        json={"epoch_id": "does-not-exist"},
        headers={
            "X-PSBX-CSRF": "1",
            "Origin": "http://attacker.example:8765",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert response.status_code == 403


def test_job_start_rejects_cross_site_fetch_metadata():
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)
    )
    response = client.post(
        "/api/jobs/run",
        json={"kind": "mock"},
        headers={"X-PSBX-CSRF": "1", "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin",
    ["http://[::1", "http://127.0.0.1:bad", "http://user@127.0.0.1:8765"],
)
def test_viewer_rejects_malformed_origin_cleanly(origin):
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)
    )
    response = client.post(
        "/api/sandbox/select",
        json={"epoch_id": "does-not-exist"},
        headers={"X-PSBX-CSRF": "1", "Origin": origin},
    )
    assert response.status_code == 403


def test_viewer_rejects_remote_peer_even_with_loopback_host():
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(),
        base_url="http://127.0.0.1:8765",
        client=("198.51.100.17", 50000),
    )
    assert client.get("/api/questions?reveal_truth=true").status_code == 403


def test_dashboard_child_environment_cannot_reload_stripped_dotenv(monkeypatch):
    from leaderboard.jobs import _job_subprocess_env

    monkeypatch.setenv("OPENROUTER_API_KEY", "supported-model-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-cross")
    env = _job_subprocess_env(mock=False)
    assert env["OPENROUTER_API_KEY"] == "supported-model-key"
    assert env["PSBX_DISABLE_DOTENV"] == "1"
    assert "AWS_SECRET_ACCESS_KEY" not in env


def test_dotenv_loader_honors_child_process_disable_flag(tmp_path, monkeypatch):
    from psbx.env import load_dotenv

    (tmp_path / ".env").write_text("RANDOM_TOKEN=must-not-load\n", encoding="utf-8")
    monkeypatch.setenv("PSBX_ROOT", str(tmp_path))
    monkeypatch.setenv("PSBX_DISABLE_DOTENV", "1")
    monkeypatch.delenv("RANDOM_TOKEN", raising=False)
    load_dotenv()
    assert "RANDOM_TOKEN" not in __import__("os").environ


def test_native_provider_error_never_reflects_response_body_or_key(monkeypatch):
    from psbx.agents.runner import _openai_turn

    secret = "sk-native-super-secret"
    model = ModelConfig(
        id="native-test",
        provider="openai",
        model_name="test-model",
        declared_pretraining_cutoff=date(2024, 1, 1),
        is_instruction_tuned=True,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
    )

    def reject(url, **kwargs):
        del kwargs
        return httpx.Response(
            401,
            request=httpx.Request("POST", url),
            text=f"credential={secret}; private provider diagnostic",
        )

    monkeypatch.setattr("psbx.agents.runner.httpx.post", reject)
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    monkeypatch.setenv("PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL", "1")
    with pytest.raises(RuntimeError) as caught:
        _openai_turn(model, [], base_url="https://api.example.test/v1", api_key=secret)
    message = str(caught.value)
    assert "HTTP 401" in message
    assert secret not in message
    assert "private provider diagnostic" not in message


def test_paid_key_alone_cannot_enable_network_calls(monkeypatch):
    from psbx.env import live_ready

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("PSBX_ENABLE_PAID_MODELS", raising=False)
    assert live_ready() is False


def test_paid_run_preflight_blocks_excess_request_shape(monkeypatch):
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    monkeypatch.setenv("PSBX_MAX_PAID_REQUESTS", "3")
    model = ModelConfig(
        id="budgeted",
        provider="openai",
        model_name="test",
        declared_pretraining_cutoff=date(2024, 1, 1),
        is_instruction_tuned=True,
        max_tokens=32,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0002,
    )
    with pytest.raises(SpendGuardError, match="up to 4 paid requests"):
        preflight_paid_requests([(model, 4)])


def test_swarm_options_publish_read_only_cost_and_token_projections(monkeypatch):
    from leaderboard.jobs import swarm_options

    monkeypatch.delenv("PSBX_ENABLE_PAID_MODELS", raising=False)
    options = swarm_options()
    projections = {
        row["representative_agents"]: row
        for row in options["representative_swarm_projections"]
    }
    assert options["run_type_estimates"]["practice"]["estimated_max_usd"] == 0
    assert options["run_type_estimates"]["native_full"]["maximum_requests"] == 1_200
    assert options["run_type_estimates"]["native_full"]["status"] == "blocked"
    assert projections[50]["maximum_requests"] == 100
    assert projections[50]["eligible_if_paid_mode_enabled"] is True
    assert projections[50]["can_start_paid_now"] is False
    assert projections[50]["status"] == "paid_disabled"
    assert projections[100]["maximum_requests"] == 200
    assert projections[100]["eligible_if_paid_mode_enabled"] is False
    assert projections[100]["status"] == "blocked"
    assert projections[12]["hard_input_tokens_per_request"] == 16_000
    assert projections[12]["hard_maximum_input_tokens"] == 384_000
    assert projections[12]["maximum_output_tokens"] == 6_144
    assert projections[12]["hard_maximum_total_tokens"] == 390_144


def test_paid_provider_url_is_pinned_by_default(monkeypatch):
    from psbx.security import require_safe_provider_base_url

    monkeypatch.delenv("PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL", raising=False)
    assert (
        require_safe_provider_base_url("https://api.openai.com/v1", "openai")
        == "https://api.openai.com/v1"
    )
    with pytest.raises(ValueError, match="refusing custom"):
        require_safe_provider_base_url("https://proxy.example/v1", "openai")


def test_paid_request_is_blocked_before_network_without_opt_in(monkeypatch):
    from psbx.agents.runner import _openai_turn

    called = {"value": False}

    def must_not_post(*args, **kwargs):
        del args, kwargs
        called["value"] = True
        raise AssertionError("network call must be blocked")

    model = ModelConfig(
        id="blocked",
        provider="openai",
        model_name="test",
        declared_pretraining_cutoff=date(2024, 1, 1),
        is_instruction_tuned=True,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
    )
    monkeypatch.delenv("PSBX_ENABLE_PAID_MODELS", raising=False)
    monkeypatch.setattr("psbx.agents.runner.httpx.post", must_not_post)
    with pytest.raises(SpendGuardError, match="paid models are disabled"):
        _openai_turn(
            model,
            [{"role": "user", "content": "hello"}],
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
    assert called["value"] is False


def test_local_vllm_url_cannot_be_remote():
    from psbx.security import require_loopback_base_url

    assert require_loopback_base_url("http://127.0.0.1:8000/v1", "vLLM")
    with pytest.raises(ValueError, match="loopback"):
        require_loopback_base_url("https://remote.example/v1", "vLLM")
