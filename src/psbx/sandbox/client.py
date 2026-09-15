"""In-process and HTTP clients sharing the same search contract."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import httpx

from psbx.corpus.index import HybridIndex
from psbx.schemas import EvidenceUse, SearchHit


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
    @property
    def n_calls(self) -> int: ...


class RetrievalBudgetExceeded(RuntimeError):
    """A forecast attempted retrieval after its independent allowance expired."""


class EvidencePolicyViolation(RuntimeError):
    """A research run attempted to read evidence without authenticated provenance."""


class EvidencePolicySearchClient:
    """Filter a transport according to an explicit practice/research evidence policy."""

    def __init__(self, backend: SearchClient, evidence_use: EvidenceUse):
        self.backend = backend
        self.evidence_use = evidence_use

    @property
    def queries(self) -> list[str]:
        return self.backend.queries

    @property
    def n_calls(self) -> int:
        return self.backend.n_calls

    @property
    def env(self) -> object | None:
        return getattr(self.backend, "env", None)

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        if self.evidence_use == "practice":
            return self.backend.search(
                query,
                k=k,
                min_prominence=min_prominence,
                source_types=source_types,
            )
        # Search the transport's complete bounded window before filtering so an
        # unverified high-ranking record cannot hide eligible material below it.
        hits = self.backend.search(
            query,
            k=25,
            min_prominence=min_prominence,
            source_types=source_types,
        )
        return [hit for hit in hits if hit.authenticity.startswith("authenticated_")][:k]

    def fetch(self, document_id: str) -> dict:
        payload = self.backend.fetch(document_id)
        if self.evidence_use == "research" and not str(
            payload.get("authenticity", "unverified")
        ).startswith("authenticated_"):
            raise EvidencePolicyViolation(
                f"document {document_id!r} is not eligible for research evidence"
            )
        return payload


class ForecastSearchClient:
    """Question/model-scoped accounting over a reusable search transport.

    The wrapped HTTP connection or in-memory index may be shared for efficiency;
    queries, calls, and the hard allowance never are.
    """

    def __init__(self, backend: SearchClient, max_calls: int):
        if max_calls < 0:
            raise ValueError("max_calls must be non-negative")
        while isinstance(backend, ForecastSearchClient):
            backend = backend.backend
        self.backend = backend
        self.max_calls = max_calls
        self._queries: list[str] = []
        self._n_calls = 0

    @property
    def n_calls(self) -> int:
        return self._n_calls

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self._n_calls)

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    @property
    def env(self) -> object | None:
        return getattr(self.backend, "env", None)

    def _reserve(self) -> None:
        if self._n_calls >= self.max_calls:
            raise RetrievalBudgetExceeded(
                "forecast retrieval allowance exhausted; tool call refused"
            )
        self._n_calls += 1

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        self._reserve()
        self._queries.append(query)
        if source_types is None:
            return self.backend.search(
                query,
                k=k,
                min_prominence=min_prominence,
            )
        return self.backend.search(
            query,
            k=k,
            min_prominence=min_prominence,
            source_types=source_types,
        )

    def fetch(self, document_id: str) -> dict:
        self._reserve()
        return self.backend.fetch(document_id)


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
        return self.index.search(query, k=k, min_prominence=floor, source_types=source_types)

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
        self._http = (
            httpx.Client(transport=transport, timeout=30.0)
            if transport
            else httpx.Client(timeout=30.0)
        )

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    def health(self) -> dict[str, Any]:
        response = self._http.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def require_selection(
        self,
        epoch_id: str,
        source_type: str | None,
        cutoff: date | str,
    ) -> None:
        """Fail closed if a run points at the wrong isolated corpus cell."""
        health = self.health()
        expected_source = source_type or "all"
        expected_cutoff = cutoff.isoformat() if isinstance(cutoff, date) else str(cutoff)
        if (
            health.get("epoch") != epoch_id
            or health.get("selection") != expected_source
            or health.get("cutoff") != expected_cutoff
        ):
            raise RuntimeError(
                "search sidecar selection mismatch: "
                f"wanted epoch={epoch_id} source={expected_source} cutoff={expected_cutoff}, "
                f"got epoch={health.get('epoch')} source={health.get('selection')} "
                f"cutoff={health.get('cutoff')}. "
                "Restart it with: psbx sandbox up "
                f"--epoch {epoch_id}" + (f" --source-type {source_type}" if source_type else "")
            )

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
