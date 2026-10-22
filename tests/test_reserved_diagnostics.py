import pytest

from scripts.diagnose_reserved_validation import confidence_bins


def test_confidence_bins_preserve_mass_and_weighted_calibration():
    bins = confidence_bins([[.5, .3, .2], [.9, .1, 0], [.9, .1, 0]], [0, 0, 1], [1, 1, 3])
    assert sum(b['rows'] for b in bins) == 3
    assert sum(b['weight_share'] for b in bins) == pytest.approx(1)
    assert bins[0]['lower'] == .5
    assert bins[-1]['lower'] == .9
    assert bins[-1]['mean_confidence'] == pytest.approx(.9)
    assert bins[-1]['answer_agreement'] == pytest.approx(.25)
