"""Audit an explicitly harmonized development export; never open raw panel data.

This module cannot certify a source crosswalk. A trusted importer must first map
documented source codes, retaining missingness and source lineage. The CLI accepts
2016/2020 development rows only and emits aggregates, not respondent records.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


CATEGORIES = 7
WAVES = (2016, 2020)
FOLD_SALT = "anes-panel-development-v1:"
MISSING_REASONS = {"refused", "dont_know", "not_asked", "no_interview", "invalid", "other_documented"}
FIELDS = {"person_id", "wave", "phase", "role", "party_id", "missing_reason", "mode",
          "source_field", "source_sha256", "value_origin"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "Duplicate JSON key; ambiguous fields are forbidden")
        value[key] = item
    return value


def load_export(payload):
    value = json.loads(payload, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) == {"schema", "rows"} and value["schema"] == "harmonized-panel-development-v1", "Expected explicit harmonized development export, not raw mixed-wave microdata")
    return value["rows"]


def validate_rows(rows):
    require(isinstance(rows, list) and bool(rows), "Expected nonempty development rows")
    seen = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == FIELDS, "Unexpected or missing fields; later outcomes and arbitrary features are forbidden")
        require(isinstance(row["person_id"], str) and bool(row["person_id"].strip()) and row["person_id"] == row["person_id"].strip(), "Invalid linked person ID")
        require(type(row["wave"]) is int and row["wave"] in WAVES, "Only 2016/2020 development waves admitted")
        require(row["phase"] == "pre" and row["role"] == "development" and row["value_origin"] == "observed", "Unexpected phase, role or inferred/simulated value")
        key = row["person_id"], row["wave"]
        require(key not in seen, "Duplicate person-wave; do not silently deduplicate")
        seen.add(key)
        value = row["party_id"]
        if value is None:
            require(row["missing_reason"] in MISSING_REASONS, "Missing answer needs a documented missingness reason")
        else:
            require(type(value) is int and 1 <= value <= CATEGORIES, "Party ID must be integer 1..7 or null")
            require(row["missing_reason"] is None, "Observed category cannot also be missing")
        require(row["mode"] is None or isinstance(row["mode"], str) and bool(row["mode"].strip()), "Invalid mode; use null for unknown")
        require(isinstance(row["source_field"], str) and bool(row["source_field"].strip()), "Missing source variable")
        digest = row["source_sha256"]
        require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "Missing source SHA-256")
    return rows


def person_fold(person_id):
    return int(hashlib.sha256((FOLD_SALT + person_id).encode()).hexdigest(), 16) % 5


def paired_values(rows):
    """Return eligible pairs after validation; do not impute missing states."""
    validate_rows(rows)
    people = {}
    for row in rows:
        people.setdefault(row["person_id"], {})[row["wave"]] = row
    return [(person, waves[2016]["party_id"], waves[2020]["party_id"])
            for person, waves in sorted(people.items())
            if all(w in waves and waves[w]["party_id"] is not None for w in WAVES)]


def audit(rows):
    validate_rows(rows)
    by_person = {}
    for row in rows:
        by_person.setdefault(row["person_id"], {})[row["wave"]] = row
    pairs = paired_values(rows)
    initial_people = {p for p, waves in by_person.items() if 2016 in waves}
    no_later_row = sum(2020 not in by_person[p] for p in initial_people)
    later_missing = sum(2020 in by_person[p] and by_person[p][2020]["party_id"] is None for p in initial_people)
    no_interview = sum(2020 in by_person[p] and by_person[p][2020]["missing_reason"] == "no_interview" for p in initial_people)
    initial_observed = sum(by_person[p][2016]["party_id"] is not None for p in initial_people)
    support = []
    for category in range(1, 8):
        starting = [p for p in initial_people if by_person[p][2016]["party_id"] == category]
        observed_later = [p for p in starting if 2020 in by_person[p] and by_person[p][2020]["party_id"] is not None]
        support.append(dict(category=category, initial_observed=len(starting), later_observed=len(observed_later),
                            later_unavailable=len(starting)-len(observed_later)))
    folds = []
    for fold in range(5):
        training = [(p, before, after) for p, before, after in pairs if person_fold(p) != fold]
        validation = [(p, before, after) for p, before, after in pairs if person_fold(p) == fold]
        counts = Counter(before for _, before, _ in training)
        folds.append(dict(fold=fold, fitting_people=len(training), validation_people=len(validation),
                          fitting_initial_category_support=[counts[k] for k in range(1, 8)]))
    missing = {str(w):dict(Counter(r["missing_reason"] for r in rows if r["wave"] == w and r["party_id"] is None)) for w in WAVES}
    return dict(schema="panel-development-audit-v1", scope="Unweighted development export; no population or later-wave inference",
        people=len(by_person), records=len(rows), eligible_pairs=len(pairs),
        wave_records={str(w):sum(r["wave"] == w for r in rows) for w in WAVES},
        initial_wave_people=len(initial_people), initial_observed=initial_observed,
        later_only_people=sum(2016 not in waves for waves in by_person.values()),
        no_later_row=no_later_row, later_answer_missing=later_missing,
        later_documented_no_interview=no_interview, later_item_missing=later_missing-no_interview, missing_reasons=missing,
        mode_counts={str(w):dict(Counter(r["mode"] or "unknown" for r in rows if r["wave"] == w)) for w in WAVES},
        paired_initial_counts=[sum(before == k for _, before, _ in pairs) for k in range(1, 8)],
        paired_final_counts=[sum(after == k for _, _, after in pairs) for k in range(1, 8)],
        changed_pairs=sum(before != after for _, before, after in pairs), retention_by_initial_category=support,
        folds=folds, fold_salt=FOLD_SALT,
        structural_fivefold_ready=all(f["fitting_people"] and f["validation_people"] for f in folds),
        source_crosswalk_verified=False, population_weights_verified=False, precision_sufficient=None,
        later_wave_readout_enabled=False, model_training_enabled=False,
        limits=["Missing follow-up rows do not establish a reason for nonresponse.",
                "Attrition is conditional on the supplied source universe; a survivors-only export cannot recover original-cohort losses.",
                "Nonempty folds do not establish adequate power or population representativeness.",
                "Record lineage is required but source codes and cross-wave comparability need independent documentation review."])


def fit_transition(pairs):
    """Fixed seven-category Laplace-one reference; no hyperparameter selection."""
    require(isinstance(pairs, list) and bool(pairs), "No eligible development pairs")
    counts = [[1] * CATEGORIES for _ in range(CATEGORIES)]
    seen = set()
    for person, before, after in pairs:
        require(isinstance(person, str) and bool(person) and person not in seen, "Repeated or invalid fitting identity")
        require(type(before) is int and type(after) is int and 1 <= before <= 7 and 1 <= after <= 7, "Invalid fitting category")
        seen.add(person)
        counts[before-1][after-1] += 1
    return [[value/sum(row) for value in row] for row in counts]


def scores(probabilities, initial, final):
    require(len(probabilities) == 7 and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in probabilities), "Invalid probability vector")
    require(math.isclose(sum(probabilities), 1, rel_tol=0, abs_tol=1e-10), "Probabilities do not sum to one")
    require(type(initial) is int and type(final) is int and 1 <= initial <= 7 and 1 <= final <= 7, "Invalid observed category")
    cumulative = 0.0
    rps = 0.0
    for k in range(1, 7):
        cumulative += probabilities[k-1]
        rps += (cumulative - int(final <= k)) ** 2 / 6
    change_probability = 1 - probabilities[initial-1]
    return dict(rps=rps, change_brier=(change_probability-int(initial != final))**2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = args.development_export.read_bytes()
    result = audit(load_export(payload))
    result["export_sha256"] = hashlib.sha256(payload).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(status="development_export_audited", eligible_pairs=result["eligible_pairs"],
                          later_wave_readout_enabled=False, model_training_enabled=False)))


if __name__ == "__main__":
    main()
