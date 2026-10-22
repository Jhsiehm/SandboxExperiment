"""Independent leakage checks for the development calibrator."""

import numpy as np
import pytest

from psbx.experiments.profile_ablation import folds, nested_predictions
from psbx.experiments.profile_ablation_worker import ARMS, REDUCED


def test_profile_contrasts_separate_existing_reduction_from_added_measurements():
    assert len(ARMS["original_sparse"]) == 8
    assert len(ARMS["original_rich"]) == 20
    assert len(REDUCED) == 11
    assert set(REDUCED) < set(ARMS["original_rich"])
    added = set(ARMS["reduced_plus_observed"]) - set(REDUCED)
    assert added == {"health_self", "owngun_owngun", "interest_attention", "trust_social"}
    assert not added & set(ARMS["original_rich"])


def test_outer_predictions_do_not_change_when_only_outer_test_labels_change():
    ids = [f"person-{i}" for i in range(40)]
    outer = folds(ids)
    y = np.arange(40) % 3
    weights = np.linspace(0.2, 3.5, 40)
    groups = np.array([str(i % 7) for i in range(40)])
    agent = np.random.default_rng(412).dirichlet(np.ones(3), size=40)
    original, original_decisions = nested_predictions(ids, y, weights, groups, agent, outer)
    for fold in range(5):
        held_out = np.array([outer[person] == fold for person in ids])
        changed = y.copy()
        changed[held_out] = (changed[held_out] + 1) % 3
        actual, decisions = nested_predictions(ids, changed, weights, groups, agent, outer)
        for name in original:
            np.testing.assert_allclose(original[name][held_out], actual[name][held_out])
        assert decisions[fold] == original_decisions[fold]
        assert not set(decisions[fold]["training_ids"]) & set(decisions[fold]["evaluation_ids"])


def test_fold_assignment_is_input_order_independent_and_rejects_duplicate_people():
    ids = [f"person-{i}" for i in range(40)]
    assert folds(ids) == folds(list(reversed(ids)))
    with pytest.raises(ValueError):
        folds(ids + [ids[0]])
