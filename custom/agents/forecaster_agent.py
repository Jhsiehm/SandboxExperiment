"""AgentSociety 2 forecaster: one agent, frozen date, citation-required JSON."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from psbx.society.shim import load_as2

_EnvBase, _tool, AgentBase = load_as2()


class ForecasterAgent(AgentBase):
    """Forecasts binary events using only FrozenEpochEnv search/fetch tools."""

    @classmethod
    def mcp_description(cls) -> str:
        return (
            "ForecasterAgent: contamination-controlled historical forecaster. "
            "Treats Env.epoch_clock as now. Must cite retrieved documents. "
            "Never invents a default probability."
        )

    async def restore(self, workspace_path: Path, service_proxy: Any) -> None:
        await super().restore(workspace_path, service_proxy)
        self._last_forecast: dict[str, Any] | None = None

    async def ask(self, message: str, readonly: bool = True, *, t: Any = None) -> str:
        del readonly, t
        return (
            "Use FrozenEpochEnv.search and FrozenEpochEnv.fetch, then output "
            'JSON {"probability": 0-1, "reasoning": "...", "citations": [...]} '
            f"for: {message}"
        )

    async def step(self, tick: int, t: datetime) -> str:
        self._current_time = t
        return f"ForecasterAgent {getattr(self, 'id', 1)} tick={tick} now={t.date().isoformat()}"

    async def to_workspace(self, workspace_path: Path) -> None:
        self.persist_agent_json(tick=None, t=self._current_time)
        await super().to_workspace(workspace_path)
