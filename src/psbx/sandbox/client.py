"""In-process and HTTP clients sharing the same search contract."""

from __future__ import annotations

from typing import Protocol

import httpx

from psbx.corpus.index import HybridIndex
from psbx.schemas import SearchHit


class SearchClient(Protocol):
    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]: ...
    def fetch(self, document_id: str) -> dict: ...
    @property
    def queries(self) -> list[str]: ...


class LocalSearchClient:
    def __init__(self, index: HybridIndex, min_prominence: float = 0.0):
        self.index = index
        self.min_prominence = min_prominence
        self._queries: list[str] = []
        self.n_calls = 0

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float | None = None,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        self._queries.append(query)
        self.n_calls += 1
        floor = self.min_prominence if min_prominence is None else min_prominence
        return self.index.search(
            query, k=k, min_prominence=floor, source_types=source_types
        )

    def fetch(self, document_id: str) -> dict:
        self.n_calls += 1
        return self.index.public_document(document_id)


class HttpSearchClient:
    def __init__(self, base_url: str = "http://search", uds: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.uds = uds
        self._queries: list[str] = []
        self.n_calls = 0
        transport = httpx.HTTPTransport(uds=uds) if uds else None
        self._http = httpx.Client(transport=transport, timeout=30.0) if transport else httpx.Client(timeout=30.0)

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        self._queries.append(query)
        self.n_calls += 1
        payload = {"query": query, "k": k, "min_prominence": min_prominence}
        if source_types:
            payload["source_types"] = list(source_types)
        resp = self._http.post(
            f"{self.base_url}/search",
            json=payload,
        )
        resp.raise_for_status()
        return [SearchHit.model_validate(row) for row in resp.json()]

    def fetch(self, document_id: str) -> dict:
        self.n_calls += 1
        resp = self._http.post(f"{self.base_url}/fetch", json={"document_id": document_id})
        resp.raise_for_status()
        return resp.json()
