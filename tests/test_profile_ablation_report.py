import pytest

from psbx.experiments.profile_ablation_worker import ARMS
from scripts.render_profile_ablation_report import load_completed, render


def fixture_report():
    variants = ["direct", "hybrid", "party", "prevalence"]
    pairs = [(arm, variant) for arm in ARMS for variant in variants]
    evaluation = dict(
        metrics=[dict(arm=a, variant=v, weighted=dict(brier=0.25)) for a, v in pairs], contrasts=[]
    )
    diagnostics = dict(
        conditional_hybrid_contrasts=[],
        answer_share_mae=[dict(arm=a, variant=v, weighted_share_mae=0.05) for a, v in pairs],
        modal_response_pair_proxies=[
            dict(arm=a, variant=v, weighted=dict(modal_pair_table_total_variation=0.2))
            for a, v in pairs
        ],
    )
    audit = dict(checkpoints=960, people=120, seal_sha256="fixture-only")
    ledger = dict(reserved_requests=960, entries=[dict(reported_usage=dict(provider_cost_usd=0.5))])
    config = dict(repetitions=2, max_usd=10, max_requests=1000)
    return evaluation, diagnostics, audit, ledger, config


def test_renderer_includes_caveats_and_comparisons_without_live_artifacts():
    output = render(*fixture_report(), "fixture-not-a-live-run")
    assert "0.25000" in output
    assert "$0.500000" in output
    assert "not a joint predictive distribution" in output
    assert "do not include calibration-refitting" in output
    assert "No automatic promotion" in output
    assert "50-person reserve remained excluded" in output
    for arm in ARMS:
        assert arm in output


def test_incomplete_run_cannot_produce_completed_report(tmp_path):
    with pytest.raises(ValueError, match="Completed audited run required"):
        load_completed(tmp_path)
    assert list(tmp_path.iterdir()) == []
