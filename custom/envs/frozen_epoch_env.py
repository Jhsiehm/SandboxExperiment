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

    def __init__(
        self,
        config: Any | None = None,
        epoch_id: str = "e2012",
        min_prominence: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        payload = dict(config or {})
        payload.update(kwargs)
        self.epoch_id = str(payload.get("epoch_id") or epoch_id)
        self.cutoff: date = date(2012, 6, 30)
        self.min_prominence = float(payload.get("min_prominence", min_prominence))
        self._index = None
        self.queries: list[str] = []
        self.n_calls = 0
        self._evidence: dict[str, Any] | None = None
        self._personas: list[dict[str, Any]] = []

    @classmethod
    def mcp_description(cls) -> str:
        return (
            "FrozenEpochEnv: local search over a reconstructed web corpus. "
            "Every document is hard-filtered at published_at <= epoch cutoff. "
            "No network egress. Clock is the cutoff date."
        )

    @classmethod
    def description(cls) -> str:
        return cls.mcp_description()

    @classmethod
    def init_description(cls) -> str:
        return (
            "FrozenEpochEnv(epoch_id='e2012', min_prominence=0.0): "
            "cutoff-locked search/fetch. Autoloads the psbx index for epoch_id."
        )

    @classmethod
    def is_concurrency_safe(cls) -> bool:
        return False

    def bind_index(
        self,
        index: Any,
        cutoff: date,
        epoch_id: str,
        min_prominence: float = 0.0,
    ) -> None:
        self._index = index
        self.cutoff = cutoff
        self.epoch_id = epoch_id
        self.min_prominence = min_prominence
        self.queries = []
        self.n_calls = 0

    def bind_evidence(self, pack: Any) -> None:
        """Shared retrieval pack so swarm workers do not search independently."""
        if pack is None:
            self._evidence = None
            return
        if isinstance(pack, dict):
            self._evidence = pack
            return
        self._evidence = {
            "queries": list(getattr(pack, "queries", [])),
            "hits_text": getattr(pack, "hits_text", ""),
            "n_tool_calls": int(getattr(pack, "n_tool_calls", 0)),
            "docs": [
                {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "published_at": doc.get("published_at"),
                    "source_type": doc.get("source_type"),
                    "text": (str(doc.get("text") or "")[:800]),
                }
                for doc in list(getattr(pack, "docs", []))
            ],
        }

    def bind_personas(self, personas: list[Any]) -> None:
        """Explicit simulation personas, 0-indexed to match swarm bodies."""
        rows: list[dict[str, Any]] = []
        for persona in personas or []:
            if hasattr(persona, "model_dump"):
                rows.append(persona.model_dump(mode="json"))
            elif isinstance(persona, dict):
                rows.append(dict(persona))
        self._personas = rows

    def _autoload_index(self) -> None:
        from psbx.config import load_epochs
        from psbx.corpus.index import load_index

        epoch = load_epochs()[self.epoch_id]
        self.bind_index(
            load_index(epoch),
            epoch.cutoff_date,
            epoch.id,
            min_prominence=self.min_prominence,
        )

    def _require_index(self) -> Any:
        if self._index is None:
            self._autoload_index()
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
    def evidence_pack(self, agent_id: int) -> dict[str, Any]:
        """Shared contemporaneous pack. Swarm workers read this; they do not search."""
        del agent_id
        if self._evidence is None:
            return {"available": False, "note": "No shared pack yet. Use search/fetch."}
        return {"available": True, **self._evidence}

    @tool(readonly=True)
    def list_source_types(self, agent_id: int) -> dict[str, Any]:
        """Counts of cutoff-locked documents by source_type. Read-only."""
        del agent_id
        from collections import Counter

        index = self._require_index()
        counts = Counter(str(doc.source_type) for doc in index.docs)
        return {
            "now": self.cutoff.isoformat(),
            "counts": dict(counts),
            "stimulus": ["news", "wire", "wiki", "gov", "trade"],
            "conditioners": ["survey", "ad", "academic"],
        }

    @tool(readonly=True)
    def persona_card(self, agent_id: int) -> dict[str, Any]:
        """Simulation persona for this agent_id (1-based). Never inferred."""
        if not self._personas:
            return {"available": False, "note": "No personas bound. Use explicit config."}
        idx = int(agent_id) - 1
        if idx < 0 or idx >= len(self._personas):
            return {"available": False, "note": f"No persona for agent_id={agent_id}"}
        return {"available": True, "agent_id": agent_id, **self._personas[idx]}

    @tool(readonly=True)
    def search(
        self,
        agent_id: int,
        query: str,
        k: int = 10,
        source_types: str = "",
    ) -> list[dict[str, Any]]:
        """Search contemporaneous documents. Results are cutoff-filtered.

        Optional source_types: comma-separated news,wire,wiki,gov,trade,survey,ad,academic.
        Headlines (news/wire/gov/trade/wiki) are the stimulus; survey/ad/academic condition.
        """
        del agent_id
        index = self._require_index()
        self.queries.append(query)
        self.n_calls += 1
        kinds = [part.strip() for part in str(source_types).split(",") if part.strip()]
        hits = index.search(
            query,
            k=k,
            min_prominence=self.min_prominence,
            source_types=kinds or None,
        )
        rows = []
        for hit in hits:
            published = hit.published_at.date()
            if published > self.cutoff:
                raise AssertionError(
                    f"query-time leakage: {hit.document_id} "
                    f"published_at={published} > {self.cutoff}"
                )
            rows.append(
                {
                    "document_id": hit.document_id,
                    "title": hit.title,
                    "outlet": hit.outlet,
                    "published_at": hit.published_at.isoformat(),
                    "snippet": hit.snippet,
                    "prominence": hit.prominence,
                    "source_type": hit.source_type,
                    "authenticity": hit.authenticity,
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
                f"query-time leakage: {document_id} "
                f"published_at={published.date()} > {self.cutoff}"
            )
        return doc

    async def step(self, tick: int, t: datetime) -> None:
        del tick
        self.t = t

    async def to_workspace(self, workspace_path: Any = None) -> None:
        await super().to_workspace(workspace_path)
