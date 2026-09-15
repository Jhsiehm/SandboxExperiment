import json
from pathlib import Path

import httpx
import pytest

from psbx.population.census_api import CensusApiClient
from psbx.population.runner import run_population_build


def test_fixture_build_writes_validated_artifacts(tmp_path: Path):
    result = run_population_build(
        "config/track_b_fixture.yaml",
        output_override=tmp_path,
    )
    out = Path(result["output_dir"])
    assert result["validation"]["passed"] is True
    assert result["validation"]["actual_population"] == 120
    assert result["validation"]["household_integrity"] == "not_guaranteed"
    expected = {
        "manifest.json",
        "raking_history.csv",
        "representative_cells.csv",
        "synthetic_people.csv",
        "constraints_used.csv",
        "population_validation.json",
        "source_decisions.json",
    }
    assert expected <= {path.name for path in out.iterdir()}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic_records"] == 120
    assert manifest["reasoning_calls"] == 25
    assert manifest["output_sha256"]
    assert "actual residents" in " ".join(manifest["claims"]).lower()


def test_census_cache_metadata_never_persists_api_key(tmp_path, monkeypatch):
    secret = "not-a-real-census-key"
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params):
            captured["params"] = params
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json=[["NAME"], ["Fixture"]],
            )

    monkeypatch.setattr("psbx.population.census_api.httpx.Client", FakeClient)
    client = CensusApiClient(
        cache_root=tmp_path,
        allow_network=True,
        api_key=secret,
    )
    frame = client.query(
        dataset="2010/dec/sf1",
        variables=["NAME"],
        for_clause="state:00",
    )
    assert frame.iloc[0]["NAME"] == "Fixture"
    assert ("key", secret) in captured["params"]
    metadata = next(tmp_path.glob("*.meta.json")).read_text(encoding="utf-8")
    assert secret not in metadata
    assert '"downloaded_at"' in metadata


def test_census_client_rejects_redirects_and_unsafe_dataset_ids(tmp_path, monkeypatch):
    class RedirectClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params):
            del params
            return httpx.Response(
                302,
                request=httpx.Request("GET", url),
                headers={"location": "https://attacker.example/collect"},
            )

    monkeypatch.setattr("psbx.population.census_api.httpx.Client", RedirectClient)
    client = CensusApiClient(
        cache_root=tmp_path,
        allow_network=True,
        api_key="not-a-real-key",
    )
    with pytest.raises(RuntimeError, match="redirect refused"):
        client.query(
            dataset="2024/acs/acs5",
            variables=["NAME"],
            for_clause="state:06",
        )
    with pytest.raises(ValueError, match="unsafe Census dataset"):
        client.query(
            dataset="../../outside",
            variables=["NAME"],
            for_clause="state:06",
        )
