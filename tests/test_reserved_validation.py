import copy

import numpy as np
import pytest
from test_decision_context import profile

from psbx.experiments.reserved_validation import (
    bootstrap_contrast,
    make_jobs,
    metric,
    validate_panel,
)


def fixture_jobs():
    return make_jobs(
        [profile(i) for i in range(6)],
        {"seed": 42, "repetitions": 2},
        [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    )


def test_job_matching_and_determinism():
    jobs = fixture_jobs()
    assert jobs == fixture_jobs()
    assert len(jobs) == 24
    for i in range(6):
        rows = [j for j in jobs if j["metadata"]["synthetic_person_id"] == str(i)]
        assert len({j["metadata"]["model_id"] for j in rows}) == 1
        assert {j["metadata"]["arm"] for j in rows} == {"sparse", "rich"}
        assert all("No external historical evidence" in j["user"] for j in rows)
        for j in rows:
            assert ("finance_finpast" in j["user"]) == (j["metadata"]["arm"] == "rich")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "model", "probabilities"])
def test_panel_rejects_corruption(mutation):
    jobs = fixture_jobs()
    rows = [dict(metadata=copy.deepcopy(j["metadata"]), probabilities=None) for j in jobs]
    validate_panel(jobs, rows)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[0]
    elif mutation == "model":
        rows[0]["metadata"]["model_id"] = "wrong"
    else:
        rows[0]["probabilities"] = {"vote": [1, 1, 1]}
    with pytest.raises(ValueError):
        validate_panel(jobs, rows)


def test_metric_and_cluster_bootstrap():
    perfect = metric([[1, 0, 0], [0, 1, 0]], [0, 1], [1, 1])
    assert perfect["brier"] == 0
    assert perfect["agreement"] == 1
    assert perfect["effective_n"] == 2
    uniform = metric([[1 / 3] * 3] * 2, [0, 1], [1, 1])
    assert uniform["brier"] == pytest.approx(1 / 3)
    changes = np.full((30, 3), -0.02)
    changes[0, 0] = np.nan
    result = bootstrap_contrast(changes, np.ones(30))
    assert result["macro_change"] == pytest.approx(-0.02)
    assert result["macro_interval"] == pytest.approx([-0.02, -0.02])
