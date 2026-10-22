"""Frozen independent/private/swarm/replay confirmation comparison, research only."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

from psbx import openrouter, spending
from psbx.agents.runner import complete_turn
from psbx.config import load_models
from psbx.env import load_dotenv
from psbx.experiments.anes_society import _canonical_json_sha256, _parse_llm_json, _sha256_file
from psbx.experiments.decision_profiles import check_seal, seal
from psbx.experiments.decision_profiles import dump as private_dump
from psbx.experiments.social_benchmark import docker_job, read, scores, validate_result, verify
from psbx.paths import resolve, validate_run_id
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

RUN_ID = "debate-social-comparison-20261022"
ARMS = ["direct", "private", "swarm", "replay"]


def dump(path, value):
    """Atomic durable checkpoint update; never expose half-written paid-call records."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    private_dump(temporary, value)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def configure_runtime(config):
    spending._LEDGER_MAX_BYTES = 4_000_000
    openrouter._MAX_429_RETRIES = 0
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD=str(config["max_usd"]),
        PSBX_MAX_PAID_REQUESTS=str(config["max_requests"]),
        OPENROUTER_MAX_PER_MINUTE="60",
        OPENROUTER_MIN_INTERVAL_SEC="1",
        OPENROUTER_MAX_CONCURRENCY="2",
    )


def prepare(root):
    if (root / "contract.json").exists():
        return verify(root)
    manifest = read(root / "cohort-manifest.json")
    provenance = {
        **manifest["source_bindings"],
        **{str(root / name): digest for name, digest in manifest["artifact_hashes"].items()},
    }
    for name, digest in provenance.items():
        if _sha256_file(Path(name)) != digest:
            raise ValueError("Cohort provenance changed: " + name)
    cases = read(root / "cases.json")
    groups = {c["group_id"] for c in cases}
    if len(groups) != 29 or len(cases) != 116:
        raise ValueError("Frozen cohort must contain 29 groups / 116 respondents")
    model = load_models()["openrouter-gpt-4.1-mini"]
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    catalog = next(r for r in response.json()["data"] if r["id"] == model.model_name)
    if "response_format" not in catalog["supported_parameters"]:
        raise ValueError("JSON unsupported")
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
    config = dict(
        run_id=root.name,
        groups=29,
        people=116,
        rounds=3,
        passes_per_round=2,
        runtime=dict(
            ledger_max_bytes=4_000_000,
            provider_internal_retries=0,
            rpm=60,
            min_interval_seconds=1,
            concurrency=2,
        ),
        repetitions=1,
        planned_calls=1856,
        max_requests=2000,
        max_usd=30,
        seed=20261022,
        primary="Group-clustered RPS: swarm minus development-selected statistical comparator",
        primary_comparator=manifest["selected_baseline"],
        meaningful_rps_improvement=0.01,
        success_rule="Exploratory signal requires primary delta <= -0.01 and CI upper < 0; "
        "no promotion without independent replication and broader fidelity review",
        secondary="swarm-direct, swarm-private, replay-direct; opinion shares and unchanged people",
        promotion="Exploratory; no automatic promotion",
        direct_worker_arm="private, empty history",
    )
    dump(root / "config.json", config)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "psbx-social-worker:local", "--format", "{{.Id}}"], text=True
    ).strip()
    probe = dict(profile=cases[0]["profile"], arm="private", stage="final", round=3, history=[])
    dump(root / "docker-probe.json", docker_job(probe, image)["isolation"])
    files = [
        root / n
        for n in [
            "cohort-manifest.json",
            "cases.json",
            "baseline-predictions.json",
            "baseline-fit.json",
            "worker.json",
            "catalog.json",
            "config.json",
            "docker-probe.json",
        ]
    ]
    files += [
        Path(__file__),
        Path(__file__).with_name("social_cohort.py"),
        Path(__file__).with_name("social_benchmark.py"),
        Path(__file__).with_name("social_worker.py"),
    ]
    files += [
        resolve(n)
        for n in [
            "src/psbx/openrouter.py",
            "src/psbx/agents/runner.py",
            "src/psbx/spending.py",
            "Dockerfile.social-worker",
            "config/behavior-event-budget.yaml",
        ]
    ]
    files += list(resolve("src/psbx").rglob("*.py"))
    contract = seal(
        dict(
            config=config,
            image_id=image,
            bindings={**provenance, **{str(p): _sha256_file(p) for p in files}},
            targets_path=manifest["targets_path"],
            targets_sha256=manifest["targets_sha256"],
            license="DEBATE Research-Only License (Non-Commercial v1.0); "
            "Chuang et al. arXiv:2510.25110",
            limitations="29 structurally admitted groups, one model and repetition. "
            "Historical model "
            "contamination not excluded. Replay conditions on real messages and is not a causal "
            "control. Host broker and remote inference are outside Docker. "
            "No population inference.",
        )
    )
    archive = root / "frozen-source"
    archive.mkdir(exist_ok=True)
    for p in files:
        if p.suffix == ".py" or p.name.startswith("Dockerfile"):
            destination = archive / p.relative_to(resolve("."))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(p.read_bytes())
    dump(root / "contract.json", contract)
    return contract


