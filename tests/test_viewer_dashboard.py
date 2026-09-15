from leaderboard.explain import explain_scores
from leaderboard.store import forecast_rows
from psbx.schemas import Citation, Prediction, Question


def _q(**kwargs):
    base = dict(
        id="q1",
        epoch_id="e2012",
        category="economic",
        text="Will the unemployment rate stay above 7 percent by 2012-12-31?",
        resolution_criteria="BLS",
        cutoff_date="2012-06-30",
        resolution_date="2012-12-31",
        ground_truth=True,
        generator="test",
        prior_signal={"kind": "analyst_consensus", "probability": 0.7, "source": "test"},
    )
    base.update(kwargs)
    return Question.model_validate(base)


def test_explain_miss_when_models_worse_than_prior():
    payload = {
        "run_id": "phase1-e2012-smoke",
        "source": "computed",
        "baselines": {"prior_signal": 0.17, "always_base_rate": 0.25, "always_0.5": 0.25},
        "report": {
            "brier_by_model": {"gpt-oss-2012ish": 0.226, "frontier-a": 0.226},
            "brier_index_by_model": {"gpt-oss-2012ish": 52.5, "frontier-a": 52.5},
            "models_beating_prior_signal": [],
            "n_predictions": 50,
            "n_flagged": 0,
            "contamination": [{"post_cutoff_mean_brier": None}],
        },
    }
    ex = explain_scores(payload, {})
    assert ex["verdict"]["tone"] == "miss"
    assert "prior" in ex["verdict"]["headline"].lower()
    assert ex["scoreboard"][0]["id"] == "prior_signal"
    heuristic = next(r for r in ex["scoreboard"] if r["id"] == "gpt-oss-2012ish")
    assert heuristic["beats_prior"] is False
    assert "c_index" in heuristic
    assert "c_bar" in heuristic
    assert ex["story"]
    assert ex["metrics"][0]["id"] == "brier"
    assert ex["metrics"][1]["id"] == "c_index"
    assert ex["verdict"].get("ranking") is not None
    assert "keyword" in ex["verdict"]["detail"].lower()
    assert "2012" in ex["contamination_note"]


def test_forecast_rows_join_question_and_error():
    q = _q()
    pred = Prediction(
        run_id="r",
        question_id="q1",
        model_id="frontier-a",
        probability=0.8,
        reasoning="test",
        citations=[Citation(document_id="d", quoted_span="span here", supports="context")],
    )
    hidden = forecast_rows([pred], [q], reveal_truth=False, limit=10)
    assert hidden[0]["question_text"].startswith("Will ")
    assert hidden[0]["ground_truth"] is None
    shown = forecast_rows([pred], [q], reveal_truth=True, limit=10)
    assert shown[0]["ground_truth"] is True
    assert shown[0]["item_brier"] == (0.8 - 1.0) ** 2


def test_compute_scores_does_not_borrow_another_run(monkeypatch):
    from types import SimpleNamespace

    from leaderboard.store import compute_scores

    other = SimpleNamespace(run_id="phase1-e2012-smoke")

    def fake_report(run_id=None):
        if run_id in (None, "phase1-e2012-smoke"):
            return other
        return None

    monkeypatch.setattr("leaderboard.store.load_score_report", fake_report)
    monkeypatch.setattr("leaderboard.store.load_predictions", lambda run_id=None: [])
    payload = compute_scores([], [], "phase1-e2012-docker")
    assert payload["run_id"] == "phase1-e2012-docker"
    assert payload["source"] == "baselines-only"


