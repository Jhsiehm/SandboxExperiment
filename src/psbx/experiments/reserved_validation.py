"""Frozen independent replication with offline Docker planning and response validation.

The container has no provider credentials/network. A trusted host broker executes only
hash-bound prompts; evaluation targets are opened separately after predictions seal.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

from psbx.config import load_models
from psbx.env import load_dotenv
from psbx.experiments.anes_society import _canonical_json_sha256, _sha256_file
from psbx.experiments.decision_experiment import (
    SYSTEM,
    TASK,
    Calls,
    context,
    readiness,
    validate_probabilities,
)
from psbx.experiments.decision_profiles import (
    TARGETS,
    check_seal,
    choose_cohort,
    dump,
    previously_prompted,
    seal,
)
from psbx.paths import resolve, validate_run_id
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

ARMS = ("sparse", "rich")
DEFAULT_ID = "anes2012-ohio-reserved-validation-20261012"


def read(path):
    return json.loads(Path(path).read_text())


def make_jobs(cohort, config, workers):
    rng = np.random.default_rng(config["seed"] + 1)
    jobs = []
    for rep in range(config["repetitions"]):
        for index, profile in enumerate(cohort):
            for arm in rng.permutation(ARMS):
                metadata = dict(
                    phase="reserved_validation",
                    arm=str(arm),
                    repetition=rep,
                    synthetic_person_id=profile["synthetic_person_id"],
                    model_id=workers[index % len(workers)]["id"],
                )
                jobs.append(
                    dict(
                        metadata=metadata,
                        user=context(profile, arm == "rich", False, {}) + "\n" + TASK,
                    )
                )
    return jobs


def validate_panel(jobs, rows):
    expected = {_canonical_json_sha256(j["metadata"]): j["metadata"] for j in jobs}
    if len(expected) != len(jobs) or len(rows) != len(jobs):
        raise ValueError("Duplicate jobs or incomplete prediction panel")
    seen = set()
    for row in rows:
        key = _canonical_json_sha256(row["metadata"])
        if key not in expected or key in seen:
            raise ValueError("Unexpected or duplicated prediction metadata")
        seen.add(key)
        if row["probabilities"] is not None:
            validate_probabilities(row["probabilities"])


def isolation_probe():
    result = dict(
        uid=os.getuid(),
        interfaces=[n for _, n in socket.if_nameindex()],
        active_nonloopback=[
            name
            for _, name in socket.if_nameindex()
            if name != "lo" and int(Path(f"/sys/class/net/{name}/flags").read_text(), 16) & 1
        ],
        credential_present=bool(os.environ.get("OPENROUTER_API_KEY")),
        unexpected_paths=[
            p
            for p in [
                "/workspace/.env",
                "/input/targets.json",
                "/workspace/data/evaluation-vault",
                "/var/run/docker.sock",
            ]
            if Path(p).exists()
        ],
    )
    for name, path in [("root_readonly", "/workspace/probe"), ("input_readonly", "/input/probe")]:
        try:
            Path(path).write_text("probe")
        except OSError:
            result[name] = True
        else:
            result[name] = False
            Path(path).unlink()
    result["no_new_privileges"] = "NoNewPrivs:\t1" in Path("/proc/self/status").read_text()
    if (
        result["uid"] == 0
        or result["active_nonloopback"]
        or result["credential_present"]
        or result["unexpected_paths"]
        or not result["root_readonly"]
        or not result["input_readonly"]
        or not result["no_new_privileges"]
    ):
        raise RuntimeError(f"Isolation checks failed: {result}")
    return result


def container_stage(stage):
    audit = isolation_probe()
    config, cohort, workers = (
        read("/input/" + n + ".json") for n in ["config", "cohort", "workers"]
    )
    jobs = make_jobs(cohort, config, workers)
    if stage == "plan":
        dump(Path("/output/jobs.json"), jobs)
    else:
        if jobs != read("/output/jobs.json"):
            raise ValueError("Container reconstructed different prompts")
        rows = read("/output/responses.json")
        validate_panel(jobs, rows)
        dump(Path("/output/predictions.json"), rows)
        dump(
            Path("/output/prediction-seal.json"),
            seal(
                {
                    "jobs_sha256": _sha256_file(Path("/output/jobs.json")),
                    "predictions_sha256": _sha256_file(Path("/output/predictions.json")),
                    "n_predictions": len(rows),
                    "missing": sum(r["probabilities"] is None for r in rows),
                    "engine": "offline_docker_planner_validator_with_trusted_host_provider_broker",
                }
            ),
        )
    dump(Path("/output/" + stage + "-isolation.json"), audit)


def docker_stage(root, stage, image):
    name = root.name + "-" + stage
    args = [
        "docker",
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--cpus",
        "2",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,src={root / 'input'},dst=/input,readonly",
        "--mount",
        f"type=bind,src={root / 'output'},dst=/output",
        image,
        "python",
        "-m",
        "psbx.experiments.reserved_validation",
        "container-" + stage,
    ]
    subprocess.run(args, check=True, capture_output=True, text=True)
    try:
        inspection = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
        dump(root / (stage + "-docker-inspect.json"), inspection)
        result = subprocess.run(["docker", "start", "-a", name], capture_output=True, text=True)
        (root / (stage + "-docker.log")).write_text(result.stdout + result.stderr)
        state = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]["State"]
        if result.returncode or state["ExitCode"]:
            raise RuntimeError("Container failed: " + result.stdout + result.stderr)
    finally:
        subprocess.run(["docker", "rm", name], check=True, capture_output=True)


def verify_contract(root):
    contract = read(root / "contract.json")
    check_seal(contract)
    for path, digest in contract["bindings"].items():
        if _sha256_file(Path(path)) != digest:
            raise ValueError("Frozen input changed: " + path)
    return contract


def prepare(root):
    if (root / "contract.json").exists():
        return verify_contract(root)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    for name in ["input", "output"]:
        (root / name).mkdir(exist_ok=True)
        (root / name).chmod(0o700)
    old = resolve("data/runs/anes2012-decision-context-20261011")
    manifest = read(old / "profile-seal.json")
    check_seal(manifest)
    if _sha256_file(old / "profiles.jsonl") != manifest["profiles_sha256"]:
        raise ValueError("Profile source changed")
    profiles = [json.loads(x) for x in (old / "profiles.jsonl").read_text().splitlines()]
    seen = previously_prompted(resolve("data/runs"))
    config = dict(
        run_id=root.name,
        state_fips=39,
        sample_n=120,
        reserve_n=50,
        repetitions=2,
        seed=20261012,
        max_requests=960,
        max_usd=5,
        primary="Equal-task mean weighted half-multiclass Brier: rich minus sparse",
        practical_improvement=0.005,
        maximum_task_regression=0.01,
        baseline_party_pseudocount=5,
        scope="Previously unprompted development validation; not pristine holdout "
        "from all prior retrospective analyses. No historical pack or conversation.",
    )
    selected = choose_cohort(profiles, seen, 39, 170, config["seed"], "2012-08-03")
    dump(root / "input/cohort.json", selected[:120])
    dump(root / "reserved-respondent-ids.json", [p["synthetic_person_id"] for p in selected[120:]])
    dump(root / "previously-prompted-ids.json", sorted(seen))
    dump(root / "input/config.json", config)
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    catalog = {m["id"]: m for m in response.json()["data"]}
    workers, selected_catalog = [], {}
    defaults = load_models()
    for prior in read(old / "workers.json"):
        model = defaults[prior["id"]]
        row = catalog[model.model_name]
        if "response_format" not in row["supported_parameters"]:
            raise ValueError("JSON mode unavailable")
        selected_catalog[model.model_name] = row
        workers.append(
            model.model_copy(
                update=dict(
                    max_tokens=256,
                    temperature=0.4,
                    json_output=True,
                    cost_per_1k_input=float(row["pricing"]["prompt"]) * 1000,
                    cost_per_1k_output=float(row["pricing"]["completion"]) * 1000,
                )
            ).model_dump(mode="json")
        )
    dump(root / "input/workers.json", workers)
    dump(root / "catalog.json", selected_catalog)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "psbx-anes-validation:local", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    docker_stage(root, "plan", image)
    paths = list((root / "input").glob("*.json")) + [
        root / "output/jobs.json",
        root / "reserved-respondent-ids.json",
        root / "previously-prompted-ids.json",
        root / "catalog.json",
        old / "profiles.jsonl",
        old / "profile-seal.json",
        Path(__file__),
        resolve("src/psbx/experiments/decision_profiles.py"),
        resolve("src/psbx/experiments/decision_experiment.py"),
        resolve("src/psbx/agents/runner.py"),
        resolve("src/psbx/openrouter.py"),
        resolve("src/psbx/spending.py"),
        resolve("Dockerfile"),
        resolve("Dockerfile.validation"),
    ]
    contract = seal(
        dict(
            config=config,
            image_id=image,
            system_sha256=_canonical_json_sha256(SYSTEM),
            bindings={str(p): _sha256_file(p) for p in paths},
            targets_manifest=str(old / "profile-seal.json"),
            prior_profiles=str(old / "profiles.jsonl"),
            planned_calls=480,
            reserved_respondents=50,
            broker_boundary="Host broker has credentials and host access; "
            "only frozen jobs forwarded. Docker planner/validator have no network, "
            "raw data, labels, credentials or Docker socket.",
        )
    )
    dump(root / "contract.json", contract)
    return contract


def execute(root):
    contract = verify_contract(root)
    load_dotenv()
    config = contract["config"]
    readiness(root)
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD=str(config["max_usd"]),
        PSBX_MAX_PAID_REQUESTS=str(config["max_requests"]),
    )
    workers = [ModelConfig.model_validate(m) for m in read(root / "input/workers.json")]
    dump(root / "preflight.json", preflight_paid_requests([(w, 320) for w in workers]))
    begin_spend_run(root.name)
    jobs = read(root / "output/jobs.json")

    def run_worker(worker):
        checkpoint_dir = root / worker.id
        checkpoint_dir.mkdir(exist_ok=True)
        checkpoint_dir.chmod(0o700)
        calls = Calls(checkpoint_dir)
        rows = []
        for job in jobs:
            if job["metadata"]["model_id"] == worker.id:
                result = calls.call(worker, job["user"], job["metadata"])
                rows.append(dict(metadata=job["metadata"], probabilities=result))
        return rows

    with ThreadPoolExecutor(max_workers=3) as executor:
        rows = [row for group in executor.map(run_worker, workers) for row in group]
    verify_contract(root)
    validate_panel(jobs, rows)
    dump(root / "output/responses.json", rows)
    docker_stage(root, "validate", contract["image_id"])
    dump(
        root / "prediction-boundary-seal.json",
        seal(
            dict(
                contract_sha256=_sha256_file(root / "contract.json"),
                prediction_seal_sha256=_sha256_file(root / "output/prediction-seal.json"),
                checkpoint_hashes={
                    str(p.relative_to(root)): _sha256_file(p)
                    for p in root.glob("*/call-checkpoints.jsonl")
                },
            )
        ),
    )


def metric(probabilities, y, weights):
    p, y, w = np.asarray(probabilities), np.asarray(y, dtype=int), np.asarray(weights)
    oh = np.eye(3)[y]
    loss = 0.5 * ((p - oh) ** 2).sum(axis=1)
    share = np.average(p, axis=0, weights=w)
    truth = np.average(oh, axis=0, weights=w)
    return dict(
        n=len(y),
        effective_n=float(w.sum() ** 2 / (w * w).sum()),
        brier=float(np.average(loss, weights=w)),
        unweighted_brier=float(loss.mean()),
        agreement=float(np.average(p.argmax(axis=1) == y, weights=w)),
        log_loss=float(np.average(-np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1)), weights=w)),
        distribution_tv=float(abs(share - truth).sum() / 2),
        predicted_shares=share.tolist(),
        observed_shares=truth.tolist(),
        mean_confidence=float(np.average(p.max(axis=1), weights=w)),
    )


def bootstrap_contrast(person_losses, person_weights, seed=20261012):
    """Cluster-resample people jointly across tasks, preserving task-specific missingness."""
    losses, weights = np.asarray(person_losses, float), np.asarray(person_weights, float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(weights), (4000, len(weights)))
    valid = np.isfinite(losses)
    numerator = np.where(valid, losses * weights[:, None], 0)
    denominator = valid * weights[:, None]
    samples = numerator[draws].sum(axis=1) / denominator[draws].sum(axis=1)
    point = numerator.sum(axis=0) / denominator.sum(axis=0)
    return dict(
        task_changes=point.tolist(),
        macro_change=float(point.mean()),
        task_intervals=np.quantile(samples, [0.025, 0.975], axis=0).T.tolist(),
        macro_interval=np.quantile(samples.mean(axis=1), [0.025, 0.975]).tolist(),
    )


def evaluate(root):
    contract = verify_contract(root)
    boundary = read(root / "prediction-boundary-seal.json")
    check_seal(boundary)
    for name, digest in boundary["checkpoint_hashes"].items():
        if _sha256_file(root / name) != digest:
            raise ValueError("Checkpoint changed")
    if boundary["contract_sha256"] != _sha256_file(root / "contract.json"):
        raise ValueError("Contract changed")
    if boundary["prediction_seal_sha256"] != _sha256_file(root / "output/prediction-seal.json"):
        raise ValueError("Prediction seal changed")
    ps = read(root / "output/prediction-seal.json")
    check_seal(ps)
    for name in ["jobs", "predictions"]:
        if ps[name + "_sha256"] != _sha256_file(root / ("output/" + name + ".json")):
            raise ValueError("Sealed predictions or jobs changed")
    rows = read(root / "output/predictions.json")
    validate_panel(read(root / "output/jobs.json"), rows)
    manifest = read(contract["targets_manifest"])
    check_seal(manifest)
    if _sha256_file(Path(manifest["targets_path"])) != manifest["targets_sha256"]:
        raise ValueError("Target vault changed")
    targets = {p["synthetic_person_id"]: p for p in read(manifest["targets_path"])}
    profiles = {
        p["synthetic_person_id"]: p
        for p in map(json.loads, Path(contract["prior_profiles"]).read_text().splitlines())
    }
    cohort = read(root / "input/cohort.json")
    ids = [p["synthetic_person_id"] for p in cohort]
    training_ids = read(root / "previously-prompted-ids.json")
    predictions = {
        (
            r["metadata"]["synthetic_person_id"],
            r["metadata"]["arm"],
            r["metadata"]["repetition"],
        ): r["probabilities"]
        for r in rows
    }
    reps = contract["config"]["repetitions"]
    complete = [
        i for i in ids if all(predictions[i, a, r] is not None for a in ARMS for r in range(reps))
    ]
    metrics, baselines, stability, subgroups = [], [], [], []
    person_delta = np.full((len(complete), len(TARGETS)), np.nan)
    for task_index, (task, spec) in enumerate(TARGETS.items()):
        task_ids = [i for i in complete if targets[i][task] in spec["codes"]]
        y = [spec["codes"].index(targets[i][task]) for i in task_ids]
        w = [targets[i]["weight"] for i in task_ids]
        for arm in ARMS:
            # Average losses across repetitions; do not score an ensemble as a single agent.
            p = np.array([predictions[i, arm, r][task] for i in task_ids for r in range(reps)])
            result = metric(p, np.repeat(y, reps), np.repeat(w, reps))
            result.update(
                task=task,
                arm=arm,
                unique_respondents=len(task_ids),
                effective_respondent_n=float(np.sum(w) ** 2 / np.sum(np.array(w) ** 2)),
            )
            metrics.append(result)
            by_person = p.reshape(len(task_ids), reps, 3)
            stability.append(
                dict(
                    task=task,
                    arm=arm,
                    n=len(task_ids),
                    mean_repeat_tv=float(
                        np.mean(abs(by_person[:, 0] - by_person[:, 1]).sum(axis=1) / 2)
                    ),
                    modal_disagreement=float(
                        np.mean(by_person[:, 0].argmax(axis=1) != by_person[:, 1].argmax(axis=1))
                    ),
                )
            )
            for model_id in contract_model_ids(root):
                subset = [
                    j
                    for j, i in enumerate(task_ids)
                    if contract_model_ids(root)[ids.index(i) % 3] == model_id
                ]
                if subset:
                    subgroups.append(
                        dict(
                            task=task,
                            arm=arm,
                            model=model_id,
                            **metric(
                                by_person[subset].reshape(-1, 3),
                                np.repeat(np.array(y)[subset], reps),
                                np.repeat(np.array(w)[subset], reps),
                            ),
                        )
                    )
        for i in task_ids:
            truth = np.eye(3)[spec["codes"].index(targets[i][task])]
            losses = {
                a: np.mean(
                    [
                        0.5 * np.sum((np.array(predictions[i, a, r][task]) - truth) ** 2)
                        for r in range(reps)
                    ]
                )
                for a in ARMS
            }
            person_delta[complete.index(i), task_index] = losses["rich"] - losses["sparse"]
        train = [i for i in training_ids if i in targets and targets[i][task] in spec["codes"]]
        counts = np.ones(3)
        for i in train:
            counts[spec["codes"].index(targets[i][task])] += targets[i]["weight"]
        prior = counts / counts.sum()
        for kind in ["previous_cohort_prevalence", "party_smoothed_previous_cohort"]:
            probs = []
            for i in task_ids:
                count = 5 * prior.copy()
                if kind.startswith("party"):
                    party = profiles[i]["observed"]["pid_x"]["code"]
                    for t in train:
                        if profiles[t]["observed"]["pid_x"]["code"] == party:
                            count[spec["codes"].index(targets[t][task])] += targets[t]["weight"]
                probs.append(count / count.sum())
            baselines.append(
                dict(task=task, baseline=kind, training_n=len(train), **metric(probs, y, w))
            )
    contrast = bootstrap_contrast(person_delta, [targets[i]["weight"] for i in complete])
    config = contract["config"]
    gate = (
        contrast["macro_change"] <= -config["practical_improvement"]
        and max(contrast["task_changes"]) <= config["maximum_task_regression"]
        and contrast["macro_interval"][1] < 0
    )
    ledger = read(root / "spend_ledger.json")
    report = dict(
        scientific_result=False,
        run_id=root.name,
        metrics=metrics,
        paired_contrast=dict(task_order=list(TARGETS), **contrast),
        predeclared_development_gate_passed=bool(gate),
        gate_definition="Macro Brier improves >=.005, no task worsens >.01, "
        "and exploratory respondent-bootstrap macro interval excludes zero.",
        baselines=baselines,
        repeat_stability=stability,
        by_model=subgroups,
        complete_respondents=len(complete),
        reserved_respondents=50,
        missing_predictions=sum(r["probabilities"] is None for r in rows),
        requests=ledger["reserved_requests"],
        cost_usd=sum(
            (e.get("reported_usage") or {}).get("provider_cost_usd", 0) or 0
            for e in ledger["entries"]
        ),
        unreconciled_requests=sum(e.get("reported_usage") is None for e in ledger["entries"]),
        limitations=[
            "No power calculation; conditional respondent bootstrap, not complex survey.",
            "National weights are descriptive within Ohio; no state calibration.",
            "Previously unprompted cases, not guaranteed unseen in earlier retrospective analysis.",
            "Model assignments balanced but not crossed within respondents.",
            "Only three outcomes; policy items are retrospective imputation, not attitude change.",
            "Use effective_respondent_n for uncertainty; repeated rows are not independent.",
            "Host broker is trusted; remote provider inference is outside Docker.",
            "Reserve IDs excluded from calls; raw dataset previously existed on host.",
        ],
    )
    dump(root / "evaluation.json", report)
    dump(
        root / "evaluation-seal.json",
        seal(
            dict(
                report_sha256=_sha256_file(root / "evaluation.json"),
                boundary_sha256=_sha256_file(root / "prediction-boundary-seal.json"),
                targets_sha256=manifest["targets_sha256"],
                source_sha256=_sha256_file(Path(__file__)),
            )
        ),
    )
    print(json.dumps(report, indent=2))


def contract_model_ids(root):
    return [w["id"] for w in read(root / "input/workers.json")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["prepare", "run", "evaluate", "container-plan", "container-validate"]
    )
    parser.add_argument("--run-id", default=DEFAULT_ID)
    args = parser.parse_args()
    if args.phase.startswith("container-"):
        container_stage(args.phase.split("-")[1])
        return
    root = resolve("data/runs") / validate_run_id(args.run_id)
    if args.phase == "prepare":
        print(json.dumps(prepare(root), indent=2))
    elif args.phase == "run":
        execute(root)
    else:
        evaluate(root)


if __name__ == "__main__":
    main()
