from io import BytesIO

import httpx

from psbx.config import load_epochs
from psbx.corpus.fetch_commoncrawl import _outlet_for_url, ingest_commoncrawl
from psbx.corpus.fetch_wikipedia import ingest_wikipedia
from psbx.corpus.ia_http import DEFAULT_UA, ia_get, parse_retry_after, user_agent


def test_user_agent_product_and_optional_suffix(monkeypatch):
    monkeypatch.delenv("PSBX_IA_USER_AGENT_SUFFIX", raising=False)
    assert user_agent() == DEFAULT_UA
    assert "PredictionSandbox" in user_agent()
    monkeypatch.setenv("PSBX_IA_USER_AGENT_SUFFIX", "cursor-grok-4.6")
    assert user_agent().endswith("cursor-grok-4.6")


def test_parse_retry_after_seconds_and_cap():
    assert parse_retry_after("2") == 2.0
    assert parse_retry_after("9999") == 120.0
    assert parse_retry_after(None) == 30.0


def test_ia_get_sends_user_agent_and_retries_429(monkeypatch):
    monkeypatch.delenv("PSBX_IA_USER_AGENT_SUFFIX", raising=False)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert "PredictionSandbox/0.1.0" in request.headers["User-Agent"]
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, headers={"User-Agent": user_agent()})
    resp = ia_get(client, "https://web.archive.org/cdx/search/cdx")
    assert resp.json() == {"ok": True}
    assert calls["n"] == 2


def test_commoncrawl_warc_cutoff_and_domain(tmp_path, monkeypatch):
    from warcio.statusandheaders import StatusAndHeaders
    from warcio.warcwriter import WARCWriter

    root = tmp_path / "cc"
    root.mkdir()
    monkeypatch.setattr("psbx.corpus.fetch_commoncrawl.warc_dir", lambda: root)
    warc_path = root / "sample.warc.gz"
    html = (
        "<html><body>"
        + ("unemployment rate in May 2012 was discussed. " * 20)
        + "</body></html>"
    )
    with warc_path.open("wb") as fh:
        writer = WARCWriter(fh, gzip=True)
        headers = StatusAndHeaders("200 OK", [("Content-Type", "text/html")], protocol="HTTP/1.1")
        rec = writer.create_warc_record(
            "https://www.reuters.com/article/unrate",
            "response",
            payload=BytesIO(html.encode()),
            http_headers=headers,
            warc_headers_dict={"WARC-Date": "2012-05-15T12:00:00Z"},
        )
        writer.write_record(rec)
        future = writer.create_warc_record(
            "https://www.reuters.com/article/july",
            "response",
            payload=BytesIO(html.encode()),
            http_headers=headers,
            warc_headers_dict={"WARC-Date": "2012-07-15T12:00:00Z"},
        )
        writer.write_record(future)
    epoch = load_epochs()["e2012"]
    docs = ingest_commoncrawl(epoch)
    assert docs
    assert all(d.published_at.date() <= epoch.cutoff_date for d in docs)
    assert all(d.outlet == "Reuters" for d in docs)
    assert _outlet_for_url("https://www.nytimes.com/x", [{"domain": "nytimes.com", "name": "NYT"}])


def test_wikipedia_jsonl_cache(tmp_path, monkeypatch):
    cache = tmp_path / "wiki"
    cache.mkdir()
    (cache / "e2012.jsonl").write_text(
        '{"title":"Test","url":"https://en.wikipedia.org/wiki/Test","published_at":"2012-06-01T00:00:00Z","text":"'
        + ("fiscal cliff sequestration debate in congress " * 10)
        + '"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("psbx.corpus.fetch_wikipedia.wiki_cache_dir", lambda: cache)
    epoch = load_epochs()["e2012"]
    docs = ingest_wikipedia(epoch)
    titles = {d.title for d in docs}
    assert "Test" in titles
    assert "United States fiscal cliff" in titles
