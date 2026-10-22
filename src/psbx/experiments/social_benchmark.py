"""Research-only DEBATE pilot: matched reflection versus isolated interacting agents.

Dataset: Chuang et al., DEBATE, arXiv:2510.25110. Research-only license applies
also to derivatives. No ANES reserve, dataset final opinion or exit survey enters prompts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

import httpx
import numpy as np

from psbx.agents.runner import complete_turn
from psbx.config import load_models
from psbx.env import load_dotenv
from psbx.experiments.anes_society import _canonical_json_sha256, _parse_llm_json, _sha256_file
from psbx.experiments.decision_experiment import readiness
from psbx.experiments.decision_profiles import check_seal, dump, seal
from psbx.experiments.social_worker import build_prompt
from psbx.experiments.telemetry import observe, observed_run
from psbx.paths import resolve, validate_run_id
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

RUN_ID = "debate-isolated-social-pilot-20261014"
ARMS = ["private", "swarm", "replay"]


def read(path):
    return json.loads(Path(path).read_text())


def rating(row):
    try:
        x = float(row["sliderValue"])
    except (ValueError, TypeError):
        return None
    return int(x) if x.is_integer() and 1 <= x <= 6 else None


def parse_group(rows, topic, group_id):
    """Separate future labels; use initial statements and explicit directed message edges only."""
    initial = [r for r in rows if r["event_type"] == "Initial Opinion"]
    if len(initial) != 4 or len({r["worker_id"] for r in initial}) != 4:
        raise ValueError("Expected four unique initial respondents")
    mapping = {r["worker_id"]: f"{group_id}p{i}" for i, r in enumerate(initial)}
    cases, targets = [], []
    for row in initial:
        raw_id = row["worker_id"]
        agent = mapping[raw_id]
        if rating(row) is None or not row["text"].strip():
            raise ValueError("Incomplete initial opinion")
        posts = [
            r
            for r in rows
            if r["event_type"] == "Post Opinion"
            and r["worker_id"] == raw_id
            and rating(r) is not None
        ]
        if not posts:
            raise ValueError("Missing final score")
        # Deterministic rule: last numeric post event, including repeated submission exports.
        post = sorted(posts, key=lambda r: float(r["event_order"]))[-1]
        partners, incoming = {}, []
        for round_ in range(1, 4):
            sent = [
                r
                for r in rows
                if r["event_type"] == "message_sent" and r["chat_round_order"] == f"{round_}.0"
            ]
            contacts = {r["recipient_id"] for r in sent if r["sender_id"] == raw_id}
            if len(contacts) != 1 or next(iter(contacts)) not in mapping:
                raise ValueError("Ambiguous partner schedule")
            partners[str(round_)] = mapping[next(iter(contacts))]
            for message in sorted(sent, key=lambda r: float(r["event_order"])):
                if message["recipient_id"] == raw_id and message["text"].strip():
                    incoming.append(
                        dict(
                            speaker=mapping[message["sender_id"]],
                            direction="received",
                            round=round_,
                            text=message["text"],
                        )
                    )
        if len(set(partners.values())) != 3 or agent in partners.values():
            raise ValueError("Expected three distinct other partners")
        profile = dict(
            agent_id=agent,
            topic=topic,
            initial_score=rating(row),
            initial_text=row["text"],
            partners=partners,
        )
        cases.append(dict(group_id=group_id, profile=profile, real_incoming=incoming))
        targets.append(
            dict(
                group_id=group_id,
                agent_id=agent,
                final_score=rating(post),
                numeric_post_records=len(posts),
            )
        )
    for case in cases:
        for round_, peer in case["profile"]["partners"].items():
            other = next(x for x in cases if x["profile"]["agent_id"] == peer)
            if other["profile"]["partners"][round_] != case["profile"]["agent_id"]:
                raise ValueError("Asymmetric pairing")
    return cases, targets


def validate_result(value, stage):
    if stage == "message":
        if set(value) != {"message"} or not isinstance(value["message"], str):
            raise ValueError("Expected one message string")
        if len(value["message"]) > 4000:
            raise ValueError("Message exceeds limit")
        return value
    if set(value) != {"probabilities"}:
        raise ValueError("Expected six probabilities")
    p = np.asarray(value["probabilities"], dtype=float)
    if (
        p.shape != (6,)
        or not np.isfinite(p).all()
        or (p < 0).any()
        or (p > 1).any()
        or abs(p.sum() - 1) > 0.02
    ):
        raise ValueError("Invalid probability vector")
    return {"probabilities": (p / p.sum()).tolist()}


def docker_job(payload, image):
    command = [
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
    result = subprocess.run(
        command, input=json.dumps(payload), text=True, capture_output=True, timeout=30, check=True
    )
    job = json.loads(result.stdout)
    expected = build_prompt(payload)
    if any(job[k] != expected[k] for k in expected):
        raise ValueError("Host/container prompt mismatch")
    return job


def verify(root):
    contract = read(root / "contract.json")
    check_seal(contract)
    for name, digest in contract["bindings"].items():
        if _sha256_file(Path(name)) != digest:
            raise ValueError("Contract bound input changed: " + name)
    return contract


def prepare(root):
    if (root / "contract.json").exists():
        return verify(root)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    source = resolve("data/corpus-cache/debate-20261014")
    cases, targets = [], []
    source_files = [source / "LICENSE", source / "README.md", source / "revision.txt"]
    for index in range(8):
        meta = read(source / f"{index}.source.json")
        with (source / f"{index}.csv").open() as handle:
            group, labels = parse_group(list(csv.DictReader(handle)), meta["topic"], f"g{index}")
        cases += group
        targets += labels
        source_files += [source / f"{index}.csv", source / f"{index}.source.json"]
    dump(root / "cases.json", cases)
    vault = resolve("data/evaluation-vault") / root.name
    vault.mkdir(parents=True, exist_ok=True)
    vault.chmod(0o700)
    dump(vault / "targets.json", targets)
    defaults = load_models()
    model = defaults["openrouter-gpt-4.1-mini"]
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
        groups=8,
        people=32,
        rounds=3,
        passes_per_round=2,
        repetitions=1,
        planned_calls=480,
        max_requests=1000,
        max_usd=5,
        seed=20261014,
        primary="Group-clustered mean ranked probability score, swarm minus private",
        secondary=[
            "ordinal MAE",
            "signed-change error",
            "change-direction accuracy",
            "false movement",
            "group dispersion error",
            "persistence baseline",
        ],
        promotion="No automatic promotion from this eight-group convenience pilot",
        topic_selection="Four topics; first two lexicographic golden files each",
        profile="Initial private score and explanation only; no exit-survey demographic data",
        design="Two synchronous message passes per recorded dyadic round; shorter than human chat. "
        "Replay contains only real incoming chat messages, no human post statements/ratings.",
    )
    dump(root / "config.json", config)
    image = subprocess.check_output(
        ["docker", "image", "inspect", "psbx-social-worker:local", "--format", "{{.Id}}"], text=True
    ).strip()
    probe = dict(profile=cases[0]["profile"], arm="private", stage="final", round=3, history=[])
    dump(root / "docker-probe.json", docker_job(probe, image)["isolation"])
    files = source_files + [
        root / "cases.json",
        root / "config.json",
        root / "worker.json",
        root / "catalog.json",
        Path(__file__),
        Path(__file__).with_name("social_worker.py"),
        resolve("src/psbx/openrouter.py"),
        resolve("src/psbx/agents/runner.py"),
        resolve("src/psbx/spending.py"),
        resolve("Dockerfile.social-worker"),
    ]
    contract = seal(
        dict(
            config=config,
            image_id=image,
            bindings={str(p): _sha256_file(p) for p in files},
            targets_path=str(vault / "targets.json"),
            targets_sha256=_sha256_file(vault / "targets.json"),
            dataset_revision=(source / "revision.txt").read_text(),
            license="DEBATE Research-Only License (Non-Commercial v1.0); "
            "Chuang et al. arXiv:2510.25110",
            limitations="Not ANES or a full DEBATE replication. One model and seed, eight groups. "
            "Real incoming messages are a conditional diagnostic, not a causal control. "
            "Host broker is trusted; remote inference is outside Docker. "
            "No claim of temporal decontamination.",
        )
    )
    dump(root / "contract.json", contract)
    # Exact source archive; original bound files remain unchanged for earlier studies.
    archive = root / "frozen-source"
    archive.mkdir(exist_ok=True)
    for p in files:
        if p.suffix == ".py" or p.name.startswith("Dockerfile"):
            destination = archive / p.name
            destination.write_bytes(p.read_bytes())
            destination.chmod(0o600)
    return contract


class Broker:
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
                raise RuntimeError("Persisted invalid result; do not retry")
            return saved["parsed"]
        actor = (metadata.get("group"), metadata.get("agent"))
        observe("agent_started", agent_key=actor, phase=payload["stage"])
        job = docker_job(payload, self.contract["image_id"])
        history = [dict(role="user", content=job["user"])]
        raw = []
        parsed = None
        for attempt in range(2):
            try:
                observe("model_requested", agent_key=actor, phase=payload["stage"])
                turn = complete_turn(self.model, history, system=job["system"], tools=False)
                observe("response_received", agent_key=actor, phase=payload["stage"])
            except Exception as exc:
                # Sequential execution surfaces failure immediately, without worker joins.
                failure = self.root / "provider-failures.jsonl"
                with failure.open("a") as handle:
                    handle.write(
                        json.dumps(
                            dict(
                                call_id=call_id,
                                metadata=metadata,
                                exception_type=type(exc).__name__,
                                status="provider_failure",
                            )
                        )
                        + "\n"
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                failure.chmod(0o600)
                raise
            raw.append(turn.text)
            try:
                parsed = validate_result(_parse_llm_json(turn.text), payload["stage"])
                break
            except (ValueError, TypeError, KeyError):
                history += [
                    dict(role="assistant", content=turn.text),
                    dict(
                        role="user",
                        content="Return the requested JSON schema; probabilities must sum to one.",
                    ),
                ]
        dump(
            path,
            dict(
                metadata=metadata,
                fingerprint=fingerprint,
                payload=payload,
                prompt_sha256=_canonical_json_sha256({k: job[k] for k in ["system", "user"]}),
                isolation=job["isolation"],
                status="completed" if parsed is not None else "invalid_format",
                parsed=parsed,
                raw=raw,
                attempts=attempt + 1,
            ),
        )
        observe("checkpoint_saved", agent_key=actor, phase=payload["stage"])
        print(
            json.dumps(
                dict(
                    completed=len(list(self.directory.glob("*.json"))),
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


@observed_run(study_id="debate")
def run(root):
    contract = verify(root)
    load_dotenv()
    readiness(root)
    config = contract["config"]
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD=str(config["max_usd"]),
        PSBX_MAX_PAID_REQUESTS=str(config["max_requests"]),
    )
    broker = Broker(root, contract)
    dump(root / "preflight.json", preflight_paid_requests([(broker.model, 960)]))
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
                            result = broker.call(payload, meta)
                            messages[agent] = result["message"]
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
                                observe("message_sent", agent_key=(group, peer), phase="message")
            for c in people:
                p = c["profile"]
                agent = p["agent_id"]
                payload = dict(
                    profile=p,
                    arm=arm,
                    stage="final",
                    round=3,
                    history=c["real_incoming"] if arm == "replay" else histories[agent],
                )
                meta = dict(group=group, agent=agent, arm=arm, stage="final", round=3, pass_index=0)
                result = broker.call(payload, meta)
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


def scores(p, initial, final):
    p = np.asarray(p, float)
    initial = np.asarray(initial)
    final = np.asarray(final)
    expected = p @ np.arange(1, 7)
    truth = np.eye(6)[final.astype(int) - 1]
    rps = ((p.cumsum(axis=1)[:, :-1] - truth.cumsum(axis=1)[:, :-1]) ** 2).mean(axis=1)
    # Use nearest category for direction; expected-score error remains continuous.
    modal = p.argmax(axis=1) + 1
    return dict(
        rps=rps,
        mae=np.abs(expected - final),
        mean=expected,
        direction=(np.sign(modal - initial) == np.sign(final - initial)).astype(float),
        movement=np.abs(expected - initial),
        false_movement=((modal != initial) & (final == initial)).astype(float),
    )


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
    initial = np.array([c["profile"]["initial_score"] for c in cases])
    final = np.array([labels[c["profile"]["agent_id"]]["final_score"] for c in cases])
    lookup = {(r["agent"], r["arm"]): r["probabilities"] for r in predictions}
    ids = [c["profile"]["agent_id"] for c in cases]
    groups = [c["group_id"] for c in cases]
    summaries = []
    all_scores = {}
    group_results = []
    for arm in ["persistence"] + ARMS:
        p = (
            np.eye(6)[initial - 1]
            if arm == "persistence"
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
    rng = np.random.default_rng(20261014)
    for before, after in [("private", "swarm"), ("persistence", "swarm"), ("private", "replay")]:
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
        inference="Exploratory group bootstrap with only eight groups across four chosen topics; "
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
