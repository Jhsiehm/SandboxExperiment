"""AgentSociety 2 environment: contemporaneous search, frozen clock.

Class lives in this file (scanner requirement). Tools hard-assert
published_at <= epoch.cutoff_date on every search/fetch.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psbx.society.shim import load_as2

EnvBase, tool, _AgentBase = load_as2()


class FrozenEpochEnv(EnvBase):
    """Cutoff-enforced document environment for historical forecasting."""

    def __init__(self, config: Any | None = None) -> None:
        super().__init__()
        self.epoch_id = "e2012"
        self.cutoff: date = date(2012, 6, 30)
        self.min_prominence = 0.0
        self._index = None
        self.queries: list[str] = []
        self.n_calls = 0

    @classmethod
    def mcp_description(cls) -> str:
        return (
            "FrozenEpochEnv: local search over a reconstructed web corpus. "
            "Every document is hard-filtered at published_at <= epoch cutoff. "
            "No network egress. Clock is the cutoff date."
        )

    def bind_index(self, index: Any, cutoff: date, epoch_id: str, min_prominence: float = 0.0) -> None:
        self._index = index
        self.cutoff = cutoff
        self.epoch_id = epoch_id
        self.min_prominence = min_prominence
        self.queries = []
        self.n_calls = 0

    def _require_index(self) -> Any:
        if self._index is None:
            raise RuntimeError("FrozenEpochEnv.bind_index() was not called")
        return self._index

    @tool(readonly=True, kind="observe")
    def epoch_clock(self, agent_id: int) -> dict[str, Any]:
        """Frozen 'now' for this epoch. Treat as the only clock."""
        del agent_id
        return {
            "now": self.cutoff.isoformat(),
            "epoch_id": self.epoch_id,
            "min_prominence": self.min_prominence,
        }

    @tool(readonly=True)
    def search(self, agent_id: int, query: str, k: int = 10) -> list[dict[str, Any]]:
        """Search contemporaneous documents. Results are cutoff-filtered."""
        del agent_id
        index = self._require_index()
        self.queries.append(query)
        self.n_calls += 1
        hits = index.search(query, k=k, min_prominence=self.min_prominence)
        rows = []
        for hit in hits:
            published = hit.published_at.date()
            if published > self.cutoff:
                raise AssertionError(
                    f"query-time leakage: {hit.document_id} published_at={published} > {self.cutoff}"
                )
            rows.append(
                {
                    "document_id": hit.document_id,
                    "title": hit.title,
                    "outlet": hit.outlet,
                    "published_at": hit.published_at.isoformat(),
                    "snippet": hit.snippet,
                    "prominence": hit.prominence,
                }
            )
        return rows

    @tool(readonly=True)
    def fetch(self, agent_id: int, document_id: str) -> dict[str, Any]:
        """Fetch full document text. Embedding is stripped."""
        del agent_id
        index = self._require_index()
        self.n_calls += 1
        doc = index.public_document(document_id)
        published = datetime.fromisoformat(str(doc["published_at"]).replace("Z", "+00:00"))
        if published.date() > self.cutoff:
            raise AssertionError(
                f"query-time leakage: {document_id} published_at={published.date()} > {self.cutoff}"
            )
        return doc

    async def step(self, tick: int, t: datetime) -> None:
        del tick
        self.t = t

    async def to_workspace(self, workspace_path: Any = None) -> None:
        await super().to_workspace(workspace_path)
