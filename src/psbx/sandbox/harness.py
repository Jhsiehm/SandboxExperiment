"""Phase 1 harness: agent loop on the host.

Search may be in-process (host) or a libfaketime Docker sidecar (`container`).
The LLM always stays on the host so vendor APIs still work.
"""

from __future__ import annotations

import os

from psbx.agents.runner import skip_reason
from psbx.agents.single_agent import run_single_agent
from psbx.agents.swarm import SWARM_MEDIAN_ID, load_roster, require_swarm_ready, run_swarm
from psbx.corpus.index import HybridIndex, load_index
from psbx.io import read_jsonl, write_jsonl
from psbx.paths import resolve
from psbx.sandbox.citations import validate_citations
from psbx.sandbox.client import HttpSearchClient, LocalSearchClient
from psbx.sandbox.clock import DEFAULT_SOCKET
from psbx.schemas import Epoch, ModelConfig, Prediction, Question, RunConfig, SwarmVote


def search_client_for(run: RunConfig, index: HybridIndex):
    if run.sandbox_mode != "container":
        return LocalSearchClient(index, min_prominence=run.min_prominence)
    sock = resolve(DEFAULT_SOCKET)
    if sock.exists():
        return HttpSearchClient(uds=str(sock))
    return HttpSearchClient(base_url="http://127.0.0.1:8766")


def run_question(
    question: Question,
    model: ModelConfig,
    epoch: Epoch,
    run_id: str,
    *,
    index: HybridIndex | None = None,
    client: object | None = None,
    max_tool_calls: int = 12,
    min_prominence: float = 0.0,
) -> Prediction:
    index = index or load_index(epoch)
    search_client = client or LocalSearchClient(index, min_prominence=min_prominence)
    pred = run_single_agent(
        question,
        model,
        epoch,
        run_id,
        search_client,
        max_tool_calls=max_tool_calls,
    )
    return validate_citations(pred, index)


def run_set(
    questions: list[Question],
    models: list[ModelConfig],
    epoch: Epoch,
    run: RunConfig,
) -> list[Prediction]:
    if run.use_swarm:
        return run_swarm_set(questions, epoch, run)
    index = load_index(epoch)
    client = search_client_for(run, index)
    chosen = questions[: run.n_questions]
    dest = resolve(f"data/runs/{run.run_id}/predictions.jsonl")
    existing: list[Prediction] = []
    if dest.exists() and dest.stat().st_size > 0:
        existing = read_jsonl(dest, Prediction)
    done = {(p.model_id, p.question_id) for p in existing}
    preds = list(existing)
    for model in models:
        if os.environ.get("PSBX_MOCK_LLM", "0") != "1":
            reason = skip_reason(model)
            if reason:
                if run.allow_mock is False and model.provider != "local_vllm":
                    raise RuntimeError(f"{model.id}: {reason}")
                print(f"skip {model.id}: {reason}")
                continue
        for question in chosen:
            key = (model.id, question.id)
            if key in done:
                print(f"resume skip {model.id} {question.id}")
                continue
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
            preds.append(pred)
            done.add(key)
            write_jsonl(dest, preds)
    return preds


def run_swarm_set(
    questions: list[Question],
    epoch: Epoch,
    run: RunConfig,
) -> list[Prediction]:
    """Sequential 12-agent median. One scored row per question (swarm-median)."""
    roster = load_roster(run.swarm_roster or "config/swarm.yaml")
    workers = require_swarm_ready(roster)
    n_q = max(1, min(run.n_questions, len(questions)))
    n_calls = len(workers) * n_q
    print(
        f"swarm {len(workers)} agents × {n_q} questions = {n_calls} OpenRouter calls "
        "(serialized, ≥2s/req). A full 12×50 pass is hours. Keep --limit small.",
        flush=True,
    )
    index = load_index(epoch)
    client = search_client_for(run, index)
    chosen = questions[: run.n_questions]
    dest = resolve(f"data/runs/{run.run_id}/predictions.jsonl")
    votes_dest = resolve(f"data/runs/{run.run_id}/swarm_votes.jsonl")
    existing: list[Prediction] = []
    if dest.exists() and dest.stat().st_size > 0:
        existing = read_jsonl(dest, Prediction)
    votes: list[SwarmVote] = []
    if votes_dest.exists() and votes_dest.stat().st_size > 0:
        votes = read_jsonl(votes_dest, SwarmVote)
    done = {(p.model_id, p.question_id) for p in existing}
    preds = list(existing)
    n_fetch = max(1, run.max_tool_calls - 1) if run.max_tool_calls else 3
    for question in chosen:
        key = (SWARM_MEDIAN_ID, question.id)
        if key in done:
            print(f"resume skip {SWARM_MEDIAN_ID} {question.id}")
            continue
        result = run_swarm(
            question,
            epoch,
            run.run_id,
            client,
            roster=roster,
            max_retrieval=n_fetch,
        )
        pred = validate_citations(result.prediction, index)
        preds.append(pred)
        votes.extend(result.votes)
        done.add(key)
        write_jsonl(dest, preds)
        write_jsonl(votes_dest, votes)
    return preds
