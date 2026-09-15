"""Person-level population synthesis by raking and exact integerization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .integerize import controlled_integerize, integerize_weights
from .schemas import PopulationConstraint, PopulationSpec, RakingIteration


@dataclass(frozen=True)
class RakingResult:
    donors: pd.DataFrame
    weights: np.ndarray
    history: list[RakingIteration]


def _raking_constraints(
    constraints: list[PopulationConstraint],
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for row in constraints:
        if row.role != "raking":
            continue
        result.setdefault(row.dimension, {})[row.category] = row.target_count
    return result


def _max_relative_error(
    donors: pd.DataFrame,
    weights: np.ndarray,
    target_maps: dict[str, dict[str, float]],
) -> float:
    worst = 0.0
    for dimension, targets in target_maps.items():
        actual = (
            pd.DataFrame({dimension: donors[dimension].astype(str), "weight": weights})
            .groupby(dimension, dropna=False)["weight"]
            .sum()
        )
        for category, target in targets.items():
            observed = float(actual.get(category, 0.0))
            denominator = max(float(target), 1.0)
            worst = max(worst, abs(observed - target) / denominator)
    return float(worst)


def rake_donors(
    donors: pd.DataFrame,
    constraints: list[PopulationConstraint],
    *,
    target_population: int,
    weight_column: str = "donor_weight",
    max_iterations: int = 500,
    tolerance: float = 1e-5,
) -> RakingResult:
    target_maps = _raking_constraints(constraints)
    if not target_maps:
        raise ValueError("no raking constraints")
    if weight_column not in donors:
        raise ValueError(f"donor weight column not found: {weight_column}")
    frame = donors.copy().reset_index(drop=True)
    for dimension in target_maps:
        frame[dimension] = frame[dimension].astype(str)
    weights = pd.to_numeric(frame[weight_column], errors="coerce").fillna(0.0).to_numpy(float)
    if np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("donor weights must be nonnegative with a positive sum")
    weights = weights / weights.sum() * target_population
    history: list[RakingIteration] = []
    for iteration in range(1, max_iterations + 1):
        for dimension, targets in target_maps.items():
            current = (
                pd.DataFrame({dimension: frame[dimension], "weight": weights})
                .groupby(dimension, dropna=False)["weight"]
                .sum()
            )
            factors: dict[str, float] = {}
            for category, target in targets.items():
                observed = float(current.get(category, 0.0))
                if target > 0 and observed <= 0:
                    raise ValueError(f"structural zero for {dimension}={category}")
                factors[category] = 0.0 if target == 0 else float(target / observed)
            multipliers = frame[dimension].map(factors).fillna(0.0).to_numpy(float)
            weights *= multipliers
        total = float(weights.sum())
        if total <= 0:
            raise ValueError("raking collapsed all donor weights to zero")
        weights *= target_population / total
        error = _max_relative_error(frame, weights, target_maps)
        history.append(
            RakingIteration(
                iteration=iteration,
                max_relative_error=error,
                total_weight=float(weights.sum()),
            )
        )
        if error <= tolerance:
            return RakingResult(frame, weights, history)
    raise RuntimeError(
        f"raking did not converge after {max_iterations} iterations; "
        f"max relative error={history[-1].max_relative_error:.6g}"
    )


def expand_population(
    raking: RakingResult,
    constraints: list[PopulationConstraint],
    spec: PopulationSpec,
) -> pd.DataFrame:
    if len(raking.donors) <= spec.controlled_integerization_max_donors:
        counts = controlled_integerize(
            raking.donors,
            raking.weights,
            constraints,
            target_n=spec.target_population,
        )
    else:
        counts = integerize_weights(raking.weights, spec.target_population, spec.seed)
    repeated = np.repeat(np.arange(len(raking.donors)), counts)
    population = raking.donors.iloc[repeated].reset_index(drop=True).copy()
    population.rename(columns={"donor_id": "source_donor_id"}, inplace=True)
    if "source_donor_id" not in population:
        population["source_donor_id"] = [f"donor-{idx:08d}" for idx in repeated]
    population["replicate_index"] = population.groupby("source_donor_id").cumcount()
    population["synthetic_person_id"] = [
        f"{spec.id}:person:{idx:08d}" for idx in range(1, len(population) + 1)
    ]
    population["population_weight"] = 1
    population["population_id"] = spec.id
    population["epoch_id"] = spec.epoch_id
    provenance = [
        "synthetic_person_id",
        "population_id",
        "epoch_id",
        "source_donor_id",
        "replicate_index",
        "population_weight",
    ]
    if "source_household_id" in population:
        provenance.append("source_household_id")
    selected = provenance + [field for field in spec.profile_fields if field in population]
    selected = list(dict.fromkeys(selected))
    return population[selected]


def build_synthetic_population(
    donors: pd.DataFrame,
    constraints: list[PopulationConstraint],
    spec: PopulationSpec,
) -> tuple[pd.DataFrame, RakingResult]:
    raking = rake_donors(
        donors,
        constraints,
        target_population=spec.target_population,
        weight_column=spec.donor_weight_column,
        max_iterations=spec.max_iterations,
        tolerance=spec.tolerance,
    )
    population = expand_population(raking, constraints, spec)
    return population, raking
