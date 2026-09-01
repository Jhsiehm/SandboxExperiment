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


def agentsociety_root() -> Path | None:
    """Sibling ``AgentSociety`` clone, or ``PSBX_AGENTSOCIETY_ROOT``. Not vendored."""
    override = os.environ.get("PSBX_AGENTSOCIETY_ROOT")
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.exists() else None
    sibling = repo_root().parent / "AgentSociety"
    if sibling.is_dir() and (sibling / "packages" / "agentsociety2").is_dir():
        return sibling
    return None
