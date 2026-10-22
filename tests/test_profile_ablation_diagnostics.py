import numpy as np

from scripts.profile_ablation_diagnostics import (
    modal_pair_diagnostic,
    paired_interval,
    share_mae,
)


def test_matching_marginals_can_hide_wrong_relationships():
    first = np.array([0, 0, 1, 1])
    second = first.copy()
    predicted_second = np.eye(3)[[0, 1, 0, 1]]
    assert share_mae(second, predicted_second, np.ones(4)) == 0
    result = modal_pair_diagnostic(first, second, np.eye(3)[first], predicted_second, np.ones(4))
    assert result["observed_cramers_v"] == 1
    assert result["predicted_modal_cramers_v"] == 0
    assert result["modal_pair_table_total_variation"] == 0.5


def test_degenerate_modal_table_has_undefined_association():
    y = np.array([0, 1, 2])
    p = np.tile([1.0, 0, 0], (3, 1))
    result = modal_pair_diagnostic(y, y, p, p, np.ones(3))
    assert result["predicted_modal_cramers_v"] is None
    assert result["cramers_v_absolute_error"] is None


def test_bootstrap_preserves_constant_paired_effect_with_missing_task_labels():
    result = paired_interval(
        ["a", "b", "c"],
        {"x": {"a": -0.1, "b": -0.1}, "y": {"b": -0.1, "c": -0.1}},
        {"a": 2, "b": 1, "c": 3},
        draws=100,
    )
    np.testing.assert_allclose(result["conditional_person_bootstrap95"], [-0.1, -0.1])
    assert not result["bootstrap_refits_calibration"]
    assert result["macro_brier_delta"] < 0
