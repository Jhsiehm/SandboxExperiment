from __future__ import annotations

import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent
ROOT = _PKG.parents[1]


def repo_root() -> Path:
    override = os.environ.get("PSBX_ROOT")
    if override:
        return Path(override).resolve()
    return ROOT


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else repo_root() / p
