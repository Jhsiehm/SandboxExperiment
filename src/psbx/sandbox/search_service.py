"""Local HTTP search API — the only tool the agent gets."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from psbx.corpus.index import HybridIndex
from psbx.sandbox.clock import clock_payload
from psbx.schemas import FetchRequest, SearchHit, SearchRequest

query_log: list[dict[str, Any]] = []


class FetchResponse(BaseModel):
    document: dict[str, Any]


def create_app(index: HybridIndex) -> FastAPI:
    app = FastAPI(title="psbx-search", version="0.1.0")

    @app.post("/search", response_model=list[SearchHit])
    def search(body: SearchRequest) -> list[SearchHit]:
        hits = index.search(
            body.query,
            k=body.k,
            min_prominence=body.min_prominence,
            source_types=list(body.source_types) or None,
        )
        for hit in hits:
            assert hit.published_at.date() <= index.cutoff
        query_log.append({"query": body.query, "k": body.k, "n": len(hits)})
        return hits

    @app.post("/fetch")
    def fetch(body: FetchRequest) -> dict[str, Any]:
        try:
            doc = index.public_document(body.document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown document_id") from exc
        query_log.append({"fetch": body.document_id})
        return doc

    @app.get("/archive")
    def archive(url: str = "") -> dict[str, Any]:
        """Replay a URL from the frozen index only. No live origin fetch."""
        doc = index.lookup_url(url)
        if doc is None:
            raise HTTPException(status_code=404, detail="not in frozen index")
        assert doc.published_at.date() <= index.cutoff
        query_log.append({"archive": url})
        return index.public_document(doc.id)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "cutoff": index.cutoff.isoformat()}

    @app.get("/clock")
    def clock() -> dict[str, str | None]:
        """Wall clock as seen inside this process (libfaketime if LD_PRELOAD is set)."""
        return clock_payload(index.cutoff)

    return app


def serve(index: HybridIndex, host: str = "127.0.0.1", port: int = 8766, uds: str | None = None) -> None:
    import uvicorn

    app = create_app(index)
    if uds:
        uvicorn.run(app, uds=uds, log_level="warning")
        return
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main_from_env() -> None:
    from psbx.config import load_epochs
    from psbx.corpus.index import load_index

    epoch_id = os.environ.get("PSBX_EPOCH", "e2012")
    index = load_index(load_epochs()[epoch_id])
    uds = os.environ.get("PSBX_SEARCH_UDS")
    host = os.environ.get("PSBX_SEARCH_HOST", "0.0.0.0")
    port = int(os.environ.get("PSBX_SEARCH_PORT", "8766"))
    serve(index, host=host, port=port, uds=uds or None)


if __name__ == "__main__":
    main_from_env()
