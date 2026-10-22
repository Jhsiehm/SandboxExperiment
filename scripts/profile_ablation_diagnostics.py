"""Post-evaluation diagnostics; never changes frozen forecasts or refits on the reserve.

Modal response-pair tables are descriptive proxies, not joint predictive distributions.
Intervals condition on already fitted OOF predictions and do not refit calibration.
"""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_experiment import validate_probabilities
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.profile_ablation import RUN, SEED, nested_predictions, read, verify
from psbx.experiments.profile_ablation_worker import ARMS
from psbx.paths import resolve


def share_mae(y, probabilities, weights):
    actual = np.average(np.eye(3)[y], axis=0, weights=weights)
    predicted = np.average(probabilities, axis=0, weights=weights)
    return float(np.abs(actual - predicted).mean())


def contingency(first, second, weights):
    table = np.zeros((3, 3))
    np.add.at(table, (first, second), weights)
    return table / table.sum()


def cramers_v(table):
    """Weighted descriptive association; no chi-square significance test."""
    expected = table.sum(1)[:, None] * table.sum(0)[None, :]
    active_rows = int(np.count_nonzero(table.sum(1)))
    active_columns = int(np.count_nonzero(table.sum(0)))
    dimension = min(active_rows, active_columns) - 1
    if dimension <= 0:
        return None
    chi = np.sum(
        np.divide((table - expected) ** 2, expected, out=np.zeros_like(table), where=expected > 0)
    )
    return float(np.sqrt(chi / dimension))


def modal_pair_diagnostic(y_first, y_second, p_first, p_second, weights):
    observed = contingency(y_first, y_second, weights)
    modal = contingency(p_first.argmax(1), p_second.argmax(1), weights)
    actual_v, predicted_v = cramers_v(observed), cramers_v(modal)
    return dict(
        n=len(weights),
        observed_pair_shares=observed.tolist(),
        predicted_modal_pair_shares=modal.tolist(),
        modal_pair_table_total_variation=float(np.abs(observed - modal).sum() / 2),
        observed_cramers_v=actual_v,
        predicted_modal_cramers_v=predicted_v,
        cramers_v_absolute_error=None
        if actual_v is None or predicted_v is None
        else abs(actual_v - predicted_v),
        modal_pair_accuracy=float(
            np.average(
                (p_first.argmax(1) == y_first) & (p_second.argmax(1) == y_second), weights=weights
            )
        ),
    )


def paired_interval(ids, deltas, weights, draws=2000):
    """One person resample shared across tasks; preserve task-specific missingness."""
    positions = {person: i for i, person in enumerate(ids)}
    task_data = []
    for task in deltas:
        people = list(deltas[task])
        task_data.append(
            (
                np.array([positions[p] for p in people]),
                np.array([deltas[task][p] for p in people]),
                np.array([weights[p] for p in people]),
            )
        )
    point = float(np.mean([np.average(d, weights=w) for _, d, w in task_data]))
    rng = np.random.default_rng(SEED)
    samples = []
    for _ in range(draws):
        counts = np.bincount(rng.integers(0, len(ids), len(ids)), minlength=len(ids))
        if all((w * counts[pos]).sum() for pos, _, w in task_data):
            samples.append(
                np.mean([np.average(d, weights=w * counts[pos]) for pos, d, w in task_data])
            )
    return dict(
        macro_brier_delta=point,
        conditional_person_bootstrap95=np.quantile(samples, [0.025, 0.975]).tolist(),
        valid_bootstrap_draws=len(samples),
        bootstrap_refits_calibration=False,
    )


