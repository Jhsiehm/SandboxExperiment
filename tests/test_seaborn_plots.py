from pathlib import Path

from psbx.io import read_jsonl
from psbx.schemas import Citation, Prediction, Question, SwarmVote
from psbx.scoring.plots import render_performance_plots, short_name


def test_short_species_names():
    assert short_name("openrouter-haiku") == "Haiku"
    assert short_name("swarm-median") == "Median of 12"


def _sample_plot_inputs():
    question = next(
        row
        for row in read_jsonl("data/questions/e2012.jsonl", Question)
        if row.ground_truth is not None
    )
    run_id = "phase2-e2012-swarm-probe"
    probabilities = (0.38, 0.44, 0.49, 0.53, 0.58, 0.63)
    model_ids = (
        "openrouter-gpt-4.1-mini",
        "openrouter-gpt-4o-mini",
        "openrouter-haiku",
        "openrouter-gemini-flash-lite",
        "openrouter-llama-3.1-8b",
        "openrouter-qwen-2.5-7b",
    )
    votes = [
        SwarmVote(
            run_id=run_id,
            question_id=question.id,
            agent_index=index,
            agent_id=f"swarm:{model_id}:{index:02d}",
            model_id=model_id,
            model_slug=model_id.removeprefix("openrouter-"),
            temperature=0.2,
            max_tokens=128,
            probability=probabilities[index % len(probabilities)],
        )
        for index, model_id in enumerate(model_ids * 2)
    ]
    prediction = Prediction(
        run_id=run_id,
        question_id=question.id,
        model_id="swarm-median",
        probability=0.51,
        reasoning="Synthetic plotting fixture.",
        citations=[
            Citation(document_id="fixture", quoted_span="synthetic fixture", supports="context")
        ],
    )
    return [question], [prediction], votes


def test_seaborn_swarm_plots(tmp_path):
    questions, preds, votes = _sample_plot_inputs()
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
    questions, sample, _ = _sample_plot_inputs()
    source = sample[0]
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
