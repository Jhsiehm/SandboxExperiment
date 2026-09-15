import hashlib
from datetime import datetime, timezone

import pytest

from psbx.config import load_epochs
from psbx.corpus.sync_survey_sources import (
    SurveyArtifact,
    ingest_synced_survey_sources,
    load_survey_catalog,
    sync_survey_sources,
)


def test_sync_is_cutoff_aware_and_never_automates_gated_data(tmp_path):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        """
artifacts:
  - id: public-2012
    provider: pew
    outlet: Pew
    title: Public 2012 summary
    url: https://example.com/public
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: wayback
    index: true
  - id: future-version
    provider: cses
    outlet: CSES
    title: Future corrected file
    url: https://example.com/future
    fieldwork_year_start: 2011
    fieldwork_year_end: 2012
    released_at: 2018-01-01T12:00:00Z
    access: public
    retrieval: wayback
    index: true
  - id: gated-2012
    provider: issp
    outlet: ISSP
    title: Gated microdata
    url: https://example.com/gated
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: registration
    retrieval: manual
    index: false
""",
        encoding="utf-8",
    )
    calls: list[str] = []

    def fetcher(artifact, epoch, destination):
        calls.append(artifact.id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "<html><body>" + ("Cutoff-safe public survey summary. " * 20) + "</body></html>",
            encoding="utf-8",
        )
        return {
            "snapshot_timestamp": "20120502120000",
            "snapshot_url": "https://web.archive.org/example",
            "content_type": "text/html",
        }

    epoch = load_epochs()["e2012"]
    payload = sync_survey_sources(
        epoch,
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
    )
    assert calls == ["public-2012"]
    statuses = {row["id"]: row["status"] for row in payload["artifacts"]}
    assert statuses == {
        "public-2012": "downloaded",
        "future-version": "blocked_future_release",
        "gated-2012": "manual_required",
    }
    docs = ingest_synced_survey_sources(
        epoch,
        manifest_path=tmp_path / "cache" / "e2012" / "manifest.json",
        catalog_path=catalog,
    )
    assert len(docs) == 1
    assert docs[0].source_type == "survey"
    assert docs[0].published_at == datetime(2012, 5, 1, 12, tzinfo=timezone.utc)

    calls.clear()
    second = sync_survey_sources(
        epoch,
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
    )
    assert calls == []
    assert second["counts"]["cached"] == 1


def test_sync_plan_lists_providers_without_downloading(tmp_path):
    epoch = load_epochs()["e2012"]
    payload = sync_survey_sources(epoch, provider="pew", cache_root=tmp_path, plan=True)
    assert payload["artifacts"]
    assert {row["provider"] for row in payload["artifacts"]} == {"pew"}
    assert not (tmp_path / "e2012" / "manifest.json").exists()


def test_direct_artifacts_require_and_enforce_a_pinned_checksum(tmp_path):
    with pytest.raises(ValueError, match="pinned expected_sha256"):
        SurveyArtifact.model_validate(
            {
                "id": "unpinned",
                "provider": "pew",
                "outlet": "Pew",
                "title": "Unpinned release",
                "url": "https://example.com/report.html",
                "fieldwork_year_start": 2012,
                "fieldwork_year_end": 2012,
                "released_at": "2012-05-01T12:00:00Z",
                "access": "public",
                "retrieval": "direct",
                "format": "html",
                "index": True,
            }
        )

    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        """
artifacts:
  - id: pinned
    provider: pew
    outlet: Pew
    title: Pinned release
    url: https://example.com/report.html
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: direct
    format: html
    expected_sha256: "0000000000000000000000000000000000000000000000000000000000000000"
    index: true
""",
        encoding="utf-8",
    )

    def wrong_fetcher(artifact, epoch, destination):
        del artifact, epoch
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("not the pinned release", encoding="utf-8")
        return {"snapshot_timestamp": "20120501120000"}

    payload = sync_survey_sources(
        load_epochs()["e2012"],
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=wrong_fetcher,
    )
    assert payload["counts"] == {"error": 1}
    assert "does not match pinned" in payload["artifacts"][0]["reason"]
    assert not (tmp_path / "cache" / "e2012" / "pew" / "pinned.html").exists()


def test_direct_download_does_not_claim_an_archival_snapshot(tmp_path):
    body = (
        "<html><body>"
        + ("A checksum-pinned direct survey release. " * 12)
        + "</body></html>"
    ).encode()
    digest = hashlib.sha256(body).hexdigest()
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        f"""
artifacts:
  - id: pinned
    provider: pew
    outlet: Pew
    title: Pinned release
    url: https://example.com/report.html
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: direct
    format: html
    expected_sha256: {digest}
    index: true
""",
        encoding="utf-8",
    )

    def fetcher(artifact, epoch, destination):
        del artifact, epoch
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return {
            "snapshot_timestamp": "20120501120000",
            "snapshot_url": "https://not-really-an-archive.example/report",
        }

    payload = sync_survey_sources(
        load_epochs()["e2012"],
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
    )
    row = payload["artifacts"][0]
    assert row["status"] == "downloaded"
    assert row["source_url"] == "https://example.com/report.html"
    assert "snapshot_timestamp" not in row
    assert "snapshot_url" not in row
    docs = ingest_synced_survey_sources(
        load_epochs()["e2012"],
        manifest_path=tmp_path / "cache" / "e2012" / "manifest.json",
        catalog_path=catalog,
    )
    assert len(docs) == 1
    assert "checksum-pinned direct release" in docs[0].provenance
    assert "snapshot" not in docs[0].provenance.casefold()


def test_provider_sync_drops_removed_rows_for_that_provider(tmp_path):
    catalog = tmp_path / "catalog.yaml"

    def write_catalog(include_removed: bool) -> None:
        removed = (
            """
  - id: remove-me
    provider: pew
    outlet: Pew
    title: Revoked report
    url: https://example.com/remove
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: wayback
    index: true
"""
            if include_removed
            else ""
        )
        catalog.write_text(
            """
artifacts:
  - id: keep-pew
    provider: pew
    outlet: Pew
    title: Retained report
    url: https://example.com/keep
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: wayback
    index: true
  - id: keep-cses
    provider: cses
    outlet: CSES
    title: Other provider report
    url: https://example.com/cses
    fieldwork_year_start: 2012
    fieldwork_year_end: 2012
    released_at: 2012-05-01T12:00:00Z
    access: public
    retrieval: wayback
    index: true
"""
            + removed,
            encoding="utf-8",
        )

    def fetcher(artifact, epoch, destination):
        del epoch
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "<html><body>" + (f"{artifact.id} survey evidence. " * 20) + "</body></html>",
            encoding="utf-8",
        )
        return {
            "snapshot_timestamp": "20120502120000",
            "snapshot_url": "https://web.archive.org/example",
        }

    epoch = load_epochs()["e2012"]
    write_catalog(include_removed=True)
    first = sync_survey_sources(
        epoch,
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
    )
    assert {row["id"] for row in first["artifacts"]} == {
        "keep-pew",
        "keep-cses",
        "remove-me",
    }

    write_catalog(include_removed=False)
    second = sync_survey_sources(
        epoch,
        provider="pew",
        catalog_path=catalog,
        cache_root=tmp_path / "cache",
        fetcher=fetcher,
    )
    assert {row["id"] for row in second["artifacts"]} == {"keep-pew", "keep-cses"}


def test_checked_in_direct_artifacts_have_pinned_hashes():
    direct = [item for item in load_survey_catalog() if item.retrieval == "direct"]
    assert direct
    assert all(item.expected_sha256 for item in direct)
