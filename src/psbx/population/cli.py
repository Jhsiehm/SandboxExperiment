"""Track B command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .census_sync import summarize_plan, sync_census_pack, verify_census_pack
from .registry import load_source_registry
from .runner import plan_population, run_population_build, validate_population_file

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("sync-census")
def sync_census_cmd(
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Download the planned official Census artifacts."),
    ] = False,
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/population-input/e2012/census"
    ),
    workers: Annotated[int, typer.Option("--workers", min=1, max=8)] = 4,
) -> None:
    """Plan or execute the e2012 state, D.C., and national Census data sync."""
    if not execute:
        typer.echo(json.dumps(summarize_plan(), indent=2))
        return

    def progress(completed: int, total: int, artifact) -> None:
        if completed == 1 or completed % 10 == 0 or completed == total:
            typer.echo(f"[{completed}/{total}] {artifact.artifact_id}", err=True)

    result = sync_census_pack(output_root=output, workers=workers, progress=progress)
    summary = {key: value for key, value in result.items() if key != "artifacts"}
    typer.echo(json.dumps(summary, indent=2))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("verify-census")
def verify_census_cmd(
    manifest: Annotated[Path, typer.Option("--manifest")] = Path(
        "data/population-input/e2012/census/manifest.json"
    ),
) -> None:
    """Recheck every downloaded Census ZIP and recorded SHA-256."""
    result = verify_census_pack(manifest)
    typer.echo(json.dumps(result, indent=2))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("normalize-census")
def normalize_census_cmd(
    areas: Annotated[str, typer.Option("--areas")] = "wy,dc,ca",
    census_root: Annotated[Path, typer.Option("--census-root")] = Path(
        "data/population-input/e2012/census"
    ),
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/population-input/e2012/normalized"
    ),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Parse pinned ACS/DP/CVAP/PUMS inputs into safe weighted donor cells."""
    from .census_ingest import normalize_census_area, parse_area_selection

    selected = parse_area_selection(areas)
    results = []
    for index, area in enumerate(selected, start=1):
        typer.echo(f"[{index}/{len(selected)}] normalize {area.abbreviation}", err=True)
        results.append(
            normalize_census_area(
                area,
                census_root=census_root,
                normalized_root=output,
                force=force,
            )
        )
    typer.echo(json.dumps({"completed": len(results), "results": results}, indent=2))


