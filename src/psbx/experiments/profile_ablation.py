"""New development-only ablations and nested out-of-fold calibration.

No historical context, conversation, inferred traits, or reserve evaluation. A prepared
plan is offline; `run` explicitly enables paid inference with the existing spend guard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from psbx.agents.runner import complete_turn
from psbx.env import load_dotenv
from psbx.experiments.anes_society import _parse_llm_json, _pseudonymous_id, _sha256_file
from psbx.experiments.decision_experiment import validate_probabilities
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.individual_worker import NEW
from psbx.experiments.profile_ablation_worker import ARMS, build_prompt
from psbx.experiments.telemetry import observe, observed_run
from psbx.paths import resolve
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

SEED = 20261021
RUN = "anes2012-ohio-profile-ablation-development-v1"


def read(path):
    return json.loads(Path(path).read_text())


def folds(ids, count=5):
    """Stable person-level folds, independent of outcomes and input row ordering."""
    if len(set(ids)) != len(ids) or len(ids) < count:
        raise ValueError("Unique respondents and enough people for folds required")
    shuffled = np.random.default_rng(SEED).permutation(sorted(ids))
    return {str(person): i % count for i, person in enumerate(shuffled)}


def evidence(person, field):
    v = person["observed"][field]
    return dict(
        label=v["label"],
        answer=v["answer"],
        status=v["status"],
        source="ANES 2012 Time Series respondent record",
        source_variable=field,
        observed_date=person["baseline_date"],
        date_precision="interview completion; exact item date unknown",
        missing=v.get("code") is None,
        inference=False,
        exposure="Personal exposure not established by this record",
    )


def payload(person, arm):
    return dict(
        arm=arm,
        baseline_date=person["baseline_date"],
        observations={f: evidence(person, f) for f in ARMS[arm]},
    )


def verify(root):
    c = read(root / "contract.json")
    check_seal(c)
    for name, digest in c["bindings"].items():
        if _sha256_file(Path(name)) != digest:
            raise ValueError("Frozen input changed: " + name)
    return c


def prepare(root):
    if (root / "contract.json").exists():
        return verify(root)
    prior = resolve("data/runs/anes2012-ohio-reserved-validation-20261012")
    old = resolve("data/runs/anes2012-ohio-individual-development-20261020")
    source = resolve("data/survey-microdata/anes/2012/source/anes_timeseries_2012.dta")
    target_manifest = resolve("data/runs/anes2012-decision-context-20261011/profile-seal.json")
    manifest = read(target_manifest)
    check_seal(manifest)
    if _sha256_file(source) != manifest["source_sha256"]:
        raise ValueError("Source checksum mismatch")
    prior_contract = read(prior / "contract.json")
    check_seal(prior_contract)
    cohort_path = prior / "input/cohort.json"
    if _sha256_file(cohort_path) != prior_contract["bindings"][str(cohort_path)]:
        raise ValueError("Prior cohort checksum mismatch")
    cohort = read(cohort_path)
    reserve = set(read(prior / "reserved-respondent-ids.json"))
    ids = [p["synthetic_person_id"] for p in cohort]
    if set(ids) & reserve:
        raise ValueError("Reserve contamination")
    reader = pd.io.stata.StataReader(source)
    labels, values = reader.variable_labels(), reader.value_labels()
    maps = {f: values.get(reader._lbllist[reader._varlist.index(f)], {}) for f in NEW}
    if not all(labels[f].startswith("PRE:") for f in NEW):
        raise ValueError("New covariates must be PRE observations")
    frame = pd.read_stata(source, columns=["caseid"] + NEW, convert_categoricals=False)
    rows = {_pseudonymous_id(r["caseid"]): r for _, r in frame.iterrows()}
    for person in cohort:
        for f in NEW:
            value = rows[person["synthetic_person_id"]][f]
            missing = pd.isna(value) or float(value) < 0
            person["observed"][f] = dict(
                label=labels[f],
                code=None if missing else float(value),
                answer="Not observed; do not invent."
                if missing
                else re.sub(r"^-?\d+\.\s*", "", str(maps[f].get(value, value))),
                status="missing" if missing else "observed_pre_election",
            )
        for arm in ARMS:
            build_prompt(payload(person, arm))
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    dump(root / "cohort.json", cohort)
    dump(root / "folds.json", folds(ids))
    dump(root / "worker.json", read(old / "worker.json"))
    config = dict(
        seed=SEED,
        repetitions=2,
        people=len(cohort),
        arms=list(ARMS),
        planned_calls=len(cohort) * len(ARMS) * 2,
        max_requests=1000,
        max_usd=10,
        scope="Previously inspected development cohort; no fresh holdout claim",
        calibration="5 outer person folds; 4 inner folds; weighted Brier selection",
        primary_contrasts=[
            ["original_rich", "reduced_existing"],
            ["reduced_existing", "reduced_plus_observed"],
        ],
        promotion=False,
        historical_context=False,
        conversation=False,
    )
    dump(root / "config.json", config)
    paths = [root / n for n in ["cohort.json", "folds.json", "worker.json", "config.json"]]
    paths += [
        source,
        cohort_path,
        prior / "contract.json",
        target_manifest,
        prior / "reserved-respondent-ids.json",
        Path(__file__),
        resolve("src/psbx/experiments/profile_ablation_worker.py"),
        resolve("src/psbx/experiments/individual_worker.py"),
        resolve("src/psbx/experiments/social_worker.py"),
        resolve("Dockerfile.profile-ablation"),
        *[
            resolve("src/psbx/" + name)
            for name in [
                "agents/runner.py",
                "schemas.py",
                "spending.py",
                "config.py",
                "env.py",
                "openrouter.py",
                "experiments/decision_experiment.py",
                "experiments/decision_profiles.py",
                "experiments/anes_society.py",
            ]
        ],
    ]
    contract = seal(
        dict(
            bindings={str(p): _sha256_file(p) for p in paths},
            target_manifest=str(target_manifest),
            reserve_ids=str(prior / "reserved-respondent-ids.json"),
            config=config,
        )
    )
    dump(root / "contract.json", contract)
    return contract


@observed_run(study_id="ablation")
def run(root, image):
    c = verify(root)
    if not image.startswith("sha256:"):
        raise ValueError("Use immutable Docker image ID")
    image_path = root / "image.json"
    if image_path.exists() and read(image_path)["image_id"] != image:
        raise ValueError("Cannot change image on resume")
    dump(image_path, dict(image_id=image))
    load_dotenv()
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD="10",
        PSBX_MAX_PAID_REQUESTS="1000",
    )
    model = ModelConfig.model_validate(read(root / "worker.json"))
    checkpoint = root / "checkpoints"
    checkpoint.mkdir(exist_ok=True, mode=0o700)
    ledger_path = root / "spend_ledger.json"
    if ledger_path.exists() and any(
        e.get("reported_usage") is None for e in read(ledger_path)["entries"]
    ):
        raise ValueError("Unresolved provider usage: reconcile ledger before resuming")
    remaining = c["config"]["planned_calls"] - len(list(checkpoint.glob("*.json")))
    dump(root / "preflight.json", preflight_paid_requests([(model, remaining)]))
    begin_spend_run(root.name)

    def predict(job_spec):
        rep, person, arm = job_spec
        meta = dict(person=person["synthetic_person_id"], arm=arm, repetition=rep)
        # Pseudonymous IDs are generated by our importer, never user filenames.
        path = checkpoint / f"{meta['person']}-{arm}-{rep}.json"
        data = payload(person, arm)
        expected = build_prompt(data)
        if path.exists():
            row = read(path)
            if row["metadata"] != meta or row["payload"] != data:
                raise ValueError("Unsafe checkpoint resume")
            validate_probabilities(row["probabilities"])
        else:
            observe("agent_started", agent_key=meta["person"], phase="final")
            args = [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "32",
                "--memory",
                "64m",
                "--cpus",
                "1",
                image,
            ]
            result = subprocess.run(
                args, input=json.dumps(data), text=True, capture_output=True, timeout=30, check=True
            )
            job = json.loads(result.stdout)
            if any(job[k] != v for k, v in expected.items()):
                raise ValueError("Docker prompt mismatch")
            iso = job["isolation"]
            if (
                iso["uid"] != 10001
                or not iso["root_readonly"]
                or not iso["no_new_privileges"]
                or iso["active_external_interfaces"]
                or int(iso["effective_capabilities"], 16)
                or iso["provider_key_present"]
                or iso["forbidden_paths_present"]
            ):
                raise ValueError("Runtime isolation failed")
            observe("model_requested", agent_key=meta["person"], phase="final")
            response = complete_turn(
                model, [dict(role="user", content=job["user"])], system=job["system"], tools=False
            )
            observe("response_received", agent_key=meta["person"], phase="final")
            answer = validate_probabilities(_parse_llm_json(response.text))
            row = dict(
                metadata=meta,
                payload=data,
                probabilities=answer,
                raw=response.text,
                isolation=job["isolation"],
            )
            dump(path, row)
            observe("checkpoint_saved", agent_key=meta["person"], phase="final")
            print(
                json.dumps(
                    dict(
                        completed=len(list(checkpoint.glob("*.json"))),
                        planned=c["config"]["planned_calls"],
                    )
                ),
                flush=True,
            )
        return dict(metadata=meta, probabilities=row["probabilities"])

    jobs = [(rep, p, arm) for rep in range(2) for p in read(root / "cohort.json") for arm in ARMS]
    np.random.default_rng(SEED).shuffle(jobs)
    predictions = [predict(job) for job in jobs]
    verify(root)
    dump(root / "predictions.json", predictions)
    dump(
        root / "prediction-seal.json",
        seal(
            dict(
                bindings={
                    str(p): _sha256_file(p)
                    for p in [
                        root / "predictions.json",
                        root / "contract.json",
                        image_path,
                        *sorted(checkpoint.glob("*.json")),
                    ]
                }
            )
        ),
    )


def baseline(y, w, groups, test_groups, strength):
    counts = np.bincount(y, weights=w / w.mean(), minlength=3)
    prior = (counts + 1) / (counts.sum() + 3)
    result = []
    for group in test_groups:
        mask = groups == group
        count = np.bincount(y[mask], weights=(w / w.mean())[mask], minlength=3)
        result.append(
            prior if strength is None else (count + strength * prior) / (count.sum() + strength)
        )
    return np.array(result)


def nested_predictions(ids, y, w, groups, agent, outer):
    """Every scored person's label is excluded from fitting and parameter selection."""
    outputs = {k: np.zeros_like(agent) for k in ["prevalence", "party", "hybrid"]}
    decisions = []
    for fold in sorted(set(outer.values())):
        test = np.array([outer[i] == fold for i in ids])
        train = ~test
        inner = folds(list(np.array(ids)[train]), 4)
        scored = []
        for strength in [1, 5, 20]:
            for alpha in [0, 0.25, 0.5, 0.75, 1]:
                losses, weights = [], []
                for f in range(4):
                    validation = train & np.array([inner.get(i, -1) == f for i in ids])
                    fitting = train & ~validation
                    if not fitting.any() or not validation.any():
                        continue
                    stat = baseline(
                        y[fitting], w[fitting], groups[fitting], groups[validation], strength
                    )
                    prediction = alpha * agent[validation] + (1 - alpha) * stat
                    losses.extend(((prediction - np.eye(3)[y[validation]]) ** 2).sum(1) / 2)
                    weights.extend(w[validation])
                scored.append((float(np.average(losses, weights=weights)), strength, alpha))
        _, strength, alpha = min(scored)
        party_strength = min(x for x in scored if x[2] == 0)[1]
        for name, s in [("prevalence", None), ("party", party_strength), ("hybrid", strength)]:
            pred = baseline(y[train], w[train], groups[train], groups[test], s)
            outputs[name][test] = (
                alpha * agent[test] + (1 - alpha) * pred if name == "hybrid" else pred
            )
        decisions.append(
            dict(
                outer_fold=fold,
                training_ids=list(np.array(ids)[train]),
                evaluation_ids=list(np.array(ids)[test]),
                party_strength=party_strength,
                hybrid_strength=strength,
                agent_weight=alpha,
            )
        )
    return outputs, decisions


