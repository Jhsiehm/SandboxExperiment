"""Population constraint loading, checks, and uncertainty realizations."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .integerize import largest_remainder
from .schemas import PopulationConstraint, PopulationSpec


def load_constraints(path: str | Path) -> list[PopulationConstraint]:
    frame = pd.read_csv(path)
    required = {"dimension", "category", "target_count", "source_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("constraint file missing columns: " + ", ".join(sorted(missing)))
    rows: list[PopulationConstraint] = []
    for record in frame.to_dict(orient="records"):
        clean = {
            key: (None if pd.isna(value) else value)
            for key, value in record.items()
        }
        rows.append(PopulationConstraint.model_validate(clean))
    return rows


def constraints_to_frame(constraints: list[PopulationConstraint]) -> pd.DataFrame:
    return pd.DataFrame([row.model_dump(mode="json") for row in constraints])


def validate_constraints(spec: PopulationSpec, constraints: list[PopulationConstraint]) -> None:
    raking = [row for row in constraints if row.role == "raking"]
    if not raking:
        raise ValueError("at least one raking constraint is required")
    seen: set[tuple[str, str]] = set()
    totals: dict[str, float] = defaultdict(float)
    for row in raking:
        key = (row.dimension, row.category)
        if key in seen:
            raise ValueError(f"duplicate raking constraint: {row.dimension}/{row.category}")
        seen.add(key)
        if row.universe != spec.universe:
            raise ValueError(
                f"constraint {row.dimension}/{row.category} universe={row.universe} "
                f"does not match spec universe={spec.universe}"
            )
        totals[row.dimension] += row.target_count
    for dimension, total in totals.items():
        if not np.isclose(total, spec.target_population, rtol=0, atol=1e-6):
            raise ValueError(
                f"raking dimension {dimension} sums to {total}, "
                f"expected {spec.target_population}"
            )


def sample_constraint_realization(
    constraints: list[PopulationConstraint],
    *,
    target_population: int,
    seed: int,
) -> list[PopulationConstraint]:
    """Sample a plausible target vector using reported 90-percent MOEs.

    This treats each cell's published MOE as a normal approximation. It is an uncertainty stress
    test, not a substitute for Census replicate-weight methods.
    """
    rng = np.random.default_rng(seed)
    grouped: dict[str, list[PopulationConstraint]] = defaultdict(list)
    passthrough: list[PopulationConstraint] = []
    for row in constraints:
        if row.role == "raking":
            grouped[row.dimension].append(row)
        else:
            passthrough.append(row)
    sampled: list[PopulationConstraint] = []
    for dimension, rows in grouped.items():
        values = []
        for row in rows:
            sd = (row.moe90 or 0.0) / 1.645
            draw = row.target_count if sd == 0 else rng.normal(row.target_count, sd)
            values.append(max(float(draw), 0.0))
        integerized = largest_remainder(target_population, np.asarray(values, dtype=float))
        for row, value in zip(rows, integerized):
            sampled.append(
                row.model_copy(
                    update={
                        "target_count": float(value),
                        "notes": (row.notes + " sampled from 90% MOE realization").strip(),
                    }
                )
            )
    return sampled + passthrough
