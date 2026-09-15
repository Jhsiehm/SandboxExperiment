"""Run the e2012 forecast through AgentSociety-shaped env + agent specs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from psbx.config import load_epochs, load_models, load_run
from psbx.corpus.index import load_index
from psbx.io import read_jsonl, write_json, write_jsonl
from psbx.paths import repo_root
from psbx.paths import run_dir as resolve_run_dir
from psbx.run_provenance import ensure_run_provenance
from psbx.sandbox.citations import validate_citations
from psbx.sandbox.harness import (
    prepare_spend_guard,
    require_question_epoch,
    run_question,
    search_client_for,
)
from psbx.schemas import Prediction, Question, RunConfig, SwarmVote
from psbx.society.adapters import EnvSearchClient
from psbx.society.as2_config import export_society_bundle, swarm_agent_specs

WORKSPACE = repo_root()


def _ensure_workspace_on_path() -> None:
    import sys

    root = str(WORKSPACE)
    if root not in sys.path:
        sys.path.insert(0, root)


def agent_specs_for_models(model_ids: list[str]) -> list[dict]:
    """AgentSociety metadata-first specs; one forecaster per model config."""
    specs = []
    for i, mid in enumerate(model_ids, start=1):
        specs.append(
            {
                "id": i,
                "profile": {
                    "name": f"forecaster-{mid}",
                    "role": "historical forecaster",
                    "bio": "Uses only FrozenEpochEnv search/fetch as of the cutoff date.",
                },
                "config": {"model_id": mid, "agent_class": "ForecasterAgent"},
            }
        )
    return specs


def bind_frozen_env(
    epoch_id: str,
    min_prominence: float = 0.0,
    source_type: str | None = None,
):
    _ensure_workspace_on_path()
    from custom.envs.frozen_epoch_env import FrozenEpochEnv

    epoch = load_epochs()[epoch_id]
    index = load_index(epoch, source_type=source_type)
    env = FrozenEpochEnv()
    env.bind_index(index, epoch.cutoff_date, epoch.id, min_prominence=min_prominence)
    return env, epoch, index


def run_society(
    run: RunConfig,
    *,
    limit: int | None = None,
    config_path: str | Path | None = None,
) -> list[Prediction]:
    """Route every search/fetch through FrozenEpochEnv, then existing scoring JSONL."""
    n = limit if limit is not None else run.n_questions
    if limit is not None:
        run = run.model_copy(update={"n_questions": n})
    all_questions = read_jsonl(run.question_set, Question)
    if run.use_swarm:
        prepare_spend_guard(all_questions, [], run)
        return run_society_swarm(run, limit=limit, config_path=config_path)
    env, epoch, index = bind_frozen_env(run.epoch, run.min_prominence, source_type=run.source_type)
    models = load_models()
    chosen = [models[mid] for mid in run.models]
    qs = all_questions[:n]
    require_question_epoch(qs, epoch)
    prepare_spend_guard(qs, chosen, run)
    dest = resolve_run_dir(run.run_id) / "predictions.jsonl"
    ensure_run_provenance(run, epoch, index, qs, [dest])
    existing: list[Prediction] = []
    if dest.exists() and dest.stat().st_size > 0:
        existing = read_jsonl(dest, Prediction)
    done = {(p.model_id, p.question_id) for p in existing}
    preds = list(existing)
    run_dir = resolve_run_dir(run.run_id) / "society"
    run_dir.mkdir(parents=True, exist_ok=True)
    backend = try_as2_router(env)
    write_steps_clock(run.run_id, epoch.cutoff_date.isoformat())
    write_json(
        run_dir / "agent_specs.json",
        {
            "agent_specs": agent_specs_for_models(run.models),
            "agent_class_name": "ForecasterAgent",
            "backend": backend,
        },
    )
    for model in chosen:
        if os.environ.get("PSBX_MOCK_LLM", "0") != "1":
            from psbx.agents.runner import skip_reason

            reason = skip_reason(model)
            if reason:
                if run.allow_mock is False and model.provider != "local_vllm":
                    raise RuntimeError(f"{model.id}: {reason}")
                print(f"skip {model.id}: {reason}")
                continue
        for question in qs:
            key = (model.id, question.id)
            if key in done:
                continue
            env.queries = []
            env.n_calls = 0
            client = (
                search_client_for(run, index)
                if run.sandbox_mode == "container"
                else EnvSearchClient(env, agent_id=1)
            )
            pred = run_question(
                question,
                model,
                epoch,
                run.run_id,
                index=index,
                client=client,
                max_tool_calls=run.max_tool_calls,
                min_prominence=run.min_prominence,
            )
            pred = validate_citations(pred, index)
            preds.append(pred)
            done.add(key)
            write_jsonl(dest, preds)
    return preds


def run_society_swarm(
    run: RunConfig,
    *,
    limit: int | None = None,
    config_path: str | Path | None = None,
) -> list[Prediction]:
    """12-agent swarm through FrozenEpochEnv, plus AgentSociety 2 config export.

    Votes stay on the serialized OpenRouter path (species mix + rate limits).
    The sibling AgentSociety clone is used for InitConfig / workspaces / CLI
    shape — not for Ray city simulation.
    """
    from psbx.agents.swarm import SWARM_MEDIAN_ID, load_roster, run_swarm

    n = limit if limit is not None else run.n_questions
    env, epoch, index = bind_frozen_env(run.epoch, run.min_prominence, source_type=run.source_type)
    qs = read_jsonl(run.question_set, Question)[:n]
    require_question_epoch(qs, epoch)
    dest = resolve_run_dir(run.run_id) / "predictions.jsonl"
    votes_dest = resolve_run_dir(run.run_id) / "swarm_votes.jsonl"
    ensure_run_provenance(run, epoch, index, qs, [dest, votes_dest])
    run_dir = resolve_run_dir(run.run_id) / "society"
    roster = load_roster(run.swarm_roster or "config/swarm.yaml")
    specs = swarm_agent_specs(roster)
    from psbx.society.perspectives import assign_personas, load_perspectives

    try:
        path = run.perspectives or "config/perspectives.yaml"
        env.bind_personas(assign_personas(roster, load_perspectives(path)))
    except (FileNotFoundError, ValueError):
        pass
    export_society_bundle(
        run,
        qs,
        run_dir,
        roster=roster,
    )
    write_steps_clock(run.run_id, epoch.cutoff_date.isoformat())
    write_json(
        run_dir / "agent_specs.json",
        {
            "agent_specs": specs,
            "agent_class_name": "ForecasterAgent",
            "backend": try_as2_router(env),
            "n_agents": len(specs),
        },
    )
    existing: list[Prediction] = []
    if dest.exists() and dest.stat().st_size > 0:
        existing = read_jsonl(dest, Prediction)
    votes: list[SwarmVote] = []
    if votes_dest.exists() and votes_dest.stat().st_size > 0:
        votes = read_jsonl(votes_dest, SwarmVote)
    done = {(p.model_id, p.question_id) for p in existing}
    preds = list(existing)
    if run.max_tool_calls < 2:
        raise ValueError("swarm retrieval requires max_tool_calls >= 2")
    client = (
        search_client_for(run, index)
        if run.sandbox_mode == "container"
        else EnvSearchClient(env, agent_id=1)
    )
    for question in qs:
        key = (SWARM_MEDIAN_ID, question.id)
        if key in done:
            continue
        env.queries = []
        env.n_calls = 0
        result = run_swarm(
            question,
            epoch,
            run.run_id,
            client,
            roster=roster,
            max_retrieval=run.max_tool_calls,
            perspectives_path=run.perspectives,
        )
        pred = validate_citations(result.prediction, index)
        preds.append(pred)
        votes.extend(result.votes)
        done.add(key)
        write_jsonl(dest, preds)
        write_jsonl(votes_dest, votes)
    del config_path
    return preds


def try_as2_router(env: object) -> str:
    """Optional: spin CodeGenRouter when agentsociety2 is installed."""
    try:
        from agentsociety2.env import CodeGenRouter

        CodeGenRouter(env_modules=[env])
        return "agentsociety2"
    except Exception:
        return "shim"


def write_steps_clock(run_id: str, cutoff: str) -> Path:
    dest = resolve_run_dir(run_id) / "society" / "clock.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "now": cutoff,
                "source": "epoch.cutoff_date",
                "written_at": datetime.now(timezone.utc).isoformat(),
                "mock": os.environ.get("PSBX_MOCK_LLM", "0"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return dest


def load_experiment_run(config: str | Path | None = None) -> RunConfig:
    path = config or "config/run.yaml"
    return load_run(path)
