"""Load real repo data for the viewer. Build fixture questions/index if missing."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psbx.config import load_epochs, load_models, load_run
from psbx.corpus.index import HybridIndex, load_index
from psbx.io import read_json, read_jsonl
from psbx.paths import resolve, run_dir, validate_run_id
from psbx.schemas import (
    Epoch,
    ModelConfig,
    Prediction,
    Question,
    RunConfig,
    ScoreReport,
    SwarmVote,
)

QUESTIONS_DIR = "data/questions"
RUNS_DIR = "data/runs"
COIN_FLIP_BRIER = 0.25

CORPORATION_META = {
    "openai": {"label": "OpenAI", "asset": "openai"},
    "anthropic": {"label": "Anthropic", "asset": "anthropic"},
    "google": {"label": "Google", "asset": "google"},
    "meta": {"label": "Meta", "asset": "meta"},
    "qwen": {"label": "Alibaba / Qwen", "asset": "qwen"},
    "local": {"label": "Local lab", "asset": "local"},
}

AGENT_CALLSIGNS = {
    "openai": "VECTOR",
    "anthropic": "SONAR",
    "google": "PRISM",
    "meta": "ATLAS",
    "qwen": "JADE",
    "local": "FORGE",
}

MODEL_CALLSIGNS = {
    "openrouter-gpt-4.1-mini": "VECTOR",
    "openrouter-gpt-4o-mini": "NOVA",
    "openrouter-haiku": "SONAR",
    "openrouter-gemini-flash-lite": "PRISM",
    "openrouter-llama-3.1-8b": "ATLAS",
    "openrouter-qwen-2.5-7b": "JADE",
}


@dataclass
class ViewerState:
    epoch: Epoch
    run: RunConfig
    models: dict[str, ModelConfig]
    questions: list[Question]
    index: HybridIndex
    questions_source: str
    index_source: str
    errors: list[str] = field(default_factory=list)


def bootstrap(epoch_id: str | None = None) -> ViewerState:
    errors: list[str] = []
    epochs = load_epochs()
    base_run = load_run()
    models = load_models()
    selected = epoch_id or base_run.epoch
    if selected not in epochs:
        raise KeyError(f"unknown epoch: {selected}")
    epoch = epochs[selected]
    run = base_run
    if epoch.id != base_run.epoch:
        run = base_run.model_copy(
            update={
                "epoch": epoch.id,
                "question_set": f"{QUESTIONS_DIR}/{epoch.id}.jsonl",
                "run_id": f"viewer-{epoch.id}",
            }
        )

    questions, questions_source, q_err = _load_or_build_questions(epoch, run)
    if q_err:
        errors.append(q_err)

    index, index_source, i_err = _load_or_build_index(epoch, run)
    if i_err:
        errors.append(i_err)

    return ViewerState(
        epoch=epoch,
        run=run,
        models=models,
        questions=questions,
        index=index,
        questions_source=questions_source,
        index_source=index_source,
        errors=errors,
    )


def era_catalog() -> list[dict[str, Any]]:
    """Describe configured epochs without building or mutating their data."""
    rows: list[dict[str, Any]] = []
    for epoch in load_epochs().values():
        corpus_root = resolve(epoch.corpus_index_path)
        docs_path = corpus_root / "documents.jsonl"
        questions_path = _questions_path(epoch.id)
        meta_path = corpus_root / "meta.json"
        has_corpus = docs_path.is_file() and docs_path.stat().st_size > 0
        has_questions = questions_path.is_file() and questions_path.stat().st_size > 0
        n_documents = 0
        n_questions = _count_jsonl(questions_path) if has_questions else 0
        source_types: list[str] = []
        silos: dict[str, int] = {}
        if meta_path.is_file():
            try:
                meta = read_json(meta_path)
                n_documents = int(meta.get("n_docs", n_documents))
                source_types = sorted(str(v) for v in meta.get("source_types", []))
                silos = {
                    str(key): int(value)
                    for key, value in (meta.get("silos") or {}).items()
                }
            except Exception:
                pass
        if has_corpus and not n_documents:
            n_documents = _count_jsonl(docs_path)
        ready = has_corpus and has_questions
        rows.append(
            {
                "id": epoch.id,
                "year": epoch.cutoff_date.year,
                "cutoff_date": epoch.cutoff_date.isoformat(),
                "resolution_window_end": epoch.resolution_window_end.isoformat(),
                "corpus_index_path": epoch.corpus_index_path,
                "has_corpus": has_corpus,
                "has_questions": has_questions,
                "ready": ready,
                "status": "ready" if ready else "not built",
                "n_documents": n_documents,
                "n_questions": n_questions,
                "source_types": source_types,
                "silos": silos,
            }
        )
    return rows


def _questions_path(epoch_id: str) -> Path:
    return resolve(f"{QUESTIONS_DIR}/{epoch_id}.jsonl")


def _load_or_build_questions(
    epoch: Epoch, run: RunConfig
) -> tuple[list[Question], str, str | None]:
    path = _questions_path(epoch.id)
    candidates = [path]
    if run.epoch == epoch.id:
        candidates.append(resolve(run.question_set))
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                return read_jsonl(candidate, Question), f"disk:{candidate}", None
            except Exception as exc:
                return [], f"disk:{candidate}", f"questions unreadable: {exc}"
    try:
        from psbx.questions.build_set import build_questions, write_question_set

        qs = build_questions(epoch, limit=run.n_questions)
    except Exception as exc:
        return [], "missing", f"question build failed: {exc}"
    try:
        write_question_set(epoch, qs)
        return qs, f"generated:{path}", None
    except Exception as exc:
        return qs, "generated:in-memory", f"questions generated but not written: {exc}"


def _load_or_build_index(epoch: Epoch, run: RunConfig) -> tuple[HybridIndex, str, str | None]:
    dest = resolve(epoch.corpus_index_path)
    docs_path = dest / "documents.jsonl"
    err = None
    if docs_path.exists() and docs_path.stat().st_size > 0:
        try:
            return load_index(epoch), f"disk:{dest}", None
        except Exception as exc:
            err = f"index load failed ({exc}); rebuilding from seeds"
    try:
        from psbx.corpus.build_index import build_index

        index = build_index(epoch, live=False, backend=run.embedding_backend)
        note = f"built:{dest}"
        return index, note, err
    except Exception as exc:
        from psbx.corpus.embed import embed_texts
        from psbx.corpus.index import HybridIndex
        from psbx.corpus.prominence import apply_prominence
        from psbx.corpus.seed_documents import seed_documents

        docs = apply_prominence(seed_documents())
        docs = [d for d in docs if d.published_at.date() <= epoch.cutoff_date]
        embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
        return (
            HybridIndex(docs, embeddings, epoch.cutoff_date),
            "in-process:seed_documents",
            f"{err + '; ' if err else ''}index build fell back to seeds: {exc}",
        )


def list_runs() -> list[dict[str, Any]]:
    root = resolve(RUNS_DIR)
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            validate_run_id(child.name)
        except ValueError:
            continue
        preds = _first_existing(child, ("predictions.jsonl", "predictions.json"))
        scores = _first_existing(child, ("scores.json", "results.json", "score_report.json"))
        votes_path = _first_existing(child, ("swarm_votes.jsonl",))
        manifest_path = _first_existing(child, ("manifest.json",))
        manifest: dict[str, Any] = {}
        if manifest_path:
            try:
                manifest = read_json(manifest_path)
            except Exception:
                manifest = {}
        n_preds = _count_jsonl(preds) if preds and preds.suffix == ".jsonl" else 0
        predictions = load_predictions(child.name) if preds else []
        votes: list[SwarmVote] = []
        if votes_path:
            try:
                votes = read_jsonl(votes_path, SwarmVote)
            except Exception:
                votes = []
        composition = list(manifest.get("composition") or [])
        if not composition and votes:
            agent_models = {vote.agent_id: vote.model_id for vote in votes}
            counts = Counter(agent_models.values())
            models = load_models()
            composition = [
                {
                    "model_id": model_id,
                    "label": models[model_id].label if model_id in models else model_id,
                    "model_slug": (
                        models[model_id].model_name if model_id in models else model_id
                    ),
                    "count": count,
                }
                for model_id, count in sorted(counts.items())
            ]
        report = load_score_report(child.name) if scores else None
        primary_model = None
        if report and "swarm-median" in report.brier_by_model:
            primary_model = "swarm-median"
        elif report and report.brier_by_model:
            primary_model = min(report.brier_by_model, key=report.brier_by_model.get)
        scored_questions = len({prediction.question_id for prediction in predictions})
        modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc).isoformat()
        from leaderboard.explain import run_label

        rows.append(
            {
                "run_id": child.name,
                "path": str(child),
                "label": manifest.get("label") or run_label(child.name),
                "epoch_id": manifest.get("epoch_id"),
                "kind": manifest.get("kind") or ("swarm" if votes else "recorded"),
                "status": manifest.get("status") or "recorded",
                "created_at": manifest.get("created_at") or modified,
                "finished_at": manifest.get("finished_at"),
                "duration_s": manifest.get("duration_s"),
                "source_type": manifest.get("source_type") or "all",
                "sandbox_mode": manifest.get("sandbox_mode") or "unknown",
                "n_agents": int(
                    manifest.get("n_agents")
                    or sum(int(row.get("count") or 0) for row in composition)
                    or len({prediction.model_id for prediction in predictions})
                ),
                "n_questions": int(
                    manifest.get("n_questions")
                    or scored_questions
                ),
                "n_scored_questions": scored_questions,
                "n_votes": len(votes),
                "composition": composition,
                "population_selection": manifest.get("population_selection"),
                "dataset_selection": manifest.get("dataset_selection"),
                "has_predictions": bool(preds),
                "has_scores": bool(scores),
                "has_log": bool(_first_existing(child, ("run.log",))),
                "n_predictions": n_preds,
                "predictions_path": str(preds) if preds else None,
                "scores_path": str(scores) if scores else None,
                "primary_model": primary_model,
                "primary_brier": (
                    report.brier_by_model.get(primary_model)
                    if report is not None and primary_model is not None
                    else None
                ),
                "primary_c_index": (
                    report.c_index_by_model.get(primary_model)
                    if report is not None and primary_model is not None
                    else None
                ),
                "goal_target_brier": (
                    report.baselines.get("prior_signal") if report is not None else None
                ),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)


def list_runs_for_epoch(epoch_id: str, questions: list[Question]) -> list[dict[str, Any]]:
    """Return only run folders that can be attributed to the selected epoch."""
    question_ids = {q.id for q in questions}
    rows: list[dict[str, Any]] = []
    for row in list_runs():
        if row.get("epoch_id") == epoch_id or epoch_id in row["run_id"]:
            rows.append(row)
            continue
        preds = load_predictions(row["run_id"])
        belongs = any(p.question_id in question_ids for p in preds)
        if belongs:
            rows.append(row)
    return rows


def build_goal_progress(
    runs: list[dict[str, Any]], benchmark_questions: int
) -> dict[str, Any]:
    """Measure progress toward beating the public prior on the full benchmark.

    Quality starts at a 0.25 coin-flip Brier and reaches 100% when the run
    matches the epoch's public-prior Brier. Coverage is the share of benchmark
    questions actually scored. Overall progress multiplies the two so a strong
    one-question demo cannot claim the full research milestone.
    """
    points: list[dict[str, Any]] = []
    denominator_questions = max(1, int(benchmark_questions))
    for run in runs:
        score = run.get("primary_brier")
        target = run.get("goal_target_brier")
        if score is None or target is None:
            continue
        score = float(score)
        target = float(target)
        if target >= COIN_FLIP_BRIER:
            quality = 1.0 if score <= target else 0.0
        else:
            quality = (COIN_FLIP_BRIER - score) / (COIN_FLIP_BRIER - target)
            quality = max(0.0, min(1.0, quality))
        scored_questions = int(run.get("n_scored_questions") or 0)
        coverage = max(0.0, min(1.0, scored_questions / denominator_questions))
        progress = quality * coverage
        points.append(
            {
                "run_id": run["run_id"],
                "label": run.get("label") or run["run_id"],
                "created_at": run.get("created_at"),
                "n_agents": int(run.get("n_agents") or 0),
                "n_questions": scored_questions,
                "brier": score,
                "target_brier": target,
                "quality_percent": round(quality * 100, 1),
                "coverage_percent": round(coverage * 100, 1),
                "progress_percent": round(progress * 100, 1),
                "percent_away": round((1.0 - progress) * 100, 1),
                "goal_met": progress >= 1.0,
            }
        )
    points.sort(key=lambda point: str(point.get("created_at") or ""))
    best_so_far = 0.0
    for point in points:
        best_so_far = max(best_so_far, float(point["progress_percent"]))
        point["best_so_far_percent"] = round(best_so_far, 1)
    latest = points[-1] if points else None
    best = max(points, key=lambda point: point["progress_percent"]) if points else None
    target_brier = latest["target_brier"] if latest else None
    return {
        "status": "measured" if points else "no_scored_runs",
        "metric": "Brier probability error",
        "target": "Beat the frozen public prior across the full benchmark",
        "target_brier": target_brier,
        "starting_brier": COIN_FLIP_BRIER,
        "benchmark_questions": denominator_questions,
        "n_scored_runs": len(points),
        "latest": latest,
        "best": best,
        "points": points,
        "human_emulation": {
            "status": "not_measured",
            "label": "Human-decision emulation is not scored yet",
            "requirement": (
                "Add held-out respondent-level survey outcomes before assigning a "
                "human-emulation percentage."
            ),
        },
    }


def _corporation_key(
    model_id: str,
    model_slug: str = "",
    models: dict[str, ModelConfig] | None = None,
) -> str:
    """Map configured model identity to a stable leaderboard corporation."""
    haystack = f"{model_id} {model_slug}".lower()
    if "anthropic" in haystack or "claude" in haystack or model_id == "frontier-a":
        return "anthropic"
    if "google" in haystack or "gemini" in haystack:
        return "google"
    if "meta" in haystack or "llama" in haystack:
        return "meta"
    if "qwen" in haystack or "alibaba" in haystack:
        return "qwen"
    if "openai" in haystack or model_id == "frontier-b":
        return "openai"
    if models and model_id in models:
        provider = str(models[model_id].provider).lower()
        if provider in CORPORATION_META:
            return provider
    return "local"


def _model_type(model_id: str, model_slug: str, models: dict[str, ModelConfig]) -> str:
    haystack = f"{model_id} {model_slug}".lower()
    if "llama" in haystack or "qwen" in haystack or "gpt-oss" in haystack:
        return "Open-weight model"
    if model_id.startswith("local-") or (
        model_id in models and str(models[model_id].provider) == "local_vllm"
    ):
        return "Local model"
    return "Hosted model"


def _agent_callsign(model_id: str, corporation: str, agent_index: int) -> str:
    family = MODEL_CALLSIGNS.get(model_id, AGENT_CALLSIGNS[corporation])
    return f"{family}-{agent_index + 1:02d}"


def _arena_row(bucket: dict[str, Any]) -> dict[str, Any]:
    forecasts = int(bucket.get("n_forecasts") or 0)
    brier = (
        float(bucket.get("error_sum") or 0.0) / forecasts
        if forecasts
        else None
    )
    accuracy = (
        float(bucket.get("correct_sum") or 0.0) / forecasts
        if forecasts
        else None
    )
    return {
        **{key: value for key, value in bucket.items() if not key.endswith("_sum")},
        "n_forecasts": forecasts,
        "n_runs": len(bucket.get("run_ids") or []),
        "brier": None if brier is None else round(brier, 6),
        "accuracy": None if accuracy is None else round(accuracy, 6),
        "arena_score": None if brier is None else round((1.0 - brier) * 100.0, 1),
        "run_ids": sorted(bucket.get("run_ids") or []),
    }


def build_leaderboard(
    runs: list[dict[str, Any]],
    questions: list[Question],
    models: dict[str, ModelConfig],
) -> dict[str, Any]:
    """Build auditable agent, swarm, model, and corporation standings.

    Individual agents are scored directly from saved ``swarm_votes.jsonl`` files.
    Model and corporation standings add ordinary scored predictions, while excluding
    the swarm median so an aggregate result is not counted again as a corporation.
    """
    from leaderboard.explain import model_label

    truth = {
        question.id: 1.0 if question.ground_truth else 0.0
        for question in questions
        if question.ground_truth is not None
    }
    agents: dict[str, dict[str, Any]] = {}
    model_buckets: dict[str, dict[str, Any]] = {}
    corporation_buckets: dict[str, dict[str, Any]] = {}
    per_run_agents: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    per_run_champions: dict[str, str] = {}
    scored_ballots = 0

    def model_bucket(model_id: str, model_slug: str = "") -> dict[str, Any]:
        bucket = model_buckets.get(model_id)
        if bucket is None:
            corporation = _corporation_key(model_id, model_slug, models)
            meta = CORPORATION_META[corporation]
            config = models.get(model_id)
            bucket = {
                "id": model_id,
                "label": model_label(model_id, models),
                "model_slug": model_slug or (config.model_name if config else model_id),
                "model_type": _model_type(model_id, model_slug, models),
                "corporation_id": corporation,
                "corporation": meta["label"],
                "asset": meta["asset"],
                "error_sum": 0.0,
                "correct_sum": 0,
                "n_forecasts": 0,
                "run_ids": set(),
                "agent_ids": set(),
            }
            model_buckets[model_id] = bucket
        return bucket

    def corporation_bucket(corporation: str) -> dict[str, Any]:
        bucket = corporation_buckets.get(corporation)
        if bucket is None:
            meta = CORPORATION_META[corporation]
            bucket = {
                "id": corporation,
                "label": meta["label"],
                "asset": meta["asset"],
                "error_sum": 0.0,
                "correct_sum": 0,
                "n_forecasts": 0,
                "run_ids": set(),
                "model_ids": set(),
                "agent_ids": set(),
            }
            corporation_buckets[corporation] = bucket
        return bucket

    for run in runs:
        run_id = str(run["run_id"])
        votes_path = run_dir(run_id) / "swarm_votes.jsonl"
        votes: list[SwarmVote] = []
        if votes_path.is_file():
            try:
                votes = read_jsonl(votes_path, SwarmVote)
            except Exception:
                votes = []
        for vote in votes:
            if vote.question_id not in truth:
                continue
            outcome = truth[vote.question_id]
            error = (float(vote.probability) - outcome) ** 2
            correct = int((vote.probability >= 0.5) == bool(outcome))
            corporation = _corporation_key(vote.model_id, vote.model_slug, models)
            meta = CORPORATION_META[corporation]
            agent = agents.get(vote.agent_id)
            if agent is None:
                agent = {
                    "id": vote.agent_id,
                    "label": _agent_callsign(vote.model_id, corporation, vote.agent_index),
                    "agent_index": vote.agent_index,
                    "model_id": vote.model_id,
                    "model": model_label(vote.model_id, models),
                    "model_slug": vote.model_slug,
                    "model_type": _model_type(vote.model_id, vote.model_slug, models),
                    "corporation_id": corporation,
                    "corporation": meta["label"],
                    "asset": meta["asset"],
                    "perspective": vote.perspective_label or "Unassigned simulation role",
                    "perspective_id": vote.perspective_id,
                    "error_sum": 0.0,
                    "correct_sum": 0,
                    "n_forecasts": 0,
                    "run_ids": set(),
                    "wins": 0,
                }
                agents[vote.agent_id] = agent
            agent["error_sum"] += error
            agent["correct_sum"] += correct
            agent["n_forecasts"] += 1
            agent["run_ids"].add(run_id)

            run_agent = per_run_agents[run_id].setdefault(
                vote.agent_id, {"error_sum": 0.0, "n": 0}
            )
            run_agent["error_sum"] += error
            run_agent["n"] += 1

            mb = model_bucket(vote.model_id, vote.model_slug)
            mb["error_sum"] += error
            mb["correct_sum"] += correct
            mb["n_forecasts"] += 1
            mb["run_ids"].add(run_id)
            mb["agent_ids"].add(vote.agent_id)
            cb = corporation_bucket(corporation)
            cb["error_sum"] += error
            cb["correct_sum"] += correct
            cb["n_forecasts"] += 1
            cb["run_ids"].add(run_id)
            cb["model_ids"].add(vote.model_id)
            cb["agent_ids"].add(vote.agent_id)
            scored_ballots += 1

        for prediction in load_predictions(run_id):
            if prediction.question_id not in truth or prediction.model_id == "swarm-median":
                continue
            outcome = truth[prediction.question_id]
            error = (float(prediction.probability) - outcome) ** 2
            correct = int((prediction.probability >= 0.5) == bool(outcome))
            mb = model_bucket(prediction.model_id)
            mb["error_sum"] += error
            mb["correct_sum"] += correct
            mb["n_forecasts"] += 1
            mb["run_ids"].add(run_id)
            corporation = str(mb["corporation_id"])
            cb = corporation_bucket(corporation)
            cb["error_sum"] += error
            cb["correct_sum"] += correct
            cb["n_forecasts"] += 1
            cb["run_ids"].add(run_id)
            cb["model_ids"].add(prediction.model_id)
            scored_ballots += 1

    for run_id, run_agents in per_run_agents.items():
        means = {
            agent_id: row["error_sum"] / row["n"]
            for agent_id, row in run_agents.items()
            if row["n"]
        }
        if not means:
            continue
        per_run_champions[run_id] = min(
            means,
            key=lambda agent_id: (means[agent_id], agents[agent_id]["label"]),
        )
        winning_brier = min(means.values())
        for agent_id, brier in means.items():
            if abs(brier - winning_brier) <= 1e-12 and agent_id in agents:
                agents[agent_id]["wins"] += 1

    agent_rows = [_arena_row(row) for row in agents.values()]
    agent_rows.sort(
        key=lambda row: (row["brier"] is None, row["brier"], -row["n_forecasts"], row["label"])
    )
    for rank, row in enumerate(agent_rows, 1):
        row["rank"] = rank

    model_rows = []
    for bucket in model_buckets.values():
        bucket["n_agents"] = len(bucket.pop("agent_ids"))
        model_rows.append(_arena_row(bucket))
    model_rows.sort(
        key=lambda row: (row["brier"] is None, row["brier"], -row["n_forecasts"], row["label"])
    )
    for rank, row in enumerate(model_rows, 1):
        row["rank"] = rank

    corporation_rows = []
    for bucket in corporation_buckets.values():
        bucket["n_models"] = len(bucket.pop("model_ids"))
        bucket["n_agents"] = len(bucket.pop("agent_ids"))
        corporation_rows.append(_arena_row(bucket))
    corporation_rows.sort(
        key=lambda row: (row["brier"] is None, row["brier"], -row["n_forecasts"], row["label"])
    )
    for rank, row in enumerate(corporation_rows, 1):
        row["rank"] = rank

    run_lookup = {str(run["run_id"]): run for run in runs}
    swarm_rows: list[dict[str, Any]] = []
    for run in runs:
        if not int(run.get("n_votes") or 0) or run.get("primary_brier") is None:
            continue
        run_id = str(run["run_id"])
        brier = float(run["primary_brier"])
        champion_id = per_run_champions.get(run_id)
        swarm_rows.append(
            {
                "id": run_id,
                "label": run.get("label") or run_id,
                "status": run.get("status") or "recorded",
                "asset": "swarm",
                "brier": round(brier, 6),
                "arena_score": round((1.0 - brier) * 100.0, 1),
                "c_index": run.get("primary_c_index"),
                "n_agents": int(run.get("n_agents") or 0),
                "n_questions": int(run.get("n_scored_questions") or run.get("n_questions") or 0),
                "n_votes": int(run.get("n_votes") or 0),
                "created_at": run.get("created_at"),
                "source_type": run.get("source_type") or "all",
                "has_log": bool(run.get("has_log")),
                "has_predictions": bool(run.get("has_predictions")),
                "beats_prior": bool(
                    run.get("goal_target_brier") is not None
                    and brier < float(run["goal_target_brier"])
                ),
                "champion_agent": agents[champion_id]["label"] if champion_id else None,
                "composition": run.get("composition") or [],
            }
        )
    swarm_rows.sort(key=lambda row: (row["brier"], -row["n_questions"], row["label"]))
    for rank, row in enumerate(swarm_rows, 1):
        row["rank"] = rank

    dates = [str(run.get("created_at")) for run in run_lookup.values() if run.get("created_at")]
    return {
        "status": "measured" if agent_rows or swarm_rows else "empty",
        "updated_at": max(dates) if dates else None,
        "rules": {
            "primary_metric": "Brier probability error; lower is better",
            "arena_score": "100 × (1 − mean Brier); higher is better",
            "accuracy": "Share of forecasts on the correct side of 50%",
            "scope": "Saved forecasts with known later ground truth in this epoch",
        },
        "summary": {
            "n_agents": len(agent_rows),
            "n_swarms": len(swarm_rows),
            "n_models": len(model_rows),
            "n_corporations": len(corporation_rows),
            "n_scored_ballots": scored_ballots,
        },
        "agents": agent_rows,
        "swarms": swarm_rows,
        "models": model_rows,
        "corporations": corporation_rows,
    }


def load_predictions(run_id: str | None = None) -> list[Prediction]:
    root = resolve(RUNS_DIR)
    if not root.exists():
        return []
    dirs = [run_dir(run_id)] if run_id else sorted(p for p in root.iterdir() if p.is_dir())
    preds: list[Prediction] = []
    for folder in dirs:
        path = _first_existing(folder, ("predictions.jsonl",))
        if path:
            try:
                preds.extend(read_jsonl(path, Prediction))
            except Exception:
                continue
        path_json = _first_existing(folder, ("predictions.json",))
        if path_json:
            try:
                raw = json.loads(path_json.read_text(encoding="utf-8"))
                rows = raw if isinstance(raw, list) else raw.get("predictions", [])
                preds.extend(Prediction.model_validate(row) for row in rows)
            except Exception:
                continue
    return preds


def load_score_report(run_id: str | None = None) -> ScoreReport | None:
    root = resolve(RUNS_DIR)
    if not root.exists():
        return None
    dirs = [run_dir(run_id)] if run_id else sorted(p for p in root.iterdir() if p.is_dir())
    for folder in dirs:
        path = _first_existing(folder, ("scores.json", "results.json", "score_report.json"))
        if not path:
            continue
        try:
            return ScoreReport.model_validate(read_json(path))
        except Exception:
            continue
    return None


def compute_scores(
    questions: list[Question],
    models: list[ModelConfig],
    run_id: str,
    preds: list[Prediction] | None = None,
) -> dict[str, Any]:
    """Prefer on-disk ScoreReport; else score predictions; always include baselines."""
    from psbx.scoring.baselines import baseline_scores

    payload: dict[str, Any] = {
        "source": "baselines-only",
        "run_id": run_id,
        "baselines": baseline_scores(questions) if questions else {},
        "report": None,
        "prior_signal": None,
    }
    if questions:
        payload["prior_signal"] = _prior_signal_view(questions, run_id)

    disk = load_score_report(run_id)
    if disk is not None:
        payload["source"] = "disk"
        payload["report"] = _dump(disk)
        payload["run_id"] = run_id
        return _with_explain(payload, models)

    preds = preds if preds is not None else load_predictions(run_id)
    if not preds or not questions:
        return _with_explain(payload, models)
    try:
        from psbx.scoring.report import score_run
    except Exception:
        return _with_explain(payload, models)
    used_models = [m for m in models if any(p.model_id == m.id for p in preds)]
    if not used_models:
        # Predictions may use ids not in config/models.yaml.
        from datetime import date

        used_models = [
            ModelConfig(
                id=mid,
                provider="local_vllm",
                model_name=mid,
                declared_pretraining_cutoff=date(2012, 1, 1),
                is_instruction_tuned=False,
            )
            for mid in sorted({p.model_id for p in preds})
        ]
    report = score_run(preds, questions, used_models, run_id)
    payload["source"] = "computed"
    payload["report"] = _dump(report)
    payload["run_id"] = run_id
    return _with_explain(payload, used_models)


def _with_explain(
    payload: dict[str, Any], models: list[ModelConfig] | dict[str, ModelConfig]
) -> dict[str, Any]:
    from leaderboard.explain import explain_scores

    by_id = models if isinstance(models, dict) else {m.id: m for m in models}
    payload["explain"] = explain_scores(payload, by_id)
    return payload


def _prior_signal_view(questions: list[Question], run_id: str) -> dict[str, Any]:
    from psbx.scoring.baselines import as_predictions
    from psbx.scoring.brier import brier, brier_index
    from psbx.scoring.calibration import calibration_curve
    from psbx.scoring.concordance import concordance_index

    qs = {q.id: q for q in questions}
    preds = as_predictions(
        questions,
        run_id,
        "prior_signal",
        lambda q: q.prior_signal.probability if q.prior_signal else 0.5,
    )
    score = brier(preds, qs)
    c, n_pairs = concordance_index(preds, qs)
    return {
        "brier": score,
        "brier_index": brier_index(score),
        "c_index": c,
        "c_index_pairs": n_pairs,
        "calibration": _dump(calibration_curve(preds, qs)),
    }


def forecast_rows(
    preds: list[Prediction],
    questions: list[Question],
    *,
    reveal_truth: bool,
    limit: int,
) -> list[dict[str, Any]]:
    qs = {q.id: q for q in questions}
    rows: list[dict[str, Any]] = []
    for p in preds[:limit]:
        dump = p.model_dump(mode="json")
        dump.pop("raw_response", None)
        q = qs.get(p.question_id)
        dump["question_text"] = q.text if q else None
        dump["category"] = q.category if q else None
        dump["prior"] = q.prior_signal.probability if q and q.prior_signal else None
        if reveal_truth and q is not None:
            outcome = 1.0 if q.ground_truth else 0.0
            dump["ground_truth"] = q.ground_truth
            dump["item_brier"] = (p.probability - outcome) ** 2
        else:
            dump["ground_truth"] = None
            dump["item_brier"] = None
        rows.append(dump)
    return rows


def public_question(q: Question, reveal_truth: bool) -> dict[str, Any]:
    row = q.model_dump(mode="json")
    if not reveal_truth:
        row["ground_truth"] = None
        row["ground_truth_hidden"] = True
    else:
        row["ground_truth_hidden"] = False
    return row


def public_document_row(doc) -> dict[str, Any]:
    return {
        "document_id": doc.id,
        "title": doc.title,
        "outlet": doc.outlet,
        "published_at": doc.published_at.isoformat(),
        "source_type": doc.source_type,
        "prominence": doc.prominence,
        "url": doc.url,
    }


def _first_existing(folder: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = folder / name
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _count_jsonl(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return json.loads(model.model_dump_json())
    return model
