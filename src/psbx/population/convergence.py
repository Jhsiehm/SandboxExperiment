"""Offline representative-agent convergence and cost projection experiments."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from psbx.config import load_models

from .profiles import PROFILE_DIMENSIONS
from .registry import sha256_file

DEFAULT_BUDGETS = (25, 50, 100, 250, 500, 1_000, 5_000)
DEFAULT_SEEDS = (20120630, 20120631, 20120632, 20120633, 20120634)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def _report_outputs_valid(output: Path, report: dict[str, Any]) -> bool:
    checksums = report.get("output_sha256") or {}
    if not checksums:
        return False
    return all(
        (output / name).is_file() and sha256_file(output / name) == expected
        for name, expected in checksums.items()
    )


def parse_integer_list(value: str, *, minimum: int = 1) -> list[int]:
    values: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        number = int(part)
        if number < minimum:
            raise ValueError(f"values must be at least {minimum}")
        if number not in values:
            values.append(number)
    if not values:
        raise ValueError("at least one value is required")
    return values


def _systematic_targets(total: int, budget: int, seed: int) -> np.ndarray:
    if budget < 1 or total < 1:
        raise ValueError("total and budget must be positive")
    step = total / budget
    start = float(np.random.default_rng(seed).uniform(0.0, step))
    return start + np.arange(budget, dtype=float) * step


def _pricing(model_id: str) -> dict[str, Any]:
    models = load_models()
    if model_id not in models:
        raise ValueError(f"unknown model ID for cost projection: {model_id}")
    model = models[model_id]
    return {
        "model_id": model.id,
        "provider": model.provider,
        "model_name": model.model_name,
        "cost_per_1k_input": model.cost_per_1k_input,
        "cost_per_1k_output": model.cost_per_1k_output,
    }


def _usage_projection(
    calls: int,
    *,
    input_tokens_per_call: int,
    output_tokens_per_call: int,
    pricing: dict[str, Any],
) -> dict[str, Any]:
    input_tokens = calls * input_tokens_per_call
    output_tokens = calls * output_tokens_per_call
    cost = (
        input_tokens / 1_000 * float(pricing["cost_per_1k_input"])
        + output_tokens / 1_000 * float(pricing["cost_per_1k_output"])
    )
    return {
        "model_calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "projected_cost_usd": cost,
    }


def analyze_convergence_cells(
    cells_path: str | Path,
    *,
    represented_population: int,
    representative_cells: int,
    budgets: list[int],
    seeds: list[int],
    dimensions: list[str],
    pricing: dict[str, Any],
    input_tokens_per_call: int,
    output_tokens_per_call: int,
    chunksize: int = 200_000,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Stream cells once while evaluating systematic PPS samples for every condition."""
    if any(budget > represented_population for budget in budgets):
        raise ValueError("agent budgets cannot exceed the represented population")
    targets = {
        (budget, seed): _systematic_targets(represented_population, budget, seed)
        for budget in budgets
        for seed in seeds
    }
    target_cursors = {key: 0 for key in targets}
    selected: dict[tuple[int, int], list[dict[str, Any]]] = {
        key: [] for key in targets
    }
    population_counts: dict[str, defaultdict[str, float]] = {
        dimension: defaultdict(float) for dimension in dimensions
    }
    seen_rows = 0
    cumulative_before = 0.0
    usecols = ["cell_id", "population_weight", *dimensions]
    for chunk in pd.read_csv(cells_path, usecols=usecols, chunksize=chunksize):
        weights = pd.to_numeric(chunk["population_weight"], errors="raise").to_numpy(float)
        if np.any(weights <= 0):
            raise ValueError("convergence input requires positive cell weights")
        cumulative = np.cumsum(weights)
        cumulative_after = cumulative_before + float(cumulative[-1])
        seen_rows += len(chunk)
        for dimension in dimensions:
            grouped = chunk.groupby(dimension, dropna=False)["population_weight"].sum()
            for category, weight in grouped.items():
                population_counts[dimension][str(category)] += float(weight)
        for key, positions in targets.items():
            cursor = target_cursors[key]
            end = int(np.searchsorted(positions, cumulative_after, side="left"))
            if end <= cursor:
                continue
            local_positions = positions[cursor:end] - cumulative_before
            indices = np.searchsorted(cumulative, local_positions, side="right")
            records = chunk.iloc[indices][usecols].to_dict(orient="records")
            selected[key].extend(records)
            target_cursors[key] = end
        cumulative_before = cumulative_after
    if seen_rows != representative_cells:
        raise ValueError(
            f"manifest says {representative_cells} cells but CSV contains {seen_rows}"
        )
    if int(round(cumulative_before)) != represented_population:
        raise ValueError(
            f"manifest population {represented_population} does not match cell weights "
            f"{cumulative_before}"
        )
    population_shares = {
        dimension: {
            category: weight / represented_population
            for category, weight in categories.items()
        }
        for dimension, categories in population_counts.items()
    }
    replication_rows: list[dict[str, Any]] = []
    share_vectors: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    for budget in budgets:
        for seed in seeds:
            rows = selected[(budget, seed)]
            if len(rows) != budget:
                raise RuntimeError(
                    f"systematic sample returned {len(rows)} rows for budget={budget}, seed={seed}"
                )
            sample = pd.DataFrame(rows)
            tvds: dict[str, float] = {}
            max_category_error = 0.0
            for dimension in dimensions:
                sample_share = sample[dimension].astype(str).value_counts() / budget
                categories = set(population_shares[dimension]) | set(sample_share.index)
                differences = []
                for category in sorted(categories):
                    observed = float(sample_share.get(category, 0.0))
                    expected = float(population_shares[dimension].get(category, 0.0))
                    differences.append(abs(observed - expected))
                    share_vectors[(budget, dimension, category)].append(observed)
                tvds[dimension] = 0.5 * sum(differences)
                max_category_error = max(max_category_error, *differences)
            unique = sample.drop_duplicates("cell_id")
            usage = _usage_projection(
                budget,
                input_tokens_per_call=input_tokens_per_call,
                output_tokens_per_call=output_tokens_per_call,
                pricing=pricing,
            )
            replication_rows.append(
                {
                    "condition": str(budget),
                    "agent_budget": budget,
                    "seed": seed,
                    "represented_population": represented_population,
                    "representative_cells": representative_cells,
                    "sampled_unique_cells": len(unique),
                    "unique_cell_coverage": len(unique) / representative_cells,
                    "sampled_source_population_share": float(
                        unique["population_weight"].sum() / represented_population
                    ),
                    "effective_sample_size": float(budget),
                    "mean_dimension_tvd": float(np.mean(list(tvds.values()))),
                    "max_dimension_tvd": max(tvds.values()),
                    "max_category_share_error": max_category_error,
                    "tvd_by_dimension": json.dumps(tvds, sort_keys=True),
                    "held_out_error": None,
                    **usage,
                }
            )
    replications = pd.DataFrame(replication_rows)
    summaries: list[dict[str, Any]] = []
    for budget in budgets:
        subset = replications.loc[replications["agent_budget"] == budget]
        seed_ranges = [
            max(values) - min(values)
            for (condition_budget, _, _), values in share_vectors.items()
            if condition_budget == budget and values
        ]
        seed_variances = [
            float(np.var(values))
            for (condition_budget, _, _), values in share_vectors.items()
            if condition_budget == budget and values
        ]
        usage = _usage_projection(
            budget * len(seeds),
            input_tokens_per_call=input_tokens_per_call,
            output_tokens_per_call=output_tokens_per_call,
            pricing=pricing,
        )
        summaries.append(
            {
                "condition": str(budget),
                "agent_budget": budget,
                "replications": len(seeds),
                "mean_dimension_tvd": float(subset["mean_dimension_tvd"].mean()),
                "p95_replication_max_dimension_tvd": float(
                    subset["max_dimension_tvd"].quantile(0.95)
                ),
                "worst_dimension_tvd": float(subset["max_dimension_tvd"].max()),
                "mean_unique_cell_coverage": float(subset["unique_cell_coverage"].mean()),
                "mean_source_population_coverage": float(
                    subset["sampled_source_population_share"].mean()
                ),
                "max_between_seed_category_range": max(seed_ranges, default=0.0),
                "mean_between_seed_category_variance": float(
                    np.mean(seed_variances) if seed_variances else 0.0
                ),
                "max_between_seed_category_variance": max(seed_variances, default=0.0),
                "held_out_error": None,
                **usage,
            }
        )
    for condition, calls in (
        ("full_representative_cells", representative_cells),
        ("full_records", represented_population),
    ):
        summaries.append(
            {
                "condition": condition,
                "agent_budget": calls,
                "replications": 1,
                "mean_dimension_tvd": 0.0,
                "p95_replication_max_dimension_tvd": 0.0,
                "worst_dimension_tvd": 0.0,
                "mean_unique_cell_coverage": 1.0,
                "mean_source_population_coverage": 1.0,
                "max_between_seed_category_range": 0.0,
                "mean_between_seed_category_variance": 0.0,
                "max_between_seed_category_variance": 0.0,
                "held_out_error": None,
                **_usage_projection(
                    calls,
                    input_tokens_per_call=input_tokens_per_call,
                    output_tokens_per_call=output_tokens_per_call,
                    pricing=pricing,
                ),
            }
        )
    summary = pd.DataFrame(summaries)
    detail = {
        "dimensions": dimensions,
        "population_shares": population_shares,
        "note": (
            "This measures demographic representation convergence only. Held-out behavior error "
            "remains null until a sealed behavior-validation artifact is supplied."
        ),
        "metric_definitions": {
            "p95_replication_max_dimension_tvd": (
                "95th percentile across seeds of each replication's worst dimension TVD"
            ),
            "between_seed_category_variance": (
                "population variance across seeded samples for each dimension-category share"
            ),
        },
    }
    return replications, summary, detail


