"""Prompt contract, native search/fetch tools, strict JSON parse, one retry.

Never fall back to a default probability — silent defaults poison Brier.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from psbx.sandbox.client import SearchClient
from psbx.schemas import Citation, ModelConfig, Question

FINAL_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM_TEMPLATE = """You are a forecaster dropped into a frozen historical epoch.

Today's date is {today}. Treat that as now. You have no access to anything published
after that date. The search and fetch tools return only contemporaneous documents.

Rules:
1. Use the search and fetch tools to gather evidence before answering.
2. Output a calibrated probability in [0, 1] that the question resolves YES.
3. Every claim must cite a retrieved document. quoted_span must appear verbatim
   in that document.
4. Do not use hindsight. Do not invent documents.
5. When you are ready, output ONLY a JSON object with this shape:
{{
  "probability": 0.34,
  "reasoning": "...",
  "citations": [
    {{"document_id": "...", "quoted_span": "...", "supports": "yes"}}
  ]
}}
supports must be one of: yes, no, context.

You may also issue a single text action per turn if tools are unavailable:
SEARCH <query>
FETCH <document_id>
"""

ANTHROPIC_TOOLS = [
    {
        "name": "search",
        "description": "Search contemporaneous documents available as of the frozen date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch",
        "description": "Fetch the full text of a retrieved document by document_id.",
        "input_schema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
        },
    },
]

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search contemporaneous documents available as of the frozen date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch",
            "description": "Fetch the full text of a retrieved document by document_id.",
            "parameters": {
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
            },
        },
    },
]


def system_prompt(cutoff: date) -> str:
    return SYSTEM_TEMPLATE.format(today=cutoff.isoformat())


def user_prompt(question: Question) -> str:
    return (
        f"Question id: {question.id}\n"
        f"Resolution date: {question.resolution_date.isoformat()}\n"
        f"Resolution criteria: {question.resolution_criteria}\n\n"
        f"{question.text}\n"
    )


class ParseError(ValueError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    anthropic_content: list[dict[str, Any]] | None = None
    openai_message: dict[str, Any] | None = None


def parse_action(text: str) -> tuple[str, str] | None:
    for line in text.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("SEARCH "):
            return "search", line[7:].strip()
        if line.upper().startswith("FETCH "):
            return "fetch", line[6:].strip()
    return None


def parse_prediction_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = FINAL_RE.search(raw)
        if not match:
            raise ParseError("no JSON object in model output") from None
        payload = json.loads(match.group(0))
    if "probability" not in payload:
        raise ParseError("missing probability")
    p = float(payload["probability"])
    if not 0.0 <= p <= 1.0:
        raise ParseError("probability out of range")
    cites = payload.get("citations") or []
    if not cites:
        raise ParseError("citations must be non-empty")
    citations = [Citation.model_validate(c) for c in cites]
    return {
        "probability": p,
        "reasoning": str(payload.get("reasoning") or ""),
        "citations": citations,
    }


def skip_reason(model: ModelConfig) -> str | None:
    """Why this model cannot be called. None means ready."""
    if model.provider == "anthropic":
        return None if os.environ.get("ANTHROPIC_API_KEY") else "ANTHROPIC_API_KEY is not set"
    if model.provider == "openai":
        return None if os.environ.get("OPENAI_API_KEY") else "OPENAI_API_KEY is not set"
    if model.provider == "together":
        return None if os.environ.get("TOGETHER_API_KEY") else "TOGETHER_API_KEY is not set"
    if model.provider == "local_vllm":
        base = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
        try:
            httpx.get(base.rstrip("/") + "/models", timeout=1.5)
        except Exception:
            return f"vLLM not reachable at {base}"
        return None
    return f"unsupported provider {model.provider}"


def execute_tool(client: SearchClient, name: str, arguments: dict[str, Any]) -> str:
    if name == "search":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return "SEARCH ERROR: empty query"
        k = int(arguments.get("k") or 10)
        hits = client.search(query, k=k)
        if not hits:
            return "NO HITS"
        return "\n".join(
            f"{h.document_id} | {h.outlet} | {h.published_at.date()} | {h.title} | {h.snippet}"
            for h in hits
        )
    if name == "fetch":
        doc_id = str(arguments.get("document_id") or "").strip()
        if not doc_id:
            return "FETCH ERROR: empty document_id"
        try:
            doc = client.fetch(doc_id)
        except Exception as exc:
            return f"FETCH ERROR: {exc}"
        return (
            f"id={doc['id']}\ntitle={doc['title']}\n"
            f"published_at={doc['published_at']}\n{doc['text']}"
        )
    return f"unknown tool {name}"


def complete_turn(model: ModelConfig, messages: list[dict[str, Any]], *, system: str) -> Turn:
    if os.environ.get("PSBX_MOCK_LLM", "0") == "1":
        return Turn(text="")
    if model.provider == "anthropic":
        return _anthropic_turn(model, messages, system=system)
    if model.provider == "openai":
        return _openai_turn(
            model,
            messages,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    if model.provider == "together":
        return _openai_turn(
            model,
            messages,
            base_url="https://api.together.xyz/v1",
            api_key=os.environ.get("TOGETHER_API_KEY", ""),
        )
    if model.provider == "local_vllm":
        return _openai_turn(
            model,
            messages,
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "local"),
        )
    raise RuntimeError(f"unsupported provider {model.provider}")


def complete(model: ModelConfig, messages: list[dict[str, str]]) -> str:
    """Text-only completion (ReAct fallback / tests)."""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    body = [m for m in messages if m["role"] != "system"]
    turn = complete_turn(model, body, system=system)
    return turn.text


def _anthropic_turn(model: ModelConfig, messages: list[dict[str, Any]], *, system: str) -> Turn:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model.model_name,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "system": system,
            "tools": ANTHROPIC_TOOLS,
            "messages": messages,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content") or []
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text") or "")
        elif btype == "tool_use":
            raw_input = block.get("input") or {}
            if not isinstance(raw_input, dict):
                raw_input = {}
            calls.append(
                ToolCall(
                    id=str(block.get("id") or ""),
                    name=str(block.get("name") or ""),
                    arguments=raw_input,
                )
            )
    return Turn(text="".join(text_parts), tool_calls=calls, anthropic_content=content)


def _openai_turn(
    model: ModelConfig,
    messages: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
) -> Turn:
    if not api_key:
        raise RuntimeError(f"API key missing for {model.provider}")
    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"authorization": f"Bearer {api_key}"},
        json={
            "model": model.model_name,
            "messages": messages,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
            "tools": OPENAI_TOOLS,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    message = resp.json()["choices"][0]["message"]
    text = message.get("content") or ""
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = raw.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            ToolCall(
                id=str(raw.get("id") or ""),
                name=str(fn.get("name") or ""),
                arguments=args,
            )
        )
    return Turn(text=text, tool_calls=calls, openai_message=message)
