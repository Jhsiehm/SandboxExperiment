"""Population-fidelity diagnostics."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from .schemas import (
    MarginalError,
    PopulationConstraint,
    PopulationSpec,
    PopulationValidationReport,
)


def validate_population(
    population: pd.DataFrame,
    constraints: list[PopulationConstraint],
    spec: PopulationSpec,
) -> PopulationValidationReport:
    errors: list[MarginalError] = []
    by_dimension: dict[str, list[MarginalError]] = defaultdict(list)
    unsupported: list[str] = []
    for row in constraints:
        if row.dimension not in population:
            unsupported.append(row.dimension)
            continue
        actual_counts = population[row.dimension].astype(str).value_counts()
        actual = float(actual_counts.get(row.category, 0.0))
        absolute = abs(actual - row.target_count)
        relative = absolute / row.target_count if row.target_count > 0 else None
        item = MarginalError(
            role=row.role,
            dimension=row.dimension,
            category=row.category,
            target_count=row.target_count,
            actual_count=actual,
            absolute_error=absolute,
            relative_error=relative,
            moe90=row.moe90,
            error_over_moe90=(
                absolute / row.moe90 if row.moe90 is not None and row.moe90 > 0 else None
            ),
        )
        errors.append(item)
        by_dimension[row.dimension].append(item)
    tvd: dict[str, float] = {}
    for dimension, rows in by_dimension.items():
        total = sum(row.target_count for row in rows)
        tvd[dimension] = (
            0.5 * sum(row.absolute_error for row in rows) / total if total else 0.0
        )
    max_absolute = max((row.absolute_error for row in errors), default=0.0)
    max_relative = max(
        (row.relative_error or 0.0 for row in errors),
        default=0.0,
    )
    max_moe_ratio = max(
        (row.error_over_moe90 for row in errors if row.error_over_moe90 is not None),
        default=None,
    )
    actual_population = len(population)
    passed = (
        actual_population == spec.target_population
        and not unsupported
        and all(value <= spec.validation_tvd_tolerance for value in tvd.values())
        and (
            spec.validation_moe_ratio_tolerance is None
            or max_moe_ratio is None
            or max_moe_ratio <= spec.validation_moe_ratio_tolerance
        )
    )
    return PopulationValidationReport(
        population_id=spec.id,
        epoch_id=spec.epoch_id,
        geography_id=spec.geography.id,
        universe=spec.universe,
        target_population=spec.target_population,
        actual_population=actual_population,
        passed=passed,
        max_absolute_error=max_absolute,
        max_relative_error=max_relative,
        max_error_over_moe90=max_moe_ratio,
        acceptance_rule=(
            f"TVD <= {spec.validation_tvd_tolerance}"
            + (
                ""
                if spec.validation_moe_ratio_tolerance is None
                else f" and cell error/MOE90 <= {spec.validation_moe_ratio_tolerance}"
            )
        ),
        total_variation_by_dimension=tvd,
        marginal_errors=errors,
        unsupported_categories=sorted(set(unsupported)),
        household_integrity="not_guaranteed",
        notes=[
            "Synthetic records are statistically constructed and are not actual residents.",
            "The person-level MVP preserves donor-row joint attributes but does not guarantee "
            "whole-household replication.",
            "Raking constraints measure fitted fidelity; validation-role constraints can "
            "be used for held-out population checks.",
            "Population fidelity does not establish political-behavior fidelity.",
        ],
    )


def validate_weighted_population(
    population: pd.DataFrame,
    constraints: list[PopulationConstraint],
    spec: PopulationSpec,
    *,
    weight_column: str = "population_weight",
) -> PopulationValidationReport:
    """Validate integer weighted cells using represented counts rather than row counts."""
    if weight_column not in population:
        raise ValueError(f"population weight column not found: {weight_column}")
    weights = pd.to_numeric(population[weight_column], errors="coerce")
    if weights.isna().any() or (weights < 0).any():
        raise ValueError("population weights must be finite and nonnegative")
    marginal_errors: list[MarginalError] = []
    unsupported: list[str] = []
    variation: dict[str, float] = {}
    by_dimension: dict[str, list[tuple[float, float]]] = {}
    for row in constraints:
        if row.dimension not in population:
            unsupported.append(f"{row.dimension}={row.category}")
            actual = 0.0
        else:
            matches = population[row.dimension].astype(str) == row.category
            actual = float(weights.loc[matches].sum())
        absolute = abs(actual - row.target_count)
        relative = None if row.target_count == 0 else absolute / row.target_count
        marginal_errors.append(
            MarginalError(
                role=row.role,
                dimension=row.dimension,
                category=row.category,
                target_count=row.target_count,
                actual_count=actual,
                absolute_error=absolute,
                relative_error=relative,
                moe90=row.moe90,
                error_over_moe90=(
                    absolute / row.moe90
                    if row.moe90 is not None and row.moe90 > 0
                    else None
                ),
            )
        )
        by_dimension.setdefault(row.dimension, []).append((actual, row.target_count))
    for dimension, pairs in by_dimension.items():
        actual_total = sum(actual for actual, _ in pairs)
        target_total = sum(target for _, target in pairs)
        denominator = max(actual_total, target_total, 1.0)
        variation[dimension] = 0.5 * sum(
            abs(actual / denominator - target / denominator)
            for actual, target in pairs
        )
    actual_population = int(round(float(weights.sum())))
    max_absolute = max((row.absolute_error for row in marginal_errors), default=0.0)
    max_relative = max(
        (row.relative_error or 0.0 for row in marginal_errors),
        default=0.0,
    )
    max_moe_ratio = max(
        (
            row.error_over_moe90
            for row in marginal_errors
            if row.error_over_moe90 is not None
        ),
        default=None,
    )
    passed = (
        actual_population == spec.target_population
        and not unsupported
        and all(value <= spec.validation_tvd_tolerance for value in variation.values())
        and (
            spec.validation_moe_ratio_tolerance is None
            or max_moe_ratio is None
            or max_moe_ratio <= spec.validation_moe_ratio_tolerance
        )
    )
    return PopulationValidationReport(
        population_id=spec.id,
        epoch_id=spec.epoch_id,
        geography_id=spec.geography.id,
        universe=spec.universe,
        target_population=spec.target_population,
        actual_population=actual_population,
        passed=passed,
        max_absolute_error=max_absolute,
        max_relative_error=max_relative,
        max_error_over_moe90=max_moe_ratio,
        acceptance_rule=(
            f"TVD <= {spec.validation_tvd_tolerance}"
            + (
                ""
                if spec.validation_moe_ratio_tolerance is None
                else f" and cell error/MOE90 <= {spec.validation_moe_ratio_tolerance}"
            )
        ),
        total_variation_by_dimension=variation,
        marginal_errors=marginal_errors,
        unsupported_categories=unsupported,
        household_integrity="not_guaranteed",
        notes=[
            "Counts are represented by integer cell weights; rows are not actual residents.",
            "Person and household models are validated separately and are not linked households.",
            "Population fidelity does not establish political-behavior fidelity.",
        ],
    )
