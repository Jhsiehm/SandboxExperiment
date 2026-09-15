import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
from typer.testing import CliRunner

from psbx.cli import app
from psbx.population.census_sync import (
    AREAS,
    CensusArtifact,
    _download_one,
    census_artifact_plan,
    summarize_plan,
)


def test_census_sync_plan_covers_all_states_dc_and_nation():
    artifacts = census_artifact_plan()
    summary = summarize_plan(artifacts)
    assert len(AREAS) == 51
    assert summary["states_plus_dc"] == 51
    assert summary["national_aggregate"] is True
    assert summary["artifact_count"] == 625
    assert summary["families"] == {
        "pums_person": 51,
        "pums_housing": 51,
        "decennial_demographic_profile": 52,
        "acs5_summary_sequence": 468,
        "support": 2,
        "cvap": 1,
    }
    assert any(row.geography_id == "us:1" for row in artifacts)
    assert all(
        date.fromisoformat(row.release_date) <= date(2012, 6, 30)
        for row in artifacts
    )


def test_census_sync_plan_uses_only_official_https_urls_and_safe_paths():
    artifacts = census_artifact_plan()
    for artifact in artifacts:
        assert artifact.url.startswith("https://www2.census.gov/")
        assert not artifact.relative_path.startswith("/")
        assert ".." not in artifact.relative_path.split("/")
    dc_sequences = [
        row for row in artifacts if row.artifact_id.startswith("acs5-dc-seq-")
    ]
    assert len(dc_sequences) == 9
    assert all("/DistrictOfColumbia/" in row.url for row in dc_sequences)
    ohio = next(row for row in artifacts if row.artifact_id == "decennial-dp-oh")
    assert ohio.url.endswith("/Ohio/oh2010.dp.zip?download=1")


def test_census_sync_cli_is_plan_only_without_execute():
    result = CliRunner().invoke(app, ["population", "sync-census"])
    assert result.exit_code == 0, result.output
    assert '"artifact_count": 625' in result.output
    assert '"states_plus_dc": 51' in result.output


def test_download_rejects_200_status_html_before_accepting_zip(
    tmp_path: Path, monkeypatch
):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("fixture.csv", "value\n1\n")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = b"<html>Request Rejected</html>" if calls == 1 else buffer.getvalue()
        return httpx.Response(200, content=content, request=request)

    monkeypatch.setattr("psbx.population.census_sync.time.sleep", lambda _seconds: None)
    artifact = CensusArtifact(
        artifact_id="fixture",
        source_id="fixture",
        family="support",
        geography_id="us:1",
        url="https://www2.census.gov/fixture.zip",
        relative_path="raw/fixture.zip",
        release_date="2011-01-01",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _download_one(client, artifact, tmp_path, retries=2)
    assert calls == 2
    assert result["status"] == "downloaded"
    with zipfile.ZipFile(tmp_path / "raw/fixture.zip") as archive:
        assert archive.read("fixture.csv") == b"value\n1\n"