class Broker:
    """Durable per-attempt records; ambiguous provider calls block automatic resume."""

    def __init__(self, root, contract):
        self.root, self.contract = root, contract
        self.model = ModelConfig.model_validate(read(root / "worker.json"))
        self.directory = root / "checkpoints"
        self.directory.mkdir(exist_ok=True)
        self.directory.chmod(0o700)

    def call(self, payload, metadata):
        call_id = _canonical_json_sha256(metadata)
        path = self.directory / (call_id + ".json")
        fingerprint = _canonical_json_sha256(
            dict(payload=payload, worker=self.model.model_dump(mode="json"))
        )
        if path.exists():
            saved = read(path)
            if saved["fingerprint"] != fingerprint:
                raise ValueError("Resume payload changed")
            if saved["status"] != "completed":
                raise RuntimeError("Invalid checkpoint; review required")
            return saved["parsed"]
        raw, parsed = [], None
        for attempt in range(2):
            attempt_path = self.directory / (call_id + f".attempt-{attempt}.json")
            if attempt_path.exists():
                record = read(attempt_path)
                if record["fingerprint"] != fingerprint or record["status"] != "returned":
                    raise RuntimeError("Ambiguous provider attempt; reconcile before resume")
                raw.append(record["text"])
                job = record["job"]
            else:
                # Every paid attempt receives a freshly isolated worker.
                job = docker_job(payload, self.contract["image_id"])
                history = [dict(role="user", content=job["user"])]
                if raw:
                    history += [
                        dict(role="assistant", content=raw[-1]),
                        dict(
                            role="user",
                            content="Return the requested JSON schema; "
                            "probabilities must sum to one.",
                        ),
                    ]
                record = dict(
                    fingerprint=fingerprint, status="inflight", metadata=metadata, job=job
                )
                dump(attempt_path, record)
                turn = complete_turn(self.model, history, system=job["system"], tools=False)
                record.update(status="returned", text=turn.text)
                dump(attempt_path, record)
                raw.append(turn.text)
            try:
                parsed = validate_result(_parse_llm_json(raw[-1]), payload["stage"])
                break
            except (ValueError, TypeError, KeyError):
                pass
        dump(
            path,
            dict(
                metadata=metadata,
                fingerprint=fingerprint,
                payload=payload,
                isolation=job["isolation"],
                status="completed" if parsed is not None else "invalid_format",
                parsed=parsed,
                raw=raw,
                attempts=len(raw),
            ),
        )
        print(
            json.dumps(
                dict(
                    completed=len(
                        [p for p in self.directory.glob("*.json") if ".attempt-" not in p.name]
                    ),
                    group=metadata["group"],
                    arm=metadata["arm"],
                    stage=payload["stage"],
                )
            ),
            flush=True,
        )
        if parsed is None:
            raise RuntimeError("Invalid format after one repair; checkpoint preserved")
        return parsed