def main(root):
    contract = verify(root)
    prediction_seal = read(root / "prediction-seal.json")
    check_seal(prediction_seal)
    for name, digest in prediction_seal["bindings"].items():
        if _sha256_file(Path(name)) != digest:
            raise ValueError("Prediction artifact changed")
    evaluation_seal = read(root / "evaluation-seal.json")
    check_seal(evaluation_seal)
    if (
        _sha256_file(root / "evaluation.json") != evaluation_seal["report_sha256"]
        or _sha256_file(root / "prediction-seal.json") != evaluation_seal["prediction_seal_sha256"]
    ):
        raise ValueError("Evaluation artifact changed")
    manifest = read(contract["target_manifest"])
    check_seal(manifest)
    if (
        _sha256_file(Path(manifest["targets_path"])) != manifest["targets_sha256"]
        or manifest["targets_sha256"] != evaluation_seal["target_sha256"]
    ):
        raise ValueError("Target artifact changed")
    cohort = read(root / "cohort.json")
    ids = [p["synthetic_person_id"] for p in cohort]
    if set(ids) & set(read(contract["reserve_ids"])):
        raise ValueError("Reserve contamination")
    rows = read(root / "predictions.json")
    lookup = {
        (
            r["metadata"]["person"],
            r["metadata"]["arm"],
            r["metadata"]["repetition"],
        ): validate_probabilities(r["probabilities"])
        for r in rows
    }
    expected = {(person, arm, rep) for person in ids for arm in ARMS for rep in range(2)}
    if len(rows) != len(expected) or set(lookup) != expected:
        raise ValueError("Incomplete or duplicate panel")
    targets = {p["synthetic_person_id"]: p for p in read(manifest["targets_path"])}
    outer = read(root / "folds.json")
    weights = {p["synthetic_person_id"]: p["weight"] for p in cohort}
    evaluation = read(root / "evaluation.json")
    cached, losses, shares = {}, {}, []
    for task, spec in TARGETS.items():
        valid = [p for p in cohort if targets[p["synthetic_person_id"]][task] in spec["codes"]]
        vi = [p["synthetic_person_id"] for p in valid]
        y = np.array([spec["codes"].index(targets[i][task]) for i in vi])
        w = np.array([weights[i] for i in vi])
        groups = np.array([str(p["observed"]["pid_x"]["code"]) for p in valid])
        for arm in ARMS:
            direct = np.array([[lookup[i, arm, r][task] for r in range(2)] for i in vi]).mean(1)
            variants, decisions = nested_predictions(vi, y, w, groups, direct, outer)
            original = next(
                a["folds"]
                for a in evaluation["fitting_audit"]
                if a["task"] == task and a["arm"] == arm
            )
            if decisions != original:
                raise ValueError("Reconstruction changed calibration decisions")
            for variant, probs in {"direct": direct, **variants}.items():
                cached[arm, variant, task] = {i: (int(t), p) for i, t, p in zip(vi, y, probs)}
                loss = ((probs - np.eye(3)[y]) ** 2).sum(1) / 2
                losses[arm, variant, task] = dict(zip(vi, loss))
                previous = next(
                    m["weighted"]["brier"]
                    for m in evaluation["metrics"]
                    if (m["task"], m["arm"], m["variant"]) == (task, arm, variant)
                )
                if not np.isclose(np.average(loss, weights=w), previous, atol=1e-12, rtol=0):
                    raise ValueError("Reconstruction changed reported Brier")
                shares.append(
                    dict(
                        task=task,
                        arm=arm,
                        variant=variant,
                        weighted_share_mae=share_mae(y, probs, w),
                        unweighted_share_mae=share_mae(y, probs, np.ones(len(y))),
                    )
                )
    associations, contrasts = [], []
    for arm in ARMS:
        for before in ["party", "direct"]:
            delta = {
                task: {
                    i: loss - losses[arm, before, task][i]
                    for i, loss in losses[arm, "hybrid", task].items()
                }
                for task in TARGETS
            }
            contrasts.append(
                dict(arm=arm, before=before, after="hybrid", **paired_interval(ids, delta, weights))
            )
        for variant in ["direct", "prevalence", "party", "hybrid"]:
            for first, second in combinations(TARGETS, 2):
                a, b = cached[arm, variant, first], cached[arm, variant, second]
                valid_ids = [i for i in ids if i in a and i in b]
                y1, y2 = [np.array([v[i][0] for i in valid_ids]) for v in [a, b]]
                p1, p2 = [np.array([v[i][1] for i in valid_ids]) for v in [a, b]]
                w = np.array([weights[i] for i in valid_ids])
                associations.append(
                    dict(
                        arm=arm,
                        variant=variant,
                        tasks=[first, second],
                        weighted=modal_pair_diagnostic(y1, y2, p1, p2, w),
                        unweighted=modal_pair_diagnostic(y1, y2, p1, p2, np.ones(len(w))),
                    )
                )
    report = dict(
        scope="Exploratory post-evaluation development diagnostics",
        promotion=False,
        reserved_respondents_used=0,
        answer_share_mae=shares,
        modal_response_pair_proxies=associations,
        conditional_hybrid_contrasts=contrasts,
        limitations="Modal pair tables are descriptive response-assignment proxies, not joint "
        "predictive distributions. Ties use first-index argmax. Bootstrap conditions on fixed "
        "OOF predictions and does not capture calibration refitting, model or cohort-selection "
        "uncertainty. Multiple exploratory comparisons; no fresh-validation or causal claim.",
    )
    output = root / "additional-diagnostics.json"
    dump(output, report)
    dump(
        root / "additional-diagnostics-seal.json",
        seal(
            dict(
                bindings={
                    str(p): _sha256_file(p)
                    for p in [
                        output,
                        Path(__file__).resolve(),
                        root / "evaluation-seal.json",
                        root / "prediction-seal.json",
                        root / "contract.json",
                    ]
                }
            )
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=resolve("data/runs") / RUN)
    main(parser.parse_args().root)
