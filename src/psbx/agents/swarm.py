"""Sequential 12-agent society: shared retrieval, JSON votes, median p.

Default experiment lives in ``config/swarm.yaml`` (single source of truth):

- 12 agents: 8 × ``openrouter-gpt-4.1-mini`` (``openai/gpt-4.1-mini``) plus
  4 × ``openrouter-haiku`` (``anthropic/claude-3.5-haiku``, cheap non-thinking).
- Each worker: short JSON ``{p, rationale}``, no chain-of-thought, max_tokens
  256, temperature ~0.8. Agents only read a shared search pack.
- OpenRouter calls stay serialized through the existing limiter
  (OPENROUTER_MIN_INTERVAL_SEC=2, OPENROUTER_MAX_PER_MINUTE=20, concurrency 1).
  12 agents × N questions at ≥2s/req is slow on purpose — keep ``--limit`` /
  ``n_questions`` small (default 1). Do not weaken those env caps.

Optional, not in the default 12:

- Gemini Flash-Lite (``google/gemini-2.5-flash-lite``) for cheapest volume.
- Llama 3.1 8B Instruct and Qwen2.5 7B Instruct as *local-only* scale-up
  (``needs_endpoint``, ``local_vllm``). Never fan those out through
  ``OPENROUTER_API_KEY``.

The scored series is ``swarm-median``. Per-agent votes go to
``swarm_votes.jsonl`` (audit trail: inputs + model slug). Do not dump
AgentSociety source here — ``psbx society run`` is a separate path.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psbx.agents.runner import (
    ParseError,
    complete_turn,
    skip_reason,
    system_prompt,
)
from psbx.config import load_models, load_swarm
from psbx.sandbox.client import SearchClient
from psbx.schemas import (
    Citation,
    Epoch,
    ModelConfig,
    Prediction,
    Question,
    SwarmRoster,
    SwarmSpecies,
    SwarmVote,
)

SWARM_MEDIAN_ID = "swarm-median"
RATIONALE_MAX_WORDS = 40
PACK_FETCH_DEFAULT = 3
PACK_SEARCH_K = 8
PACK_EXCERPT_CHARS = 800

MINI_VOICE = (
    "You are a concise statistical forecaster. Be numerically calibrated. "
    "Do not think out loud. Do not search. Forecast only from the evidence pack."
)
HAIKU_VOICE = (
    "You are a terse newsroom skeptic. Discount hype and treat silence as "
    "information. Do not think out loud. Do not search. Forecast only from "
    "the evidence pack."
)


@dataclass
class SearchPack:
    queries: list[str]
    hits_text: str
    docs: list[dict[str, Any]]
    n_tool_calls: int
    citations: list[Citation]


@dataclass
class SwarmResult:
    prediction: Prediction
    votes: list[SwarmVote] = field(default_factory=list)


def load_roster(path: str | Path = "config/swarm.yaml") -> SwarmRoster:
    return load_swarm(path)


def expand_bodies(roster: SwarmRoster | None = None) -> list[SwarmSpecies]:
    """Repeat each species ``count`` times. Does not call any model."""
    roster = roster or load_roster()
    expanded: list[SwarmSpecies] = []
    for species in roster.bodies:
        for _ in range(species.count):
            expanded.append(species)
    return expanded


def worker_models(roster: SwarmRoster | None = None) -> list[ModelConfig]:
    """Resolve default-12 bodies to ModelConfig. Local scale-up is omitted."""
    models = load_models()
    out: list[ModelConfig] = []
    for species in expand_bodies(roster):
        cfg = models[species.model_id]
        if cfg.needs_endpoint:
            continue
        if cfg.temperature != species.temperature or cfg.max_tokens != species.max_tokens:
            cfg = cfg.model_copy(
                update={"temperature": species.temperature, "max_tokens": species.max_tokens}
            )
        out.append(cfg)
    return out


def median_probability(values: list[float]) -> float:
    if not values:
        raise ParseError("no swarm votes to aggregate")
    return float(statistics.median(values))


def parse_swarm_json(raw: str) -> dict[str, Any]:
    """Short worker JSON: ``p`` / ``probability`` plus a ≤40-word rationale."""
    from psbx.agents.runner import FINAL_RE

    blob = (raw or "").strip()
    if not blob:
        raise ParseError("empty swarm forecast")
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        match = FINAL_RE.search(blob)
        if not match:
            raise ParseError("no JSON object in swarm output") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ParseError("swarm JSON must be an object")
    if "p" not in payload and "probability" not in payload:
        raise ParseError("missing p")
    p = float(payload.get("p", payload.get("probability")))
    if not 0.0 <= p <= 1.0:
        raise ParseError("probability out of range")
    rationale = str(payload.get("rationale") or payload.get("reasoning") or "").strip()
    words = rationale.split()
    if len(words) > RATIONALE_MAX_WORDS:
        rationale = " ".join(words[:RATIONALE_MAX_WORDS])
    return {"probability": p, "rationale": rationale}


def _voice_for(model: ModelConfig) -> str:
    if "haiku" in model.id or "haiku" in (model.model_name or ""):
        return HAIKU_VOICE
    return MINI_VOICE


def _worker_system(model: ModelConfig, cutoff) -> str:
    frozen = system_prompt(cutoff)
    return (
        f"{frozen}\n\n{_voice_for(model)}\n"
        "Output ONLY a JSON object with this shape:\n"
        '{"p": 0.34, "rationale": "at most forty words, no chain of thought"}\n'
        "p is the probability the question resolves YES, in [0, 1]."
    )


def _pack_excerpt(doc: dict[str, Any]) -> str:
    text = str(doc.get("text") or "").strip()
    if len(text) > PACK_EXCERPT_CHARS:
        return text[:PACK_EXCERPT_CHARS] + "…"
    return text


def build_search_pack(
    question: Question,
    client: SearchClient,
    *,
    k: int = PACK_SEARCH_K,
    n_fetch: int = PACK_FETCH_DEFAULT,
) -> SearchPack:
    """One retrieval per question. Workers only read the resulting pack."""
    before = int(getattr(client, "n_calls", 0))
    hits = client.search(question.text, k=k)
    if not hits:
        raise ParseError("shared retrieval returned no documents")
    lines = [
        f"{h.document_id} | {h.outlet} | {h.published_at.date()} | {h.title} | {h.snippet}"
        for h in hits
    ]
    docs: list[dict[str, Any]] = []
    for hit in hits[: max(1, n_fetch)]:
        try:
            docs.append(client.fetch(hit.document_id))
        except Exception:
            continue
    citations: list[Citation] = []
    for doc in docs:
        text = str(doc.get("text") or "").strip()
        span = text[:180] if len(text) >= 20 else text
        if not span:
            continue
        citations.append(
            Citation(
                document_id=str(doc.get("id") or ""),
                quoted_span=span,
                supports="context",
            )
        )
        if len(citations) >= 3:
            break
    if not citations:
        raise ParseError("shared retrieval produced no citable documents")
    n_calls = int(getattr(client, "n_calls", before + 1 + len(docs))) - before
    return SearchPack(
        queries=list(client.queries),
        hits_text="\n".join(lines),
        docs=docs,
        n_tool_calls=n_calls,
        citations=citations,
    )


def _pack_user_block(pack: SearchPack) -> str:
    blocks = [pack.hits_text]
    for doc in pack.docs:
        excerpt = _pack_excerpt(doc)
        blocks.append(
            f"FETCH {doc.get('id')}\n"
            f"title={doc.get('title')}\n"
            f"published_at={doc.get('published_at')}\n{excerpt}"
        )
    return "\n\n".join(blocks)


def _worker_user(question: Question, pack: SearchPack) -> str:
    return (
        f"Question id: {question.id}\n"
        f"Resolution date: {question.resolution_date.isoformat()}\n"
        f"Resolution criteria: {question.resolution_criteria}\n\n"
        f"{question.text}\n\n"
        "Shared contemporaneous evidence pack (do not browse; do not call tools):\n"
        f"{_pack_user_block(pack)}\n\n"
        'Reply with JSON only: {"p": <0-1>, "rationale": "<≤40 words>"}.'
    )


def _refuse_local(model: ModelConfig) -> None:
    if model.needs_endpoint:
        raise RuntimeError(
            f"{model.id} is local-only (needs_endpoint); refusing OpenRouter "
            "so we do not bill OPENROUTER_API_KEY"
        )


def require_swarm_ready(roster: SwarmRoster | None = None) -> list[ModelConfig]:
    """Fail loud before any retrieval if workers cannot be called."""
    workers = worker_models(roster)
    if not workers:
        raise RuntimeError(
            "swarm roster expanded to zero OpenRouter workers "
            "(local Llama/Qwen are never auto-routed onto OPENROUTER_API_KEY)"
        )
    for worker in workers:
        _refuse_local(worker)
        if os.environ.get("PSBX_MOCK_LLM") == "1":
            continue
        reason = skip_reason(worker)
        if reason:
            raise RuntimeError(f"{worker.id}: {reason}")
    return workers


def run_swarm(
    question: Question,
    epoch: Epoch,
    run_id: str,
    client: SearchClient,
    *,
    roster: SwarmRoster | None = None,
    model: ModelConfig | None = None,
    max_retrieval: int = PACK_FETCH_DEFAULT,
) -> SwarmResult:
    """One shared pack, sequential OpenRouter votes, median probability."""
    t0 = time.perf_counter()
    roster = roster or load_roster()
    workers = require_swarm_ready(roster)
    output = model or load_models()[SWARM_MEDIAN_ID]
    pack = build_search_pack(question, client, n_fetch=max_retrieval)
    votes: list[SwarmVote] = []
    if os.environ.get("PSBX_MOCK_LLM") == "1":
        votes = _mock_votes(question, workers, pack, run_id)
    else:
        for index, worker in enumerate(workers):
            votes.append(_live_vote(question, epoch, worker, pack, run_id, index))
    ps = [v.probability for v in votes]
    median = median_probability(ps)
    bits = " ".join(f"{v.agent_id}={v.probability:.3f}" for v in votes)
    print(f"swarm votes {bits}", flush=True)
    print(f"swarm median p={median:.3f} n={len(votes)} question={question.id}", flush=True)
    reasoning = (
        f"Median of {len(votes)} sequential votes (no chairman model). {bits}"
    )
    raw = json.dumps(
        {
            "median": median,
            "votes": [
                {
                    "agent_id": v.agent_id,
                    "model_id": v.model_id,
                    "model_slug": v.model_slug,
                    "p": v.probability,
                    "rationale": v.rationale,
                }
                for v in votes
            ],
        }
    )
    pred = Prediction(
        run_id=run_id,
        question_id=question.id,
        model_id=output.id,
        probability=median,
        reasoning=reasoning[:2000],
        citations=pack.citations,
        search_queries=list(pack.queries),
        n_tool_calls=pack.n_tool_calls,
        latency_s=time.perf_counter() - t0,
        raw_response=raw,
        parse_attempts=max((v.parse_attempts for v in votes), default=1),
    )
    return SwarmResult(prediction=pred, votes=votes)


def _agent_id(model: ModelConfig, index: int) -> str:
    return f"swarm:{model.id}:{index:02d}"


def _live_vote(
    question: Question,
    epoch: Epoch,
    worker: ModelConfig,
    pack: SearchPack,
    run_id: str,
    index: int,
) -> SwarmVote:
    _refuse_local(worker)
    system = _worker_system(worker, epoch.cutoff_date)
    user = _worker_user(question, pack)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    parsed: dict[str, Any] | None = None
    raw_chunks: list[str] = []
    attempts = 0
    for _ in range(2):
        turn = complete_turn(worker, messages, system=system, tools=False)
        raw_chunks.append(turn.text or "")
        attempts += 1
        try:
            parsed = parse_swarm_json(turn.text or "")
            break
        except (ParseError, ValueError, json.JSONDecodeError) as exc:
            if attempts >= 2:
                raise ParseError(
                    f"swarm worker {worker.id} #{index} parse failed after retry: {exc}"
                ) from exc
            messages.append({"role": "assistant", "content": turn.text or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Parse error: {exc}. Output ONLY "
                        '{"p": <0-1>, "rationale": "<≤40 words>"}. '
                        "Do not invent a default probability."
                    ),
                }
            )
    if parsed is None:
        raise ParseError(f"swarm worker {worker.id} #{index} produced no forecast")
    print(
        f"swarm vote {_agent_id(worker, index)} slug={worker.model_name} "
        f"p={parsed['probability']:.3f}",
        flush=True,
    )
    return SwarmVote(
        run_id=run_id,
        question_id=question.id,
        agent_index=index,
        agent_id=_agent_id(worker, index),
        model_id=worker.id,
        model_slug=worker.model_name,
        temperature=worker.temperature,
        max_tokens=worker.max_tokens,
        probability=parsed["probability"],
        rationale=parsed["rationale"],
        raw_response="\n---\n".join(raw_chunks),
        parse_attempts=attempts,
        system_prompt=system,
        search_queries=list(pack.queries),
    )


def _mock_votes(
    question: Question,
    workers: list[ModelConfig],
    pack: SearchPack,
    run_id: str,
) -> list[SwarmVote]:
    """Deterministic spread around a retrieval heuristic. Not a silent Brier default."""
    from psbx.agents.single_agent import NO_CUES, YES_CUES

    blob = pack.hits_text + " " + " ".join(_pack_excerpt(d) for d in pack.docs)
    lower = blob.lower()
    yes = sum(1 for c in YES_CUES if c in lower)
    no = sum(1 for c in NO_CUES if c in lower)
    base = min(0.85, max(0.15, 0.5 + 0.08 * (yes - no)))
    n = max(len(workers), 1)
    votes: list[SwarmVote] = []
    for index, worker in enumerate(workers):
        offset = 0.02 * (index - (n - 1) / 2)
        p = min(0.95, max(0.05, base + offset))
        votes.append(
            SwarmVote(
                run_id=run_id,
                question_id=question.id,
                agent_index=index,
                agent_id=_agent_id(worker, index),
                model_id=worker.id,
                model_slug=worker.model_name,
                temperature=worker.temperature,
                max_tokens=worker.max_tokens,
                probability=p,
                rationale="Mock retrieval heuristic over the shared pack.",
                raw_response="MOCK_SWARM_HEURISTIC",
                parse_attempts=1,
                system_prompt="PSBX_MOCK_LLM=1",
                search_queries=list(pack.queries),
            )
        )
    return votes
