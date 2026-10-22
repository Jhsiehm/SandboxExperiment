import copy

import numpy as np
import pytest

from psbx.experiments.profile_ablation import evidence, folds, metrics, nested_predictions, payload
from psbx.experiments.profile_ablation_worker import ARMS, build_prompt


def person():
    return dict(
        baseline_date="2012-09-12",
        observed={
            f: dict(label=f, answer="measured", status="observed_pre_election", code=1)
            for fields in ARMS.values()
            for f in fields
        },
    )


def test_ablations_isolate_added_fields_and_removed_fields():
    assert len(ARMS["original_sparse"]) == 8
    assert len(ARMS["original_rich"]) == 20
    assert len(ARMS["reduced_existing"]) == 11
    assert len(ARMS["reduced_plus_observed"]) == 15
    assert set(ARMS["reduced_existing"]) < set(ARMS["original_rich"])
    assert len(set(ARMS["reduced_plus_observed"]) - set(ARMS["reduced_existing"])) == 4
    for arm in ARMS:
        build_prompt(payload(person(), arm))


def test_provenance_unknown_dates_missingness_and_target_boundary():
    p = person()
    f = ARMS["original_sparse"][0]
    p["observed"][f].update(code=None, status="missing", answer="Not observed")
    ev = evidence(p, f)
    assert ev["missing"] and "item date unknown" in ev["date_precision"]
    data = payload(p, "original_sparse")
    build_prompt(data)
    data["observations"]["gun_control"] = copy.deepcopy(ev)
    with pytest.raises(ValueError, match="fields"):
        build_prompt(data)
    del data["observations"]["gun_control"]
    data["observations"][f]["inference"] = True
    with pytest.raises(ValueError, match="measured"):
        build_prompt(data)


def test_outer_label_changes_cannot_change_own_fold_predictions():
    ids = [f"p{i}" for i in range(40)]
    outer = folds(ids)
    y = np.arange(40) % 3
    weights = np.ones(40)
    groups = np.array([str(i % 4) for i in range(40)])
    probs = np.tile([0.2, 0.3, 0.5], (40, 1))
    first, audit = nested_predictions(ids, y, weights, groups, probs, outer)
    mask = np.array([outer[i] == 0 for i in ids])
    altered = y.copy()
    altered[mask] = (altered[mask] + 1) % 3
    second, _ = nested_predictions(ids, altered, weights, groups, probs, outer)
    for variant in first:
        np.testing.assert_allclose(first[variant][mask], second[variant][mask])
        np.testing.assert_allclose(first[variant].sum(1), 1)
    for item in audit:
        assert not set(item["training_ids"]) & set(item["evaluation_ids"])
    assert folds(ids) == folds(ids[::-1])


def test_distribution_match_does_not_hide_individual_errors():
    y = np.array([0, 1, 2])
    p = np.eye(3)[[1, 2, 0]]
    result = metrics(y, p, np.ones(3))
    assert result["total_variation"] == 0
    assert result["accuracy"] == 0
    assert result["brier"] == 1
