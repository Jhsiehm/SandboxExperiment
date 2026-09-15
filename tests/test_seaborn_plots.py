from pathlib import Path

from psbx.io import read_jsonl
from psbx.schemas import Prediction, Question, SwarmVote
from psbx.scoring.plots import render_performance_plots, short_name


def test_short_species_names():
    assert short_name("openrouter-haiku") == "Haiku"
    assert short_name("swarm-median") == "Median of 12"


def test_seaborn_swarm_plots(tmp_path):
    questions = read_jsonl("data/questions/e2012.jsonl", Question)
    votes = read_jsonl("data/runs/phase2-e2012-swarm-probe/swarm_votes.jsonl", SwarmVote)
    preds = read_jsonl("data/runs/phase2-e2012-swarm-probe/predictions.jsonl", Prediction)
    dest = Path(tmp_path) / "plots"
    specs = render_performance_plots(
        run_id="phase2-e2012-swarm-probe",
        questions=questions,
        predictions=preds,
        votes=votes,
        dest=dest,
    )
    ids = {s["id"] for s in specs}
    assert "vote_swarm" in ids
    assert "brier_bars" in ids
    assert "signed_error" in ids
    for spec in specs:
        assert spec["question"]
        assert spec["good_result"]
        png = dest / spec["file"]
        assert png.is_file()
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_seaborn_plots_skip_when_unscored(tmp_path):
    specs = render_performance_plots(
        run_id="empty",
        questions=[],
        predictions=[],
        votes=[],
        dest=Path(tmp_path) / "plots",
    )
    assert specs == []


def test_mixed_known_and_custom_species_can_share_a_vote_plot(tmp_path):
    questions = read_jsonl("data/questions/e2012.jsonl", Question)
    source = read_jsonl(
        "data/runs/phase2-e2012-swarm-probe/predictions.jsonl", Prediction
    )[0]
    predictions = [
        source.model_copy(update={"model_id": "frontier-a"}),
        source.model_copy(update={"model_id": "frontier-b"}),
        source.model_copy(update={"model_id": "gpt-oss-2012ish"}),
    ]
    specs = render_performance_plots(
        run_id="mixed",
        questions=questions,
        predictions=predictions,
        votes=[],
        dest=Path(tmp_path) / "plots",
    )
    assert {spec["id"] for spec in specs} >= {"vote_swarm", "brier_bars"}
