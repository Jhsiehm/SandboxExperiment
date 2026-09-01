"""AgentSociety 2 forecaster: one agent, frozen date, citation-required JSON."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from psbx.society.shim import load_as2

_EnvBase, _tool, AgentBase = load_as2()


class ForecasterAgent(AgentBase):
    """Forecasts binary events using only FrozenEpochEnv search/fetch tools."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().__init__(*args, **kwargs)
        except TypeError:
            super().__init__()
        self._last_forecast: dict[str, Any] | None = None

    @classmethod
    def mcp_description(cls) -> str:
        return (
            "ForecasterAgent: contamination-controlled historical forecaster. "
            "Treats Env.epoch_clock as now. Must cite retrieved documents. "
            "Never invents a default probability."
        )

    @classmethod
    def description(cls) -> str:
        return cls.mcp_description()

    @classmethod
    def init_description(cls) -> str:
        return (
            "ForecasterAgent: JSON {p, rationale} from FrozenEpochEnv only. "
            "create(workspace_path, profile, config); "
            "from_workspace(workspace_path, service_proxy)."
        )

    @classmethod
    def create(cls, workspace_path: Path, profile: dict, config: dict) -> None:
        from psbx.society.workspaces import write_agent_workspace

        agent_id = int(profile.get("id") or 0)
        write_agent_workspace(
            Path(workspace_path).parent,
            {"id": agent_id, "profile": profile, "config": config},
        )

    async def restore(self, workspace_path: Path, service_proxy: Any) -> None:
        await super().restore(workspace_path, service_proxy)
        self._last_forecast = None

    async def ask(self, message: str, readonly: bool = True, *, t: Any = None) -> str:
        del readonly, t
        acompletion = getattr(self, "acompletion", None)
        if callable(acompletion):
            try:
                response = await acompletion([{"role": "user", "content": message}])
                choices = getattr(response, "choices", None)
                if choices:
                    return choices[0].message.content or ""
            except Exception:
                pass
        return (
            "Use FrozenEpochEnv.epoch_clock, evidence_pack, search, and fetch, "
            'then output JSON {"p": 0-1, "rationale": "..."} '
            f"for: {message}"
        )

    async def step(self, tick: int, t: datetime) -> str:
        self._current_time = t
        return f"ForecasterAgent {getattr(self, 'id', 1)} tick={tick} now={t.date().isoformat()}"

    async def to_workspace(self, workspace_path: Path) -> None:
        self.persist_agent_json(tick=None, t=self._current_time)
        await super().to_workspace(workspace_path)
