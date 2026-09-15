"""FastAPI viewer: static console + search API + repo-backed JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from leaderboard.activity import build_activity_payload, reseal_sandbox, sandbox_snapshot
from leaderboard.explain import run_label
from leaderboard.jobs import (
    EraNotRunnable,
    InvalidSwarm,
    JobBusy,
    LiveNotReady,
    SandboxNotReady,
    get_job,
    ready,
    start_job,
    swarm_options,
)
from leaderboard.store import (
    ViewerState,
    bootstrap,
    build_goal_progress,
    compute_scores,
    era_catalog,
    forecast_rows,
    list_runs_for_epoch,
    load_predictions,
    public_document_row,
    public_question,
)
from psbx.sandbox.search_service import create_app as create_search_app
from psbx.paths import run_dir
from psbx.schemas import FetchRequest, SearchRequest

STATIC = Path(__file__).resolve().parent / "static"


class RunRequest(BaseModel):
    mock: bool = True
    kind: str | None = Field(
        default=None,
        description="mock | live | swarm. Overrides mock when set.",
    )
    run_id: str | None = Field(default=None, description="Defaults to the kind's config run_id")
    epoch_id: str | None = Field(default=None, description="Selected frozen-data epoch")
    source_type: str | None = Field(default=None, description="Frozen corpus source silo")
    isolated_retrieval: bool = Field(
        default=True, description="Route retrieval through the sealed sidecar"
    )
    label: str | None = Field(default=None, max_length=80)
    n_questions: int | None = Field(default=None, ge=1, le=50)
    swarm_bodies: list[dict[str, Any]] | None = None


class SandboxSelection(BaseModel):
    epoch_id: str
    source_type: str | None = None


def create_viewer(state: ViewerState | None = None) -> FastAPI:
    from psbx.env import load_dotenv

    load_dotenv()
    state = state or bootstrap()
    app = create_search_app(state.index, epoch_id=state.epoch.id)
    app.title = "psbx-viewer"
    app.state.viewer = state
    app.state.viewer_states = {state.epoch.id: state}
    app.state.default_epoch_id = state.epoch.id

    def state_for(epoch_id: str | None = None) -> ViewerState:
        selected = epoch_id or app.state.default_epoch_id
        eras = {row["id"]: row for row in era_catalog()}
        if selected not in eras:
            raise HTTPException(status_code=404, detail=f"unknown epoch: {selected}")
        if not eras[selected]["ready"]:
            raise HTTPException(
                status_code=409,
                detail=f"{selected} is configured but needs both a corpus index and question set",
            )
        cached = app.state.viewer_states.get(selected)
        if cached is None:
            try:
                cached = bootstrap(selected)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"could not load epoch {selected}: {exc}"
                ) from exc
            app.state.viewer_states[selected] = cached
        return cached

    def runs_for(s: ViewerState) -> list[dict[str, Any]]:
        return list_runs_for_epoch(s.epoch.id, s.questions)

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(
            STATIC / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/eras")
    def eras() -> dict[str, Any]:
        rows = era_catalog()
        return {
            "default_epoch_id": app.state.default_epoch_id,
            "n_configured": len(rows),
            "n_ready": sum(1 for row in rows if row["ready"]),
            "eras": rows,
        }

    @app.get("/api/overview")
    def overview(epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        runs = runs_for(s)
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
            "goal_progress": build_goal_progress(runs, len(s.questions)),
            "errors": s.errors,
            "live_run_id": ready()["live_run_id"],
            "mock_run_id": ready()["mock_run_id"],
            "swarm_run_id": ready()["swarm_run_id"],
            "run_labels": {
                r["run_id"]: r.get("label") or run_label(r["run_id"]) for r in runs
            },
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
        epoch: str | None = None,
    ) -> dict[str, Any]:
        s = state_for(epoch)
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
    def corpus(
        limit: int = Query(200, ge=1, le=2000), epoch: str | None = None
    ) -> dict[str, Any]:
        s = state_for(epoch)
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
    def runs(epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        rows = runs_for(s)
        for row in rows:
            row["label"] = row.get("label") or run_label(row["run_id"])
        return {"runs": rows}

    @app.get("/api/swarm/options")
    def swarm_builder_options() -> dict[str, Any]:
        return swarm_options()

    @app.get("/api/runs/{run_id}/log")
    def run_log(run_id: str, epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        rows = runs_for(s)
        record = next((row for row in rows if row["run_id"] == run_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        path = run_dir(run_id) / "run.log"
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        return {"run": record, "lines": lines[-400:]}

    @app.get("/api/runs/{run_id}")
    def run_detail(
        run_id: str,
        limit: int = Query(200, ge=1, le=2000),
        reveal_truth: bool = Query(False),
        epoch: str | None = None,
    ) -> dict[str, Any]:
        s = state_for(epoch)
        record = next((r for r in runs_for(s) if r["run_id"] == run_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        preds = load_predictions(run_id)
        rows = forecast_rows(preds, s.questions, reveal_truth=reveal_truth, limit=limit)
        models = sorted({p.model_id for p in preds})
        return {
            "run_id": run_id,
            "run_label": record.get("label") or run_label(run_id),
            "n_predictions": len(preds),
            "n_shown": len(rows),
            "models": models,
            "predictions": rows,
        }

    @app.get("/api/runs/{run_id}/plots")
    def list_plots(
        run_id: str, force: bool = Query(False), epoch: str | None = None
    ) -> dict[str, Any]:
        s = state_for(epoch)
        record = next((r for r in runs_for(s) if r["run_id"] == run_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        from psbx.scoring.plots import write_performance_plots

        plots = write_performance_plots(run_id, s.questions, force=force)
        return {
            "run_id": run_id,
            "run_label": record.get("label") or run_label(run_id),
            "n": len(plots),
            "plots": plots,
        }

    @app.get("/api/runs/{run_id}/plots/{name}")
    def get_plot(run_id: str, name: str, epoch: str | None = None) -> FileResponse:
        import re

        if not re.fullmatch(r"[a-z0-9_]+\.png", name):
            raise HTTPException(status_code=400, detail="unknown plot")
        s = state_for(epoch)
        if not any(r["run_id"] == run_id for r in runs_for(s)):
            raise HTTPException(status_code=404, detail="unknown run_id")
        path = run_dir(run_id) / "plots" / name
        if not path.is_file():
            from psbx.scoring.plots import write_performance_plots

            write_performance_plots(run_id, s.questions)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="plot not generated")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/scores")
    def scores(run_id: str | None = None, epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        rid = run_id or s.run.run_id
        if run_id and not any(r["run_id"] == run_id for r in runs_for(s)):
            raise HTTPException(status_code=404, detail="unknown run_id")
        return compute_scores(s.questions, list(s.models.values()), rid)

    @app.post("/api/eras/{epoch_id}/search")
    def era_search(epoch_id: str, body: SearchRequest) -> list[Any]:
        s = state_for(epoch_id)
        hits = s.index.search(
            body.query,
            k=body.k,
            min_prominence=body.min_prominence,
            source_types=list(body.source_types) or None,
        )
        assert all(hit.published_at.date() <= s.index.cutoff for hit in hits)
        return hits

    @app.post("/api/eras/{epoch_id}/fetch")
    def era_fetch(epoch_id: str, body: FetchRequest) -> dict[str, Any]:
        s = state_for(epoch_id)
        try:
            return s.index.public_document(body.document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown document_id") from exc

    @app.get("/api/activity")
    def activity(epoch: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        job = get_job()
        rid = run_id or (
            job.get("run_id")
            if job.get("status") == "running"
            else ready()["swarm_run_id"]
        )
        known = any(row["run_id"] == rid for row in runs_for(s))
        if not known and not (job.get("status") == "running" and job.get("run_id") == rid):
            raise HTTPException(status_code=404, detail="unknown run_id")
        return build_activity_payload(s, str(rid), job)

    @app.post("/api/sandbox/select")
    def sandbox_select(body: SandboxSelection) -> dict[str, Any]:
        s = state_for(body.epoch_id)
        if get_job().get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail="wait for the active run before changing the frozen access scope",
            )
        allowed = {str(doc.source_type) for doc in s.index.docs}
        if body.source_type and body.source_type not in allowed:
            raise HTTPException(status_code=422, detail="source silo is not built for this epoch")
        try:
            return reseal_sandbox(body.epoch_id, body.source_type)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"could not seal the search container: {exc}"
            ) from exc

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
            selected = req.epoch_id or app.state.default_epoch_id
            s = state_for(selected)
            if req.isolated_retrieval:
                snapshot = sandbox_snapshot(selected, s.epoch.cutoff_date.isoformat())
                expected_scope = req.source_type or "all"
                if not snapshot.get("verified") or snapshot.get("selection") != expected_scope:
                    raise SandboxNotReady(
                        f"seal the container to epoch={selected} "
                        f"source={expected_scope} before running"
                    )
            return start_job(
                run_id=req.run_id,
                mock=req.mock,
                kind=req.kind,
                epoch_id=selected,
                isolated=req.isolated_retrieval,
                source_type=req.source_type,
                n_questions=req.n_questions,
                swarm_bodies=req.swarm_bodies,
                label=req.label,
                unique_run=True,
            )
        except JobBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveNotReady as exc:
            raise HTTPException(status_code=412, detail=str(exc)) from exc
        except EraNotRunnable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SandboxNotReady as exc:
            raise HTTPException(status_code=412, detail=str(exc)) from exc
        except InvalidSwarm as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

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
