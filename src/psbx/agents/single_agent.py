"""Phase 1 baseline: single agent, search/fetch/reason loop."""

from __future__ import annotations

import os
import time
from typing import Any

from psbx.agents.runner import (
    ParseError,
    Turn,
    complete_turn,
    execute_tool,
    parse_action,
    parse_prediction_json,
    sanitize_openai_message,
    system_prompt,
    user_prompt,
)
from psbx.sandbox.client import ForecastSearchClient, SearchClient
from psbx.schemas import Epoch, ModelConfig, Prediction, Question

YES_CUES = (
    "widely expected",
    "must-pass",
    "working assumption",
    "high probability",
    "plausible",
    "continues to hold",
    "still the consensus",
    "both parties publicly support",
)
NO_CUES = (
    "rarely become law",
    "remote",
    "low-probability",
    "will not take up",
    "died in the senate",
    "without an agreement",
    "lack nine votes",
    "not scheduled",
    "faces an uncertain",
    "tail risk",
)


def run_single_agent(
    question: Question,
    model: ModelConfig,
    epoch: Epoch,
    run_id: str,
    client: SearchClient,
    *,
    max_tool_calls: int = 12,
) -> Prediction:
    t0 = time.perf_counter()
    # The transport may be reused across an entire run, but each forecast owns
    # independent query history and a fresh hard allowance.
    forecast_client = ForecastSearchClient(client, max_tool_calls)
    if os.environ.get("PSBX_MOCK_LLM", "0") == "1":
        pred = _mock_loop(
            question, model, epoch, run_id, forecast_client, max_tool_calls
        )
        pred.latency_s = time.perf_counter() - t0
        return pred
    pred = _live_loop(
        question, model, epoch, run_id, forecast_client, max_tool_calls
    )
    pred.latency_s = time.perf_counter() - t0
    return pred


def _live_loop(
    question: Question,
    model: ModelConfig,
    epoch: Epoch,
    run_id: str,
    client: SearchClient,
    max_tool_calls: int,
) -> Prediction:
    system = system_prompt(epoch.cutoff_date)
    user = user_prompt(question)
    if model.provider == "anthropic":
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    raw_chunks: list[str] = []
    parsed: dict | None = None
    attempts = 0
    for _ in range(max_tool_calls + 4):
        allow_tools = client.n_calls < max_tool_calls
        turn = complete_turn(model, messages, system=system, tools=allow_tools)
        raw_chunks.append(turn.text or json_preview(turn))
        if turn.tool_calls and allow_tools:
            # Fulfill every tool_call in the turn. Slicing leftover ids is an
            # OpenRouter/OpenAI 400 ("assistant tool_calls must be followed by
            # tool messages").
            _append_assistant(model, messages, turn)
            if model.provider == "anthropic":
                blocks = []
                for call in turn.tool_calls:
                    observation = execute_tool(client, call.name, call.arguments)
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": observation,
                        }
                    )
                messages.append({"role": "user", "content": blocks})
            else:
                for call in turn.tool_calls:
                    observation = execute_tool(client, call.name, call.arguments)
                    _append_tool_result(model, messages, call, observation)
            continue
        if turn.tool_calls and not allow_tools:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have used all tool calls. Output ONLY the JSON object "
                        "with probability, reasoning, and citations. Do not call tools."
                    ),
                }
            )
            continue
        react = parse_action(turn.text or "")
        if react and client.n_calls < max_tool_calls:
            kind, arg = react
            payload = {"query": arg} if kind == "search" else {"document_id": arg}
            observation = execute_tool(client, kind, payload)
            messages.append({"role": "assistant", "content": turn.text})
            messages.append({"role": "user", "content": observation})
            continue
        attempts += 1
        try:
            parsed = parse_prediction_json(turn.text or "")
            break
        except (ParseError, ValueError) as exc:
            if attempts >= 2:
                raise ParseError(f"parse failed after retry: {exc}") from exc
            _append_assistant(model, messages, turn)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Parse error: {exc}. Output the JSON object only. "
                        "Do not invent a default probability."
                    ),
                }
            )
    if parsed is None:
        raise ParseError("loop ended without a valid prediction")
    return Prediction(
        run_id=run_id,
        question_id=question.id,
        model_id=model.id,
        probability=parsed["probability"],
        reasoning=parsed["reasoning"],
        citations=parsed["citations"],
        search_queries=list(client.queries),
        n_tool_calls=client.n_calls,
        latency_s=0.0,
        raw_response="\n---\n".join(raw_chunks),
        parse_attempts=max(1, attempts),
    )


def json_preview(turn: Turn) -> str:
    if turn.tool_calls:
        names = ", ".join(c.name for c in turn.tool_calls)
        return f"[tool_calls: {names}]"
    return ""


def _append_assistant(model: ModelConfig, messages: list[dict[str, Any]], turn: Turn) -> None:
    if model.provider == "anthropic":
        content = turn.anthropic_content or [{"type": "text", "text": turn.text}]
        messages.append({"role": "assistant", "content": content})
        return
    if turn.openai_message:
        messages.append(sanitize_openai_message(turn.openai_message))
        return
    messages.append({"role": "assistant", "content": turn.text or ""})


def _append_tool_result(
    model: ModelConfig,
    messages: list[dict[str, Any]],
    call,
    observation: str,
) -> None:
    if model.provider == "anthropic":
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": observation,
                    }
                ],
            }
        )
        return
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": observation,
        }
    )


def _mock_loop(
    question: Question,
    model: ModelConfig,
    epoch: Epoch,
    run_id: str,
    client: SearchClient,
    max_tool_calls: int,
) -> Prediction:
    """Retrieval heuristic used when PSBX_MOCK_LLM=1. Not a silent Brier default."""
    del epoch, max_tool_calls
    hits = client.search(question.text, k=5)
    if not hits:
        raise ParseError("mock agent retrieved no documents")
    fetched = client.fetch(hits[0].document_id)
    text = fetched["text"]
    blob = " ".join(h.snippet for h in hits) + " " + text
    lower = blob.lower()
    yes = sum(1 for c in YES_CUES if c in lower)
    no = sum(1 for c in NO_CUES if c in lower)
    p = 0.5 + 0.08 * (yes - no)
    p = min(0.85, max(0.15, p))
    span = text.strip()[:180]
    if len(span) < 20:
        span = text.strip()
    return Prediction(
        run_id=run_id,
        question_id=question.id,
        model_id=model.id,
        probability=p,
        reasoning=(
            "Retrieval heuristic over contemporaneous snippets "
            f"(yes_cues={yes}, no_cues={no}). Frozen date enforced by the index."
        ),
        citations=[
            {
                "document_id": fetched["id"],
                "quoted_span": span,
                "supports": "yes" if p >= 0.5 else "no",
            }
        ],
        search_queries=list(client.queries),
        n_tool_calls=client.n_calls,
        raw_response="MOCK_RETRIEVAL_HEURISTIC",
        parse_attempts=1,
    )
