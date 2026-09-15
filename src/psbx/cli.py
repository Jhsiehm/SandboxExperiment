from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from psbx.config import load_epochs, load_models, load_run
from psbx.corpus.build_index import build_index
from psbx.corpus.fetch_wayback import DEFAULT_MAX_DOCS
from psbx.corpus.index import SOURCE_TYPES, load_index
from psbx.env import load_dotenv
from psbx.io import read_json, read_jsonl, write_json, write_jsonl
from psbx.paths import resolve, run_dir, validate_run_id
from psbx.questions.build_set import build_questions, write_question_set
from psbx.sandbox.harness import run_set
from psbx.schemas import Prediction, Question
from psbx.scoring.agenda import correlate_gallup
from psbx.scoring.report import score_run, write_plots
from psbx.store import upsert_predictions, upsert_questions

app = typer.Typer(no_args_is_help=True, add_completion=False)
questions_app = typer.Typer(no_args_is_help=True)
corpus_app = typer.Typer(no_args_is_help=True)
society_app = typer.Typer(no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=True)
epoch_app = typer.Typer(no_args_is_help=True)
app.add_typer(questions_app, name="questions")
app.add_typer(corpus_app, name="corpus")
sandbox_app = typer.Typer(no_args_is_help=True)
app.add_typer(society_app, name="society")
app.add_typer(eval_app, name="eval")
app.add_typer(epoch_app, name="epoch")
app.add_typer(sandbox_app, name="sandbox")


@app.callback()
def _root() -> None:
    load_dotenv()


def _maybe_enable_mock() -> None:
    if os.environ.get("PSBX_MOCK_LLM"):
        return
    if any(
        os.environ.get(k)
        for k in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "TOGETHER_API_KEY",
            "OPENROUTER_API_KEY",
        )
    ):
        return
    os.environ["PSBX_MOCK_LLM"] = "1"


def _config_for_run_id(run_id: str):
    run_id = validate_run_id(run_id)
    saved = run_dir(run_id) / "run.yaml"
    if saved.is_file():
        return load_run(saved)
    for path in (
        "config/run.yaml",
        "config/run-phase2.yaml",
        "config/run-openrouter.yaml",
        "config/run-swarm.yaml",
        "config/run-society.yaml",
        "config/run-society-swarm.yaml",
        "config/run-society-swarm-mock.yaml",
        "config/run-sandbox.yaml",
    ):
        cfg = load_run(path)
        if cfg.run_id == run_id:
            return cfg
    cfg = load_run()
    return cfg.model_copy(update={"run_id": run_id})


