"""Development-only grouped prediction harness; no source field assumptions.

Input is normalized JSONL exported under a reviewed source contract. This program
rejects reserved households rather than silently using or scoring their outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bucket(household, salt, modulus):
    token = f"{salt}:{household}".encode()
    return int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % modulus


def allocation(household, salt):
    return "reserve" if bucket(household, salt + ":reserve", 5) == 0 else "development"


def validate(rows, contract):
    if contract.get("admission_status") != "approved":
        raise ValueError("Source admission is not approved; no real-data benchmark allowed")
    required = [
        "source_sha256",
        "outcome_definition",
        "prediction_cutoff",
        "field_provenance",
        "sample_definition",
        "weight_definition",
        "household_definition",
    ]
    if any(not contract.get(key) for key in required):
        raise ValueError("Incomplete source contract")
    if contract.get("cutoff_scope") != "single_common_cutoff":
        raise ValueError("Variable prediction cutoffs require a separate reviewed adapter")
    try:
        cutoff = date.fromisoformat(contract["prediction_cutoff"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid prediction cutoff") from exc
    for feature in contract["features"]:
        provenance = contract["field_provenance"].get(feature, {})
        if provenance.get("role") != "pre_assignment_observation":
            raise ValueError("Predictor is not an approved pre-assignment observation")
        if not provenance.get("source_variable"):
            raise ValueError("Missing source variable provenance")
        try:
            available = date.fromisoformat(provenance.get("available_by"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Missing or invalid predictor availability date") from exc
        if available > cutoff:
            raise ValueError("Predictor unavailable at prediction cutoff")
    seen = set()
    for row in rows:
        for key in ("person_id", "household_id"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError("Missing or invalid person/household ID")
        if row["person_id"] in seen:
            raise ValueError("Duplicate person")
        seen.add(row["person_id"])
        if allocation(row["household_id"], contract["split_salt"]) != "development":
            raise ValueError("Reserved household present; refusing all analysis")
        if row["assignment"] not in (0, 1) or row["outcome"] not in (0, 1):
            raise ValueError("Assignment and outcome must be observed binary values")
        if not np.isfinite(row["weight"]) or row["weight"] <= 0:
            raise ValueError("Weights must be finite and positive")
        if set(row["features"]) != set(contract["features"]):
            raise ValueError("Unexpected or missing predictor")
    assignments = {}
    for row in rows:
        group = row["household_id"]
        if group in assignments and assignments[group] != row["assignment"]:
            raise ValueError("Within-household assignment inconsistency")
        assignments[group] = row["assignment"]


def matrix(train, test, features):
    """Fit category vocabulary on training people only; unknowns get all zero."""
    a = [np.ones(len(train)), np.array([r["assignment"] for r in train])]
    b = [np.ones(len(test)), np.array([r["assignment"] for r in test])]
    for name in features:

        def value(row):
            return json.dumps(row["features"][name], sort_keys=True)

        vocabulary = sorted({value(row) for row in train})
        if len(vocabulary) > 32:
            raise ValueError("High-cardinality predictor requires approved preprocessing")
        for category in vocabulary[1:]:
            a.append(np.array([value(row) == category for row in train], dtype=float))
            b.append(np.array([value(row) == category for row in test], dtype=float))
    return np.column_stack(a), np.column_stack(b)


def fit_predict(train, test, features):
    x, xt = matrix(train, test, features)
    y = np.array([r["outcome"] for r in train])
    w = np.array([r["weight"] for r in train])
    w = w / w.mean()

    def objective(beta):
        z = x @ beta
        loss = np.sum(w * (np.logaddexp(0, z) - y * z)) + 0.5 * np.dot(beta[1:], beta[1:])
        grad = x.T @ (w * (expit(z) - y))
        grad[1:] += beta[1:]
        return loss, grad

    result = minimize(objective, np.zeros(x.shape[1]), jac=True, method="L-BFGS-B")
    if not result.success:
        raise ValueError("Logistic fit failed: " + result.message)
    return expit(xt @ result.x)


def evaluate(rows, contract):
    validate(rows, contract)
    nfold = contract.get("folds", 5)
    if nfold < 2:
        raise ValueError("At least two folds required")
    folds = np.array(
        [bucket(r["household_id"], contract["split_salt"] + ":fold", nfold) for r in rows]
    )
    pred = {"assignment_rate": np.empty(len(rows)), "fixed_l2_logistic": np.empty(len(rows))}
    for fold in range(nfold):
        train = [r for i, r in enumerate(rows) if folds[i] != fold]
        test = [r for i, r in enumerate(rows) if folds[i] == fold]
        if not test:
            raise ValueError("Empty evaluation fold")
        rates = {}
        for arm in (0, 1):
            subset = [r for r in train if r["assignment"] == arm]
            if not subset:
                raise ValueError("Missing training assignment arm")
            rates[arm] = np.average(
                [r["outcome"] for r in subset], weights=[r["weight"] for r in subset]
            )
        pred["assignment_rate"][folds == fold] = [rates[r["assignment"]] for r in test]
        pred["fixed_l2_logistic"][folds == fold] = fit_predict(train, test, contract["features"])
    y = np.array([r["outcome"] for r in rows])
    w = np.array([r["weight"] for r in rows])
    assignment = np.array([r["assignment"] for r in rows])
    metrics = {}
    for name, p in pred.items():
        clipped = np.clip(p, 1e-8, 1 - 1e-8)
        arms = {}
        for arm in (0, 1):
            mask = assignment == arm
            actual = float(np.average(y[mask], weights=w[mask]))
            forecast = float(np.average(p[mask], weights=w[mask]))
            arms[str(arm)] = {
                "observed": actual,
                "predicted": forecast,
                "absolute_error": abs(actual - forecast),
            }
        metrics[name] = {
            "brier": float(np.average((p - y) ** 2, weights=w)),
            "log_loss": float(
                np.average(-y * np.log(clipped) - (1 - y) * np.log(1 - clipped), weights=w)
            ),
            "assignment_arm_shares": arms,
            "descriptive_assigned_arm_difference_error": abs(
                (arms["1"]["predicted"] - arms["0"]["predicted"])
                - (arms["1"]["observed"] - arms["0"]["observed"])
            ),
        }
    return {
        "status": "development_only",
        "n_people": len(rows),
        "n_households": len({r["household_id"] for r in rows}),
        "reserve_scored": 0,
        "folds": nfold,
        "metrics": metrics,
        "limitations": [
            "Not a published reference replication or design-adjusted ITT.",
            "Fixed L2=1; no tuning or calibration.",
            "Categorical encoding; continuous covariates require approved preprocessing.",
            "No uncertainty estimates; not a promotion decision.",
        ],
    }, pred


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    contract = json.loads(Path(args.contract).read_text())
    if contract.get("admission_status") != "approved":
        raise ValueError("Source contract not approved")
    expected = contract.get("normalized_input_sha256")
    if not expected or digest(args.input) != expected:
        raise ValueError("Normalized input checksum is missing or mismatched")
    rows = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line]
    result, _ = evaluate(rows, contract)
    result["input_sha256"] = digest(args.input)
    result["contract_sha256"] = digest(args.contract)
    result["implementation_sha256"] = digest(__file__)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
