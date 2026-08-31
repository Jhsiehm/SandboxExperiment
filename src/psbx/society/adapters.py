"""SearchClient that goes through FrozenEpochEnv tools (cutoff asserted there)."""

from __future__ import annotations

from datetime import datetime

from psbx.schemas import SearchHit


class EnvSearchClient:
    def __init__(self, env: object, agent_id: int = 1):
        self.env = env
        self.agent_id = agent_id
        self.n_calls = 0

    @property
    def queries(self) -> list[str]:
        return list(getattr(self.env, "queries", []))

    def search(self, query: str, k: int = 10, min_prominence: float = 0.0) -> list[SearchHit]:
        del min_prominence
        rows = self.env.search(self.agent_id, query, k)  # type: ignore[attr-defined]
        self.n_calls = int(getattr(self.env, "n_calls", self.n_calls + 1))
        hits: list[SearchHit] = []
        for row in rows:
            hits.append(
                SearchHit(
                    document_id=row["document_id"],
                    title=row["title"],
                    outlet=row["outlet"],
                    published_at=datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00")),
                    snippet=row.get("snippet") or "",
                    prominence=float(row.get("prominence") or 0.0),
                )
            )
        return hits

    def fetch(self, document_id: str) -> dict:
        payload = self.env.fetch(self.agent_id, document_id)  # type: ignore[attr-defined]
        self.n_calls = int(getattr(self.env, "n_calls", self.n_calls + 1))
        return payload
