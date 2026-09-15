from __future__ import annotations

import os
import re
from pathlib import Path

_PKG = Path(__file__).resolve().parent
ROOT = _PKG.parents[1]
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def repo_root() -> Path:
    override = os.environ.get("PSBX_ROOT")
    if override:
        return Path(override).resolve()
    return ROOT


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else repo_root() / p


def validate_run_id(run_id: str) -> str:
    """Return a filesystem-safe run identifier or fail before path construction."""
    value = str(run_id).strip()
    if not RUN_ID_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise ValueError(
            "run_id must be 1-128 characters using only letters, numbers, '.', '_', or '-'"
        )
    return value


def run_dir(run_id: str) -> Path:
    """Resolve one validated run directory and enforce containment below data/runs."""
    root = resolve("data/runs").resolve()
    destination = (root / validate_run_id(run_id)).resolve()
    if destination == root or not destination.is_relative_to(root):
        raise ValueError("run_id escapes the data/runs directory")
    return destination


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
