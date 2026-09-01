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
    assert "Run live mix" in html
    assert "Run live AI" not in html
    assert "app.js?v=22" in html
    assert "app.css?v=17" in html
    assert "enchant.css?v=8" in html
    assert 'id="perf-plots"' in html
    assert 'aria-live="polite"' in html
    assert "sr-only" in html
    assert 'for="run-select"' in html
    assert "tabindex=" not in html.split("enchant-menu")[1].split("</ol>")[0]
