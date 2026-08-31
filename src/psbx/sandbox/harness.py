"""Phase 1 harness: agent loop on the host.

Search may be in-process (host) or a libfaketime Docker sidecar (`container`).
The LLM always stays on the host so vendor APIs still work.
"""

from __future__ import annotations

import os

from psbx.agents.runner import skip_reason
from psbx.agents.single_agent import run_single_agent
from psbx.corpus.index import HybridIndex, load_index
from psbx.io import read_jsonl, write_jsonl
from psbx.paths import resolve
from psbx.sandbox.citations import validate_citations
from psbx.sandbox.client import HttpSearchClient, LocalSearchClient
from psbx.sandbox.clock import DEFAULT_SOCKET
from psbx.schemas import Epoch, ModelConfig, Prediction, Question, RunConfig


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
