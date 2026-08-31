"""FastAPI viewer: static console + search API + repo-backed JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from leaderboard.jobs import JobBusy, LiveNotReady, get_job, ready, start_job
from leaderboard.explain import run_label
from leaderboard.store import (
    ViewerState,
    bootstrap,
    compute_scores,
    forecast_rows,
    list_runs,
    load_predictions,
    public_document_row,
    public_question,
)
from psbx.sandbox.search_service import create_app as create_search_app

STATIC = Path(__file__).resolve().parent / "static"


class RunRequest(BaseModel):
    mock: bool = True
    run_id: str | None = Field(default=None, description="Defaults to config/run.yaml run_id")


def create_viewer(state: ViewerState | None = None) -> FastAPI:
    from psbx.env import load_dotenv

    load_dotenv()
    state = state or bootstrap()
    app = create_search_app(state.index)
    app.title = "psbx-viewer"
    app.state.viewer = state

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(
            STATIC / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        s: ViewerState = app.state.viewer
        runs = list_runs()
        return {
            "epoch": {
                "id": s.epoch.id,
                "cutoff_date": s.epoch.cutoff_date.isoformat(),
                "resolution_window_end": s.epoch.resolution_window_end.isoformat(),
                "corpus_index_path": s.epoch.corpus_index_path,
            },
            "run": s.run.model_dump(mode="json"),
            "n_questions": len(s.questions),
            "n_documents": len(s.index.docs),
            "models": [m.model_dump(mode="json") for m in s.models.values()],
            "questions_source": s.questions_source,
            "index_source": s.index_source,
            "cutoff_filter": f"published_at <= {s.index.cutoff.isoformat()}",
            "runs": runs,
            "errors": s.errors,
            "live_run_id": "phase2-e2012-real",
            "run_labels": {r["run_id"]: run_label(r["run_id"]) for r in runs},
            "connected": {
                "questions": bool(s.questions),
                "corpus": bool(s.index.docs),
                "search": True,
                "predictions": any(r["has_predictions"] for r in runs),
                "scores": any(r["has_scores"] for r in runs),
            },
        }

    @app.get("/api/questions")
    def questions(
        reveal_truth: bool = Query(False),
        category: str | None = None,
    ) -> dict[str, Any]:
        s: ViewerState = app.state.viewer
        rows = s.questions
        if category:
            rows = [q for q in rows if q.category == category]
        counts: dict[str, int] = {}
        for q in s.questions:
            counts[q.category] = counts.get(q.category, 0) + 1
        return {
            "epoch_id": s.epoch.id,
            "cutoff_date": s.epoch.cutoff_date.isoformat(),
            "reveal_truth": reveal_truth,
            "n": len(rows),
            "categories": counts,
            "questions": [public_question(q, reveal_truth) for q in rows],
        }

    @app.get("/api/corpus")
    def corpus(limit: int = Query(80, ge=1, le=500)) -> dict[str, Any]:
        s: ViewerState = app.state.viewer
        leaked = [
            d.id for d in s.index.docs if d.published_at.date() > s.index.cutoff
        ]
        docs = [public_document_row(d) for d in s.index.docs[:limit]]
        return {
            "cutoff_date": s.index.cutoff.isoformat(),
            "assertion": f"hard-filter published_at <= {s.index.cutoff.isoformat()}",
            "n_documents": len(s.index.docs),
            "n_shown": len(docs),
            "n_leaked": len(leaked),
            "source": s.index_source,
            "documents": docs,
        }

    @app.get("/api/runs")
    def runs() -> dict[str, Any]:
        rows = list_runs()
        for row in rows:
            row["label"] = run_label(row["run_id"])
        return {"runs": rows}

    @app.get("/api/runs/{run_id}")
    def run_detail(
        run_id: str,
        limit: int = Query(200, ge=1, le=2000),
        reveal_truth: bool = Query(False),
    ) -> dict[str, Any]:
        s: ViewerState = app.state.viewer
        preds = load_predictions(run_id)
        if not preds and not any(r["run_id"] == run_id for r in list_runs()):
            raise HTTPException(status_code=404, detail="unknown run_id")
        rows = forecast_rows(preds, s.questions, reveal_truth=reveal_truth, limit=limit)
        models = sorted({p.model_id for p in preds})
        return {
            "run_id": run_id,
            "run_label": run_label(run_id),
            "n_predictions": len(preds),
            "n_shown": len(rows),
            "models": models,
            "predictions": rows,
        }

    @app.get("/api/scores")
    def scores(run_id: str | None = None) -> dict[str, Any]:
        s: ViewerState = app.state.viewer
        rid = run_id or s.run.run_id
        return compute_scores(s.questions, list(s.models.values()), rid)

    @app.get("/api/jobs/ready")
    def job_ready() -> dict[str, Any]:
        return ready()

    @app.get("/api/jobs/run")
    def job_status() -> dict[str, Any]:
        return get_job()

    @app.post("/api/jobs/run")
    def job_start(body: RunRequest | None = None) -> dict[str, Any]:
        req = body or RunRequest()
        try:
            return start_job(run_id=req.run_id, mock=req.mock)
        except JobBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveNotReady as exc:
            raise HTTPException(status_code=412, detail=str(exc)) from exc

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_viewer()


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Prediction Sandbox local viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"Prediction Sandbox viewer → http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