def test_goal_progress_combines_quality_with_benchmark_coverage():
    from leaderboard.store import build_goal_progress

    payload = build_goal_progress(
        [
            {
                "run_id": "full-but-weak",
                "label": "Full but weak",
                "created_at": "2026-01-01T00:00:00Z",
                "primary_brier": 0.23,
                "goal_target_brier": 0.17,
                "n_scored_questions": 50,
                "n_agents": 12,
            },
            {
                "run_id": "strong-but-half",
                "label": "Strong but half",
                "created_at": "2026-01-02T00:00:00Z",
                "primary_brier": 0.16,
                "goal_target_brier": 0.17,
                "n_scored_questions": 25,
                "n_agents": 25,
            },
        ],
        benchmark_questions=50,
    )
    assert payload["points"][0]["quality_percent"] == 25.0
    assert payload["points"][0]["progress_percent"] == 25.0
    assert payload["points"][1]["quality_percent"] == 100.0
    assert payload["points"][1]["coverage_percent"] == 50.0
    assert payload["points"][1]["progress_percent"] == 50.0
    assert payload["best"]["run_id"] == "strong-but-half"
    assert payload["human_emulation"]["status"] == "not_measured"


def test_run_labels_match_hud_kinds():
    from leaderboard.explain import run_label

    assert "Practice" in run_label("phase1-e2012-smoke")
    assert "6 species" in run_label("phase2-e2012-openrouter")
    assert "median" in run_label("phase2-e2012-swarm-probe").lower()
    assert "native" in run_label("phase2-e2012-real").lower()


def test_dashboard_html_a11y_landmarks():
    from pathlib import Path

    html = Path("leaderboard/static/index.html").read_text()
    assert 'lang="en"' in html
    assert 'href="#main"' in html
    assert "Skip to content" in html
    assert 'href="#run-box"' in html
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'role="tabpanel"' in html
    assert 'id="run-swarm-btn"' in html
    assert 'id="tab-eras"' in html
    assert 'id="view-eras"' in html
    assert 'id="era-grid"' in html
    assert 'id="tab-activity"' in html
    assert 'id="view-activity"' in html
    assert 'id="agent-grid"' in html
    assert 'id="tab-runs"' in html
    assert 'id="view-runs"' in html
    assert 'id="swarm-builder"' in html
    assert 'id="run-history"' in html
    assert 'id="saved-log"' in html
    assert 'id="tab-architecture"' in html
    assert 'id="view-architecture"' in html
    assert 'id="arch-flow"' in html
    assert 'id="arch-inspector"' in html
    assert "Repository tree" in html
    assert "they do not independently browse" in html
    assert "Run live mix" in html
    assert "Run live AI" not in html
    assert "app.js?v=27" in html
    assert "app.css?v=23" in html
    assert "enchant.css?v=8" in html
    assert 'id="perf-plots"' in html
    assert 'id="goal-chart"' in html
    assert 'id="goal-percent"' in html
    assert "Human-decision emulation: not measured" in html
    assert 'aria-live="polite"' in html
    assert "sr-only" in html
    assert 'for="run-select"' in html
    assert "tabindex=" not in html.split("enchant-menu")[1].split("</ol>")[0]


def test_era_catalog_reports_only_built_epochs_as_ready():
    from leaderboard.store import era_catalog

    eras = era_catalog()
    e2012 = next(era for era in eras if era["id"] == "e2012")
    assert e2012["ready"] is True
    assert e2012["n_documents"] > 0
    assert e2012["n_questions"] == 50
    assert "survey" in e2012["source_types"]


def test_viewer_era_api_routes_selected_epoch():
    from fastapi.testclient import TestClient

    from leaderboard.app import create_viewer

    client = TestClient(create_viewer())
    catalog = client.get("/api/eras")
    assert catalog.status_code == 200
    assert catalog.json()["default_epoch_id"] == "e2012"

    overview = client.get("/api/overview", params={"epoch": "e2012"})
    assert overview.status_code == 200
    assert overview.json()["epoch"]["id"] == "e2012"
    assert overview.json()["goal_progress"]["benchmark_questions"] == 50
    assert overview.json()["goal_progress"]["points"]

    search = client.post(
        "/api/eras/e2012/search", json={"query": "unemployment", "k": 2}
    )
    assert search.status_code == 200
    assert all(hit["published_at"][:10] <= "2012-06-30" for hit in search.json())

    unknown = client.get("/api/overview", params={"epoch": "e2099"})
    assert unknown.status_code == 404

    options = client.get("/api/swarm/options")
    assert options.status_code == 200
    assert options.json()["ceiling"] == 100
    assert {preset["n_agents"] for preset in options.json()["presets"]} >= {
        12,
        25,
        50,
        100,
    }


