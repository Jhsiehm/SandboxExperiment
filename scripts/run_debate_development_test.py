"""One-group development comparison. Never admits or consumes reserve cohorts."""

import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import subprocess

import httpx
import numpy as np

from psbx import openrouter
from psbx.config import load_models
from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import seal, check_seal
from psbx.experiments.social_benchmark import parse_group, read, scores, verify, docker_job
from psbx.experiments.social_confirmation import Broker, dump
from psbx.experiments.telemetry import observed_run, observe
from psbx.paths import repo_root, run_dir
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

RUN_ID = "debate-development-comparison-20261023"
ARMS = ["direct", "private", "swarm"]


def runtime():
    openrouter._MAX_429_RETRIES = 0
    os.environ.update(PSBX_ENABLE_PAID_MODELS="1", PSBX_MOCK_LLM="0",
                      PSBX_MAX_PAID_REQUESTS="72", PSBX_MAX_RUN_USD="0.50",
                      PSBX_MAX_REQUEST_USD="0.02", OPENROUTER_MAX_CONCURRENCY="1",
                      OPENROUTER_MIN_INTERVAL_SEC="2", OPENROUTER_MAX_PER_MINUTE="20")


def prepare(root):
    if (root / "contract.json").exists():
        return verify(root)
    base = repo_root()
    source = base / "experiments/debate-sft-replication"
    manifest = read(source / "inputs/manifest.json")
    audit = read(source / "preparation-audit.json")
    groups = [g for g in manifest["groups"]
              if g["partition"] == "train" and g["group_id"] in audit["per_group"]]
    selected = groups[0]  # Frozen metadata order; same group as the prior API smoke.
    inputs = []
    def load(g):
        path = source / "inputs" / (g["group_id"] + ".csv")
        assert _sha256_file(path) == g["sha256"]
        inputs.append(path)
        with path.open() as stream:
            return parse_group(list(csv.DictReader(stream)), g["topic"], g["group_id"])
    cases, targets = load(selected)
    for c in cases:
        c.pop("real_incoming")  # No real later messages in forecast arms.
    counts = np.ones((6, 6))  # Fixed Laplace-one transition; no tuning.
    fitted, excluded = [], {}
    for g in groups[1:]:
        if g["topic"] == selected["topic"]:
            continue
        try:
            training, labels = load(g)
        except ValueError as exc:
            excluded[g["group_id"]] = str(exc)
            continue
        truth = {r["agent_id"]: r["final_score"] for r in labels}
        for c in training:
            counts[c["profile"]["initial_score"] - 1, truth[c["profile"]["agent_id"]] - 1] += 1
        fitted.append(g["group_id"])
    assert fitted and selected["group_id"] not in fitted
    transition = counts / counts.sum(axis=1, keepdims=True)
    vault = base / "data/evaluation-vault" / root.name
    vault.mkdir(parents=True, exist_ok=True)
    vault.chmod(0o700)
    dump(vault / "targets.json", targets)
    dump(root / "cases.json", cases)
    dump(root / "baseline.json", dict(fit_groups=fitted, excluded=excluded,
         method="fixed Laplace-one P(final|initial), excluding selected group and topic",
         participant_overlap_audited=False, probabilities=transition.tolist()))
    catalog_response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    catalog_response.raise_for_status()
    catalog = next(x for x in catalog_response.json()["data"] if x["id"] == "openai/gpt-4.1-mini")
    model = load_models()["openrouter-gpt-4.1-mini"].model_copy(update=dict(
        temperature=.4, max_tokens=256, json_output=True,
        cost_per_1k_input=float(catalog["pricing"]["prompt"]) * 1000,
        cost_per_1k_output=float(catalog["pricing"]["completion"]) * 1000))
    dump(root / "worker.json", model.model_dump(mode="json"))
    dump(root / "catalog.json", catalog)
    image = subprocess.check_output(["docker", "image", "inspect", "psbx-social-worker:local",
                                     "--format", "{{.Id}}"], text=True).strip()
    probe = docker_job(dict(profile=cases[0]["profile"], arm="private", stage="final",
                            round=3, history=[]), image)
    dump(root / "docker-probe.json", probe["isolation"])
    runtime()
    dump(root / "preflight.json", preflight_paid_requests([(model, 72)]))
    bound = inputs + [Path(__file__), source / "inputs/manifest.json", source / "preparation-audit.json"]
    bound += list((base / "src/psbx").rglob("*.py"))
    bound += [root / name for name in ["cases.json", "baseline.json", "worker.json", "catalog.json"]]
    contract = seal(dict(
        purpose="development comparison only; four previously inspected people, one group",
        arms=ARMS, planned_calls=60, max_requests=72, max_usd=.5,
        repair_policy="one format repair per job, all attempts charged to shared 72-call ceiling",
        seed=20261023, rounds=3, passes_per_round=2, image_id=image,
        primary_metric="mean ranked probability score; descriptive only",
        limitations="No independent evaluation, no population inference or confidence intervals. "
        "Recorded contact schedule assumed known. No actual human messages in prompts. "
        "Statistical baseline participant overlap not audited. Not a base-versus-SFT comparison.",
        targets_path=str(vault / "targets.json"), targets_sha256=_sha256_file(vault / "targets.json"),
        bindings={str(p): _sha256_file(p) for p in bound}))
    dump(root / "contract.json", contract)
    print("Prepared 4-person, 60-call development test; max 72 requests / $0.50", flush=True)


