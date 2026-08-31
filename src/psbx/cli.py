from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from psbx.config import load_epochs, load_models, load_run
from psbx.env import load_dotenv
from psbx.corpus.build_index import build_index
from psbx.corpus.index import load_index
from psbx.io import read_jsonl, write_json, write_jsonl
from psbx.paths import resolve
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
app.add_typer(questions_app, name="questions")
app.add_typer(corpus_app, name="corpus")
sandbox_app = typer.Typer(no_args_is_help=True)
app.add_typer(society_app, name="society")
app.add_typer(sandbox_app, name="sandbox")


@app.callback()
def _root() -> None:
    load_dotenv()


def _maybe_enable_mock() -> None:
    if os.environ.get("PSBX_MOCK_LLM"):
        return
    if any(os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY")):
        return
    os.environ["PSBX_MOCK_LLM"] = "1"


def _config_for_run_id(run_id: str):
    for path in (
        "config/run.yaml",
        "config/run-phase2.yaml",
        "config/run-society.yaml",
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
) -> None:
    ep = load_epochs()[epoch]
    index = build_index(ep, live=live)
    typer.echo(f"indexed {len(index.docs)} documents <= {ep.cutoff_date} at {ep.corpus_index_path}")


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
    dest = resolve(f"data/runs/{run.run_id}/predictions.jsonl")
    write_jsonl(dest, preds)
    upsert_predictions(preds)
    typer.echo(f"wrote {len(preds)} predictions to {dest}")


@app.command("score")
def score_cmd(run: Annotated[str, typer.Option("--run")]) -> None:
    cfg = _config_for_run_id(run)
    epoch = load_epochs()[cfg.epoch]
    qs = read_jsonl(cfg.question_set, Question)
    preds = read_jsonl(f"data/runs/{run}/predictions.jsonl", Prediction)
    models = [m for m in load_models().values() if m.id in {p.model_id for p in preds}]
    report = score_run(preds, qs, models, run)
    dest = resolve(f"data/runs/{run}")
    write_json(dest / "results.json", report)
    write_plots(report, dest)
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
    preds = run_society(run, limit=limit)
    dest = resolve(f"data/runs/{run.run_id}/predictions.jsonl")
    upsert_predictions(preds)
    typer.echo(f"society wrote {len(preds)} predictions to {dest}")


@app.command("search")
def search_cmd(
    epoch: Annotated[str, typer.Option("--epoch")] = "e2012",
    port: Annotated[int, typer.Option("--port")] = 8766,
) -> None:
    from psbx.sandbox.search_service import serve

    serve(load_index(load_epochs()[epoch]), port=port)


@sandbox_app.command("up")
def sandbox_up(epoch: Annotated[str, typer.Option("--epoch")] = "e2012") -> None:
    """Start libfaketime search: Docker if present, else host DYLD/LD_PRELOAD."""
    import shutil

    if shutil.which("docker"):
        from psbx.sandbox.docker_sidecar import build_image, up

        build_image()
        url = up(epoch)
        typer.echo(f"search sidecar up (docker, iptables egress lock) · {url} · epoch {epoch}")
        return
    from psbx.sandbox.host_sidecar import up as host_up

    url = host_up(epoch)
    typer.echo(f"search sidecar up (host libfaketime) · {url} · epoch {epoch}")


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