def test_activity_payload_distinguishes_forecast_from_human_validation(monkeypatch):
    from leaderboard.activity import build_activity_payload
    from leaderboard.store import bootstrap

    monkeypatch.setattr(
        "leaderboard.activity.sandbox_snapshot",
        lambda epoch_id, cutoff: {
            "verified": True,
            "selection": "all",
            "epoch_match": epoch_id == "e2012",
            "cutoff_match": cutoff == "2012-06-30",
        },
    )
    payload = build_activity_payload(
        bootstrap("e2012"),
        "phase2-e2012-swarm-probe",
        {"status": "idle", "run_id": "phase1-e2012-smoke", "log": []},
    )
    assert payload["experiment"]["score_target"] == "later observed ground-truth outcomes"
    assert "not yet validated" in payload["experiment"]["human_emulation_status"]
    assert payload["run"]["shared_retrieval"] is True
    assert payload["run"]["n_agents"] == 12
    assert payload["access"]["verified"] is True


def test_dashboard_config_can_force_container_and_source_silo(tmp_path, monkeypatch):
    from leaderboard.jobs import _dashboard_config
    from psbx.config import load_run

    monkeypatch.setattr(
        "leaderboard.jobs.resolve",
        lambda _path: tmp_path / "isolated-run.yaml",
    )
    prepared, path = _dashboard_config(
        load_run("config/run-openrouter.yaml"),
        "config/run-openrouter.yaml",
        kind="live",
        isolated=True,
        source_type="survey",
        run_id=None,
    )
    assert prepared.sandbox_mode == "container"
    assert prepared.source_type == "survey"
    assert prepared.run_id.endswith("-survey-container")
    assert path == str(tmp_path / "isolated-run.yaml")
    assert (tmp_path / "isolated-run.yaml").is_file()


def test_dashboard_config_saves_a_unique_100_agent_roster(tmp_path, monkeypatch):
    from pathlib import Path

    import yaml

    from leaderboard.jobs import _dashboard_config
    from psbx.config import load_run
    from psbx.schemas import SwarmRoster

    def fake_resolve(path):
        candidate = Path(path)
        return candidate if candidate.is_absolute() else tmp_path / candidate

    monkeypatch.setattr("leaderboard.jobs.resolve", fake_resolve)
    prepared, path = _dashboard_config(
        load_run("config/run-swarm.yaml"),
        "config/run-swarm.yaml",
        kind="swarm",
        isolated=True,
        source_type="survey",
        run_id="../../must-not-be-used",
        n_questions=3,
        swarm_bodies=[{"model_id": "openrouter-gpt-4.1-mini", "count": 100}],
        unique_run=True,
    )
    assert prepared.run_id.startswith("e2012-swarm-100-")
    assert "must-not-be-used" not in prepared.run_id
    assert prepared.n_questions == 3
    assert prepared.sandbox_mode == "container"
    assert Path(path).name == "run.yaml"
    roster_data = yaml.safe_load(Path(prepared.swarm_roster).read_text())
    roster = SwarmRoster.model_validate(roster_data)
    assert roster.n_agents == 100
    assert roster.bodies[0].count == 100


def test_manifest_keeps_run_id_inside_the_saved_payload(tmp_path, monkeypatch):
    from leaderboard.jobs import _update_manifest
    from psbx.io import read_json

    monkeypatch.setattr(
        "leaderboard.jobs._manifest_path",
        lambda _run_key: tmp_path / "manifest.json",
    )
    _update_manifest("folder-id", run_id="folder-id", status="running")
    assert read_json(tmp_path / "manifest.json") == {
        "run_id": "folder-id",
        "status": "running",
    }
