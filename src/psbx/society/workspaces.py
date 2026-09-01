"""Write AgentSociety 2 agent workspaces (``agent_0001`` / AGENT.json / config.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STANDARD_WORKSPACE_DIRS = ("state", "memory")


def agent_workspace_path(root: Path, agent_id: int) -> Path:
    return Path(root) / f"agent_{int(agent_id):04d}"


def write_agent_workspace(root: Path, spec: dict[str, Any]) -> Path:
    """Match AgentSociety 2 ``AgentBase.create`` layout without importing Ray."""
    agent_id = int(spec["id"])
    workspace = agent_workspace_path(root, agent_id)
    workspace.mkdir(parents=True, exist_ok=True)
    for rel in STANDARD_WORKSPACE_DIRS:
        (workspace / rel).mkdir(parents=True, exist_ok=True)
    profile = dict(spec.get("profile") or {})
    profile.setdefault("id", agent_id)
    config = dict(spec.get("config") or {})
    (workspace / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    name = str(profile.get("name") or f"Agent_{agent_id}")
    payload = {
        "schema_version": 1,
        "agent_class": config.get("agent_class") or "ForecasterAgent",
        "agent_id": agent_id,
        "id": agent_id,
        "name": name,
        "profile": profile,
        "step_count": 0,
        "current_time": None,
        "tick": None,
        "visible_skills": [],
        "activated_skills": [],
        "disabled_skills": [],
        "default_activated_skills": [],
        "initialized_at": None,
    }
    (workspace / "AGENT.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return workspace


def write_agent_workspaces(root: Path, specs: list[dict[str, Any]]) -> Path:
    dest = Path(root)
    dest.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        write_agent_workspace(dest, spec)
    return dest
