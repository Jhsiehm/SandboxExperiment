from datetime import date

from fastapi.testclient import TestClient

from psbx.config import load_epochs
from psbx.sandbox.client import LocalSearchClient
from psbx.sandbox.clock import faketime_env, faketime_stamp
from psbx.sandbox.harness import search_client_for
from psbx.sandbox.search_service import create_app
from psbx.schemas import RunConfig


def test_faketime_stamp_freezes_end_of_cutoff_day():
    assert faketime_stamp(date(2012, 6, 30)) == "@2012-06-30 12:00:00"
    env = faketime_env(date(2012, 6, 30), lib="/usr/lib/faketime/libfaketime.so.1")
    assert env["FAKETIME"].startswith("@2012-06-30")
    assert env["FAKETIME_NO_CACHE"] == "1"
    assert "libfaketime.so.1" in env["LD_PRELOAD"]


def test_clock_endpoint_reports_cutoff():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    client = TestClient(create_app(index))
    body = client.get("/clock").json()
    assert body["cutoff"] == "2012-06-30"
    assert "now" in body
    assert "today" in body


def test_archive_proxy_serves_index_only():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    client = TestClient(create_app(index))
    known = docs[0]
    ok = client.get("/archive", params={"url": known.url})
    assert ok.status_code == 200
    body = ok.json()
    assert body["id"] == known.id
    assert body["url"] == known.url
    assert body["published_at"][:10] <= "2012-06-30"

    missing = client.get(
        "/archive",
        params={"url": "https://www.nytimes.com/2013/07/01/world/syria.html"},
    )
    assert missing.status_code == 404
    empty = client.get("/archive", params={"url": ""})
    assert empty.status_code == 404
    unknown = client.get("/archive", params={"url": "https://example.com/never-indexed"})
    assert unknown.status_code == 404


def test_host_sandbox_uses_local_client():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    run = RunConfig(
        run_id="t",
        epoch="e2012",
        models=["gpt-oss-2012ish"],
        question_set="data/questions/e2012.jsonl",
        sandbox_mode="host",
    )
    client = search_client_for(run, index)
    assert isinstance(client, LocalSearchClient)