def metrics(y, probs, w):
    truth = np.eye(3)[y]
    actual, predicted = np.average(truth, axis=0, weights=w), np.average(probs, axis=0, weights=w)
    return dict(
        n=len(y),
        effective_n=float(w.sum() ** 2 / (w * w).sum()),
        brier=float(np.average(((probs - truth) ** 2).sum(1) / 2, weights=w)),
        log_loss=float(
            np.average(-np.log(np.maximum(probs[np.arange(len(y)), y], 1e-12)), weights=w)
        ),
        accuracy=float(np.average(probs.argmax(1) == y, weights=w)),
        observed_shares=actual.tolist(),
        predicted_shares=predicted.tolist(),
        total_variation=float(abs(actual - predicted).sum() / 2),
    )


def evaluate(root):
    c = verify(root)
    boundary = read(root / "prediction-seal.json")
    check_seal(boundary)
    for path, digest in boundary["bindings"].items():
        if _sha256_file(Path(path)) != digest:
            raise ValueError("Prediction artifact changed")
    people = read(root / "cohort.json")
    ids = [p["synthetic_person_id"] for p in people]
    if set(ids) & set(read(c["reserve_ids"])):
        raise ValueError("Reserve contamination")
    predictions = read(root / "predictions.json")
    expected = {(i, a, r) for i in ids for a in ARMS for r in range(2)}
    lookup = {
        (
            p["metadata"]["person"],
            p["metadata"]["arm"],
            p["metadata"]["repetition"],
        ): validate_probabilities(p["probabilities"])
        for p in predictions
    }
    if set(lookup) != expected or len(predictions) != len(expected):
        raise ValueError("Incomplete or duplicate prediction panel")
    manifest = read(c["target_manifest"])
    check_seal(manifest)
    if _sha256_file(Path(manifest["targets_path"])) != manifest["targets_sha256"]:
        raise ValueError("Target hash mismatch")
    targets = {p["synthetic_person_id"]: p for p in read(manifest["targets_path"])}
    outer = read(root / "folds.json")
    reports, audit = [], []
    individual_losses = {}
    for task, spec in TARGETS.items():
        valid = [p for p in people if targets[p["synthetic_person_id"]][task] in spec["codes"]]
        vi = [p["synthetic_person_id"] for p in valid]
        y = np.array([spec["codes"].index(targets[i][task]) for i in vi])
        w = np.array([p["weight"] for p in valid])
        groups = np.array([str(p["observed"]["pid_x"]["code"]) for p in valid])
        for arm in ARMS:
            repeats = np.array([[lookup[i, arm, r][task] for r in range(2)] for i in vi])
            agent = repeats.mean(1)
            variants, decisions = nested_predictions(vi, y, w, groups, agent, outer)
            audit.append(dict(task=task, arm=arm, folds=decisions))
            for variant, probs in {"direct": agent, **variants}.items():
                individual_losses[arm, variant, task] = dict(
                    zip(vi, (((probs - np.eye(3)[y]) ** 2).sum(1) / 2).tolist())
                )
                reports.append(
                    dict(
                        task=task,
                        arm=arm,
                        variant=variant,
                        weighted=metrics(y, probs, w),
                        unweighted=metrics(y, probs, np.ones(len(y))),
                        repeat_agreement=float(
                            np.average(
                                repeats[:, 0].argmax(1) == repeats[:, 1].argmax(1), weights=w
                            )
                        )
                        if variant == "direct"
                        else None,
                        party_subgroups={
                            g: metrics(y[groups == g], probs[groups == g], w[groups == g])
                            for g in sorted(set(groups))
                        },
                    )
                )
    contrasts = []
    rng = np.random.default_rng(SEED)
    bootstrap = [
        np.bincount(rng.integers(0, len(ids), len(ids)), minlength=len(ids)) for _ in range(2000)
    ]
    person_weights = {p["synthetic_person_id"]: p["weight"] for p in people}
    for before, after in c["config"]["primary_contrasts"]:
        tasks = []
        for task in TARGETS:
            first = individual_losses[before, "direct", task]
            second = individual_losses[after, "direct", task]
            positions = [i for i, person in enumerate(ids) if person in first]
            delta = np.array([second[ids[i]] - first[ids[i]] for i in positions])
            weights = np.array([person_weights[ids[i]] for i in positions])
            tasks.append((positions, delta, weights))
        draws = []
        for counts in bootstrap:
            if all((weights * counts[pos]).sum() for pos, _, weights in tasks):
                draws.append(
                    np.mean(
                        [
                            np.average(delta, weights=weights * counts[pos])
                            for pos, delta, weights in tasks
                        ]
                    )
                )
        contrasts.append(
            dict(
                before=before,
                after=after,
                macro_brier_delta=float(np.mean([np.average(d, weights=w) for _, d, w in tasks])),
                conditional_person_bootstrap95=np.quantile(draws, [0.025, 0.975]).tolist(),
                bootstrap_refits_calibration=False,
            )
        )
    result = dict(
        contrasts=contrasts,
        scope=c["config"]["scope"],
        promotion=False,
        reserved_respondents_used=0,
        metrics=reports,
        fitting_audit=audit,
        limitations="Development OOF calibration, not fresh external validation; "
        "averaged-repeat probabilities; small subgroups are descriptive only. "
        "Cross-attitude joint fidelity and longitudinal change require further evaluation.",
    )
    dump(root / "evaluation.json", result)
    dump(
        root / "evaluation-seal.json",
        seal(
            dict(
                report_sha256=_sha256_file(root / "evaluation.json"),
                prediction_seal_sha256=_sha256_file(root / "prediction-seal.json"),
                target_sha256=manifest["targets_sha256"],
            )
        ),
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "run", "evaluate"])
    parser.add_argument("--root", type=Path, default=resolve("data/runs") / RUN)
    parser.add_argument("--image", default="")
    args = parser.parse_args()
    if args.phase == "run":
        run(args.root, args.image)
    else:
        {"prepare": prepare, "evaluate": evaluate}[args.phase](args.root)


if __name__ == "__main__":
    main()