@observed_run(study_id="debate")
def run(root):
    contract = verify(root)
    runtime()
    begin_spend_run(root.name)
    broker = Broker(root, contract)
    people = read(root / "cases.json")
    predictions, transcript = [], []
    order = np.random.default_rng(contract["seed"]).permutation(ARMS)
    for arm in order:
        arm = str(arm)
        histories = {c["profile"]["agent_id"]: [] for c in people}
        if arm in ["private", "swarm"]:
            for round_ in range(1, 4):
                for pass_ in range(2):
                    messages = {}
                    for c in people:
                        p = c["profile"]
                        meta = dict(group=c["group_id"], agent=p["agent_id"], arm=arm,
                                    stage="message", round=round_, pass_index=pass_)
                        payload = dict(profile=p, arm=arm, stage="message", round=round_,
                                       history=list(histories[p["agent_id"]]))
                        observe("model_requested", agent_key=p["agent_id"], phase="message")
                        result = broker.call(payload, meta)
                        messages[p["agent_id"]] = result["message"]
                        transcript.append({**meta, **result})
                    for c in people:
                        p = c["profile"]
                        agent = p["agent_id"]
                        histories[agent].append(dict(speaker=agent,
                            direction="private" if arm == "private" else "own",
                            round=round_, text=messages[agent]))
                        if arm == "swarm":
                            peer = p["partners"][str(round_)]
                            histories[agent].append(dict(speaker=peer, direction="received",
                                                         round=round_, text=messages[peer]))
        for c in people:
            p = c["profile"]
            meta = dict(group=c["group_id"], agent=p["agent_id"], arm=arm,
                        stage="final", round=3, pass_index=0)
            payload = dict(profile=p, arm="private" if arm == "direct" else arm,
                           stage="final", round=3, history=histories[p["agent_id"]])
            result = broker.call(payload, meta)
            predictions.append({**meta, **result})
    verify(root)
    assert len(predictions) == 12 and len(transcript) == 48
    dump(root / "predictions.json", predictions)
    dump(root / "transcript.json", transcript)
    dump(root / "prediction-seal.json", seal(dict(bindings={
        str(p): _sha256_file(p) for p in [root / "contract.json", root / "predictions.json",
        root / "transcript.json", *sorted((root / "checkpoints").glob("*.json"))]})))


def evaluate(root):
    contract = verify(root)
    sealed = read(root / "prediction-seal.json")
    check_seal(sealed)
    for path, digest in sealed["bindings"].items():
        assert _sha256_file(Path(path)) == digest
    assert _sha256_file(Path(contract["targets_path"])) == contract["targets_sha256"]
    people = read(root / "cases.json")
    labels = {r["agent_id"]: r["final_score"] for r in read(contract["targets_path"])}
    ids = [c["profile"]["agent_id"] for c in people]
    initial = np.array([c["profile"]["initial_score"] for c in people])
    final = np.array([labels[i] for i in ids])
    lookup = {(r["agent"], r["arm"]): r["probabilities"] for r in read(root / "predictions.json")}
    baseline = np.array(read(root / "baseline.json")["probabilities"])
    report = []
    for arm in ["persistence", "transition"] + ARMS:
        probs = (np.eye(6)[initial - 1] if arm == "persistence" else
                 baseline[initial - 1] if arm == "transition" else
                 np.array([lookup[i, arm] for i in ids]))
        values = scores(probs, initial, final)
        report.append(dict(arm=arm, n=4, rps=float(values["rps"].mean()),
                           expected_rating_mae=float(values["mae"].mean())))
    ledger = read(root / "spend_ledger.json")
    costs = [e.get("reported_usage", {}).get("provider_cost_usd") for e in ledger["entries"]]
    result = dict(status="completed", scope="single-group development diagnostic only",
                  comparisons=report, requests=ledger["reserved_requests"],
                  provider_reported_usd=sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None,
                  limitations=contract["limitations"])
    dump(root / "evaluation.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "run", "evaluate"])
    parser.add_argument("--credentials", type=Path)
    args = parser.parse_args()
    if args.credentials:
        for line in args.credentials.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    root = run_dir(RUN_ID)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {"prepare": prepare, "run": run, "evaluate": evaluate}[args.phase](root)
