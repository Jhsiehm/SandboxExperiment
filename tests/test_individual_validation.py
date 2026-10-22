import copy
from types import SimpleNamespace

import pytest

from psbx.experiments.individual_validation import call, payload, validate_panel
from psbx.experiments.individual_worker import ARMS, FOCUSED, NEW, SPARSE, build_prompt


def person():
    from psbx.experiments.individual_worker import EXTRA

    return dict(
        synthetic_person_id="one",
        baseline_date="2012-09-01",
        observed={
            f: dict(label=f, answer="Observed", status="observed_pre_election")
            for f in set(SPARSE + EXTRA + NEW)
        },
    )


def test_focused_selection_and_direct_memory_boundary():
    p = payload(person(), "focused_direct")
    assert set(p["observations"]) == set(FOCUSED)
    assert "medsrc_socmedia" not in p["observations"]
    build_prompt(p)
    p["review"] = "Another stage"
    with pytest.raises(ValueError, match="memory"):
        build_prompt(p)


@pytest.mark.parametrize("key", ["presvote2012_x", "health_2010hcr", "gun_control", "peer_profile"])
def test_target_and_peer_fields_rejected(key):
    p = payload(person(), "focused_direct")
    p["observations"][key] = dict(label=key, answer="secret", status="observed")
    with pytest.raises(ValueError, match="fields"):
        build_prompt(p)


def test_review_cannot_receive_previous_memory():
    p = payload(person(), "focused_review", "review", "previous")
    with pytest.raises(ValueError, match="review"):
        build_prompt(p)


def test_complete_unique_panel_required():
    p = person()
    answer = {k: [0.2, 0.3, 0.5] for k in ["vote", "health_law", "gun_policy"]}
    rows = [
        dict(metadata=dict(person="one", arm=a, repetition=r), probabilities=answer)
        for a in ARMS
        for r in range(2)
    ]
    validate_panel([p], rows)
    with pytest.raises(ValueError):
        validate_panel([p], rows[:-1])
    with pytest.raises(ValueError):
        validate_panel([p], rows + rows[:1])


def test_resumption_fingerprint_and_immediate_failure(tmp_path, monkeypatch):
    from test_decision_context import worker

    (tmp_path / "checkpoints").mkdir()
    monkeypatch.setattr(
        "psbx.experiments.individual_validation.docker_job",
        lambda p, i: {**build_prompt(p), "isolation": {}},
    )
    calls = []

    def complete(*a, **kw):
        calls.append(1)
        return SimpleNamespace(text='{"vote":[1,0,0],"health_law":[0,1,0],"gun_policy":[0,0,1]}')

    monkeypatch.setattr("psbx.experiments.individual_validation.complete_turn", complete)
    p = payload(person(), "sparse_direct")
    meta = dict(person="one", arm="sparse_direct", stage="final")
    call(tmp_path, {"image_id": "fake"}, worker(), p, meta)
    call(tmp_path, {"image_id": "fake"}, worker(), p, meta)
    assert len(calls) == 1
    changed = copy.deepcopy(p)
    changed["observations"][SPARSE[0]]["answer"] = "Changed"
    with pytest.raises(ValueError, match="resume"):
        call(tmp_path, {"image_id": "fake"}, worker(), changed, meta)

    def fail(*a, **kw):
        raise TimeoutError("not for logs")

    monkeypatch.setattr("psbx.experiments.individual_validation.complete_turn", fail)
    with pytest.raises(TimeoutError):
        call(tmp_path, {"image_id": "fake"}, worker(), p, {**meta, "rep": 1})
    assert "not for logs" not in (tmp_path / "provider-failure.json").read_text()
