"""Load real repo data for the viewer. Build fixture questions/index if missing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psbx.config import load_epochs, load_models, load_run
from psbx.corpus.index import HybridIndex, load_index
from psbx.io import read_json, read_jsonl
from psbx.paths import resolve
from psbx.schemas import Epoch, ModelConfig, Prediction, Question, RunConfig, ScoreReport

QUESTIONS_DIR = "data/questions"
RUNS_DIR = "data/runs"


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


def bootstrap() -> ViewerState:
    errors: list[str] = []
    epochs = load_epochs()
    run = load_run()
    models = load_models()
    epoch = epochs.get(run.epoch) or next(iter(epochs.values()))

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


def _questions_path(epoch_id: str) -> Path:
    return resolve(f"{QUESTIONS_DIR}/{epoch_id}.jsonl")


def _load_or_build_questions(epoch: Epoch, run: RunConfig) -> tuple[list[Question], str, str | None]:
    path = _questions_path(epoch.id)
    configured = resolve(run.question_set)
    for candidate in (path, configured):
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
        preds = _first_existing(child, ("predictions.jsonl", "predictions.json"))
        scores = _first_existing(child, ("scores.json", "results.json", "score_report.json"))
        n_preds = _count_jsonl(preds) if preds and preds.suffix == ".jsonl" else 0
        rows.append(
            {
                "run_id": child.name,
                "path": str(child),
                "has_predictions": bool(preds),
                "has_scores": bool(scores),
                "n_predictions": n_preds,
                "predictions_path": str(preds) if preds else None,
                "scores_path": str(scores) if scores else None,
            }
        )
    return rows


def load_predictions(run_id: str | None = None) -> list[Prediction]:
    root = resolve(RUNS_DIR)
    if not root.exists():
        return []
    dirs = [root / run_id] if run_id else sorted(p for p in root.iterdir() if p.is_dir())
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
    dirs = [root / run_id] if run_id else sorted(p for p in root.iterdir() if p.is_dir())
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
    if disk is None and not preds:
        # Any run on disk, not just the configured id.
        disk = load_score_report(None)
    if disk is not None:
        payload["source"] = "disk"
        payload["report"] = _dump(disk)
        payload["run_id"] = disk.run_id
        return _with_explain(payload, models)

    preds = preds if preds is not None else load_predictions(run_id) or load_predictions(None)
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
    report = score_run(preds, questions, used_models, preds[0].run_id)
    payload["source"] = "computed"
    payload["report"] = _dump(report)
    payload["run_id"] = report.run_id
    return _with_explain(payload, used_models)


def _with_explain(payload: dict[str, Any], models: list[ModelConfig] | dict[str, ModelConfig]) -> dict[str, Any]:
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
