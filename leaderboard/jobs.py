"""Background host-side `psbx run` then `psbx score` for the viewer."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from psbx.config import load_models, load_run, load_swarm
from psbx.env import live_ready, load_dotenv, provider_status
from psbx.io import read_json, write_json
from psbx.paths import repo_root, resolve, run_dir as resolve_run_dir, validate_run_id
from psbx.schemas import RunConfig, SwarmRoster, SwarmSpecies

_LOCK = threading.Lock()
_LOG_CAP = 400
MOCK_CONFIG = "config/run.yaml"
LIVE_CONFIG = "config/run-phase2.yaml"
OPENROUTER_CONFIG = "config/run-openrouter.yaml"
SWARM_CONFIG = "config/run-swarm.yaml"
ISOLATED_MOCK_CONFIG = "config/run-sandbox.yaml"
MAX_SWARM_AGENTS = 100
MAX_RUN_QUESTIONS = 50
SWARM_PRESET_SIZES = (6, 12, 25, 50, 100)
UTC = timezone.utc


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


def config_for_kind(kind: str, *, isolated: bool = False) -> str:
    if kind == "mock":
        return ISOLATED_MOCK_CONFIG if isolated else MOCK_CONFIG
    if kind == "swarm":
        return SWARM_CONFIG
    return live_config_path()


class JobBusy(RuntimeError):
    pass


class LiveNotReady(RuntimeError):
    pass


class EraNotRunnable(RuntimeError):
    pass


class SandboxNotReady(RuntimeError):
    pass


class InvalidSwarm(RuntimeError):
    pass


def _balanced_counts(total: int, model_ids: list[str]) -> dict[str, int]:
    base, remainder = divmod(total, len(model_ids))
    return {
        model_id: base + (1 if index < remainder else 0)
        for index, model_id in enumerate(model_ids)
    }


def swarm_options() -> dict[str, Any]:
    """Return the safe OpenRouter species and reusable swarm-size presets."""
    roster = load_swarm()
    models = load_models()
    default_counts = {body.model_id: body.count for body in roster.bodies}
    model_ids = [body.model_id for body in roster.bodies]
    species = []
    for body in roster.bodies:
        model = models[body.model_id]
        species.append(
            {
                "model_id": body.model_id,
                "label": model.label or body.model_id,
                "model_slug": model.model_name,
                "provider": model.provider,
                "notes": body.notes,
                "default_count": body.count,
            }
        )
    presets = [
        {
            "id": f"balanced-{size}",
            "label": f"Balanced {size}",
            "n_agents": size,
            "counts": _balanced_counts(size, model_ids),
        }
        for size in SWARM_PRESET_SIZES
    ]
    return {
        "ceiling": MAX_SWARM_AGENTS,
        "question_ceiling": MAX_RUN_QUESTIONS,
        "default_preset": "balanced-12",
        "default_counts": default_counts,
        "species": species,
        "presets": presets,
        "execution": "sequential",
        "shared_retrieval": roster.shared_retrieval,
        "minimum_seconds_per_call": 2,
    }


def _normalize_swarm_bodies(rows: list[dict[str, Any]] | None) -> list[SwarmSpecies]:
    roster = load_swarm()
    templates = {body.model_id: body for body in roster.bodies}
    if rows is None:
        return list(roster.bodies)
    counts: dict[str, int] = {}
    for row in rows:
        model_id = str(row.get("model_id") or "").strip()
        if model_id not in templates:
            raise InvalidSwarm(f"model {model_id!r} is not an allowed swarm species")
        count = int(row.get("count") or 0)
        if count < 0:
            raise InvalidSwarm("agent counts cannot be negative")
        counts[model_id] = counts.get(model_id, 0) + count
    total = sum(counts.values())
    if not 1 <= total <= MAX_SWARM_AGENTS:
        raise InvalidSwarm(f"swarm must contain 1 to {MAX_SWARM_AGENTS} agents")
    return [
        templates[model_id].model_copy(update={"count": count})
        for model_id, count in counts.items()
        if count
    ]


def _new_run_id(epoch_id: str, kind: str, n_agents: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")[:-3].lower()
    return f"{epoch_id}-{kind}-{n_agents}-{stamp}z"


def _clean_label(value: str | None, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    return clean[:80] or fallback


def _composition(config: RunConfig) -> list[dict[str, Any]]:
    models = load_models()
    if config.use_swarm:
        roster = load_swarm(config.swarm_roster or "config/swarm.yaml")
        return [
            {
                "model_id": body.model_id,
                "label": models[body.model_id].label or body.model_id,
                "model_slug": models[body.model_id].model_name,
                "count": body.count,
                "temperature": body.temperature,
            }
            for body in roster.bodies
            if body.model_id in models
        ]
    return [
        {
            "model_id": model_id,
            "label": models[model_id].label or model_id,
            "model_slug": models[model_id].model_name,
            "count": 1,
            "temperature": models[model_id].temperature,
        }
        for model_id in config.models
        if model_id in models
    ]


def _dashboard_config(
    config: RunConfig,
    config_path: str,
    *,
    kind: str,
    isolated: bool,
    source_type: str | None,
    run_id: str | None,
    n_questions: int | None = None,
    swarm_bodies: list[dict[str, Any]] | None = None,
    unique_run: bool = False,
) -> tuple[RunConfig, str]:
    """Create an ignored, run-specific config and optional custom swarm roster."""
    bodies = _normalize_swarm_bodies(swarm_bodies) if config.use_swarm else []
    n_agents = sum(body.count for body in bodies) if bodies else len(config.models)
    if unique_run:
        # Dashboard launches are append-only experiments. Never allow a caller-
        # supplied id to select or overwrite a filesystem path.
        rid = _new_run_id(config.epoch, kind, n_agents)
    else:
        rid = validate_run_id((run_id or config.run_id).strip() or config.run_id)
        if source_type and run_id is None and not rid.endswith(f"-{source_type}"):
            rid = f"{rid}-{source_type}"
        if isolated and config.sandbox_mode != "container" and run_id is None:
            rid = f"{rid}-container"
    run_dir = resolve_run_dir(rid)
    roster_path: str | None = config.swarm_roster
    if config.use_swarm and (unique_run or swarm_bodies is not None):
        base_roster = load_swarm(config.swarm_roster or "config/swarm.yaml")
        roster = SwarmRoster.model_validate(
            {
                **base_roster.model_dump(mode="json"),
                "name": f"{rid}-{n_agents}",
                "n_agents": n_agents,
                "bodies": [body.model_dump(mode="json") for body in bodies],
                "rate_limit_note": (
                    f"{n_agents} agents, sequential OpenRouter calls; dashboard ceiling "
                    f"is {MAX_SWARM_AGENTS}."
                ),
            }
        )
        roster_dest = run_dir / "swarm.yaml"
        roster_dest.parent.mkdir(parents=True, exist_ok=True)
        roster_dest.write_text(
            yaml.safe_dump(roster.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        roster_path = str(roster_dest)
    questions = int(n_questions if n_questions is not None else config.n_questions)
    if not 1 <= questions <= MAX_RUN_QUESTIONS:
        raise InvalidSwarm(f"question count must be 1 to {MAX_RUN_QUESTIONS}")
    updates = {
        **config.model_dump(mode="json"),
        "run_id": rid,
        "source_type": source_type,
        "sandbox_mode": "container" if isolated else config.sandbox_mode,
        "n_questions": questions,
        "swarm_roster": roster_path,
    }
    prepared = RunConfig.model_validate(updates)
    if prepared == config and not unique_run:
        return prepared, config_path
    dest = (
        run_dir / "run.yaml"
        if unique_run
        else resolve(f"data/runs/.dashboard/{kind}-{prepared.epoch}-{source_type or 'all'}.yaml")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(prepared.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )
    return prepared, str(dest)


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
    label: str = ""
    n_agents: int = 0
    n_questions: int = 0
    source_type: str = "all"
    composition: list[dict[str, Any]] = field(default_factory=list)

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
            "label": self.label,
            "n_agents": self.n_agents,
            "n_questions": self.n_questions,
            "source_type": self.source_type,
            "composition": list(self.composition),
        }


_JOB = JobState()


def get_job() -> dict[str, Any]:
    with _LOCK:
        return _JOB.snapshot()


def ready() -> dict[str, Any]:
    load_dotenv()
    status = provider_status()
    live_cfg = live_config_path(status)
    mock_cfg = load_run(MOCK_CONFIG)
    return {
        "providers": status,
        "live_ready": live_ready(),
        "mock_config": MOCK_CONFIG,
        "live_config": live_cfg,
        "live_run_id": load_run(live_cfg).run_id,
        "mock_run_id": mock_cfg.run_id,
        "run_epoch": mock_cfg.epoch,
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
        "swarm_options": swarm_options(),
    }


def _manifest_path(run_key: str) -> Path:
    return resolve_run_dir(run_key) / "manifest.json"


def _update_manifest(run_key: str, **updates: Any) -> None:
    path = _manifest_path(run_key)
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            payload = {}
    payload.update(updates)
    write_json(path, payload)


def start_job(
    *,
    run_id: str | None = None,
    mock: bool = True,
    kind: str | None = None,
    epoch_id: str | None = None,
    isolated: bool = False,
    source_type: str | None = None,
    n_questions: int | None = None,
    swarm_bodies: list[dict[str, Any]] | None = None,
    label: str | None = None,
    unique_run: bool = False,
) -> dict[str, Any]:
    load_dotenv()
    resolved = (kind or "").strip().lower()
    if resolved not in {"mock", "live", "swarm"}:
        resolved = "mock" if mock else "live"
    config_path = config_for_kind(resolved, isolated=isolated)
    cfg = load_run(config_path)
    if epoch_id and cfg.epoch != epoch_id:
        raise EraNotRunnable(
            f"{epoch_id} has no {resolved} run config yet; selected config targets {cfg.epoch}"
        )
    if resolved != "mock" and not live_ready():
        raise LiveNotReady(
            "live/swarm needs OPENROUTER_API_KEY, or both ANTHROPIC_API_KEY and "
            "OPENAI_API_KEY (see .env.example)"
        )
    cfg, config_path = _dashboard_config(
        cfg,
        config_path,
        kind=resolved,
        isolated=isolated,
        source_type=source_type,
        run_id=run_id,
        n_questions=n_questions,
        swarm_bodies=swarm_bodies,
        unique_run=unique_run,
    )
    rid = cfg.run_id
    composition = _composition(cfg)
    n_agents = sum(int(row["count"]) for row in composition)
    fallback_label = (
        f"Swarm of {n_agents}"
        if cfg.use_swarm
        else "Practice run"
        if resolved == "mock"
        else f"Live mix of {n_agents}"
    )
    display_label = _clean_label(label, fallback_label)
    started_at = time.time()
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
        _JOB.started_at = started_at
        _JOB.finished_at = None
        _JOB.label = display_label
        _JOB.n_agents = n_agents
        _JOB.n_questions = cfg.n_questions
        _JOB.source_type = str(cfg.source_type or "all")
        _JOB.composition = composition
        snap = _JOB.snapshot()
    _update_manifest(
        rid,
        schema_version=1,
        run_id=rid,
        label=display_label,
        epoch_id=cfg.epoch,
        kind=resolved,
        status="running",
        phase="starting",
        created_at=datetime.now(UTC).isoformat(),
        started_at=started_at,
        finished_at=None,
        duration_s=None,
        source_type=str(cfg.source_type or "all"),
        sandbox_mode=cfg.sandbox_mode,
        n_agents=n_agents,
        n_questions=cfg.n_questions,
        estimated_model_calls=n_agents * cfg.n_questions,
        composition=composition,
        config_path=str(config_path),
        roster_path=cfg.swarm_roster,
        log_path=str(resolve_run_dir(rid) / "run.log"),
    )
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
        run_id = _JOB.run_id
    log_path = resolve_run_dir(run_id) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        handle.write(f"{stamp} {text}\n")


def _set_phase(phase: str) -> None:
    with _LOCK:
        _JOB.phase = phase
        run_id = _JOB.run_id
    _update_manifest(run_id, phase=phase, status="running")


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
            finished_at = _JOB.finished_at
            started_at = _JOB.started_at
        _update_manifest(
            run_id,
            status="done",
            phase="done",
            finished_at=finished_at,
            duration_s=(finished_at - started_at) if started_at else None,
        )
        _append("done")
    except Exception as exc:
        with _LOCK:
            _JOB.status = "error"
            _JOB.phase = "error"
            _JOB.error = str(exc)
            _JOB.finished_at = time.time()
            finished_at = _JOB.finished_at
            started_at = _JOB.started_at
        _update_manifest(
            run_id,
            status="error",
            phase="error",
            error=str(exc),
            finished_at=finished_at,
            duration_s=(finished_at - started_at) if started_at else None,
        )
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
