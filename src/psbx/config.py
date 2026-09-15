from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from psbx.paths import resolve
from psbx.population.schemas import PopulationSpec
from psbx.schemas import (
    Epoch,
    EpochAdvanceSpec,
    ModelConfig,
    PerspectiveCatalog,
    RunConfig,
    SwarmRoster,
)

_YAML_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}


def load_yaml(path: str | Path) -> dict[str, Any]:
    resolved = resolve(path)
    st = resolved.stat()
    key = str(resolved)
    hit = _YAML_CACHE.get(key)
    if hit is not None and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2]
    with resolved.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    _YAML_CACHE[key] = (st.st_mtime, st.st_size, data)
    return data


def load_epochs(path: str | Path = "config/epochs.yaml") -> dict[str, Epoch]:
    raw = load_yaml(path)
    epochs = [Epoch.model_validate(row) for row in raw["epochs"]]
    return {e.id: e for e in epochs}


def load_models(path: str | Path = "config/models.yaml") -> dict[str, ModelConfig]:
    raw = load_yaml(path)
    models = [ModelConfig.model_validate(row) for row in raw["models"]]
    return {m.id: m for m in models}


def load_run(path: str | Path = "config/run.yaml") -> RunConfig:
    return RunConfig.model_validate(load_yaml(path))


def load_swarm(path: str | Path = "config/swarm.yaml") -> SwarmRoster:
    return SwarmRoster.model_validate(load_yaml(path))


def load_sources(path: str | Path = "config/sources.yaml") -> dict[str, Any]:
    return load_yaml(path)


def load_perspectives(path: str | Path = "config/perspectives.yaml") -> PerspectiveCatalog:
    from psbx.society.perspectives import load_perspectives as _load

    return _load(path)


def load_epoch_advance(path: str | Path = "config/epoch-advance.yaml") -> EpochAdvanceSpec:
    from psbx.epochs import load_advance_spec

    return load_advance_spec(path)


def load_population(path: str | Path = "config/track_b_fixture.yaml") -> PopulationSpec:
    """Load the separate Track B population-build contract."""
    from psbx.population.runner import load_population_spec

    return load_population_spec(resolve(path))
