"""Minimal AgentSociety 2 surface so custom modules import without Ray.

When `agentsociety2` is installed, FrozenEpochEnv / ForecasterAgent inherit
the real EnvBase / AgentBase. This shim matches the documented @tool / EnvBase
contract used by the scanner (`custom/envs/*.py`, `custom/agents/*.py`), plus
the create / from_workspace workspace layout (no Ray, no city simulator).
"""

from __future__ import annotations

import json
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

    @classmethod
    def description(cls) -> str:
        return cls.mcp_description()

    @classmethod
    def init_description(cls) -> str:
        return cls.__doc__ or cls.__name__

    @classmethod
    def is_concurrency_safe(cls) -> bool:
        return False

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
        self._id = agent_id
        self.profile = profile or {}
        self._profile = self.profile
        self._config: dict[str, Any] = {}
        self._name = str(self.profile.get("name") or f"Agent_{agent_id}")
        self._current_time: datetime | None = None
        self._step_count = 0
        self._workspace_root: Path | None = None

    @classmethod
    def mcp_description(cls) -> str:
        return cls.__doc__ or cls.__name__

    @classmethod
    def description(cls) -> str:
        return cls.mcp_description()

    @classmethod
    def init_description(cls) -> str:
        return cls.__doc__ or cls.__name__

    @classmethod
    def create(cls, workspace_path: Path, profile: dict, config: dict) -> None:
        from psbx.society.workspaces import write_agent_workspace

        write_agent_workspace(
            Path(workspace_path).parent,
            {
                "id": int(profile.get("id") or 0),
                "profile": profile,
                "config": config,
            },
        )

    @classmethod
    async def from_workspace(cls, workspace_path: Path, service_proxy: Any) -> AgentBase:
        agent = cls()
        await agent.restore(workspace_path, service_proxy)
        return agent

    async def restore(self, workspace_path: Path, service_proxy: Any) -> None:
        del service_proxy
        workspace_path = Path(workspace_path)
        self._workspace_root = workspace_path
        meta_path = workspace_path / "AGENT.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self._id = int(meta.get("agent_id", meta.get("id", 1)))
            self.id = self._id
            self._profile = meta.get("profile") or {}
            self.profile = self._profile
            self._name = str(meta.get("name") or f"Agent_{self._id}")
            self._step_count = int(meta.get("step_count") or 0)
        config_path = workspace_path / "config.json"
        if config_path.exists():
            self._config = json.loads(config_path.read_text(encoding="utf-8"))

    async def ask(self, message: str, readonly: bool = True, *, t: Any = None) -> str:
        del readonly, t
        return message

    async def step(self, tick: int, t: datetime) -> str:
        self._current_time = t
        self._step_count += 1
        return f"Agent {self.id} step {tick}"

    async def to_workspace(self, workspace_path: Path) -> None:
        self.persist_agent_json(tick=self._step_count, t=self._current_time)
        del workspace_path

    def persist_agent_json(self, tick: int | None, t: datetime | None) -> None:
        if self._workspace_root is None:
            return
        payload = {
            "schema_version": 1,
            "agent_class": type(self).__name__,
            "agent_id": self.id,
            "id": self.id,
            "name": self._name,
            "profile": self.profile,
            "step_count": tick if tick is not None else self._step_count,
            "current_time": t.isoformat() if t is not None else None,
        }
        (self._workspace_root / "AGENT.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )


def load_as2() -> tuple[type, Any, type]:
    try:
        from agentsociety2.agent.base import AgentBase as RealAgent
        from agentsociety2.env import EnvBase as RealEnv
        from agentsociety2.env import tool as real_tool

        return RealEnv, real_tool, RealAgent
    except ImportError:
        return EnvBase, tool, AgentBase
