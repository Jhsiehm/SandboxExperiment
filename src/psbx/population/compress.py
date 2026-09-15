"""Compress synthetic residents into weighted representative cells."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from .integerize import largest_remainder


def _cell_id(attributes: dict) -> str:
    payload = json.dumps(attributes, sort_keys=True, separators=(",", ":"), default=str)
    return "cell-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compress_population(population: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    if not fields:
        raise ValueError("representative cell fields cannot be empty")
    missing = set(fields) - set(population.columns)
    if missing:
        raise ValueError("population missing cell fields: " + ", ".join(sorted(missing)))
    cells = (
        population.groupby(fields, dropna=False, sort=True)
        .size()
        .rename("population_weight")
        .reset_index()
    )
    total = int(cells["population_weight"].sum())
    cells["population_share"] = cells["population_weight"] / total
    cells["cell_id"] = [
        _cell_id({field: row[field] for field in fields})
        for _, row in cells.iterrows()
    ]
    return cells[["cell_id", *fields, "population_weight", "population_share"]]


def compress_weighted_population(
    population: pd.DataFrame,
    fields: list[str],
    *,
    weight_column: str = "population_weight",
) -> pd.DataFrame:
    """Compress an already weighted population without expanding one row per resident.

    Production state populations contain tens of millions of represented residents.  Keeping the
    integerized count on each safe demographic cell preserves the represented total while avoiding
    a wasteful and privacy-confusing person-row expansion.
    """
    if not fields:
        raise ValueError("representative cell fields cannot be empty")
    missing = set(fields) - set(population.columns)
    if missing:
        raise ValueError("population missing cell fields: " + ", ".join(sorted(missing)))
    if weight_column not in population:
        raise ValueError(f"population weight column not found: {weight_column}")
    frame = population.copy()
    weights = pd.to_numeric(frame[weight_column], errors="coerce")
    if weights.isna().any() or (weights < 0).any():
        raise ValueError("population weights must be finite and nonnegative")
    frame[weight_column] = weights
    cells = (
        frame.groupby(fields, dropna=False, sort=True)[weight_column]
        .sum()
        .rename("population_weight")
        .reset_index()
    )
    cells = cells.loc[cells["population_weight"] > 0].reset_index(drop=True)
    if cells.empty:
        raise ValueError("weighted population has no positive cells")
    rounded = np.rint(cells["population_weight"].to_numpy(float)).astype(np.int64)
    if not np.allclose(cells["population_weight"], rounded, rtol=0, atol=1e-8):
        raise ValueError("population weights must be integerized before compression")
    cells["population_weight"] = rounded
    total = int(cells["population_weight"].sum())
    cells["population_share"] = cells["population_weight"] / total
    cells["cell_id"] = [
        _cell_id({field: row[field] for field in fields})
        for _, row in cells.iterrows()
    ]
    return cells[["cell_id", *fields, "population_weight", "population_share"]]


def allocate_reasoning_budget(cells: pd.DataFrame, budget: int) -> pd.DataFrame:
    result = cells.copy()
    if budget < 0:
        raise ValueError("reasoning budget must be nonnegative")
    if budget == 0:
        result["reasoning_calls"] = 0
        return result
    allocation = largest_remainder(
        budget,
        result["population_weight"].to_numpy(dtype=float),
    )
    result["reasoning_calls"] = allocation.astype(int)
    if int(result["reasoning_calls"].sum()) != budget:
        raise RuntimeError("reasoning budget allocation is not exact")
    return result


def effective_sample_size(weights: np.ndarray) -> float:
    values = np.asarray(weights, dtype=float)
    if values.sum() <= 0:
        return 0.0
    normalized = values / values.sum()
    return float(1.0 / np.square(normalized).sum())
