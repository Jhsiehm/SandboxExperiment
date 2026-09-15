"""Helpers for turning fractional targets/weights into exact counts."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .schemas import PopulationConstraint


def largest_remainder(total: int, values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if total < 0:
        raise ValueError("total must be nonnegative")
    if np.any(values < 0) or not np.all(np.isfinite(values)):
        raise ValueError("values must be finite and nonnegative")
    if len(values) == 0:
        if total == 0:
            return np.asarray([], dtype=int)
        raise ValueError("cannot allocate a positive total to zero values")
    if values.sum() == 0:
        if total == 0:
            return np.zeros(len(values), dtype=int)
        raise ValueError("cannot allocate a positive total from all-zero values")
    scaled = values / values.sum() * total
    base = np.floor(scaled).astype(int)
    remainder = total - int(base.sum())
    if remainder:
        fractional = scaled - base
        order = np.argsort(-fractional, kind="stable")
        base[order[:remainder]] += 1
    return base


def integerize_weights(weights: np.ndarray, target_n: int, seed: int) -> np.ndarray:
    """Fast stochastic integerization that preserves only the total exactly."""
    weights = np.asarray(weights, dtype=float)
    if target_n < 1:
        raise ValueError("target_n must be positive")
    if np.any(weights < 0) or not np.all(np.isfinite(weights)):
        raise ValueError("weights must be finite and nonnegative")
    if weights.sum() <= 0:
        raise ValueError("weights must have a positive sum")
    scaled = weights / weights.sum() * target_n
    counts = np.floor(scaled).astype(int)
    residual = target_n - int(counts.sum())
    if residual:
        fractions = scaled - counts
        positive = np.flatnonzero(fractions > 0)
        if residual > len(positive):
            raise RuntimeError("integerization residual exceeds positive fractional cells")
        probabilities = fractions[positive] / fractions[positive].sum()
        rng = np.random.default_rng(seed)
        chosen = rng.choice(positive, size=residual, replace=False, p=probabilities)
        counts[chosen] += 1
    if int(counts.sum()) != target_n:
        raise RuntimeError("integerization did not preserve target population")
    return counts


def balance_integer_margins(
    donors: pd.DataFrame,
    counts: np.ndarray,
    constraints: list[PopulationConstraint],
) -> np.ndarray:
    """Repair integerized counts to exact fitted margins using supported donor-cell moves.

    A move transfers represented count between two donor cells that agree on every other fitted
    dimension.  It can therefore repair one margin without disturbing margins already repaired (or
    any remaining fitted margin).  Non-fitted donor attributes may change by the small rounding
    correction, while every resulting combination remains observed in the donor support.
    """
    result = np.asarray(counts, dtype=np.int64).copy()
    if len(result) != len(donors):
        raise ValueError("counts and donors must have the same length")
    if np.any(result < 0):
        raise ValueError("integerized counts must be nonnegative")
    target_maps: dict[str, dict[str, int]] = {}
    for row in constraints:
        if row.role != "raking":
            continue
        if not np.isclose(row.target_count, round(row.target_count), rtol=0, atol=1e-8):
            raise ValueError("balanced integerization requires integer marginal targets")
        target_maps.setdefault(row.dimension, {})[row.category] = int(
            round(row.target_count)
        )
    dimensions = list(target_maps)
    for dimension in dimensions:
        other_dimensions = [name for name in dimensions if name != dimension]
        values = donors[dimension].astype(str).to_numpy()
        target = target_maps[dimension]
        categories = sorted(set(values) | set(target))
        actual = {
            category: int(result[values == category].sum()) for category in categories
        }
        delta = {category: actual[category] - target.get(category, 0) for category in categories}
        if not any(delta.values()):
            continue
        if other_dimensions:
            group_keys = list(
                donors[other_dimensions].astype(str).itertuples(index=False, name=None)
            )
        else:
            group_keys = [()] * len(donors)
        indices: defaultdict[tuple[tuple[str, ...], str], list[int]] = defaultdict(list)
        for index, (group, category) in enumerate(zip(group_keys, values)):
            indices[(group, str(category))].append(index)
        deficit_categories = [category for category in categories if delta[category] < 0]
        for deficit_category in deficit_categories:
            target_indices = np.flatnonzero(values == deficit_category)
            for target_index in target_indices:
                needed = -delta[deficit_category]
                if needed <= 0:
                    break
                group = group_keys[int(target_index)]
                for excess_category in categories:
                    available_excess = delta[excess_category]
                    if available_excess <= 0:
                        continue
                    for source_index in indices.get((group, excess_category), []):
                        movable = min(
                            needed,
                            available_excess,
                            int(result[source_index]),
                        )
                        if movable <= 0:
                            continue
                        result[source_index] -= movable
                        result[target_index] += movable
                        delta[excess_category] -= movable
                        delta[deficit_category] += movable
                        needed -= movable
                        available_excess -= movable
                        if needed <= 0 or available_excess <= 0:
                            break
                    if needed <= 0:
                        break
        remaining = {category: value for category, value in delta.items() if value}
        if remaining:
            raise RuntimeError(
                f"could not balance integerized {dimension} margin within donor support: "
                f"{remaining}"
            )
    for dimension, targets in target_maps.items():
        values = donors[dimension].astype(str).to_numpy()
        for category, expected in targets.items():
            actual = int(result[values == category].sum())
            if actual != expected:
                raise RuntimeError(
                    f"balanced integerization missed {dimension}={category}: "
                    f"expected {expected}, got {actual}"
                )
    return result


def controlled_integerize(
    donors: pd.DataFrame,
    weights: np.ndarray,
    constraints: list[PopulationConstraint],
    *,
    target_n: int,
    time_limit_s: float = 30.0,
) -> np.ndarray:
    """Find integer donor replication counts that preserve fitted marginals exactly.

    The mixed-integer program minimizes L1 distance from the fractional raked weights. It is meant
    for compressed donor/profile pools, not millions of raw PUMS rows.
    """
    weights = np.asarray(weights, dtype=float)
    n = len(weights)
    if n != len(donors):
        raise ValueError("weights and donors must have the same length")
    if n == 0:
        raise ValueError("donor pool is empty")
    raking = [row for row in constraints if row.role == "raking"]
    rows: list[np.ndarray] = []
    targets: list[float] = []
    for constraint in raking:
        if constraint.dimension not in donors:
            raise ValueError(f"missing donor dimension {constraint.dimension}")
        target = float(constraint.target_count)
        if not np.isclose(target, round(target), atol=1e-8):
            raise ValueError("controlled integerization requires integer marginal targets")
        indicator = (
            donors[constraint.dimension].astype(str).to_numpy() == constraint.category
        ).astype(float)
        rows.append(np.concatenate([indicator, np.zeros(2 * n)]))
        targets.append(float(round(target)))
    total_row = np.concatenate([np.ones(n), np.zeros(2 * n)])
    rows.append(total_row)
    targets.append(float(target_n))

    # x_i - positive_deviation_i + negative_deviation_i = fractional_weight_i
    for idx in range(n):
        row = np.zeros(3 * n)
        row[idx] = 1.0
        row[n + idx] = -1.0
        row[2 * n + idx] = 1.0
        rows.append(row)
        targets.append(float(weights[idx]))

    matrix = np.vstack(rows)
    rhs = np.asarray(targets, dtype=float)
    objective = np.concatenate([np.zeros(n), np.ones(2 * n)])
    integrality = np.concatenate([np.ones(n, dtype=int), np.zeros(2 * n, dtype=int)])
    lower = np.zeros(3 * n)
    upper = np.full(3 * n, np.inf)
    upper[:n] = target_n
    result = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=LinearConstraint(matrix, rhs, rhs),
        options={"time_limit": time_limit_s, "presolve": True},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"controlled integerization failed: {result.message}")
    counts = np.rint(result.x[:n]).astype(int)
    if int(counts.sum()) != target_n:
        raise RuntimeError("controlled integerization did not preserve total population")
    for constraint in raking:
        actual = int(
            counts[
                donors[constraint.dimension].astype(str).to_numpy() == constraint.category
            ].sum()
        )
        expected = int(round(constraint.target_count))
        if actual != expected:
            raise RuntimeError(
                f"controlled integerization missed {constraint.dimension}={constraint.category}: "
                f"expected {expected}, got {actual}"
            )
    return counts