def run_convergence_experiment(
    population_id: str,
    *,
    epoch_id: str = "e2012",
    population_root: str | Path = "data/population",
    budgets: list[int] | None = None,
    seeds: list[int] | None = None,
    dimensions: list[str] | None = None,
    model_id: str = "openrouter-gpt-4.1-mini",
    input_tokens_per_call: int = 800,
    output_tokens_per_call: int = 128,
    force: bool = False,
) -> dict[str, Any]:
    if input_tokens_per_call < 0 or output_tokens_per_call < 0:
        raise ValueError("token projections must be nonnegative")
    budgets = budgets or list(DEFAULT_BUDGETS)
    seeds = seeds or list(DEFAULT_SEEDS)
    dimensions = dimensions or list(PROFILE_DIMENSIONS)
    base = Path(population_root) / epoch_id / population_id
    manifest_path = base / "manifest.json"
    cells_path = base / "representative_cells.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("passed"):
        raise ValueError("convergence requires a validated population manifest")
    expected_cells_hash = (manifest.get("output_sha256") or {}).get(
        "representative_cells.csv"
    )
    actual_cells_hash = sha256_file(cells_path)
    if expected_cells_hash != actual_cells_hash:
        raise ValueError("representative cell checksum does not match population manifest")
    pricing = _pricing(model_id)
    config = {
        "schema_version": 3,
        "experiment": "representative_agent_convergence",
        "population_id": population_id,
        "epoch_id": epoch_id,
        "represented_population": int(manifest["represented_population"]),
        "representative_cells": int(manifest["representative_cells"]),
        "budgets": budgets,
        "seeds": seeds,
        "dimensions": dimensions,
        "pricing": pricing,
        "input_tokens_per_call": input_tokens_per_call,
        "output_tokens_per_call": output_tokens_per_call,
        "actual_llm_calls": 0,
        "costs_are_projections": True,
        "input_sha256": {
            "population_manifest": sha256_file(manifest_path),
            "representative_cells": actual_cells_hash,
        },
    }
    fingerprint = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    run_id = f"convergence-{fingerprint}"
    output = base / "experiments" / run_id
    report_path = output / "report.json"
    if not force and report_path.is_file():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            existing.get("config") == config
            and existing.get("passed")
            and _report_outputs_valid(output, existing)
        ):
            return {**existing, "status": "skipped_valid", "output_dir": str(output)}
    replications, summary, detail = analyze_convergence_cells(
        cells_path,
        represented_population=config["represented_population"],
        representative_cells=config["representative_cells"],
        budgets=budgets,
        seeds=seeds,
        dimensions=dimensions,
        pricing=pricing,
        input_tokens_per_call=input_tokens_per_call,
        output_tokens_per_call=output_tokens_per_call,
    )
    _atomic_csv(output / "replications.csv", replications)
    _atomic_csv(output / "summary.csv", summary)
    report = {
        "run_id": run_id,
        "status": "complete",
        "passed": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "summary": summary.to_dict(orient="records"),
        "detail": detail,
        "output_sha256": {
            "replications.csv": sha256_file(output / "replications.csv"),
            "summary.csv": sha256_file(output / "summary.csv"),
        },
    }
    _atomic_json(report_path, report)
    return {"status": "complete", "output_dir": str(output), **report}
