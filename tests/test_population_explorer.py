from pathlib import Path

import pytest
import yaml

from leaderboard.population import population_dashboard_payload
from psbx.population.profiles import public_population_profiles, weighted_persona_catalog
from psbx.population.runner import run_population_build


@pytest.fixture(scope="module")
def fixture_population_root(tmp_path_factory):
    repository = Path(__file__).resolve().parents[1]
    root = tmp_path_factory.mktemp("population-profile-root")
    run_population_build(
        repository / "config/track_b_fixture.yaml",
        base_dir=repository,
        output_override=root / "data/population",
    )
    return root


def test_population_explorer_has_every_state_dc_and_district_count():
    payload = population_dashboard_payload("e2012")
    states = payload["census"]["states"]
    assert len(states) == 51
    assert {row["abbreviation"] for row in states} >= {"AK", "HI", "DC"}
    assert len({(row["map_col"], row["map_row"]) for row in states}) == 51
    assert sum(row["district_count"] for row in states) == 436
    assert payload["explorer"]["district_vintage"] == "2012 congressional apportionment"


def test_fixture_profile_exposes_only_weighted_aggregate_demographics(fixture_population_root):
    profiles = public_population_profiles("e2012", root=fixture_population_root)
    fixture = next(row for row in profiles if row["population_id"] == "fixture-township-e2012")
    assert fixture["runnable"] is True
    assert fixture["target_population"] == 120
    assert fixture["demographics"]
    for group in fixture["demographics"]:
        assert sum(row["share"] for row in group["categories"]) == pytest.approx(1.0)
    serialized = str(fixture)
    assert "source_donor_id" not in serialized
    assert "synthetic_person_id" not in serialized


def test_weighted_persona_panel_is_deterministic_and_does_not_infer_politics(
    fixture_population_root,
):
    first = weighted_persona_catalog(
        "e2012", "fixture-township-e2012", 25, root=fixture_population_root
    )
    second = weighted_persona_catalog(
        "e2012", "fixture-township-e2012", 25, root=fixture_population_root
    )
    assert first == second
    assert len(first["personas"]) == 25
    assert [row["slot"] for row in first["personas"]] == list(range(25))
    assert {row["party_id"] for row in first["personas"]} == {"unspecified"}
    assert {row["urbanicity"] for row in first["personas"]} == {"unspecified"}
    assert all("population_id" in row["extra"] for row in first["personas"])


def test_dashboard_config_writes_population_weighted_perspectives(
    tmp_path, monkeypatch, fixture_population_root
):
    from leaderboard.jobs import _dashboard_config
    from psbx.config import load_run

    monkeypatch.setattr(
        "leaderboard.jobs.resolve_run_dir",
        lambda run_id: tmp_path / run_id,
    )
    monkeypatch.setattr(
        "leaderboard.jobs.weighted_persona_catalog",
        lambda epoch_id, population_id, n_agents: weighted_persona_catalog(
            epoch_id,
            population_id,
            n_agents,
            root=fixture_population_root,
        ),
    )
    prepared, _ = _dashboard_config(
        load_run("config/run-swarm.yaml"),
        "config/run-swarm.yaml",
        kind="swarm",
        isolated=True,
        source_type="survey",
        run_id=None,
        n_questions=1,
        swarm_bodies=[{"model_id": "openrouter-gpt-4.1-mini", "count": 12}],
        population_selection={
            "population_id": "fixture-township-e2012",
            "strategy": "population_weighted",
        },
        unique_run=True,
    )
    perspectives = Path(str(prepared.perspectives))
    assert perspectives.is_file()
    payload = yaml.safe_load(perspectives.read_text(encoding="utf-8"))
    assert len(payload["personas"]) == 12
    assert payload["not_inferred"] is True


def test_dashboard_contains_chain_map_and_geography_inspector():
    html = Path("leaderboard/static/index.html").read_text(encoding="utf-8")
    assert 'id="agent-chain-live"' in html
    assert 'id="agent-chain-results"' in html
    assert 'id="population-map"' in html
    assert 'id="geography-layer"' in html
    assert 'id="dataset-layer"' in html
    assert 'id="map-zoom-in"' in html
    assert 'id="cost-estimate"' in html
    assert 'id="population-boxes"' in html
    assert 'id="geography-inspector"' in html
    assert 'id="population-swarm-form"' in html
