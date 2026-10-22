import copy

import numpy as np

from psbx.experiments.social_cohort import fit_baseline, predict, rps, transition, tune


def rows():
    return [
        dict(group_id=f"g{g}", initial_score=i, final_score=min(6, i + (g % 2)))
        for g in range(4)
        for i in (1, 2, 4, 6)
    ]


def test_rps_and_probability_matrix():
    assert rps(np.eye(6)[2], 3) == 0
    assert rps(np.eye(6)[0], 6) == 1
    matrix = transition(rows(), 4)
    assert np.allclose(matrix.sum(axis=1), 1)
    assert np.all(matrix > 0)


def test_confirmation_labels_never_change_fit_or_predictions():
    development = rows()
    cases = [dict(group_id="held", profile=dict(agent_id="p", initial_score=3))]
    original = fit_baseline(development)
    first = predict(original, cases)
    changed = copy.deepcopy(cases)
    changed[0]["final_score"] = 6
    changed[0]["profile"]["final_score"] = 1
    changed[0]["real_incoming"] = [{"text": "Future outcome is six"}]
    assert predict(fit_baseline(development), changed) == first
    assert fit_baseline(development) == original


def test_held_out_group_cannot_affect_inner_tuning():
    original = rows()
    modified = copy.deepcopy(original)
    for row in modified:
        if row["group_id"] == "g0":
            row["final_score"] = 1
    left = [r for r in original if r["group_id"] != "g0"]
    right = [r for r in modified if r["group_id"] != "g0"]
    assert tune(left) == tune(right)
    alpha, _ = tune(left)
    assert np.array_equal(transition(left, alpha), transition(right, alpha))
    a, b = fit_baseline(original), fit_baseline(modified)
    assert a["outer_folds"][0]["alpha"] == b["outer_folds"][0]["alpha"]
