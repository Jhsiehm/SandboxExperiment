"""Sequential 12-agent society: shared retrieval, JSON votes, median p.

Default experiment lives in ``config/swarm.yaml`` (single source of truth):

- 12 agents, planned cheap mix (not the OpenRouter catalog), 2 of each:
  ``gpt-4.1-mini``, ``gpt-4o-mini``, Haiku, Gemini Flash-Lite,
  Llama 3.1 8B Instruct, Qwen2.5 7B Instruct (OpenRouter slugs).
- Each worker: short JSON ``{p, rationale}``, no chain-of-thought, max_tokens
  256, temperature ~0.8. Agents only read a shared search pack.
- OpenRouter calls stay serialized through the existing limiter
  (OPENROUTER_MIN_INTERVAL_SEC=2, OPENROUTER_MAX_PER_MINUTE=20, concurrency 1).
  12 agents × N questions at ≥2s/req is slow on purpose — keep ``--limit`` /
  ``n_questions`` small (default 1). Do not weaken those env caps.

``local-llama-3.1-8b`` / ``local-qwen-2.5-7b`` stay vLLM-only. The OpenRouter
twins (``openrouter-llama-3.1-8b``, ``openrouter-qwen-2.5-7b``) are in the 12.

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
    CONDITIONER_SOURCE_TYPES,
    Citation,
    Epoch,
    ModelConfig,
    PerspectivePersona,
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
FLASH_LITE_VOICE = (
    "You are an ordinary newspaper reader, not a specialist. Guess from the "
    "pack the way a person on the street would. Do not think out loud. "
    "Do not search. Forecast only from the evidence pack."
)
OPEN_WEIGHT_VOICE = (
    "You are a small open-weight chat model. Be blunt and short. "
    "Do not think out loud. Do not search. Forecast only from the evidence pack."
)


@dataclass
class SearchPack:
    queries: list[str]
    hits_text: str
    docs: list[dict[str, Any]]
    n_hits: int
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
    name = f"{model.id} {model.model_name or ''}".lower()
    if "haiku" in name:
        return HAIKU_VOICE
    if "gemini" in name or "flash-lite" in name or "flash_lite" in name:
        return FLASH_LITE_VOICE
    if "llama" in name or "qwen" in name:
        return OPEN_WEIGHT_VOICE
    return MINI_VOICE


def _persona_for_index(
    index: int, personas: list[PerspectivePersona]
) -> PerspectivePersona | None:
    if 0 <= index < len(personas):
        return personas[index]
    return None


def _persona_block(persona: PerspectivePersona | None) -> str:
    if persona is None:
        return ""
    return (
        f"{persona.prompt_block()}\n"
        "The evidence pack has two layers: (1) STIMULUS = contemporaneous "
        "headlines/news/media the public saw; (2) CONDITIONERS = surveys, "
        "political ads, and academic studies. Forecast the later public/"
        "political outcome as this constituency would react. Do not browse."
    )


def _worker_system(
    model: ModelConfig,
    cutoff,
    persona: PerspectivePersona | None = None,
) -> str:
    frozen = system_prompt(cutoff)
    persona_txt = _persona_block(persona)
    extra = f"\n\n{persona_txt}" if persona_txt else ""
    return (
        f"{frozen}\n\n{_voice_for(model)}{extra}\n"
        "Output ONLY a JSON object with this shape:\n"
        '{"p": 0.34, "rationale": "at most forty words, no chain of thought"}\n'
        "p is the probability the question resolves YES, in [0, 1]."
    )


def _pack_excerpt(doc: dict[str, Any]) -> str:
    text = str(doc.get("text") or "").strip()
    if len(text) > PACK_EXCERPT_CHARS:
        return text[:PACK_EXCERPT_CHARS] + "…"
    return text


def _hit_line(hit: Any) -> str:
    kind = getattr(hit, "source_type", None) or ""
    prefix = f"{kind} | " if kind else ""
    return (
        f"{prefix}{hit.document_id} | {hit.outlet} | {hit.published_at.date()} | "
        f"{hit.title} | {hit.snippet}"
    )


def _merge_hits(primary: list[Any], extra: list[Any]) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for hit in [*primary, *extra]:
        doc_id = str(getattr(hit, "document_id", "") or "")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        merged.append(hit)
    return merged


def build_search_pack(
    question: Question,
    client: SearchClient,
    *,
    k: int = PACK_SEARCH_K,
    n_fetch: int = PACK_FETCH_DEFAULT,
) -> SearchPack:
    """One retrieval per question. Workers only read the resulting pack.

    Main hits are the media stimulus. A second cutoff-filtered pull prefers
    survey/ad/academic conditioners so Track B can see them without extra
    OpenRouter calls.
    """
    before = int(getattr(client, "n_calls", 0))
    hits = client.search(question.text, k=k)
    cond_hits: list[Any] = []
    try:
        cond_hits = client.search(
            question.text,
            k=3,
            source_types=sorted(CONDITIONER_SOURCE_TYPES),
        )
    except TypeError:
        cond_hits = []
    merged = _merge_hits(hits, cond_hits)
    if not merged:
        raise ParseError("shared retrieval returned no documents")
    stimulus_lines = [
        _hit_line(h)
        for h in merged
        if getattr(h, "source_type", None) not in CONDITIONER_SOURCE_TYPES
    ]
    conditioner_lines = [
        _hit_line(h)
        for h in merged
        if getattr(h, "source_type", None) in CONDITIONER_SOURCE_TYPES
    ]
    sections = []
    if stimulus_lines:
        sections.append("STIMULUS (contemporaneous media):\n" + "\n".join(stimulus_lines))
    if conditioner_lines:
        sections.append(
            "CONDITIONERS (survey / ad / academic):\n" + "\n".join(conditioner_lines)
        )
    if not sections:
        sections.append("\n".join(_hit_line(h) for h in merged))
    docs: list[dict[str, Any]] = []
    fetch_ids = [h.document_id for h in merged[: max(1, n_fetch)]]
    for hit in merged:
        if hit.document_id in fetch_ids:
            continue
        kind = getattr(hit, "source_type", None)
        if kind in CONDITIONER_SOURCE_TYPES and len(fetch_ids) < n_fetch + 2:
            fetch_ids.append(hit.document_id)
    seen_fetch: set[str] = set()
    for document_id in fetch_ids:
        if document_id in seen_fetch:
            continue
        seen_fetch.add(document_id)
        try:
            docs.append(client.fetch(document_id))
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
        hits_text="\n\n".join(sections),
        docs=docs,
        n_hits=len(merged),
        n_tool_calls=n_calls,
        citations=citations,
    )


def _pack_user_block(pack: SearchPack) -> str:
    blocks = [pack.hits_text]
    for doc in pack.docs:
        excerpt = _pack_excerpt(doc)
        kind = doc.get("source_type") or ""
        layer = (
            "CONDITIONER"
            if kind in CONDITIONER_SOURCE_TYPES
            else "STIMULUS"
        )
        blocks.append(
            f"{layer} FETCH {doc.get('id')} source_type={kind}\n"
            f"title={doc.get('title')}\n"
            f"published_at={doc.get('published_at')}\n{excerpt}"
        )
    return "\n\n".join(blocks)


def _worker_user(
    question: Question,
    pack: SearchPack,
    persona: PerspectivePersona | None = None,
) -> str:
    persona_line = (
        f"Persona: {persona.label} ({persona.id}).\n" if persona is not None else ""
    )
    return (
        f"{persona_line}"
        f"Question id: {question.id}\n"
        f"Resolution date: {question.resolution_date.isoformat()}\n"
        f"Resolution criteria: {question.resolution_criteria}\n\n"
        f"{question.text}\n\n"
        "Shared contemporaneous evidence pack (do not browse; do not call tools).\n"
        "STIMULUS = headlines/news the public saw. "
        "CONDITIONERS = surveys, ads, academic studies.\n"
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
    from psbx.society.perspectives import assign_personas, load_perspectives

    t0 = time.perf_counter()
    roster = roster or load_roster()
    workers = require_swarm_ready(roster)
    output = model or load_models()[SWARM_MEDIAN_ID]
    personas_path = getattr(roster, "perspectives", None)
    try:
        catalog = load_perspectives(personas_path or "config/perspectives.yaml")
        personas = assign_personas(roster, catalog)
    except FileNotFoundError:
        personas = []
    pack = build_search_pack(question, client, n_fetch=max_retrieval)
    print(
        "activity "
        + json.dumps(
            {
                "kind": "shared_retrieval",
                "epoch_id": epoch.id,
                "question_id": question.id,
                "n_hits": pack.n_hits,
                "n_documents": len(pack.docs),
                "document_ids": [str(doc.get("id") or "") for doc in pack.docs],
                "queries": pack.queries,
            }
        ),
        flush=True,
    )
    env = getattr(client, "env", None)
    bind = getattr(env, "bind_evidence", None)
    if callable(bind):
        bind(pack)
    bind_p = getattr(env, "bind_personas", None)
    if callable(bind_p) and personas:
        bind_p(personas)
    votes: list[SwarmVote] = []
    if os.environ.get("PSBX_MOCK_LLM") == "1":
        votes = _mock_votes(question, workers, pack, run_id, personas)
    else:
        for index, worker in enumerate(workers):
            persona = _persona_for_index(index, personas)
            votes.append(_live_vote(question, epoch, worker, pack, run_id, index, persona))
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
    persona: PerspectivePersona | None = None,
) -> SwarmVote:
    _refuse_local(worker)
    system = _worker_system(worker, epoch.cutoff_date, persona)
    user = _worker_user(question, pack, persona)
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
        perspective_id=persona.id if persona else "",
        perspective_label=persona.label if persona else "",
    )


def _mock_votes(
    question: Question,
    workers: list[ModelConfig],
    pack: SearchPack,
    run_id: str,
    personas: list[PerspectivePersona] | None = None,
) -> list[SwarmVote]:
    """Deterministic spread around a retrieval heuristic. Not a silent Brier default."""
    from psbx.agents.single_agent import NO_CUES, YES_CUES

    blob = pack.hits_text + " " + " ".join(_pack_excerpt(d) for d in pack.docs)
    lower = blob.lower()
    yes = sum(1 for c in YES_CUES if c in lower)
    no = sum(1 for c in NO_CUES if c in lower)
    base = min(0.85, max(0.15, 0.5 + 0.08 * (yes - no)))
    n = max(len(workers), 1)
    personas = personas or []
    votes: list[SwarmVote] = []
    for index, worker in enumerate(workers):
        offset = 0.02 * (index - (n - 1) / 2)
        p = min(0.95, max(0.05, base + offset))
        persona = _persona_for_index(index, personas)
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
                perspective_id=persona.id if persona else "",
                perspective_label=persona.label if persona else "",
            )
        )
    return votes
