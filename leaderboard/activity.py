"""Operational view of frozen retrieval, container isolation, and agent progress."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from leaderboard.explain import run_label
from leaderboard.store import ViewerState, load_predictions
from psbx.config import load_models, load_run, load_swarm
from psbx.io import read_json, read_jsonl
from psbx.paths import resolve, run_dir
from psbx.schemas import RunConfig, SwarmVote

RUN_CONFIG_GLOBS = ("config/run*.yaml", "data/runs/.dashboard/*.yaml")
VOTE_RE = re.compile(r"^swarm vote (?P<agent>\S+) slug=(?P<slug>\S+) p=(?P<p>[0-9.]+)")


def sandbox_snapshot(epoch_id: str, cutoff: str) -> dict[str, Any]:
    """Read the running sidecar and verify its isolation controls."""
    from psbx.sandbox.docker_sidecar import status as docker_status

    try:
        container = docker_status()
    except Exception as exc:
        container = {
            "container": "psbx-search",
            "running": False,
            "url": "http://127.0.0.1:8766",
            "egress": "unknown",
            "verified_controls": False,
            "error": str(exc),
        }
    health: dict[str, Any] = {}
    clock: dict[str, Any] = {}
    if container.get("running"):
        try:
            base = str(container.get("url") or "http://127.0.0.1:8766").rstrip("/")
            health_response = httpx.get(f"{base}/health", timeout=1.5)
            health_response.raise_for_status()
            health = health_response.json()
            clock_response = httpx.get(f"{base}/clock", timeout=1.5)
            clock_response.raise_for_status()
            clock = clock_response.json()
        except Exception as exc:
            container["health_error"] = str(exc)
    epoch_match = health.get("epoch") == epoch_id
    cutoff_match = health.get("cutoff") == cutoff and clock.get("today") == cutoff
    verified = bool(
        container.get("running")
        and container.get("verified_controls")
        and health.get("status") == "ok"
        and epoch_match
        and cutoff_match
    )
    return {
        **container,
        "mode": "docker" if container.get("running") else "unavailable",
        "health": health,
        "clock": clock,
        "epoch_match": epoch_match,
        "cutoff_match": cutoff_match,
        "selection": health.get("selection") or "unknown",
        "n_documents": int(health.get("n_documents") or 0),
        "verified": verified,
        "live_web": "blocked",
        "retrieval": "read-only frozen index",
        "model_api_egress": "host only; corpus retrieval stays in the sidecar",
    }


def reseal_sandbox(epoch_id: str, source_type: str | None) -> dict[str, Any]:
    """Restart the Docker sidecar on one explicit epoch/source cell."""
    from psbx.sandbox.clock import IMAGE
    from psbx.sandbox.docker_sidecar import build_image, docker_bin, up

    image = subprocess.run(
        [docker_bin(), "image", "inspect", IMAGE],
        capture_output=True,
        text=True,
    )
    if image.returncode != 0:
        build_image()
    up(epoch_id, source_type=source_type)
    from psbx.config import load_epochs

    selected = load_epochs()[epoch_id]
    return sandbox_snapshot(selected.id, selected.cutoff_date.isoformat())


def _run_config(run_id: str, job: dict[str, Any]) -> RunConfig | None:
    candidates: list[Path] = [run_dir(run_id) / "run.yaml"]
    if job.get("run_id") == run_id and job.get("config_path"):
        candidates.append(resolve(str(job["config_path"])))
    for pattern in RUN_CONFIG_GLOBS:
        candidates.extend(sorted(resolve(".").glob(pattern)))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            config = load_run(path)
        except Exception:
            continue
        if config.run_id == run_id:
            return config
    return None


def _load_votes(run_id: str) -> list[SwarmVote]:
    path = run_dir(run_id) / "swarm_votes.jsonl"
    if not path.is_file() or path.stat().st_size == 0:
        return []
    try:
        return read_jsonl(path, SwarmVote)
    except Exception:
        return []


def _saved_run_label(run_id: str) -> str:
    path = run_dir(run_id) / "manifest.json"
    if path.is_file():
        try:
            label = str(read_json(path).get("label") or "").strip()
            if label:
                return label
        except (OSError, ValueError):
            pass
    return run_label(run_id)


def _population_selection(run_id: str, job: dict[str, Any]) -> dict[str, Any] | None:
    if job.get("run_id") == run_id and job.get("population_selection"):
        return dict(job["population_selection"])
    path = run_dir(run_id) / "manifest.json"
    if not path.is_file():
        return None
    try:
        selection = read_json(path).get("population_selection")
    except (OSError, ValueError):
        return None
    if not isinstance(selection, dict):
        return None
    return {
        key: selection.get(key)
        for key in ("population_id", "label", "geography_id", "strategy", "n_agents")
        if selection.get(key) is not None
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _logged_votes(log: list[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in log:
        match = VOTE_RE.match(line.strip())
        if match:
            rows[match.group("agent")] = {
                "model_slug": match.group("slug"),
                "probability": float(match.group("p")),
            }
    return rows


def _timeline(job: dict[str, Any], selected_run: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if job.get("run_id") != selected_run:
        return events
    for line in job.get("log") or []:
        clean = line.strip()
        if clean.startswith("activity "):
            try:
                payload = json.loads(clean.removeprefix("activity "))
                events.append(
                    {
                        "kind": "retrieval",
                        "label": "Shared evidence pack sealed",
                        "detail": (
                            f"{payload.get('n_hits', 0)} hits, "
                            f"{payload.get('n_documents', 0)} documents fetched"
                        ),
                    }
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        elif VOTE_RE.match(clean):
            match = VOTE_RE.match(clean)
            assert match is not None
            events.append(
                {
                    "kind": "agent",
                    "label": match.group("agent"),
                    "detail": f"returned {float(match.group('p')):.0%}",
                }
            )
        elif clean.startswith("swarm median"):
            events.append({"kind": "aggregate", "label": "Median computed", "detail": clean})
        elif clean.startswith("error:"):
            events.append({"kind": "error", "label": "Run stopped", "detail": clean[6:].strip()})
    return events[-30:]


def _swarm_agents(
    config: RunConfig,
    votes: list[SwarmVote],
    job: dict[str, Any],
    run_id: str,
    *,
    allow_unscoped_log: bool = True,
) -> list[dict[str, Any]]:
    from psbx.agents.swarm import expand_bodies
    from psbx.society.perspectives import assign_personas, load_perspectives

    roster = load_swarm(config.swarm_roster or "config/swarm.yaml")
    workers = expand_bodies(roster)
    models = load_models()
    try:
        catalog = load_perspectives(config.perspectives or "config/perspectives.yaml")
        personas = assign_personas(roster, catalog)
    except (FileNotFoundError, ValueError):
        personas = []
    latest_votes: dict[str, SwarmVote] = {}
    vote_counts: Counter[str] = Counter()
    for vote in votes:
        latest_votes[vote.agent_id] = vote
        vote_counts[vote.agent_id] += 1
    logged = (
        _logged_votes(job.get("log") or [])
        if allow_unscoped_log and job.get("run_id") == run_id
        else {}
    )
    active = job.get("status") == "running" and job.get("run_id") == run_id
    finished_ids = set(latest_votes) | set(logged)
    next_index = next(
        (
            index
            for index, species in enumerate(workers)
            if f"swarm:{species.model_id}:{index:02d}" not in finished_ids
        ),
        None,
    )
    rows: list[dict[str, Any]] = []
    for index, species in enumerate(workers):
        agent_id = f"swarm:{species.model_id}:{index:02d}"
        vote = latest_votes.get(agent_id)
        live = logged.get(agent_id) or {}
        model = models.get(species.model_id)
        persona = personas[index] if index < len(personas) else None
        if agent_id in finished_ids:
            status = "complete"
        elif active and index == next_index:
            status = "working"
        elif active:
            status = "queued"
        else:
            status = "idle"
        rows.append(
            {
                "index": index + 1,
                "agent_id": agent_id,
                "model_id": species.model_id,
                "model_label": (model.label if model and model.label else species.model_id),
                "model_slug": (
                    vote.model_slug
                    if vote
                    else live.get("model_slug") or (model.model_name if model else "")
                ),
                "persona_id": vote.perspective_id if vote else (persona.id if persona else ""),
                "persona_label": (
                    vote.perspective_label
                    if vote
                    else (persona.label if persona else "Unassigned simulation role")
                ),
                "status": status,
                "probability": vote.probability if vote else live.get("probability"),
                "rationale": vote.rationale if vote else "",
                "n_votes": vote_counts[agent_id],
            }
        )
    return rows


def _model_agents(config: RunConfig, run_id: str, job: dict[str, Any]) -> list[dict[str, Any]]:
    models = load_models()
    preds = load_predictions(run_id)
    by_model: dict[str, list[Any]] = {}
    for pred in preds:
        by_model.setdefault(pred.model_id, []).append(pred)
    active = job.get("status") == "running" and job.get("run_id") == run_id
    next_model = next((model_id for model_id in config.models if not by_model.get(model_id)), None)
    rows: list[dict[str, Any]] = []
    for index, model_id in enumerate(config.models):
        model = models.get(model_id)
        completed = by_model.get(model_id) or []
        status = (
            "working"
            if active and not completed and model_id == next_model
            else "queued"
            if active
            else "idle"
        )
        if completed:
            status = "complete"
        latest = completed[-1] if completed else None
        rows.append(
            {
                "index": index + 1,
                "agent_id": model_id,
                "model_id": model_id,
                "model_label": model.label if model and model.label else model_id,
                "model_slug": model.model_name if model else "",
                "persona_id": "",
                "persona_label": "Forecasting agent",
                "status": status,
                "probability": latest.probability if latest else None,
                "rationale": latest.reasoning[:240] if latest else "",
                "n_votes": len(completed),
            }
        )
    return rows


def build_activity_payload(
    state: ViewerState,
    run_id: str,
    job: dict[str, Any],
    question_id: str | None = None,
) -> dict[str, Any]:
    """Build a truthful, secret-free activity snapshot for the dashboard."""
    config = _run_config(run_id, job) or state.run.model_copy(update={"run_id": run_id})
    votes = _load_votes(run_id)
    predictions = load_predictions(run_id)
    is_swarm = bool(config.use_swarm or votes)
    persisted_question_ids = _dedupe(
        [vote.question_id for vote in votes]
        + [prediction.question_id for prediction in predictions]
    )
    configured_question_ids = [
        question.id for question in state.questions[: max(1, int(config.n_questions or 1))]
    ]
    chain_question_ids = (
        (persisted_question_ids or configured_question_ids) if is_swarm else []
    )
    selected_question_id = (
        question_id
        if question_id in chain_question_ids
        else chain_question_ids[0]
        if chain_question_ids
        else None
    )
    chain_votes = [vote for vote in votes if vote.question_id == selected_question_id]
    chain_predictions = [
        prediction for prediction in predictions if prediction.question_id == selected_question_id
    ]
    chain_available = bool(is_swarm and selected_question_id)
    agents = (
        _swarm_agents(
            config,
            chain_votes,
            job,
            run_id,
            allow_unscoped_log=config.n_questions <= 1,
        )
        if is_swarm
        else _model_agents(config, run_id, job)
    )
    completed = sum(1 for agent in agents if agent["status"] == "complete")
    evidence_predictions = chain_predictions if chain_available else predictions
    evidence_votes = chain_votes if chain_available else votes
    queries = _dedupe(
        [query for pred in evidence_predictions for query in pred.search_queries]
        + [query for vote in evidence_votes for query in vote.search_queries]
    )
    docs_by_id = {doc.id: doc for doc in state.index.docs}
    evidence_docs: list[dict[str, Any]] = []
    seen_docs: set[str] = set()
    for prediction in evidence_predictions:
        for citation in prediction.citations:
            if citation.document_id in seen_docs:
                continue
            seen_docs.add(citation.document_id)
            doc = docs_by_id.get(citation.document_id)
            evidence_docs.append(
                {
                    "document_id": citation.document_id,
                    "title": doc.title if doc else "Document outside loaded index view",
                    "outlet": doc.outlet if doc else "unknown",
                    "source_type": str(doc.source_type) if doc else "unknown",
                    "published_at": doc.published_at.isoformat() if doc else None,
                    "within_cutoff": bool(
                        doc and doc.published_at.date() <= state.epoch.cutoff_date
                    ),
                }
            )
    sources = Counter(str(doc.source_type) for doc in state.index.docs)
    access = sandbox_snapshot(state.epoch.id, state.epoch.cutoff_date.isoformat())
    config_scope = str(config.source_type or "all")
    access["config_scope"] = config_scope
    access["scope_match"] = access.get("selection") == config_scope
    access["available_sources"] = {"all": len(state.index.docs), **dict(sorted(sources.items()))}
    is_society = "society" in run_id or bool(config.perspectives)
    population_selection = _population_selection(run_id, job)
    question_labels = {question.id: question.text for question in state.questions}
    objective = (
        "Agents use explicit demographic personas and frozen evidence to forecast "
        "later public or political outcomes."
        if is_society or is_swarm
        else "Agents use frozen evidence to forecast later observed outcomes."
    )
    return {
        "epoch": {
            "id": state.epoch.id,
            "cutoff_date": state.epoch.cutoff_date.isoformat(),
            "resolution_window_end": state.epoch.resolution_window_end.isoformat(),
        },
        "experiment": {
            "mode": (
                "demographic-conditioned historical forecast"
                if is_society or is_swarm
                else "historical forecast"
            ),
            "objective": objective,
            "score_target": "later observed ground-truth outcomes",
            "human_emulation_status": (
                "Persona-conditioned responses are visible, but they are not yet validated "
                "against held-out individual survey responses."
            ),
            "next_validation": (
                "Compare demographic response distributions against held-out survey "
                "microdata or toplines."
            ),
        },
        "run": {
            "run_id": run_id,
            "run_label": _saved_run_label(run_id),
            "kind": (
                job.get("kind")
                if job.get("run_id") == run_id
                else ("swarm" if is_swarm else "model mix")
            ),
            "status": job.get("status") if job.get("run_id") == run_id else "recorded",
            "phase": job.get("phase") if job.get("run_id") == run_id else "",
            "sandbox_mode": config.sandbox_mode,
            "shared_retrieval": is_swarm,
            "chain_available": chain_available,
            "chain_reason": (
                ""
                if chain_available
                else "This run does not contain question-scoped shared-retrieval swarm votes."
            ),
            "chain_question_id": selected_question_id,
            "chain_question_label": question_labels.get(
                selected_question_id or "", selected_question_id or ""
            ),
            "chain_questions": [
                {
                    "id": available_id,
                    "label": question_labels.get(available_id, available_id),
                }
                for available_id in chain_question_ids
            ],
            "n_agents": len(agents),
            "n_complete": completed,
            "progress": (completed / len(agents)) if agents else 0.0,
            "population_selection": population_selection,
        },
        "access": access,
        "agents": agents,
        "evidence": {
            "queries": queries,
            "documents": evidence_docs,
            "n_tool_calls": sum(pred.n_tool_calls for pred in evidence_predictions),
            "all_documents_within_cutoff": all(
                doc["within_cutoff"] for doc in evidence_docs
            ),
        },
        "timeline": _timeline(job, run_id),
    }
