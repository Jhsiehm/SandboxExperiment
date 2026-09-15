"""Explicit demographic / constituency personas for the training-area swarm."""

from __future__ import annotations

from pathlib import Path

from psbx.config import load_yaml
from psbx.schemas import PerspectiveCatalog, PerspectivePersona, SwarmRoster


def load_perspectives(path: str | Path = "config/perspectives.yaml") -> PerspectiveCatalog:
    catalog = PerspectiveCatalog.model_validate(load_yaml(path))
    if not catalog.simulation_only or not catalog.not_inferred:
        raise ValueError(
            "perspective catalog must be simulation_only and not_inferred; "
            "do not load inferred demographics"
        )
    return catalog


def assign_personas(
    roster: SwarmRoster,
    catalog: PerspectiveCatalog | None = None,
) -> list[PerspectivePersona]:
    """Zip explicit personas onto bodies, cycling the validated panel at scale."""
    catalog = catalog or load_perspectives()
    slotted = sorted(
        [persona for persona in catalog.personas if persona.slot is not None],
        key=lambda persona: int(persona.slot or 0),
    )
    if not slotted:
        return []
    base = catalog.assigned(len(slotted))
    return [base[index % len(base)] for index in range(roster.n_agents)]


def persona_for_index(
    index: int,
    personas: list[PerspectivePersona],
) -> PerspectivePersona | None:
    if 0 <= index < len(personas):
        return personas[index]
    return None
