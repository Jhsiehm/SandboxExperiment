"""Synthetic fixtures only: no Oregon observations or ANES reserve are accessed."""

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "behavior_baseline", Path(__file__).with_name("baseline.py")
)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def fixture():
    c = {
        "admission_status": "approved",
        "source_sha256": "synthetic_fixture_only",
        "outcome_definition": "synthetic binary",
        "prediction_cutoff": "2008-01-01",
        "cutoff_scope": "single_common_cutoff",
        "sample_definition": "synthetic",
        "weight_definition": "unit",
        "household_definition": "two generated rows per group",
        "split_salt": "fixture-v1",
        "features": ["prior"],
        "folds": 5,
        "field_provenance": {
            "prior": {
                "role": "pre_assignment_observation",
                "source_variable": "synthetic_prior",
                "available_by": "2007-01-01",
            }
        },
    }
    rows = []
    for i in range(200):
        household = str(i)
        if b.allocation(household, c["split_salt"]) == "reserve":
            continue
        for j in (0, 1):
            rows.append(
                {
                    "person_id": f"{i}:{j}",
                    "household_id": household,
                    "assignment": i % 2,
                    "outcome": int((i + j) % 3 == 0),
                    "weight": 1,
                    "features": {"prior": str(i % 4)},
                }
            )
    return rows, c


def test_runs_with_grouped_development_only():
    rows, c = fixture()
    result, pred = b.evaluate(rows, c)
    assert result["reserve_scored"] == 0
    assert result["n_people"] == result["n_households"] * 2
    assert all(np.isfinite(p).all() for p in pred.values())


def test_evaluation_fold_outcomes_cannot_change_its_predictions():
    rows, c = fixture()
    changed = copy.deepcopy(rows)
    mask = np.array([b.bucket(r["household_id"], c["split_salt"] + ":fold", 5) == 0 for r in rows])
    for i in np.flatnonzero(mask):
        changed[i]["outcome"] = 1 - changed[i]["outcome"]
    _, original = b.evaluate(rows, c)
    _, mutated = b.evaluate(changed, c)
    for key in original:
        np.testing.assert_array_equal(original[key][mask], mutated[key][mask])


def test_reserved_household_rejected():
    rows, c = fixture()
    reserved = next(
        str(i) for i in range(200) if b.allocation(str(i), c["split_salt"]) == "reserve"
    )
    rows[0]["household_id"] = reserved
    with pytest.raises(ValueError, match="Reserved"):
        b.evaluate(rows, c)


@pytest.mark.parametrize("mutation", ["post", "late", "unapproved", "unexpected"])
def test_rejects_invalid_contract_or_leaky_fields(mutation):
    rows, c = fixture()
    if mutation == "post":
        c["field_provenance"]["prior"]["role"] = "post_assignment_observation"
    elif mutation == "late":
        c["field_provenance"]["prior"]["available_by"] = "2009-01-01"
    elif mutation == "unapproved":
        c["admission_status"] = "unresolved"
    else:
        rows[0]["features"]["outcome_proxy"] = 1
    with pytest.raises(ValueError):
        b.evaluate(rows, c)


def test_preprocessing_fits_training_vocabulary_only():
    rows, c = fixture()
    train, test = copy.deepcopy(rows[:10]), copy.deepcopy(rows[10:12])
    for r in train:
        r["features"]["prior"] = "only_training_category"
    for r in test:
        r["features"]["prior"] = "unseen_evaluation_category"
    a, z = b.matrix(train, test, c["features"])
    assert a.shape[1] == z.shape[1] == 2


def test_missing_date_and_variable_cutoff_rejected():
    rows, c = fixture()
    c["field_provenance"]["prior"].pop("available_by")
    with pytest.raises(ValueError, match="availability date"):
        b.evaluate(rows, c)
    rows, c = fixture()
    c["cutoff_scope"] = "per_lottery_draw"
    with pytest.raises(ValueError, match="Variable prediction"):
        b.evaluate(rows, c)


def test_high_cardinality_predictor_rejected():
    rows, c = fixture()
    for i, row in enumerate(rows):
        row["features"]["prior"] = i
    with pytest.raises(ValueError, match="High-cardinality"):
        b.evaluate(rows, c)


def test_cli_rejects_unbound_input_before_parsing(tmp_path, monkeypatch):
    import json
    import sys

    rows, c = fixture()
    source = tmp_path / "input.jsonl"
    source.write_text("deliberately not valid json")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(c))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "baseline.py",
            "--input",
            str(source),
            "--contract",
            str(contract),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )
    with pytest.raises(ValueError, match="checksum"):
        b.main()


@pytest.mark.parametrize("key", ["person_id", "household_id"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_identifiers_rejected(key, value):
    rows, c = fixture()
    rows[0][key] = value
    with pytest.raises(ValueError, match="person/household ID"):
        b.evaluate(rows, c)


def test_saved_oregon_reproduction_matches_published_rounding_and_frozen_code():
    import json

    here = Path(__file__).parent
    r = json.loads((here / "oregon-results.json").read_text())
    assert r["n_people"] == 74922
    assert r["fresh_holdout_claim"] is False
    assert all(
        check["passed"] for row in r["published_rounding_checks"].values() for check in row.values()
    )
    assert r["implementation_sha256"] == b.digest(here / "oregon_reference.py")
    assert r["baseline_implementation_sha256"] == b.digest(here / "baseline.py")
    assert r["reference_targets_sha256"] == b.digest(here / "reference-targets.json")