@questions_app.command("build")
def questions_build(
    epoch: Annotated[str, typer.Option("--epoch")],
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    ep = load_epochs()[epoch]
    qs = build_questions(ep, limit=limit)
    dest = write_question_set(ep, qs)
    upsert_questions(qs)
    typer.echo(f"wrote {len(qs)} questions to {dest}")


@corpus_app.command("build")
def corpus_build(
    epoch: Annotated[str, typer.Option("--epoch")],
    live: Annotated[bool, typer.Option("--live")] = False,
    max_docs: Annotated[int, typer.Option("--max-docs")] = DEFAULT_MAX_DOCS,
) -> None:
    """Build the cutoff-locked hybrid index. `--live` pulls Wayback (to=cutoff)."""
    ep = load_epochs()[epoch]
    index = build_index(ep, live=live, max_docs=max_docs)
    meta = read_json(resolve(ep.corpus_index_path) / "meta.json")
    typer.echo(
        f"indexed {len(index.docs)} documents <= {ep.cutoff_date} at "
        f"{ep.corpus_index_path}; silos={meta.get('silos', {})}"
    )


@corpus_app.command("silos")
def corpus_silos(epoch: Annotated[str, typer.Option("--epoch")] = "e2012") -> None:
    """List selectable source-type silos for one frozen epoch."""
    ep = load_epochs()[epoch]
    meta = read_json(resolve(ep.corpus_index_path) / "meta.json")
    typer.echo(
        {
            "epoch": ep.id,
            "cutoff": ep.cutoff_date.isoformat(),
            "combined_documents": meta.get("n_docs", 0),
            "silos": meta.get("silos", {}),
        }
    )


@corpus_app.command("sync-surveys")
def corpus_sync_surveys(
    epoch: Annotated[str, typer.Option("--epoch")] = "e2012",
    all_epochs: Annotated[bool, typer.Option("--all-epochs")] = False,
    provider: Annotated[str, typer.Option("--provider")] = "all",
    plan: Annotated[bool, typer.Option("--plan")] = False,
    rebuild: Annotated[bool, typer.Option("--rebuild")] = False,
) -> None:
    """Sync cutoff-safe public survey pages; inventory gated/future datasets."""
    from psbx.corpus.sync_survey_sources import sync_survey_sources

    if rebuild and plan:
        raise typer.BadParameter("--rebuild cannot be combined with --plan")
    configured = load_epochs()
    targets = list(configured.values()) if all_epochs else [configured[epoch]]
    for ep in targets:
        try:
            payload = sync_survey_sources(ep, provider=provider, plan=plan)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(
            {
                "epoch": ep.id,
                "cutoff": ep.cutoff_date.isoformat(),
                "provider": provider,
                "counts": payload["counts"],
            }
        )
        for row in payload["artifacts"]:
            if row["status"] in {
                "manual_required",
                "blocked_future_release",
                "blocked_unverified_release",
                "error",
            }:
                typer.echo(
                    f"{row['provider']}/{row['id']}: {row['status']} · {row.get('reason', '')}"
                )
        if rebuild:
            index = build_index(ep)
            typer.echo(f"rebuilt {ep.id}: {len(index.docs)} documents")


@epoch_app.command("list")
def epoch_list() -> None:
    """List selectable frozen years and their corpus paths."""
    for epoch in load_epochs().values():
        typer.echo(
            {
                "epoch": epoch.id,
                "cutoff": epoch.cutoff_date.isoformat(),
                "resolution_end": epoch.resolution_window_end.isoformat(),
                "corpus": epoch.corpus_index_path,
            }
        )


@app.command("run")
def run_cmd(
    config: Annotated[Path, typer.Option("--config")] = Path("config/run.yaml"),
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    load_dotenv()
    run = load_run(config)
    if limit is not None:
        run = run.model_copy(update={"n_questions": limit})
    if run.allow_mock:
        _maybe_enable_mock()
    elif os.environ.get("PSBX_MOCK_LLM") == "1":
        raise typer.BadParameter(
            f"{config} has allow_mock: false; unset PSBX_MOCK_LLM to run live models"
        )
    epoch = load_epochs()[run.epoch]
    models = load_models()
    chosen = [models[mid] for mid in run.models]
    qs = read_jsonl(run.question_set, Question)
    preds = run_set(qs, chosen, epoch, run)
    dest = run_dir(run.run_id) / "predictions.jsonl"
    write_jsonl(dest, preds)
    upsert_predictions(preds)
    typer.echo(f"wrote {len(preds)} predictions to {dest}")


@app.command("score")
def score_cmd(run: Annotated[str, typer.Option("--run")]) -> None:
    run = validate_run_id(run)
    cfg = _config_for_run_id(run)
    epoch = load_epochs()[cfg.epoch]
    qs = read_jsonl(cfg.question_set, Question)
    preds = read_jsonl(run_dir(run) / "predictions.jsonl", Prediction)
    models = [m for m in load_models().values() if m.id in {p.model_id for p in preds}]
    report = score_run(preds, qs, models, run)
    dest = run_dir(run)
    write_json(dest / "results.json", report)
    write_plots(report, dest)
    from psbx.scoring.plots import write_performance_plots

    write_performance_plots(run, qs, force=True)
    typer.echo(report.model_dump_json(indent=2))
    if report.models_beating_base_rate:
        typer.echo(f"beats base rate: {', '.join(report.models_beating_base_rate)}")
    else:
        typer.echo("kill signal: no model beat the always-base-rate baseline")
    if report.models_beating_prior_signal:
        typer.echo(f"beats prior_signal: {', '.join(report.models_beating_prior_signal)}")
    else:
        typer.echo("kill signal: no model beat the prior-signal baseline")
    if report.c_index_by_model:
        bits = [
            f"{mid}={('—' if v is None else f'{v:.3f}')}"
            for mid, v in report.c_index_by_model.items()
        ]
        typer.echo("c-index: " + ", ".join(bits))
    del epoch


@app.command("agenda")
def agenda_cmd(epoch: Annotated[str, typer.Option("--epoch")] = "e2012") -> None:
    ep = load_epochs()[epoch]
    index = load_index(ep)
    result = correlate_gallup(index)
    write_json(f"data/runs/{epoch}-agenda.json", result)
    typer.echo(result)


@app.command("leaderboard")
def leaderboard_cmd(run: Annotated[str, typer.Option("--run")]) -> None:
    from psbx.leaderboard_site import build_site

    dest = build_site(run)
    typer.echo(f"wrote {dest}")


@society_app.command("run")
def society_cmd(
    config: Annotated[Path, typer.Option("--config")] = Path("config/run-society.yaml"),
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    """Run the forecast through AgentSociety 2 custom env/agent scaffolding."""
    load_dotenv()
    from psbx.society.experiment import run_society

    run = load_run(config)
    if limit is not None:
        run = run.model_copy(update={"n_questions": limit})
    if run.allow_mock:
        _maybe_enable_mock()
    elif os.environ.get("PSBX_MOCK_LLM") == "1":
        raise typer.BadParameter(
            f"{config} has allow_mock: false; unset PSBX_MOCK_LLM to run live models"
        )
    preds = run_society(run, limit=limit, config_path=config)
    dest = run_dir(run.run_id) / "predictions.jsonl"
    upsert_predictions(preds)
    typer.echo(f"society wrote {len(preds)} predictions to {dest}")


@society_app.command("export")
def society_export(
    config: Annotated[Path, typer.Option("--config")] = Path("config/run-society-swarm.yaml"),
    dest: Annotated[Path | None, typer.Option("--dest")] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    """Write AgentSociety 2 InitConfig + 12 workspaces from config/swarm.yaml."""
    from psbx.society.as2_config import export_society_bundle

    run = load_run(config)
    if limit is not None:
        run = run.model_copy(update={"n_questions": limit})
    qs = read_jsonl(run.question_set, Question)[: run.n_questions]
    out = dest or (run_dir(run.run_id) / "society")
    paths = export_society_bundle(run, qs, out)
    typer.echo(f"exported {len(qs)} question(s) → {paths['init_config']}")
    typer.echo(f"steps {paths['steps']}")
    typer.echo(f"workspaces {paths['agents']}")


@eval_app.command("baseline")
def eval_baseline(
    run: Annotated[str, typer.Option("--run")],
    config: Annotated[Path, typer.Option("--config")] = Path("config/eval-baseline.yaml"),
) -> None:
    """Score swarm vs later outcomes (Track A) and demographic spread (Track B)."""
    from psbx.eval.baseline import evaluate_human_baseline, write_human_baseline

    report = evaluate_human_baseline(run, eval_config=config)
    dest = write_human_baseline(report)
    typer.echo(report.model_dump_json(indent=2))
    typer.echo(f"wrote {dest}")
    track_a = report.tracks.get("A_media_stimulus")
    if track_a and track_a.brier_vs_later_outcomes is None:
        typer.echo("no predictions yet — run the society swarm first")


@epoch_app.command("propose")
def epoch_propose(
    from_epoch: Annotated[str, typer.Option("--from")] = "e2012",
    years: Annotated[int, typer.Option("--years")] = 1,
) -> None:
    """Print the next cutoff. Does not ingest future documents or enable PolicySim."""
    from psbx.epochs import propose_year_step
    from psbx.io import write_json

    payload = propose_year_step(from_epoch, years=years)
    dest = resolve(f"data/runs/{from_epoch}-advance-propose.json")
    write_json(dest, payload)
    typer.echo(payload)
    if payload.get("ingests_documents"):
        raise typer.Exit(code=1)
    typer.echo(f"wrote {dest} (hook only; no corpus built)")


@app.command("search")
def search_cmd(
    epoch: Annotated[str, typer.Option("--epoch")] = "e2012",
    port: Annotated[int, typer.Option("--port")] = 8766,
    source_type: Annotated[str | None, typer.Option("--source-type")] = None,
) -> None:
    from psbx.sandbox.search_service import serve

    serve(
        load_index(load_epochs()[epoch], source_type=source_type),
        port=port,
        epoch_id=epoch,
    )


@sandbox_app.command("up")
def sandbox_up(
    epoch: Annotated[str, typer.Option("--epoch")] = "e2012",
    source_type: Annotated[str | None, typer.Option("--source-type")] = None,
) -> None:
    """Start libfaketime search: Docker if present, else host DYLD/LD_PRELOAD."""
    import shutil

    if source_type and source_type not in SOURCE_TYPES:
        raise typer.BadParameter(
            f"unknown source type {source_type!r}; choose one of: {', '.join(SOURCE_TYPES)}"
        )
    if shutil.which("docker"):
        from psbx.sandbox.docker_sidecar import build_image, up

        build_image()
        url = up(epoch, source_type=source_type)
        typer.echo(
            "search sidecar up (docker, iptables egress lock) · "
            f"{url} · epoch {epoch} · source {source_type or 'all'}"
        )
        return
    from psbx.sandbox.host_sidecar import up as host_up

    url = host_up(epoch, source_type=source_type)
    typer.echo(
        f"search sidecar up (host libfaketime) · {url} · epoch {epoch} · "
        f"source {source_type or 'all'}"
    )


@sandbox_app.command("down")
def sandbox_down() -> None:
    import shutil

    if shutil.which("docker"):
        from psbx.sandbox.docker_sidecar import down as docker_down

        docker_down()
    from psbx.sandbox.host_sidecar import down as host_down

    host_down()
    typer.echo("search sidecar stopped")


@sandbox_app.command("status")
def sandbox_status() -> None:
    import shutil

    from psbx.sandbox.host_sidecar import status as host_status

    if shutil.which("docker"):
        from psbx.sandbox.docker_sidecar import status as docker_status

        typer.echo(docker_status())
    typer.echo(host_status())


@sandbox_app.command("clock")
def sandbox_clock() -> None:
    """Read /clock (Unix socket or http://127.0.0.1:8766)."""
    import httpx

    from psbx.paths import resolve
    from psbx.sandbox.clock import DEFAULT_SOCKET
    from psbx.sandbox.host_sidecar import HOST_PORT

    sock = resolve(DEFAULT_SOCKET)
    if sock.exists():
        transport = httpx.HTTPTransport(uds=str(sock))
        with httpx.Client(transport=transport, timeout=10.0) as client:
            resp = client.get("http://search/clock")
            resp.raise_for_status()
            typer.echo(resp.json())
            return
    url = f"http://127.0.0.1:{HOST_PORT}/clock"
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    typer.echo(resp.json())


@app.command("viewer")
def viewer_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    """Connected HTML console plus the same POST /search and POST /fetch contract."""
    import sys

    from psbx.paths import repo_root

    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    import uvicorn

    from leaderboard.app import app as viewer_app

    typer.echo(f"Prediction Sandbox viewer → http://{host}:{port}")
    uvicorn.run(viewer_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
