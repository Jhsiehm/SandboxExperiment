"""FastAPI viewer: static console + search API + repo-backed JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from leaderboard.activity import build_activity_payload, reseal_sandbox, sandbox_snapshot
from leaderboard.explain import run_label
from leaderboard.geography import geography_catalog, geography_payload
from leaderboard.jobs import (
    EraNotRunnable,
    InvalidSwarm,
    JobBusy,
    LiveNotReady,
    SandboxNotReady,
    SpendingBlocked,
    get_job,
    ready,
    start_job,
    swarm_options,
)
from leaderboard.population import population_dashboard_payload
from leaderboard.security import require_local_mutation, require_local_request_host
from leaderboard.store import (
    ViewerState,
    bootstrap,
    build_goal_progress,
    build_leaderboard,
    compute_scores,
    era_catalog,
    forecast_rows,
    list_runs_for_epoch,
    load_predictions,
    public_document_row,
    public_question,
)
from psbx.paths import run_dir
from psbx.sandbox.search_service import create_app as create_search_app
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
    population_selection: dict[str, Any] | None = Field(
        default=None,
        description="Validated synthetic population profile used to weight swarm personas",
    )
    dataset_selection: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Display/evaluation dataset filters recorded for run comparison; never "
            "inserted into model context"
        ),
    )


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

    @app.middleware("http")
    async def local_request_boundary(request: Request, call_next):
        try:
            require_local_request_host(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    def state_for(epoch_id: str | None = None) -> ViewerState:
        selected = epoch_id or app.state.default_epoch_id
        eras = {row["id"]: row for row in era_catalog()}
        if selected not in eras:
            raise HTTPException(status_code=404, detail=f"unknown epoch: {selected}")
        if not eras[selected]["ready"]:
            raise HTTPException(
                status_code=409,
                detail=f"{selected} is configured but needs a benchmark question set",
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

    @app.get("/api/population")
    def population(epoch: str = "e2012") -> dict[str, Any]:
        return population_dashboard_payload(epoch)

    @app.get("/api/geography/catalog")
    def geography_layers(epoch: str = "e2012") -> dict[str, Any]:
        try:
            return geography_catalog(epoch)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/geography")
    def geography(
        layer: str = "states",
        state: str | None = None,
        epoch: str = "e2012",
    ) -> dict[str, Any]:
        try:
            return geography_payload(epoch, layer_id=layer, state_fips=state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/data/catalog")
    def data_catalog(epoch: str = "e2012") -> dict[str, Any]:
        """Path-free filter metadata for population, Census, and election layers."""
        return population_dashboard_payload(epoch)["data_catalog"]

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
        authenticity_counts: dict[str, int] = {}
        for document in s.index.docs:
            authenticity_counts[document.authenticity] = (
                authenticity_counts.get(document.authenticity, 0) + 1
            )
        return {
            "cutoff_date": s.index.cutoff.isoformat(),
            "assertion": f"hard-filter published_at <= {s.index.cutoff.isoformat()}",
            "n_documents": len(s.index.docs),
            "n_shown": len(docs),
            "n_leaked": len(leaked),
            "source": s.index_source,
            "authenticity_counts": authenticity_counts,
            "research_eligible_documents": sum(
                1 for document in s.index.docs if document.research_eligible
            ),
            "documents": docs,
        }

    @app.get("/api/runs")
    def runs(epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        rows = runs_for(s)
        for row in rows:
            row["label"] = row.get("label") or run_label(row["run_id"])
        return {"runs": rows}

    @app.get("/api/leaderboard")
    def leaderboard(epoch: str | None = None) -> dict[str, Any]:
        s = state_for(epoch)
        return build_leaderboard(runs_for(s), s.questions, s.models)

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
    def activity(
        epoch: str | None = None,
        run_id: str | None = None,
        question_id: str | None = None,
    ) -> dict[str, Any]:
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
        return build_activity_payload(s, str(rid), job, question_id=question_id)

    @app.post("/api/sandbox/select")
    def sandbox_select(request: Request, body: SandboxSelection) -> dict[str, Any]:
        require_local_mutation(request)
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
    def job_ready(
        epoch: str | None = None,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        payload = ready()
        selected = epoch or app.state.default_epoch_id
        catalog = {row["id"]: row for row in era_catalog()}
        row = catalog.get(selected)
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown epoch: {selected}")
        configured_epoch = state_for(selected).epoch
        snapshot = sandbox_snapshot(selected, configured_epoch.cutoff_date.isoformat())
        expected_scope = source_type or "all"
        corpus_built = bool(row.get("has_corpus"))
        questions_built = bool(row.get("has_questions"))
        seal_verified = bool(
            snapshot.get("verified") and snapshot.get("selection") == expected_scope
        )
        requirements = [
            {
                "id": "question_set",
                "ready": questions_built,
                "detail": "Benchmark question set is materialized.",
            },
            {
                "id": "generated_corpus",
                "ready": corpus_built,
                "detail": (
                    "Generated corpus index is present."
                    if corpus_built
                    else f"Run `psbx practice prepare --epoch {selected}`."
                ),
            },
            {
                "id": "sealed_sidecar",
                "ready": seal_verified,
                "detail": (
                    f"Sidecar is sealed to {selected}/{expected_scope}."
                    if seal_verified
                    else f"Run `psbx sandbox up --epoch {selected}` and verify scope "
                    f"{expected_scope}."
                ),
            },
        ]
        blocking = [item["detail"] for item in requirements if not item["ready"]]
        practice_ready = questions_built and corpus_built and seal_verified
        authenticated_ready = int(row.get("research_eligible_documents") or 0) > 0
        provider_live_ready = bool(payload.get("live_ready"))
        live_blocking = []
        if not practice_ready:
            live_blocking.append("Complete the practice corpus/sidecar prerequisites.")
        if not authenticated_ready:
            live_blocking.append(
                "The selected corpus has no authenticated research-eligible evidence."
            )
        if not provider_live_ready:
            live_blocking.append(
                "Paid mode and the required provider credentials are not enabled."
            )
        payload.update(
            {
                "requested_epoch": selected,
                "requested_source_type": expected_scope,
                "practice_ready": practice_ready,
                "practice_requirements": requirements,
                "practice_blocking_reason": " ".join(blocking),
                "provider_live_ready": provider_live_ready,
                "authenticated_evidence_ready": authenticated_ready,
                "research_run_ready": practice_ready and authenticated_ready,
                "live_ready": (
                    practice_ready and authenticated_ready and provider_live_ready
                ),
                "live_blocking_reason": " ".join(live_blocking),
                "sidecar": {
                    "verified": bool(snapshot.get("verified")),
                    "selection": snapshot.get("selection") or "unknown",
                    "epoch_match": bool(snapshot.get("epoch_match")),
                    "cutoff_match": bool(snapshot.get("cutoff_match")),
                },
            }
        )
        return payload

    @app.get("/api/jobs/run")
    def job_status() -> dict[str, Any]:
        return get_job()

    @app.post("/api/jobs/run")
    def job_start(request: Request, body: RunRequest | None = None) -> dict[str, Any]:
        require_local_mutation(request)
        req = body or RunRequest()
        try:
            selected = req.epoch_id or app.state.default_epoch_id
            s = state_for(selected)
            selected_era = next(
                row for row in era_catalog() if row["id"] == selected
            )
            if not selected_era["isolated_run_ready"]:
                raise SandboxNotReady(
                    f"prepare generated assets first with `psbx practice prepare "
                    f"--epoch {selected}`"
                )
            requested_kind = (req.kind or ("mock" if req.mock else "live")).lower()
            if requested_kind != "mock" and not selected_era["research_ready"]:
                raise LiveNotReady(
                    "live/swarm research requires authenticated evidence in the "
                    "selected corpus"
                )
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
                population_selection=req.population_selection,
                dataset_selection=req.dataset_selection,
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
        except SpendingBlocked as exc:
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
    from psbx.security import require_loopback_host

    try:
        host = require_loopback_host(args.host)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Prediction Sandbox viewer → http://{args.host}:{args.port}")
    uvicorn.run(app, host=host, port=args.port, log_level="info")
