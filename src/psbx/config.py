from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from psbx.paths import resolve
from psbx.schemas import Epoch, ModelConfig, RunConfig, SwarmRoster


def load_yaml(path: str | Path) -> dict[str, Any]:
    with resolve(path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
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