@app.command("build-census-populations")
def build_census_populations_cmd(
    areas: Annotated[str, typer.Option("--areas")] = "wy,dc,ca",
    census_root: Annotated[Path, typer.Option("--census-root")] = Path(
        "data/population-input/e2012/census"
    ),
    normalized_root: Annotated[Path, typer.Option("--normalized-root")] = Path(
        "data/population-input/e2012/normalized"
    ),
    population_root: Annotated[Path, typer.Option("--population-root")] = Path(
        "data/population"
    ),
    reasoning_budget: Annotated[int, typer.Option("--reasoning-budget", min=0)] = 100,
    seed: Annotated[int, typer.Option("--seed")] = 20120630,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Normalize and build selected states, or all 51 plus the national aggregate."""
    from .census_ingest import parse_area_selection, run_census_population_batch

    selected = parse_area_selection(areas)

    def progress(stage: str, area, index: int, total: int) -> None:
        typer.echo(f"[{index}/{total}] {stage} {area.abbreviation}", err=True)

    result = run_census_population_batch(
        areas=selected,
        census_root=census_root,
        normalized_root=normalized_root,
        population_root=population_root,
        seed=seed,
        reasoning_budget=reasoning_budget,
        force=force,
        progress=progress,
    )
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("convergence")
def convergence_cmd(
    population_id: Annotated[str, typer.Option("--population-id")] = "national-us-e2012",
    epoch_id: Annotated[str, typer.Option("--epoch")] = "e2012",
    budgets: Annotated[str, typer.Option("--budgets")] = "25,50,100,250,500,1000,5000",
    seeds: Annotated[str, typer.Option("--seeds")] = (
        "20120630,20120631,20120632,20120633,20120634"
    ),
    model_id: Annotated[str, typer.Option("--model")] = "openrouter-gpt-4.1-mini",
    input_tokens: Annotated[int, typer.Option("--input-tokens", min=0)] = 800,
    output_tokens: Annotated[int, typer.Option("--output-tokens", min=0)] = 128,
    population_root: Annotated[Path, typer.Option("--population-root")] = Path(
        "data/population"
    ),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Measure weighted-panel convergence and project calls, tokens, and cost offline."""
    from .convergence import parse_integer_list, run_convergence_experiment

    result = run_convergence_experiment(
        population_id,
        epoch_id=epoch_id,
        population_root=population_root,
        budgets=parse_integer_list(budgets),
        seeds=parse_integer_list(seeds, minimum=0),
        model_id=model_id,
        input_tokens_per_call=input_tokens,
        output_tokens_per_call=output_tokens,
        force=force,
    )
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("plan")
def plan_cmd(
    config: Annotated[Path, typer.Option("--config")] = Path("config/track_b_fixture.yaml"),
) -> None:
    """Show cutoff/source decisions without building a population."""
    typer.echo(json.dumps(plan_population(config), indent=2, default=str))


@app.command("build")
def build_cmd(
    config: Annotated[Path, typer.Option("--config")] = Path("config/track_b_fixture.yaml"),
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Build and validate a synthetic population."""
    result = run_population_build(config, output_override=output)
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["validation"]["passed"]:
        raise typer.Exit(code=2)


@app.command("validate")
def validate_cmd(
    config: Annotated[Path, typer.Option("--config")],
    population: Annotated[Path, typer.Option("--population")],
) -> None:
    """Validate an existing synthetic-person CSV against the configured constraints."""
    result = validate_population_file(config, population)
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("evaluate")
def evaluate_cmd(
    run_id: Annotated[str, typer.Option("--run-id")],
    population: Annotated[Path, typer.Option("--population")],
    responses: Annotated[Path, typer.Option("--responses")],
    targets: Annotated[Path, typer.Option("--targets")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Run an unsealed diagnostic comparison (use evaluate-sealed for validation)."""
    from psbx.eval.track_b_population import evaluate_behavior_files

    report = evaluate_behavior_files(
        run_id=run_id,
        population_path=population,
        responses_path=responses,
        targets_path=targets,
    )
    payload = report.model_dump(mode="json")
    rendered = json.dumps(payload, indent=2, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(rendered)


@app.command("seal-behavior")
def seal_behavior_cmd(
    run_id: Annotated[str, typer.Option("--run-id")],
    population: Annotated[Path, typer.Option("--population")],
    responses: Annotated[Path, typer.Option("--responses")],
    training_artifacts: Annotated[
        list[Path], typer.Option("--training-artifact")
    ],
    model_id: Annotated[str, typer.Option("--model-id")],
    output: Annotated[Path, typer.Option("--output")],
    max_mae: Annotated[float, typer.Option("--max-mae", min=0.0, max=1.0)] = 0.10,
    max_rmse: Annotated[float, typer.Option("--max-rmse", min=0.0, max=1.0)] = 0.15,
    minimum_targets: Annotated[int, typer.Option("--minimum-targets", min=1)] = 1,
) -> None:
    """Freeze prediction inputs and acceptance metrics before target reveal."""
    from psbx.eval.track_b_population import seal_behavior_predictions

    result = seal_behavior_predictions(
        run_id=run_id,
        population_path=population,
        responses_path=responses,
        training_artifacts=list(training_artifacts),
        model_id=model_id,
        output_path=output,
        max_mean_absolute_error=max_mae,
        max_root_mean_squared_error=max_rmse,
        minimum_targets=minimum_targets,
    )
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("evaluate-sealed")
def evaluate_sealed_cmd(
    seal: Annotated[Path, typer.Option("--seal")],
    seal_sha256: Annotated[str, typer.Option("--seal-sha256")],
    targets: Annotated[Path, typer.Option("--targets")],
    target_sha256: Annotated[str, typer.Option("--target-sha256")],
    target_provenance: Annotated[Path, typer.Option("--target-provenance")],
    target_provenance_sha256: Annotated[
        str, typer.Option("--target-provenance-sha256")
    ],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Reveal a checksum-pinned target file after prediction sealing."""
    from psbx.eval.track_b_population import evaluate_sealed_behavior

    result = evaluate_sealed_behavior(
        seal_path=seal,
        expected_seal_sha256=seal_sha256,
        targets_path=targets,
        expected_target_sha256=target_sha256,
        target_provenance_path=target_provenance,
        expected_target_provenance_sha256=target_provenance_sha256,
        output_path=output,
    )
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("sources")
def sources_cmd(
    registry: Annotated[Path, typer.Option("--registry")] = Path(
        "config/population_sources.yaml"
    ),
) -> None:
    """Print the population source registry."""
    sources = load_source_registry(registry)
    payload = {key: value.model_dump(mode="json") for key, value in sources.items()}
    typer.echo(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    app()
