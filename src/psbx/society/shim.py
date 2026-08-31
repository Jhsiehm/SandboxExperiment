"""Minimal AgentSociety 2 surface so custom modules import without Ray.

When `agentsociety2` is installed, FrozenEpochEnv / ForecasterAgent inherit
the real EnvBase / AgentBase. This shim matches the documented @tool / EnvBase
contract used by the scanner (`custom/envs/*.py`, `custom/agents/*.py`).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def tool(*, readonly: bool = True, kind: str | None = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        fn._as2_tool = True  # type: ignore[attr-defined]
        fn._as2_readonly = readonly  # type: ignore[attr-defined]
        fn._as2_kind = kind  # type: ignore[attr-defined]
        return fn

    return decorator


class EnvBase:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self.t: datetime | None = None
        self._workspace: Path | None = None

    @classmethod
    def mcp_description(cls) -> str:
        return cls.__doc__ or cls.__name__

    def _bind_workspace(self, workspace_path: Path | str | None) -> None:
        if workspace_path is not None:
            self._workspace = Path(workspace_path)

    async def step(self, tick: int, t: datetime) -> None:
        self.t = t

    async def to_workspace(self, workspace_path: Any = None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)

    async def restore(self, workspace_path: Any) -> bool:
        self._bind_workspace(workspace_path)
        return False


class AgentBase:
    def __init__(self, agent_id: int = 1, profile: dict | None = None) -> None:
        self.id = agent_id
        self.profile = profile or {}
        self._current_time: datetime | None = None

    @classmethod
    def mcp_description(cls) -> str:
        return cls.__doc__ or cls.__name__

    async def restore(self, workspace_path: Path, service_proxy: Any) -> None:
        del workspace_path, service_proxy

    async def ask(self, message: str, readonly: bool = True, *, t: Any = None) -> str:
        del readonly, t
        return message

    async def step(self, tick: int, t: datetime) -> str:
        self._current_time = t
        return f"Agent {self.id} step {tick}"

    async def to_workspace(self, workspace_path: Path) -> None:
        del workspace_path

    def persist_agent_json(self, tick: int | None, t: datetime | None) -> None:
        del tick, t


def load_as2() -> tuple[type, Any, type]:
    try:
        from agentsociety2.agent.base import AgentBase as RealAgent
        from agentsociety2.env import EnvBase as RealEnv
        from agentsociety2.env import tool as real_tool

        return RealEnv, real_tool, RealAgent
    except ImportError:
        return EnvBase, tool, AgentBase
