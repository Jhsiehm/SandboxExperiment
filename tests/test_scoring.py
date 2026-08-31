from datetime import date

from psbx.schemas import Citation, ModelConfig, Prediction, PriorSignal, Question
from psbx.scoring.baselines import baseline_scores
from psbx.scoring.brier import brier, brier_index
from psbx.scoring.contamination import contamination_curve


def _q(qid: str, truth: bool, resolution: date) -> Question:
    return Question(
        id=qid,
        epoch_id="e2012",
        category="economic",
        text="Will the placeholder event occur by December 31, 2012?",
        resolution_criteria="Machine check against the source series.",
        cutoff_date=date(2012, 6, 30),
        resolution_date=resolution,
        ground_truth=truth,
        generator="test",
        prior_signal=PriorSignal(kind="base_rate", probability=0.4, source="test"),
    )


def _p(qid: str, model: str, prob: float) -> Prediction:
    return Prediction(
        run_id="t",
        question_id=qid,
        model_id=model,
        probability=prob,
        reasoning="test",
        citations=[Citation(document_id="d", quoted_span="span", supports="context")],
    )


def test_brier_perfect_and_index():
    qs = {"a": _q("a", True, date(2012, 12, 1))}
    preds = [_p("a", "m", 1.0)]
    assert brier(preds, qs) == 0.0
    assert brier_index(0.25) == 50.0


def test_baselines_and_contamination_sign():
    qs_list = [
        _q("early", True, date(2012, 8, 1)),
        _q("late", True, date(2013, 1, 1)),
    ]
    bases = baseline_scores(qs_list)
    assert "always_base_rate" in bases
    assert "prior_signal" in bases
    model = ModelConfig(
        id="m",
        provider="openai",
        model_name="x",
        declared_pretraining_cutoff=date(2012, 9, 1),
        is_instruction_tuned=True,
    )
    preds = [_p("early", "m", 0.9), _p("late", "m", 0.1)]
    qs = {q.id: q for q in qs_list}
    curve = contamination_curve(preds, qs, model)
    assert curve.pre_cutoff_mean_brier is not None
    assert curve.post_cutoff_mean_brier is not None
