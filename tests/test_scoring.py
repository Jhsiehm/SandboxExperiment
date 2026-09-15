from datetime import date

import pytest

from psbx.schemas import Citation, ModelConfig, Prediction, PriorSignal, Question
from psbx.scoring.baselines import baseline_scores
from psbx.scoring.brier import brier, brier_index
from psbx.scoring.concordance import concordance_index
from psbx.scoring.contamination import contamination_curve
from psbx.scoring.report import score_run


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


def test_concordance_ranks_yes_above_no():
    qs = {
        "yes": _q("yes", True, date(2012, 12, 1)),
        "no": _q("no", False, date(2012, 12, 1)),
    }
    perfect = [_p("yes", "m", 0.9), _p("no", "m", 0.1)]
    inverted = [_p("yes", "m", 0.1), _p("no", "m", 0.9)]
    tied = [_p("yes", "m", 0.5), _p("no", "m", 0.5)]
    c_ok, n_ok = concordance_index(perfect, qs)
    c_bad, n_bad = concordance_index(inverted, qs)
    c_tie, n_tie = concordance_index(tied, qs)
    assert n_ok == n_bad == n_tie == 1
    assert c_ok == 1.0
    assert c_bad == 0.0
    assert c_tie == 0.5
    empty_c, empty_n = concordance_index([_p("yes", "m", 0.9)], {"yes": qs["yes"]})
    assert empty_c is None and empty_n == 0


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
    assert not curve.causal_interpretation_supported
    assert curve.cutoff_is_declared_metadata
    assert all(
        bucket.mean_brier is None and bucket.mean_accuracy is None
        for bucket in curve.buckets
        if bucket.n == 0
    )


def _model(model_id: str) -> ModelConfig:
    return ModelConfig(
        id=model_id,
        provider="openai",
        model_name=model_id,
        declared_pretraining_cutoff=date(2011, 1, 1),
        is_instruction_tuned=True,
    )


def test_partial_models_use_their_own_baselines_and_matched_comparison():
    questions = [
        _q("easy-yes", True, date(2012, 8, 1)),
        _q("easy-no", False, date(2012, 9, 1)),
        _q("extra-yes", True, date(2012, 10, 1)),
    ]
    models = [_model("wide"), _model("partial")]
    predictions = [
        _p("easy-yes", "wide", 0.9),
        _p("easy-no", "wide", 0.1),
        _p("extra-yes", "wide", 0.1),
        _p("easy-yes", "partial", 0.9),
        _p("easy-no", "partial", 0.1),
    ]
    report = score_run(predictions, questions, models, "partial")

    assert report.coverage_by_model["wide"].answered_questions == 3
    assert report.coverage_by_model["partial"].answered_questions == 2
    assert report.coverage_by_model["partial"].missing_question_ids == ["extra-yes"]
    assert report.coverage_by_model["partial"].failed_question_ids is None
    assert report.baselines_by_model["partial"] == baseline_scores(questions[:2])
    assert report.matched_question_ids == ["easy-yes", "easy-no"]
    assert report.matched_brier_by_model["wide"] == report.matched_brier_by_model["partial"]
    assert report.brier_by_model["wide"] > report.brier_by_model["partial"]


def test_empty_model_metrics_stay_undefined_and_coverage_is_explicit():
    questions = [_q("only", True, date(2012, 8, 1))]
    report = score_run([], questions, [_model("missing")], "empty")
    assert report.brier_by_model["missing"] is None
    assert report.brier_index_by_model["missing"] is None
    assert report.c_index_by_model["missing"] is None
    assert report.matched_brier_by_model["missing"] is None
    assert report.coverage_by_model["missing"].coverage_fraction == 0.0
    assert report.coverage_by_model["missing"].missing_question_ids == ["only"]


def test_scoring_rejects_unknown_questions_and_duplicate_predictions():
    questions = [_q("known", True, date(2012, 8, 1))]
    model = _model("m")
    with pytest.raises(ValueError, match="unknown question IDs"):
        score_run([_p("unknown", "m", 0.5)], questions, [model], "unknown")
    duplicate = _p("known", "m", 0.5)
    with pytest.raises(ValueError, match="duplicate model/question"):
        score_run([duplicate, duplicate], questions, [model], "duplicate")


def test_scoring_rejects_duplicate_question_ids():
    duplicate = _q("same", True, date(2012, 8, 1))
    with pytest.raises(ValueError, match="duplicate question IDs"):
        score_run([], [duplicate, duplicate], [_model("m")], "duplicate-questions")
