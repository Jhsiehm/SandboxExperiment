from psbx.config import load_epochs, load_run
from psbx.questions.build_set import build_questions
from psbx.questions.filters import PRIOR_HI, PRIOR_LO, filter_questions


def test_build_e2012_passes_filters():
    epoch = load_epochs()["e2012"]
    run = load_run()
    qs = build_questions(epoch, limit=50)
    assert len(qs) == 50
    again = filter_questions(
        qs,
        resolution_window_end=epoch.resolution_window_end,
        category_balance=run.category_balance,
    )
    assert {q.id for q in again} == {q.id for q in qs}
    counts = {}
    for q in qs:
        counts[q.category] = counts.get(q.category, 0) + 1
        assert q.text.lower().startswith("will ")
        assert q.prior_signal is not None
        assert PRIOR_LO <= q.prior_signal.probability <= PRIOR_HI
        assert q.resolution_date <= epoch.resolution_window_end
        assert q.cutoff_date == epoch.cutoff_date
    assert counts["economic"] == 20
    assert counts["legislative"] == 20
    assert counts["geopolitical"] == 10
