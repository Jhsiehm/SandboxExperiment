"""Background host-side `psbx run` then `psbx score` for the viewer."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from psbx.config import load_run
from psbx.env import live_ready, load_dotenv, provider_status
from psbx.paths import repo_root

_LOCK = threading.Lock()
_LOG_CAP = 400
MOCK_CONFIG = "config/run.yaml"
LIVE_CONFIG = "config/run-phase2.yaml"
OPENROUTER_CONFIG = "config/run-openrouter.yaml"
SWARM_CONFIG = "config/run-swarm.yaml"


def live_config_path(status: dict[str, bool] | None = None) -> str:
    """Dashboard **Run live mix** is the 6-species OpenRouter probe when that key exists.

    Native Claude+GPT (run-phase2.yaml) only if OpenRouter is missing but both
    native keys are set. The 12-agent median is **Run swarm** / run-swarm.yaml.
    """
    status = status if status is not None else provider_status()
    if status["openrouter"]:
        return OPENROUTER_CONFIG
    if status["anthropic"] and status["openai"]:
        return LIVE_CONFIG
    return OPENROUTER_CONFIG


def config_for_kind(kind: str) -> str:
    if kind == "mock":
        return MOCK_CONFIG
    if kind == "swarm":
        return SWARM_CONFIG
    return live_config_path()


class JobBusy(RuntimeError):
    pass


class LiveNotReady(RuntimeError):
    pass


@dataclass
class JobState:
    status: str = "idle"
    run_id: str = "phase1-e2012-smoke"
    phase: str = ""
    mock: bool = True
    kind: str = "mock"
    config_path: str = MOCK_CONFIG
    log: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "phase": self.phase,
            "mock": self.mock,
            "kind": self.kind,
            "config_path": self.config_path,
            "log": list(self.log),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_JOB = JobState()


def get_job() -> dict[str, Any]:
    with _LOCK:
        return _JOB.snapshot()


def ready() -> dict[str, Any]:
    load_dotenv()
    status = provider_status()
    live_cfg = live_config_path(status)
    return {
        "providers": status,
        "live_ready": live_ready(),
        "mock_config": MOCK_CONFIG,
        "live_config": live_cfg,
        "live_run_id": load_run(live_cfg).run_id,
        "mock_run_id": load_run(MOCK_CONFIG).run_id,
        "swarm_roster": (
            "2 × each of gpt-4.1-mini, gpt-4o-mini, Haiku, Flash-Lite, "
            "Llama 3.1 8B, Qwen 2.5 7B (12 agents; sequential OpenRouter)"
        ),
        "swarm_config": "config/swarm.yaml",
        "swarm_run_config": SWARM_CONFIG,
        "swarm_run_id": load_run(SWARM_CONFIG).run_id,
        "swarm_note": (
            "Three HUD buttons: Run practice (keyword lookup, no keys), "
            "Run live mix (each of GPT-4.1 mini, GPT-4o mini, Claude 3 Haiku, "
            "Gemini Flash-Lite, Llama 3.1 8B, Qwen 2.5 7B once — 1 question), "
            "Run swarm (2 of each species, 12 sequential votes, shared retrieval, "
            "median p; not a stub). Results draws seaborn charts (vote swarm, "
            "Brier bars, signed error). A full 12×50 pass is hours at 2s/req. "
            "local-* Llama/Qwen stay vLLM-only. Native Claude+GPT still needs "
            "both Anthropic and OpenAI keys."
        ),
    }


def start_job(
    *,
    run_id: str | None = None,
    mock: bool = True,
    kind: str | None = None,
) -> dict[str, Any]:
    load_dotenv()
    resolved = (kind or "").strip().lower()
    if resolved not in {"mock", "live", "swarm"}:
        resolved = "mock" if mock else "live"
    config_path = config_for_kind(resolved)
    cfg = load_run(config_path)
    if resolved != "mock" and not live_ready():
        raise LiveNotReady(
            "live/swarm needs OPENROUTER_API_KEY, or both ANTHROPIC_API_KEY and "
            "OPENAI_API_KEY (see .env.example)"
        )
    rid = (run_id or cfg.run_id).strip() or cfg.run_id
    with _LOCK:
        if _JOB.status == "running":
            raise JobBusy("a simulation is already running")
        _JOB.status = "running"
        _JOB.run_id = rid
        _JOB.phase = "starting"
        _JOB.mock = resolved == "mock"
        _JOB.kind = resolved
        _JOB.config_path = config_path
        _JOB.log = []
        _JOB.error = None
        _JOB.started_at = time.time()
        _JOB.finished_at = None
        snap = _JOB.snapshot()
    threading.Thread(
        target=_execute, args=(rid, resolved == "mock", config_path), daemon=True
    ).start()
    return snap


def _append(line: str) -> None:
    text = line.rstrip("\n")
    if not text:
        return
    with _LOCK:
        _JOB.log.append(text)
        if len(_JOB.log) > _LOG_CAP:
            _JOB.log = _JOB.log[-_LOG_CAP:]


def _set_phase(phase: str) -> None:
    with _LOCK:
        _JOB.phase = phase


def _execute(run_id: str, mock: bool, config_path: str) -> None:
    root = repo_root()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if mock:
        env["PSBX_MOCK_LLM"] = "1"
    else:
        env.pop("PSBX_MOCK_LLM", None)
    python = sys.executable
    try:
        _append(f"cwd={root}")
        _append(f"python={python}")
        _append(
            f"mock={mock} PSBX_MOCK_LLM={env.get('PSBX_MOCK_LLM', '0')} "
            f"config={config_path} run_id={run_id}"
        )
        _set_phase("run")
        _stream(
            [python, "-m", "psbx", "run", "--config", config_path],
            env,
            root,
        )
        _set_phase("score")
        _stream(
            [python, "-m", "psbx", "score", "--run", run_id],
            env,
            root,
        )
        with _LOCK:
            _JOB.status = "done"
            _JOB.phase = "done"
            _JOB.finished_at = time.time()
        _append("done")
    except Exception as exc:
        with _LOCK:
            _JOB.status = "error"
            _JOB.phase = "error"
            _JOB.error = str(exc)
            _JOB.finished_at = time.time()
        _append(f"error: {exc}")


def _stream(cmd: list[str], env: dict[str, str], cwd) -> None:
    _append("$ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        _append(line)
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"command exited {code}: {' '.join(cmd)}")
