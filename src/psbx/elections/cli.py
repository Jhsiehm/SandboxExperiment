"""Election and electoral-demography CLI."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from .census import (
    census_election_plan,
    execute_census_plan,
    parse_levels,
    parse_states,
    summarize_census_plan,
)
from .fec_adapter import import_fec_workbook
from .federal import sync_federal_documents
from .importer import import_election_results
from .registry import federal_coverage_plan, load_election_sources

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _date_value(value: str, *, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option} must be YYYY-MM-DD") from exc


def _year_list(value: str) -> list[int]:
    years = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = (int(part) for part in token.split("-", 1))
            years.extend(range(start, end + 1, 2))
        else:
            years.append(int(token))
    if not years:
        raise typer.BadParameter("at least one year is required")
    return sorted(set(years))


@app.command("sources")
def sources_cmd(
    registry: Annotated[Path, typer.Option("--registry")] = Path(
        "config/election_sources.yaml"
    ),
) -> None:
    sources = load_election_sources(registry)
    typer.echo(
        json.dumps(
            {key: value.model_dump(mode="json") for key, value in sources.items()},
            indent=2,
            default=str,
        )
    )


@app.command("plan")
def plan_cmd(
    start_year: Annotated[int, typer.Option("--start-year")] = 1982,
    through_year: Annotated[int, typer.Option("--through-year")] = 2026,
    as_of: Annotated[str, typer.Option("--as-of")] = date.today().isoformat(),
) -> None:
    """Plan federal coverage; never treats future or raw documents as imported results."""
    typer.echo(
        json.dumps(
            federal_coverage_plan(
                start_year=start_year,
                through_year=through_year,
                as_of=_date_value(as_of, option="--as-of"),
            ),
            indent=2,
        )
    )


@app.command("sync-federal")
def sync_federal_cmd(
    years: Annotated[str, typer.Option("--years")] = "2012-2024",
    execute: Annotated[bool, typer.Option("--execute")] = False,
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/elections/raw/federal"
    ),
    as_of: Annotated[str, typer.Option("--as-of")] = date.today().isoformat(),
    include_supplements: Annotated[
        bool, typer.Option("--include-supplements")
    ] = False,
    max_total_mb: Annotated[
        int, typer.Option("--max-total-mb", min=1, max=5000)
    ] = 500,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Plan or explicitly download official FEC federal-election publications."""
    selected = _year_list(years)
    if not execute:
        typer.echo(
            json.dumps(
                federal_coverage_plan(
                    start_year=min(selected),
                    through_year=max(selected),
                    as_of=_date_value(as_of, option="--as-of"),
                ),
                indent=2,
            )
        )
        return
    try:
        result = sync_federal_documents(
            selected,
            output_root=output,
            as_of=_date_value(as_of, option="--as-of"),
            max_total_bytes=max_total_mb * 1_000_000,
            include_supplements=include_supplements,
            force=force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("sync-census")
def sync_census_cmd(
    year: Annotated[int, typer.Option("--year")] = 2024,
    levels: Annotated[str, typer.Option("--levels")] = "all",
    states: Annotated[str, typer.Option("--states")] = "all",
    execute: Annotated[bool, typer.Option("--execute")] = False,
    output: Annotated[Path, typer.Option("--output")] = Path("data/elections/census"),
    cache: Annotated[Path, typer.Option("--cache")] = Path("data/census-cache/api"),
    max_requests: Annotated[int, typer.Option("--max-requests", min=1, max=1000)] = 350,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Plan or execute Census ACS pulls at electoral comparison geographies."""
    try:
        requests = census_election_plan(
            year=year,
            levels=parse_levels(levels),
            states=parse_states(states),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not execute:
        typer.echo(json.dumps(summarize_census_plan(requests), indent=2))
        return

    def progress(completed, total, request) -> None:
        if completed == 1 or completed % 10 == 0 or completed == total:
            typer.echo(f"[{completed}/{total}] {request.request_id}", err=True)

    try:
        result = execute_census_plan(
            requests,
            output_root=output,
            cache_root=cache,
            max_requests=max_requests,
            force=force,
            progress=progress,
        )
    except (FileExistsError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["passed"]:
        raise typer.Exit(code=2)


@app.command("import-results")
def import_results_cmd(
    input_path: Annotated[Path, typer.Option("--input")],
    dataset_id: Annotated[str, typer.Option("--dataset-id")],
    label: Annotated[str, typer.Option("--label")],
    cutoff: Annotated[str, typer.Option("--cutoff")],
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/elections/normalized"
    ),
    allow_uncertified: Annotated[bool, typer.Option("--allow-uncertified")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Validate a canonical result file and create a checksum-bound dataset manifest."""
    try:
        manifest = import_election_results(
            input_path,
            dataset_id=dataset_id,
            label=label,
            cutoff_date=_date_value(cutoff, option="--cutoff"),
            output_root=output,
            allow_uncertified=allow_uncertified,
            force=force,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(manifest.model_dump_json(indent=2))


@app.command("import-fec")
def import_fec_cmd(
    workbook: Annotated[Path, typer.Option("--workbook")],
    year: Annotated[int, typer.Option("--year")],
    source_release_date: Annotated[str, typer.Option("--source-release-date")],
    cutoff: Annotated[str, typer.Option("--cutoff")],
    dataset_id: Annotated[str, typer.Option("--dataset-id")],
    label: Annotated[str, typer.Option("--label")],
    source_url: Annotated[str | None, typer.Option("--source-url")] = None,
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/elections/normalized"
    ),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Normalize House and Senate general-election sheets from an official FEC XLSX."""
    try:
        manifest = import_fec_workbook(
            workbook,
            year=year,
            source_release_date=_date_value(
                source_release_date, option="--source-release-date"
            ),
            dataset_id=dataset_id,
            label=label,
            cutoff_date=_date_value(cutoff, option="--cutoff"),
            source_url=source_url,
            output_root=output,
            force=force,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(manifest.model_dump_json(indent=2))
