"""Frozen individual-agent development comparison; never tunes on the ANES reserve."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from psbx.agents.runner import complete_turn
from psbx.config import load_models
from psbx.env import load_dotenv
from psbx.experiments.anes_society import (
    _canonical_json_sha256,
    _parse_llm_json,
    _pseudonymous_id,
    _sha256_file,
)
from psbx.experiments.decision_experiment import readiness, validate_probabilities
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.individual_worker import ARMS, NEW, build_prompt, fields
from psbx.experiments.telemetry import observe, observed_run
from psbx.paths import resolve
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

RUN_ID = "anes2012-ohio-individual-development-20261020"


def read(p):
    return json.loads(Path(p).read_text())


def verify(root):
    c = read(root / "contract.json")
    check_seal(c)
    for p, h in c["bindings"].items():
        if _sha256_file(Path(p)) != h:
            raise ValueError("Frozen input changed: " + p)
    return c


def docker_job(payload, image):
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
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=8m",
        image,
    ]
    r = subprocess.run(
        args, input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=30
    )
    job = json.loads(r.stdout)
    if any(job[k] != v for k, v in build_prompt(payload).items()):
        raise ValueError("Container prompt mismatch")
    return job


def prepare(root):
    if (root / "contract.json").exists():
        return verify(root)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    old = resolve("data/runs/anes2012-ohio-reserved-validation-20261012")
    prior = resolve("data/runs/anes2012-decision-context-20261011")
    pool = read(old / "input/cohort.json")
    reserve = set(read(old / "reserved-respondent-ids.json"))
    rng = np.random.default_rng(20261020)
    selected = [pool[i] for i in rng.permutation(len(pool))[:24]]
    ids = {p["synthetic_person_id"] for p in selected}
    assert not ids & reserve and len(ids) == 24
    source = resolve("data/survey-microdata/anes/2012/source/anes_timeseries_2012.dta")
    manifest = read(prior / "profile-seal.json")
    check_seal(manifest)
    assert _sha256_file(source) == manifest["source_sha256"]
    reader = pd.io.stata.StataReader(source)
    labels, values = reader.variable_labels(), reader.value_labels()
    mappings = {f: values.get(reader._lbllist[reader._varlist.index(f)], {}) for f in NEW}
    assert all(labels[f].startswith("PRE:") for f in NEW)
    # Only covariate columns are read; target columns stay outside runtime preparation.
    frame = pd.read_stata(source, columns=["caseid"] + NEW, convert_categoricals=False)
    rows = {_pseudonymous_id(row["caseid"]): row for _, row in frame.iterrows()}
    audit = []
    for f in NEW:
        audit.append(
            dict(
                field=f,
                label=labels[f],
                rationale="Observed pre-election covariate; "
                "not a target alias. Same-wave imputation, not a temporal causal claim.",
            )
        )
    for p in selected:
        row = rows[p["synthetic_person_id"]]
        for f in NEW:
            value = row[f]
            missing = pd.isna(value) or float(value) < 0
            p["observed"][f] = dict(
                label=labels[f],
                code=None if missing else float(value),
                answer="Not observed; do not invent."
                if missing
                else re.sub(r"^-?\d+\.\s*", "", str(mappings[f].get(value, value))),
                status="missing" if missing else "observed_pre_election",
            )
    dump(root / "cohort.json", selected)
    dump(
        root / "baseline-training-ids.json",
        [p["synthetic_person_id"] for p in pool if p["synthetic_person_id"] not in ids],
    )
    dump(root / "field-audit.json", audit)
    config = dict(
        seed=20261020,
        people=24,
        repetitions=2,
        planned_calls=240,
        max_requests=500,
        max_usd=2,
        primary="Equal-task weighted half-Brier: focused_direct minus rich_direct",
        secondary="focused_review minus focused_direct; sparse/rich and statistical baselines",
        promotion="Development only: no automatic promotion and no reserve use",
        practical_improvement=0.005,
        maximum_task_regression=0.01,
    )
    dump(root / "config.json", config)
    model = load_models()["openrouter-gpt-4.1-mini"]
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    catalog = next(x for x in response.json()["data"] if x["id"] == model.model_name)
    assert "response_format" in catalog["supported_parameters"]
    model = model.model_copy(
        update=dict(
            temperature=0.4,
            max_tokens=256,
            json_output=True,
            cost_per_1k_input=float(catalog["pricing"]["prompt"]) * 1000,
            cost_per_1k_output=float(catalog["pricing"]["completion"]) * 1000,
        )
    )
    dump(root / "worker.json", model.model_dump(mode="json"))
    dump(root / "catalog.json", catalog)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "psbx-individual-worker:local", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    paths = [
        root / n
        for n in [
            "cohort.json",
            "baseline-training-ids.json",
            "field-audit.json",
            "config.json",
            "worker.json",
            "catalog.json",
        ]
    ]
    paths += [
        old / "input/cohort.json",
        old / "reserved-respondent-ids.json",
        prior / "profile-seal.json",
        source,
        Path(__file__),
        resolve("src/psbx/experiments/individual_worker.py"),
        resolve("src/psbx/experiments/social_worker.py"),
        resolve("src/psbx/experiments/decision_experiment.py"),
        resolve("src/psbx/experiments/decision_profiles.py"),
        resolve("src/psbx/experiments/anes_society.py"),
        resolve("src/psbx/agents/runner.py"),
        resolve("src/psbx/openrouter.py"),
        resolve("src/psbx/spending.py"),
        resolve("Dockerfile.individual-worker"),
    ]
    c = seal(
        dict(
            config=config,
            image_id=image,
            bindings={str(p): _sha256_file(p) for p in paths},
            targets_manifest=str(prior / "profile-seal.json"),
            baseline_pool=str(old / "input/cohort.json"),
            scope=(
                "Previously inspected development respondents; not fresh validation. "
                "No social interaction or historical pack."
            ),
        )
    )
    dump(
        root / "docker-probe.json",
        docker_job(payload(selected[0], "sparse_direct"), image)["isolation"],
    )
    dump(root / "contract.json", c)
    return c


def payload(person, arm, stage="final", review=""):
    return dict(
        arm=arm,
        stage=stage,
        baseline_date=person["baseline_date"],
        review=review,
        observations={
            f: {k: person["observed"][f][k] for k in ["label", "answer", "status"]}
            for f in fields(arm)
        },
    )


def call(root, contract, model, data, meta):
    key = _canonical_json_sha256(meta)
    path = root / "checkpoints" / (key + ".json")
    fingerprint = _canonical_json_sha256(dict(payload=data, model=model.model_dump(mode="json")))
    if path.exists():
        saved = read(path)
        if saved["fingerprint"] != fingerprint or saved["status"] != "completed":
            raise ValueError("Unsafe resume")
        return saved["parsed"]
    observe("agent_started", agent_key=meta.get("person"), phase=data["stage"])
    job = docker_job(data, contract["image_id"])
    history = [dict(role="user", content=job["user"])]
    raw = []
    parsed = None
    for attempt in range(2):
        try:
            observe("model_requested", agent_key=meta.get("person"), phase=data["stage"])
            turn = complete_turn(model, history, system=job["system"], tools=False)
            observe("response_received", agent_key=meta.get("person"), phase=data["stage"])
        except Exception as exc:
            dump(
                root / "provider-failure.json",
                dict(metadata=meta, exception_type=type(exc).__name__),
            )
            raise
        raw.append(turn.text)
        try:
            result = _parse_llm_json(turn.text)
            if data["stage"] == "final":
                parsed = validate_probabilities(result)
            else:
                if (
                    set(result) != {"review"}
                    or not isinstance(result["review"], str)
                    or len(result["review"]) > 4000
                ):
                    raise ValueError("Invalid review")
                parsed = result
            break
        except (ValueError, TypeError, KeyError):
            history += [
                dict(role="assistant", content=turn.text),
                dict(
                    role="user",
                    content="Return only the requested JSON schema and normalized probabilities.",
                ),
            ]
    dump(
        path,
        dict(
            metadata=meta,
            fingerprint=fingerprint,
            payload=data,
            prompt_sha256=_canonical_json_sha256(build_prompt(data)),
            isolation=job["isolation"],
            raw=raw,
            attempts=attempt + 1,
            parsed=parsed,
            status="completed" if parsed is not None else "invalid",
        ),
    )
    observe("checkpoint_saved", agent_key=meta.get("person"), phase=data["stage"])
    if parsed is None:
        raise RuntimeError("Invalid format after repair; stopped")
    print(
        json.dumps(
            dict(
                completed=len(list(path.parent.glob("*.json"))),
                arm=meta["arm"],
                stage=meta["stage"],
            )
        ),
        flush=True,
    )
    return parsed


@observed_run(study_id="individual")
def run(root):
    c = verify(root)
    load_dotenv()
    readiness(root)
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD="2",
        PSBX_MAX_PAID_REQUESTS="500",
    )
    model = ModelConfig.model_validate(read(root / "worker.json"))
    dump(root / "preflight.json", preflight_paid_requests([(model, 480)]))
    begin_spend_run(root.name)
    (root / "checkpoints").mkdir(exist_ok=True)
    (root / "checkpoints").chmod(0o700)
    cohort = read(root / "cohort.json")
    rng = np.random.default_rng(c["config"]["seed"])
    predictions = []
    for rep in range(2):
        for p in cohort:
            for arm in rng.permutation(ARMS):
                arm = str(arm)
                meta = dict(person=p["synthetic_person_id"], repetition=rep, arm=arm, stage="final")
                note = ""
                if arm == "focused_review":
                    note = call(
                        root, c, model, payload(p, arm, "review"), {**meta, "stage": "review"}
                    )["review"]
                answer = call(root, c, model, payload(p, arm, review=note), meta)
                predictions.append(dict(metadata=meta, probabilities=answer))
    verify(root)
    validate_panel(cohort, predictions)
    dump(root / "predictions.json", predictions)
    dump(
        root / "prediction-seal.json",
        seal(
            dict(
                bindings={
                    str(p): _sha256_file(p)
                    for p in [
                        root / "contract.json",
                        root / "predictions.json",
                        *sorted((root / "checkpoints").glob("*.json")),
                    ]
                }
            )
        ),
    )


def validate_panel(cohort, rows):
    expected = {(p["synthetic_person_id"], a, r) for p in cohort for a in ARMS for r in range(2)}
    actual = [
        (x["metadata"]["person"], x["metadata"]["arm"], x["metadata"]["repetition"]) for x in rows
    ]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Incomplete or duplicated panel")
    for row in rows:
        validate_probabilities(row["probabilities"])


def evaluate(root):
    c = verify(root)
    boundary = read(root / "prediction-seal.json")
    check_seal(boundary)
    for p, h in boundary["bindings"].items():
        assert _sha256_file(Path(p)) == h
    cohort = read(root / "cohort.json")
    predictions = read(root / "predictions.json")
    validate_panel(cohort, predictions)
    manifest = read(c["targets_manifest"])
    check_seal(manifest)
    assert _sha256_file(Path(manifest["targets_path"])) == manifest["targets_sha256"]
    # First target access in this run happens after complete prediction validation.
    targets = {x["synthetic_person_id"]: x for x in read(manifest["targets_path"])}
    trainids = set(read(root / "baseline-training-ids.json"))
    assert not trainids & {p["synthetic_person_id"] for p in cohort}
    train = [p for p in read(c["baseline_pool"]) if p["synthetic_person_id"] in trainids]
    lookup = {
        (r["metadata"]["person"], r["metadata"]["arm"], r["metadata"]["repetition"]): r[
            "probabilities"
        ]
        for r in predictions
    }
    arms = ARMS + ["training_prevalence", "party_smoothed"]
    metrics = []
    losses = {a: {} for a in arms}
    weights = {}
    for task, spec in TARGETS.items():
        valid = [
            i
            for i, p in enumerate(cohort)
            if targets[p["synthetic_person_id"]][task] in spec["codes"]
        ]
        y = np.array(
            [spec["codes"].index(targets[cohort[i]["synthetic_person_id"]][task]) for i in valid]
        )
        truth = np.eye(3)[y]
        w = np.array([cohort[i]["weight"] for i in valid])
        weights[task] = (valid, w)
        eligible = [p for p in train if targets[p["synthetic_person_id"]][task] in spec["codes"]]
        tw = np.array([p["weight"] for p in eligible])
        tw = tw / tw.mean()
        ty = np.array(
            [spec["codes"].index(targets[p["synthetic_person_id"]][task]) for p in eligible]
        )
        counts = np.bincount(ty, weights=tw, minlength=3)
        prior = (counts + 1) / (counts.sum() + 3)
        for arm in arms:
            if arm in ARMS:
                probs = np.array(
                    [
                        [lookup[cohort[i]["synthetic_person_id"], arm, r][task] for r in range(2)]
                        for i in valid
                    ]
                )
            else:
                pp = []
                for i in valid:
                    party = cohort[i]["observed"]["pid_x"]["code"]
                    mask = (
                        np.array([p["observed"]["pid_x"]["code"] == party for p in eligible])
                        if arm == "party_smoothed"
                        else np.zeros(len(eligible), bool)
                    )
                    count = np.bincount(ty[mask], weights=tw[mask], minlength=3)
                    pp.append((count + 5 * prior) / (count.sum() + 5))
                probs = np.array(pp)[:, None, :]
            loss = ((probs - truth[:, None, :]) ** 2).sum(axis=2).mean(axis=1) / 2
            losses[arm][task] = dict(zip(valid, loss.tolist()))
            metrics.append(
                dict(
                    arm=arm,
                    task=task,
                    n=len(valid),
                    effective_n=float(w.sum() ** 2 / (w * w).sum()),
                    brier=float(np.average(loss, weights=w)),
                    accuracy=float(
                        np.average((probs.argmax(axis=2) == y[:, None]).mean(axis=1), weights=w)
                    ),
                    mean_max_confidence=float(
                        np.average(probs.max(axis=2).mean(axis=1), weights=w)
                    ),
                    repeat_agreement=None
                    if arm not in ARMS
                    else float(
                        np.average(
                            probs[:, 0].argmax(axis=1) == probs[:, 1].argmax(axis=1), weights=w
                        )
                    ),
                )
            )
    macro = {a: float(np.mean([m["brier"] for m in metrics if m["arm"] == a])) for a in arms}
    contrasts = []
    rng = np.random.default_rng(20261020)
    for before, after in [
        ("rich_direct", "focused_direct"),
        ("focused_direct", "focused_review"),
        ("sparse_direct", "rich_direct"),
        ("party_smoothed", "focused_direct"),
    ]:
        draws = []
        for _ in range(4000):
            counts = np.bincount(rng.integers(0, len(cohort), len(cohort)), minlength=len(cohort))
            tasks = []
            for task, (ix, w) in weights.items():
                bw = w * counts[ix]
                if bw.sum():
                    tasks.append(
                        np.average(
                            [losses[after][task][i] - losses[before][task][i] for i in ix],
                            weights=bw,
                        )
                    )
            if len(tasks) == 3:
                draws.append(np.mean(tasks))
        contrasts.append(
            dict(
                before=before,
                after=after,
                delta=macro[after] - macro[before],
                bootstrap95=np.quantile(draws, [0.025, 0.975]).tolist(),
            )
        )
    primary = contrasts[0]
    taskdeltas = [
        next(m["brier"] for m in metrics if m["arm"] == "focused_direct" and m["task"] == t)
        - next(m["brier"] for m in metrics if m["arm"] == "rich_direct" and m["task"] == t)
        for t in TARGETS
    ]
    ledger = read(root / "spend_ledger.json")
    report = dict(
        scope=c["scope"],
        metrics=metrics,
        macro_brier=macro,
        contrasts=contrasts,
        development_signal_gate=bool(
            primary["delta"] <= -0.005 and primary["bootstrap95"][1] < 0 and max(taskdeltas) <= 0.01
        ),
        gate_is_not_promotion=True,
        reserved_respondents_used=0,
        training_n=len(train),
        people=len(cohort),
        provider_requests=ledger["reserved_requests"],
        unresolved_usage=sum(e.get("reported_usage") is None for e in ledger["entries"]),
        provider_reported_cost_usd=sum(
            (e.get("reported_usage") or {}).get("provider_cost_usd", 0) or 0
            for e in ledger["entries"]
        ),
        limitations=(
            "24 inspected development people, two repeats, one model; conditional bootstrap, "
            "national weights in Ohio subset. Focused changes both field selection and four "
            "observed covariates; attribution needs ablations. No population, causal or "
            "fresh-holdout claim."
        ),
    )
    dump(root / "evaluation.json", report)
    dump(
        root / "evaluation-seal.json",
        seal(
            dict(
                report_sha256=_sha256_file(root / "evaluation.json"),
                prediction_seal_sha256=_sha256_file(root / "prediction-seal.json"),
                targets_sha256=manifest["targets_sha256"],
            )
        ),
    )
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "run", "evaluate"])
    args = parser.parse_args()
    root = resolve("data/runs") / RUN_ID
    {"prepare": prepare, "run": run, "evaluate": evaluate}[args.phase](root)


if __name__ == "__main__":
    main()
