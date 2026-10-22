import json

import numpy as np
import pytest

from psbx.config import load_yaml
from psbx.experiments.decision_experiment import (
    Calls,
    context,
    independent,
    interactions,
    network_schedule,
    validate_probabilities,
)
from psbx.experiments.decision_profiles import (
    EXTRA,
    SPARSE,
    TARGETS,
    check_seal,
    choose_cohort,
    dump,
    load_pack,
    profile_text,
    seal,
)
from psbx.schemas import ModelConfig


def profile(i=0):
    return {
        "synthetic_person_id": str(i),
        "state_fips": 39,
        "weight": 1,
        "baseline_date": "2012-10-01",
        "uncertainty": "unknown exposures",
        "observed": {
            f: {"label": f, "answer": "measured answer", "code": 2} for f in SPARSE + EXTRA
        },
    }


def worker():
    return ModelConfig(
        id="fixture",
        provider="openrouter",
        model_name="fixture",
        declared_pretraining_cutoff="2024-01-01",
        is_instruction_tuned=True,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"vote": [1, 0, 0]},
        {k: [1, 1, 1] for k in TARGETS},
        {k: [np.nan, 0, 1] for k in TARGETS},
        {k: [-0.1, 0.1, 1] for k in TARGETS},
    ],
)
def test_reject_invalid_probabilities(bad):
    with pytest.raises(ValueError):
        validate_probabilities(bad)


def test_profile_excludes_all_heldout_outcomes():
    assert not set(SPARSE + EXTRA) & {v["field"] for v in TARGETS.values()}
    text = profile_text(profile(), True)
    for v in TARGETS.values():
        assert v["field"] not in text
    assert "finance_finpast" in text
    assert "finance_finpast" not in profile_text(profile(), False)


def test_new_cohort_excludes_seen_and_late_cases():
    rows = [profile(i) for i in range(6)]
    rows[4]["baseline_date"] = "2012-11-06"
    rows[5]["baseline_date"] = None
    chosen = choose_cohort(rows, {"0"}, 39, 3, 12, "2012-08-03")
    assert {p["synthetic_person_id"] for p in chosen} == {"1", "2", "3"}


def test_future_evidence_and_missing_provenance_are_rejected(tmp_path):
    path = tmp_path / "pack.json"
    dump(path, {"cutoff": "2012-08-03", "documents": [{"published_at": "2012-08-04"}]})
    with pytest.raises(ValueError, match="after cutoff"):
        load_pack(path)
    dump(path, {"cutoff": "2012-08-03", "documents": [{"published_at": "2012-08-01"}]})
    with pytest.raises(ValueError, match="provenance"):
        load_pack(path)
    with pytest.raises(ValueError, match="later than respondent"):
        context(profile(), True, True, {"documents": [{"published_at": "2012-11-01"}]})


def test_private_files_and_seals(tmp_path):
    path = tmp_path / "secret.json"
    dump(path, seal({"x": 1}))
    assert path.stat().st_mode & 0o777 == 0o600
    value = json.loads(path.read_text())
    check_seal(value)
    value["x"] = 2
    with pytest.raises(ValueError):
        check_seal(value)


def test_failed_json_is_retained_and_resume_does_not_buy_more_calls(tmp_path, monkeypatch):
    from types import SimpleNamespace

    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="not JSON")

    monkeypatch.setattr("psbx.experiments.decision_experiment.complete_turn", completion)
    metadata = {"phase": "independent", "synthetic_person_id": "1"}
    assert Calls(tmp_path).call(worker(), "prompt", metadata) is None
    assert len(calls) == 2
    assert Calls(tmp_path).call(worker(), "prompt", metadata) is None
    assert len(calls) == 2
    with pytest.raises(ValueError, match="mismatch"):
        Calls(tmp_path).call(worker(), "changed prompt", metadata)


def test_independent_factorial_and_sparse_network_control_are_matched(tmp_path):
    config = load_yaml("config/anes2012-decision-context.yaml")
    config.update(sample_n=6, repetitions=2, interaction_n=6)
    profiles = [profile(i) for i in range(6)]
    pack = {"documents": []}
    dump(tmp_path / "contract.json", {})

    class FakeCalls:
        def __init__(self):
            self.rows = []

        def call(self, model, user, metadata, message=False):
            self.rows.append((user, metadata))
            return {"message": "test"} if message else {k: [0.4, 0.3, 0.3] for k in TARGETS}

    calls = FakeCalls()
    independent(tmp_path, config, profiles, [worker()], pack, calls)
    assert len(calls.rows) == 6 * 4 * 2
    assert len({r[1]["arm"] for r in calls.rows}) == 4
    calls = FakeCalls()
    interactions(tmp_path, config, profiles, [worker()], pack, calls)
    control = [r for r in calls.rows if r[1]["arm"] == "private_matched"]
    social = [r for r in calls.rows if r[1]["arm"] == "limited_network"]
    assert len(control) == len(social)
    assert all(
        "Messages from selected contacts: []" in u for u, m in control if m["stage"] == "message"
    )
    neighbors, active = network_schedule(profiles, config)
    assert network_schedule(profiles, config) == (neighbors, active)
    assert all(len(v) == 3 and k not in v for k, v in neighbors.items())


def test_scoring_binds_targets_and_rejects_incomplete_panels(tmp_path):
    from psbx.experiments.anes_society import _sha256_file
    from psbx.experiments.decision_experiment import ARMS, save_predictions, score

    target_path = tmp_path / "private-targets.json"
    dump(target_path, [{"synthetic_person_id": "0", "weight": 1, **{key: 1 for key in TARGETS}}])
    dump(
        tmp_path / "profile-seal.json",
        seal({"targets_path": str(target_path), "targets_sha256": _sha256_file(target_path)}),
    )
    dump(tmp_path / "cohort.json", [profile()])
    dump(
        tmp_path / "contract.json",
        seal(
            {
                "config": {"repetitions": 2, "interaction_n": 1},
                "bound_files": {},
                "bound_hashes": {},
            }
        ),
    )
    rows = [
        {
            "arm": arm,
            "repetition": rep,
            "synthetic_person_id": "0",
            "model_id": "same",
            "probabilities": {key: [1, 0, 0] for key in TARGETS},
        }
        for arm in ARMS
        for rep in range(2)
    ]
    save_predictions(tmp_path, "independent", rows)
    report = score(tmp_path, "independent")
    assert len(report["metrics"]) == 12
    assert all(row["brier_half_multiclass"] == 0 for row in report["metrics"])
    assert all(row["agreement"] == 1 for row in report["metrics"])
    assert all(row["brier_change"] == 0 for row in report["contrasts"])
    save_predictions(tmp_path, "independent", rows[:-1])
    with pytest.raises(ValueError, match="Unbalanced"):
        score(tmp_path, "independent")
    save_predictions(tmp_path, "independent", rows)
    dump(target_path, [])
    with pytest.raises(ValueError, match="Target hash"):
        score(tmp_path, "independent")