def batch_calls(broker, jobs):
    """Bounded parallel calls; return only once the synchronous pass completes."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(broker.call, payload, meta) for payload, meta in jobs]
        return [(meta, future.result()) for (_, meta), future in zip(jobs, futures)]


def run(root):
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run(root)


def _run(root):
    contract = verify(root)
    load_dotenv()
    config = contract["config"]
    configure_runtime(config)
    broker = Broker(root, contract)
    preflight = preflight_paid_requests([(broker.model, config["max_requests"])])
    if not (root / "preflight.json").exists():
        dump(root / "preflight.json", preflight)
    elif read(root / "preflight.json") != preflight:
        raise ValueError("Preflight changed")
    begin_spend_run(root.name)
    cases = read(root / "cases.json")
    predictions = []
    transcript = []
    rng = np.random.default_rng(config["seed"])
    for group in sorted({c["group_id"] for c in cases}):
        people = [c for c in cases if c["group_id"] == group]
        for arm in rng.permutation(ARMS):
            arm = str(arm)
            histories = {c["profile"]["agent_id"]: [] for c in people}
            if arm in ["private", "swarm"]:
                for round_ in range(1, 4):
                    for pass_ in range(2):
                        messages = {}
                        jobs = []
                        for c in people:
                            p = c["profile"]
                            agent = p["agent_id"]
                            payload = dict(
                                profile=p,
                                arm=arm,
                                stage="message",
                                round=round_,
                                history=list(histories[agent]),
                            )
                            meta = dict(
                                group=group,
                                agent=agent,
                                arm=arm,
                                stage="message",
                                round=round_,
                                pass_index=pass_,
                            )
                            jobs.append((payload, meta))
                        for meta, result in batch_calls(broker, jobs):
                            messages[meta["agent"]] = result["message"]
                            transcript.append({**meta, **result})
                        # Deliver only after all agents in this pass finish: no order advantage.
                        for c in people:
                            p = c["profile"]
                            agent = p["agent_id"]
                            histories[agent].append(
                                dict(
                                    speaker=agent,
                                    direction="private" if arm == "private" else "own",
                                    round=round_,
                                    text=messages[agent],
                                )
                            )
                            if arm == "swarm":
                                peer = p["partners"][str(round_)]
                                histories[agent].append(
                                    dict(
                                        speaker=peer,
                                        direction="received",
                                        round=round_,
                                        text=messages[peer],
                                    )
                                )
            jobs = []
            for c in people:
                p = c["profile"]
                agent = p["agent_id"]
                payload = dict(
                    profile=p,
                    arm="private" if arm == "direct" else arm,
                    stage="final",
                    round=3,
                    history=c["real_incoming"] if arm == "replay" else histories[agent],
                )
                meta = dict(group=group, agent=agent, arm=arm, stage="final", round=3, pass_index=0)
                jobs.append((payload, meta))
            for meta, result in batch_calls(broker, jobs):
                predictions.append({**meta, **result})
    verify(root)
    validate_coverage(cases, predictions)
    dump(root / "predictions.json", predictions)
    dump(root / "transcript.json", transcript)
    dump(
        root / "prediction-seal.json",
        seal(
            dict(
                contract_sha256=_sha256_file(root / "contract.json"),
                predictions_sha256=_sha256_file(root / "predictions.json"),
                transcript_sha256=_sha256_file(root / "transcript.json"),
                checkpoints={
                    p.name: _sha256_file(p) for p in (root / "checkpoints").glob("*.json")
                },
            )
        ),
    )


def validate_coverage(cases, predictions):
    expected = {(c["group_id"], c["profile"]["agent_id"], a) for c in cases for a in ARMS}
    actual = [(r["group"], r["agent"], r["arm"]) for r in predictions]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Unbalanced panel")
    for row in predictions:
        validate_result({"probabilities": row["probabilities"]}, "final")


def evaluate(root):
    contract = verify(root)
    ps = read(root / "prediction-seal.json")
    check_seal(ps)
    for key, name in [
        ("contract", "contract.json"),
        ("predictions", "predictions.json"),
        ("transcript", "transcript.json"),
    ]:
        if ps[key + "_sha256"] != _sha256_file(root / name):
            raise ValueError("Prediction binding changed")
    for name, digest in ps["checkpoints"].items():
        if _sha256_file(root / "checkpoints" / name) != digest:
            raise ValueError("Checkpoint changed")
    if _sha256_file(Path(contract["targets_path"])) != contract["targets_sha256"]:
        raise ValueError("Targets changed")
    labels = {r["agent_id"]: r for r in read(contract["targets_path"])}
    cases = read(root / "cases.json")
    predictions = read(root / "predictions.json")
    validate_coverage(cases, predictions)
    ids_expected = {c["profile"]["agent_id"]: c["group_id"] for c in cases}
    target_rows = read(contract["targets_path"])
    if len(target_rows) != len(ids_expected) or set(labels) != set(ids_expected):
        raise ValueError("Target coverage mismatch")
    if any(labels[i]["group_id"] != g for i, g in ids_expected.items()):
        raise ValueError("Target group mismatch")
    initial = np.array([c["profile"]["initial_score"] for c in cases])
    final = np.array([labels[c["profile"]["agent_id"]]["final_score"] for c in cases])
    lookup = {(r["agent"], r["arm"]): r["probabilities"] for r in predictions}
    ids = [c["profile"]["agent_id"] for c in cases]
    groups = [c["group_id"] for c in cases]
    summaries = []
    all_scores = {}
    group_results = []
    baseline = {r["agent_id"]: r["probabilities"] for r in read(root / "baseline-predictions.json")}
    if set(baseline) != set(ids):
        raise ValueError("Baseline coverage mismatch")
    for probabilities in baseline.values():
        validate_result({"probabilities": probabilities}, "final")
    for arm in ["persistence", "statistical"] + ARMS:
        p = (
            np.eye(6)[initial - 1]
            if arm == "persistence"
            else np.array([baseline[i] for i in ids])
            if arm == "statistical"
            else np.array([lookup[i, arm] for i in ids])
        )
        values = scores(p, initial, final)
        all_scores[arm] = values
        summaries.append(
            dict(
                arm=arm,
                n=len(cases),
                rps=float(values["rps"].mean()),
                expected_score_mae=float(values["mae"].mean()),
                direction_accuracy=float(values["direction"].mean()),
                answer_share_mae=float(
                    np.abs(p.mean(axis=0) - np.eye(6)[final - 1].mean(axis=0)).mean()
                ),
                predicted_no_change_probability=float(
                    p[np.arange(len(initial)), initial - 1].mean()
                ),
                predicted_mean_change=float((values["mean"] - initial).mean()),
                mean_absolute_predicted_change=float(values["movement"].mean()),
                false_movement_among_unchanged=float(
                    values["false_movement"].sum() / max(1, (final == initial).sum())
                ),
            )
        )
        for g in sorted(set(groups)):
            ix = [i for i, v in enumerate(groups) if v == g]
            human_var = float(np.var(final[ix]))
            predicted_var = float(np.var(values["mean"][ix]))
            group_results.append(
                dict(
                    group=g,
                    arm=arm,
                    topic=cases[ix[0]]["profile"]["topic"],
                    rps=float(values["rps"][ix].mean()),
                    human_initial_variance=float(np.var(initial[ix])),
                    human_final_variance=human_var,
                    predicted_variance_of_expected_scores=predicted_var,
                    absolute_dispersion_error=abs(predicted_var - human_var),
                )
            )
    for summary in summaries:
        summary["mean_absolute_group_dispersion_error"] = float(
            np.mean(
                [
                    r["absolute_dispersion_error"]
                    for r in group_results
                    if r["arm"] == summary["arm"]
                ]
            )
        )
    contrasts = []
    rng = np.random.default_rng(20261022)
    for before, after in [
        ("statistical", "swarm"),
        ("direct", "swarm"),
        ("private", "swarm"),
        ("direct", "replay"),
    ]:
        deltas = np.array(
            [
                np.mean(
                    [
                        all_scores[after]["rps"][i] - all_scores[before]["rps"][i]
                        for i, gid in enumerate(groups)
                        if gid == g
                    ]
                )
                for g in sorted(set(groups))
            ]
        )
        draws = rng.choice(deltas, size=(4000, len(deltas)), replace=True).mean(axis=1)
        contrasts.append(
            dict(
                before=before,
                after=after,
                group_mean_rps_change=float(deltas.mean()),
                group_bootstrap_95_interval=np.quantile(draws, [0.025, 0.975]).tolist(),
            )
        )
    ledger = read(root / "spend_ledger.json")
    report = dict(
        scientific_result=False,
        primary_comparator=contract["config"]["primary_comparator"],
        exploratory_primary_signal=bool(
            contrasts[0]["group_mean_rps_change"] <= -0.01
            and contrasts[0]["group_bootstrap_95_interval"][1] < 0
        ),
        automatic_promotion=False,
        license=contract["license"],
        groups=len(set(groups)),
        people=len(cases),
        topics=len({c["profile"]["topic"] for c in cases}),
        human_unchanged=int((final == initial).sum()),
        human_changed=int((final != initial).sum()),
        human_mean_change=float((final - initial).mean()),
        human_mean_absolute_change=float(abs(final - initial).mean()),
        metrics=summaries,
        contrasts=contrasts,
        group_results=group_results,
        provider_requests=ledger["reserved_requests"],
        provider_reported_cost_usd=sum(
            (e.get("reported_usage") or {}).get("provider_cost_usd", 0) or 0
            for e in ledger["entries"]
        ),
        unresolved_usage=sum(e.get("reported_usage") is None for e in ledger["entries"]),
        limitation=contract["limitations"],
        inference="Exploratory group bootstrap with 29 admitted groups across chosen topics; "
        "conditional on fitted baseline and one simulation; "
        "no population or causal claim. Prediction probabilities do not define a joint "
        "group distribution; dispersion of expected scores can reflect uncertainty.",
        no_change_rule="Persistence predicts each initial score exactly; no model call or fitting.",
    )
    dump(root / "evaluation.json", report)
    dump(
        root / "evaluation-seal.json",
        seal(
            dict(
                report_sha256=_sha256_file(root / "evaluation.json"),
                prediction_seal_sha256=_sha256_file(root / "prediction-seal.json"),
                targets_sha256=contract["targets_sha256"],
            )
        ),
    )
    rows = [
        "# DEBATE social comparison",
        "",
        "Exploratory held-out groups; one model and repetition.",
        "",
        "| Arm | RPS | Expected-score MAE | Direction accuracy |",
        "|---|---:|---:|---:|",
    ]
    for m in summaries:
        rows.append(
            f"| {m['arm']} | {m['rps']:.6f} | {m['expected_score_mae']:.4f} "
            f"| {m['direction_accuracy']:.3f} |"
        )
    rows += [
        "",
        "Primary contrast: swarm minus development-selected statistical comparator; "
        "lower is better.",
        json.dumps(contrasts, indent=2),
        "",
        report["inference"],
        "",
        contract["limitations"],
    ]
    (root / "RESULTS.md").write_text("\n".join(rows) + "\n")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "run", "evaluate"])
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args()
    root = resolve("data/runs") / validate_run_id(args.run_id)
    if args.phase == "prepare":
        print(json.dumps(prepare(root), indent=2))
    elif args.phase == "run":
        run(root)
    else:
        evaluate(root)


if __name__ == "__main__":
    main()
