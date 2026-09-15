import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from leaderboard.population import population_dashboard_payload
from leaderboard.store import bootstrap, era_catalog
from psbx.config import _YAML_CACHE
from psbx.practice import practice_status, prepare_practice


def _copy_tracked_practice_inputs(destination: Path) -> set[str]:
    repository = Path(__file__).resolve().parents[1]
    tracked = set(
        subprocess.check_output(
            ["git", "ls-files"],
            cwd=repository,
            text=True,
        ).splitlines()
    )
    prefixes = ("config/", "data/questions/", "data/sources/", "tests/fixtures/")
    for relative in sorted(path for path in tracked if path.startswith(prefixes)):
        source = repository / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tracked


def test_clean_checkout_is_honest_and_has_explicit_provider_free_prepare_path(
    tmp_path, monkeypatch
):
    checkout = tmp_path / "clean-checkout"
    tracked = _copy_tracked_practice_inputs(checkout)
    forbidden = (
        "data/corpus/",
        "data/population/",
        "data/population-input/",
        "data/evaluation-vault/",
        "data/runs/",
    )
    assert not any(path.startswith(forbidden) for path in tracked)
    assert not (checkout / "data/corpus").exists()
    assert not (checkout / "data/population").exists()

    monkeypatch.setenv("PSBX_ROOT", str(checkout))
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "0")
    monkeypatch.delenv("PSBX_MOCK_LLM", raising=False)
    _YAML_CACHE.clear()

    before = practice_status("e2012", root=checkout)
    assert before["question_set_built"] is True
    assert before["corpus_built"] is False
    assert before["fixture_profile_ready"] is False
    assert before["isolated_run_assets_ready"] is False

    incomplete_corpus = checkout / "data/corpus/e2012"
    incomplete_corpus.mkdir(parents=True)
    (incomplete_corpus / "documents.jsonl").write_text("{}\n", encoding="utf-8")
    assert next(row for row in era_catalog() if row["id"] == "e2012")[
        "has_corpus"
    ] is False
    shutil.rmtree(checkout / "data/corpus")

    era = next(row for row in era_catalog() if row["id"] == "e2012")
    assert era["ready"] is True
    assert era["practice_ready"] is True
    assert era["isolated_run_ready"] is False
    assert era["research_ready"] is False
    assert era["status"] == "rebuildable practice fixture"

    viewer = bootstrap("e2012")
    assert viewer.index.docs
    assert viewer.index_source == "practice:in-memory-tracked-fixtures"
    assert not (checkout / "data/corpus").exists()

    monkeypatch.setattr(
        "leaderboard.app.sandbox_snapshot",
        lambda epoch_id, cutoff: {
            "verified": True,
            "selection": "all",
            "epoch_match": True,
            "cutoff_match": True,
        },
    )
    from leaderboard.app import create_viewer

    client = TestClient(
        create_viewer(viewer),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 50000),
    )
    blocked = client.post(
        "/api/jobs/run",
        headers={"X-PSBX-CSRF": "1"},
        json={"kind": "mock", "epoch_id": "e2012", "isolated_retrieval": True},
    )
    assert blocked.status_code == 412
    assert "psbx practice prepare --epoch e2012" in blocked.json()["detail"]

    population = population_dashboard_payload("e2012", root=checkout)
    assert population["profile_contract"] == {
        "status": "no_validated_profiles",
        "runnable_profiles": 0,
        "practice_fixture_ready": False,
        "can_weight_swarm": False,
        "build_command": "psbx practice prepare --epoch e2012",
        "full_census_profiles_ready": False,
        "claim_scope": (
            "Only profiles listed as runnable have passed local validation. "
            "A fixture profile is synthetic practice data, not U.S. coverage."
        ),
    }

    prepared = prepare_practice("e2012")
    assert prepared["prepared"] is True
    assert prepared["provider_calls"] == 0
    assert prepared["corpus_built"] is True
    assert prepared["fixture_profile_ready"] is True
    assert prepared["research_eligible_documents"] == 0
    assert (checkout / "data/corpus/e2012/meta.json").is_file()
    assert (
        checkout / "data/population/e2012/fixture-township-e2012/manifest.json"
    ).is_file()
    live_blocked = client.post(
        "/api/jobs/run",
        headers={"X-PSBX-CSRF": "1"},
        json={"kind": "live", "epoch_id": "e2012", "isolated_retrieval": True},
    )
    assert live_blocked.status_code == 412
    assert "authenticated evidence" in live_blocked.json()["detail"]


def test_dashboard_readiness_explains_missing_seal_before_launch(monkeypatch):
    from leaderboard.app import create_viewer

    monkeypatch.setattr(
        "leaderboard.app.sandbox_snapshot",
        lambda epoch_id, cutoff: {
            "verified": False,
            "selection": "unknown",
            "epoch_match": False,
            "cutoff_match": False,
        },
    )
    client = TestClient(
        create_viewer(),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 50000),
    )
    readiness = client.get("/api/jobs/ready", params={"epoch": "e2012"})
    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["practice_ready"] is False
    assert "psbx sandbox up --epoch e2012" in payload["practice_blocking_reason"]
    assert next(
        item for item in payload["practice_requirements"] if item["id"] == "sealed_sidecar"
    )["ready"] is False

    launch = client.post(
        "/api/jobs/run",
        headers={"X-PSBX-CSRF": "1"},
        json={"kind": "mock", "epoch_id": "e2012", "isolated_retrieval": True},
    )
    assert launch.status_code == 412
    assert "seal the container" in launch.json()["detail"]


def test_dashboard_run_controls_disclose_prerequisites_before_click():
    repository = Path(__file__).resolve().parents[1]
    html = (repository / "leaderboard/static/index.html").read_text(encoding="utf-8")
    script = (repository / "leaderboard/static/app.js").read_text(encoding="utf-8")
    assert 'id="run-prerequisite"' in html
    assert "state.ready.practice_ready" in script
    assert "practice_blocking_reason" in script
    assert "mockBtn.disabled = busy || !practiceOk" in script
