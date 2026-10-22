"""Matched profile × historical-context benchmark with a separate social pilot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import numpy as np

from psbx.agents.runner import complete_turn
from psbx.config import load_models, load_yaml
from psbx.env import load_dotenv
from psbx.experiments.anes_society import (
    _append_jsonl_durable,
    _canonical_json_sha256,
    _parse_llm_json,
    _sha256_file,
)
from psbx.experiments.decision_profiles import (
    TARGETS,
    check_seal,
    choose_cohort,
    dump,
    load_pack,
    prepare_profiles,
    previously_prompted,
    profile_text,
    seal,
    write_private,
)
from psbx.paths import resolve, validate_run_id
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests

ARMS = {
    "sparse_no_evidence": (False, False),
    "sparse_evidence": (False, True),
    "rich_no_evidence": (True, False),
    "rich_evidence": (True, True),
}
SYSTEM = (
    "Emulate a de-identified ANES 2012 respondent for aggregate research. Use only "
    "the supplied measured profile and permitted historical context. Missing attributes "
    "are unknown; do not fabricate a biography, memories, news exposure, or social ties. "
    "Do not use later events or known election results. Demographics do not determine "
    "opinions. Do not browse or use tools. Do not expose reasoning. Return JSON only."
)
TASK = "\n".join(
    f"{k}: {v['task']}. Probability array order: {v['options']}." for k, v in TARGETS.items()
)
TASK += (
    "\nReturn exactly an object with vote, health_law, and gun_policy keys. Each value "
    "is an array of three probabilities in the stated order, summing to 1. "
    "Represent uncertainty rather than forcing a certain choice. "
    "The two pre-election attitudes are held-out survey items; do not claim they "
    "are opinions observed after a simulated conversation."
)


def validate_probabilities(payload):
    if set(payload) != set(TARGETS):
        raise ValueError("Expected exactly three target distributions")
    result = {}
    for key in TARGETS:
        values = np.asarray(payload[key], dtype=float)
        if (
            values.shape != (3,)
            or not np.isfinite(values).all()
            or (values < 0).any()
            or (values > 1).any()
            or abs(values.sum() - 1) > 0.02
        ):
            raise ValueError("Invalid probability distribution")
        result[key] = (values / values.sum()).tolist()
    return result


def readiness(root):
    result = {}
    for endpoint in ["auth/key", "credits"]:
        response = httpx.get(
            "https://openrouter.ai/api/v1/" + endpoint,
            headers={"Authorization": "Bearer " + os.environ.get("OPENROUTER_API_KEY", "")},
            timeout=30,
        )
        result[endpoint] = {"status": response.status_code}
        if response.status_code == 200:
            d = response.json()["data"]
            result[endpoint].update(
                {k: d[k] for k in ["limit_remaining", "total_credits", "total_usage"] if k in d}
            )
    dump(root / "readiness.json", result)
    if any(item["status"] != 200 for item in result.values()):
        raise RuntimeError("Provider authentication failed")
    return result


def prepare(config):
    root = resolve("data/runs") / validate_run_id(config["run_id"])
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    pack_source = resolve("config/anes2012-historical-pack.json")
    load_pack(pack_source)
    frozen_pack = root / "evidence-pack.json"
    if not frozen_pack.exists():
        write_private(frozen_pack, pack_source.read_text())
    manifest = prepare_profiles(
        root,
        resolve("data/survey-microdata/anes/2012/source/anes_timeseries_2012.dta"),
        frozen_pack,
    )
    contract_path = root / "contract.json"
    if contract_path.exists():
        contract = json.loads(contract_path.read_text())
        check_seal(contract)
        if _canonical_json_sha256(contract["config"]) != _canonical_json_sha256(config):
            raise ValueError("Configuration changed; use a new run ID")
        for key, path in contract["bound_files"].items():
            if _sha256_file(resolve(path)) != contract["bound_hashes"][key]:
                raise ValueError(f"Bound input changed: {key}")
        return root, contract
    profiles = [json.loads(x) for x in (root / "profiles.jsonl").read_text().splitlines()]
    seen = previously_prompted(resolve("data/runs"))
    cohort = choose_cohort(
        profiles,
        seen,
        config["state_fips"],
        config["sample_n"],
        config["seed"],
        json.loads(frozen_pack.read_text())["cutoff"],
    )
    dump(root / "cohort.json", cohort)
    dump(root / "previously-prompted-ids.json", sorted(seen))
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    catalog = {row["id"]: row for row in response.json()["data"]}
    defaults = load_models()
    workers, selected = [], {}
    for model_id in config["models"]:
        model = defaults[model_id]
        row = catalog[model.model_name]
        if "response_format" not in row["supported_parameters"]:
            raise ValueError("JSON output mode not supported")
        price = row["pricing"]
        selected[model.model_name] = {
            "pricing": price,
            "supported_parameters": row["supported_parameters"],
        }
        workers.append(
            model.model_copy(
                update={
                    "max_tokens": 256,
                    "temperature": 0.4,
                    "json_output": True,
                    "cost_per_1k_input": float(price["prompt"]) * 1000,
                    "cost_per_1k_output": float(price["completion"]) * 1000,
                }
            ).model_dump(mode="json")
        )
    dump(root / "workers.json", workers)
    dump(root / "catalog-selection.json", selected)
    files = {
        "profiles": root / "profiles.jsonl",
        "profile_seal": root / "profile-seal.json",
        "audit": root / "field-audit.json",
        "cohort": root / "cohort.json",
        "exclusions": root / "previously-prompted-ids.json",
        "workers": root / "workers.json",
        "catalog": root / "catalog-selection.json",
        "evidence": frozen_pack,
        "runner_source": Path(__file__),
        "profile_source": Path(__file__).with_name("decision_profiles.py"),
        "provider_source": resolve("src/psbx/openrouter.py"),
        "model_runner_source": resolve("src/psbx/agents/runner.py"),
    }
    contract = seal(
        {
            "config": config,
            "profile_count": manifest["n_profiles"],
            "n_previously_prompted_excluded": len(seen),
            "system_sha256": _canonical_json_sha256(SYSTEM),
            "task_sha256": _canonical_json_sha256(TASK),
            "bound_files": {k: str(p) for k, p in files.items()},
            "bound_hashes": {k: _sha256_file(p) for k, p in files.items()},
            "design": "Independent 2x2 profile richness x historical context, matched "
            "respondents/models, two stochastic repeats. Social pilot "
            "predefined separately on first 12 cohort members; no winner selection.",
            "limitations": "Small development pilot; national survey weights in state "
            "subset; modern model weights; no proof of personal exposure. "
            "Pre-election policy outcomes are retrospective item imputation.",
        }
    )
    dump(contract_path, contract)
    return root, contract


def context(profile, rich, evidence, pack):
    text = f"Your pre-election interview baseline date: {profile['baseline_date']}.\n"
    text += profile_text(profile, rich) + "\n" + profile["uncertainty"]
    if evidence:
        text += (
            "\nHistorically available background experimentally supplied to you. "
            "We do not know whether you originally encountered or trusted it.\n"
        )
        for doc in pack["documents"]:
            if doc["published_at"] > profile["baseline_date"]:
                raise ValueError("Evidence is later than respondent baseline")
            text += f"{doc['published_at']} | {doc['title']}: {doc['text']}\n"
    else:
        text += "\nNo external historical evidence is supplied."
    return text


class Calls:
    def __init__(self, root):
        self.path = root / "call-checkpoints.jsonl"
        self.saved = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                row = json.loads(line)
                self.saved[row["call_id"]] = row

    def call(self, model, user, metadata, message=False):
        call_id = _canonical_json_sha256(metadata)
        fingerprint = _canonical_json_sha256(
            {"system": SYSTEM, "user": user, "model": model.model_dump(mode="json")}
        )
        if call_id in self.saved:
            prior = self.saved[call_id]
            if prior["request_sha256"] != fingerprint:
                raise ValueError("Resume prompt/model mismatch")
            return prior["parsed"]  # Failed JSON remains missing; never rerun until success.
        history = [{"role": "user", "content": user}]
        parsed, raw, error = None, [], None
        for attempt in range(2):
            turn = complete_turn(model, history, system=SYSTEM, tools=False)
            raw.append(turn.text)
            try:
                value = _parse_llm_json(turn.text)
                if message:
                    if not isinstance(value.get("message"), str):
                        raise ValueError("Missing text message")
                    parsed = {"message": " ".join(value["message"].split()[:35])}
                else:
                    parsed = validate_probabilities(value)
                error = None
                break
            except (ValueError, TypeError, KeyError) as exc:
                error = str(exc)
                history += [
                    {"role": "assistant", "content": turn.text},
                    {
                        "role": "user",
                        "content": "Return only the requested JSON. "
                        "Three probabilities per question must sum to 1; no prose."
                        if not message
                        else 'Return only {"message":"brief text"}.',
                    },
                ]
        row = {
            "call_id": call_id,
            **metadata,
            "request_sha256": fingerprint,
            "status": "completed" if parsed is not None else "invalid_format",
            "parsed": parsed,
            "raw_response": raw,
            "attempts": attempt + 1,
            "error": error,
        }
        _append_jsonl_durable(self.path, row)
        self.path.chmod(0o600)
        self.saved[call_id] = row
        print(
            json.dumps(
                {"checkpoint": len(self.saved), "phase": metadata["phase"], "status": row["status"]}
            ),
            flush=True,
        )
        return parsed


def save_predictions(root, phase, rows):
    path = root / f"{phase}-predictions.json"
    dump(path, rows)
    artifacts = {}
    checkpoints = root / "call-checkpoints.jsonl"
    if checkpoints.exists():
        snapshot = root / f"{phase}-checkpoints.jsonl"
        write_private(snapshot, checkpoints.read_text())
        artifacts[snapshot.name] = _sha256_file(snapshot)
    if phase == "interactions":
        for name in ["interaction-plan.json", "interaction-transcripts.json"]:
            artifacts[name] = _sha256_file(root / name)
    dump(
        root / f"{phase}-prediction-seal.json",
        seal(
            {
                "engine": "live_llm_no_tools_host",
                "phase": phase,
                "predictions_sha256": _sha256_file(path),
                "contract_sha256": _sha256_file(root / "contract.json"),
                "artifact_hashes": artifacts,
                "n_predictions": len(rows),
                "missing_predictions": sum(row["probabilities"] is None for row in rows),
            }
        ),
    )


def independent(root, config, cohort, workers, pack, calls):
    rng = np.random.default_rng(config["seed"] + 1)
    rows = []
    for repetition in range(config["repetitions"]):
        for index, profile in enumerate(cohort):
            model = workers[index % len(workers)]
            for arm in rng.permutation(list(ARMS)):
                rich, evidence = ARMS[arm]
                meta = {
                    "phase": "independent",
                    "arm": str(arm),
                    "repetition": repetition,
                    "synthetic_person_id": profile["synthetic_person_id"],
                    "model_id": model.id,
                }
                result = calls.call(
                    model, context(profile, rich, evidence, pack) + "\n" + TASK, meta
                )
                rows.append({**meta, "probabilities": result})
    save_predictions(root, "independent", rows)


def network_schedule(cohort, config):
    rng = np.random.default_rng(config["seed"] + 2)
    neighbors = {}
    for i, profile in enumerate(cohort):
        ideology = profile["observed"]["libcpre_self"]["code"]
        distances = []
        for j, other in enumerate(cohort):
            if i == j:
                continue
            other_ideology = other["observed"]["libcpre_self"]["code"]
            distance = abs(ideology - other_ideology) if ideology and other_ideology else 3
            distances.append((distance + float(rng.uniform(0, 2)), j))
        neighbors[i] = [j for _, j in sorted(distances)[: config["interaction_neighbors"]]]
    participation = []
    for _ in range(config["interaction_rounds"]):
        active = []
        for profile in cohort:
            interest = profile["observed"]["paprofile_interestpolit"]["code"]
            probability = config["participation_probability_by_interest"].get(
                interest, config["missing_interest_participation_probability"]
            )
            active.append(bool(rng.random() < probability))
        participation.append(active)
    return neighbors, participation


def interactions(root, config, cohort, workers, pack, calls):
    cohort = cohort[: config["interaction_n"]]
    neighbors, participation = network_schedule(cohort, config)
    dump(
        root / "interaction-plan.json",
        {
            "neighbors": neighbors,
            "participation": participation,
            "interpretation": "Illustrative sparse homophilous network and interest-linked "
            "participation; not observed ANES relationships or estimated influence.",
        },
    )
    predictions, transcripts = [], []
    for arm in ["private_matched", "limited_network"]:
        history = {i: [] for i in range(len(cohort))}
        for round_index, active in enumerate(participation):
            prior = {i: list(messages) for i, messages in history.items()}
            for i, profile in enumerate(cohort):
                if not active[i]:
                    continue
                exposure = (
                    [(j, prior[j][-1]) for j in neighbors[i] if prior[j]]
                    if arm == "limited_network"
                    else []
                )
                user = context(profile, True, True, pack) + "\nYour earlier statements: "
                user += json.dumps(prior[i]) + "\nMessages from selected contacts: "
                user += json.dumps([{"peer": j, "message": m} for j, m in exposure])
                user += (
                    "\nGive a brief public response to one received message if relevant; "
                    "otherwise express your own view. You may abstain with an empty message. "
                    "Do not assume peers are trustworthy or that a majority is right."
                    if arm == "limited_network"
                    else "\nReflect privately on your own views; do not invent peer opinions."
                )
                user += '\nReturn only {"message":"at most 35 words"}.'
                meta = {
                    "phase": "interactions",
                    "arm": arm,
                    "repetition": 0,
                    "stage": "message",
                    "round": round_index,
                    "synthetic_person_id": profile["synthetic_person_id"],
                    "model_id": workers[i % len(workers)].id,
                }
                result = calls.call(workers[i % len(workers)], user, meta, message=True)
                if result and result["message"]:
                    history[i].append(result["message"])
                transcripts.append(
                    {**meta, "message": result, "received_peer_ids": [j for j, _ in exposure]}
                )
        for i, profile in enumerate(cohort):
            exposure = (
                [history[j][-1] for j in neighbors[i] if history[j]]
                if arm == "limited_network"
                else []
            )
            user = context(profile, True, True, pack)
            user += "\nYour own statements: " + json.dumps(history[i])
            user += "\nSelected contact messages: " + json.dumps(exposure)
            user += "\nAnswer privately; you may retain your prior views.\n" + TASK
            meta = {
                "phase": "interactions",
                "arm": arm,
                "repetition": 0,
                "stage": "final",
                "synthetic_person_id": profile["synthetic_person_id"],
                "model_id": workers[i % len(workers)].id,
            }
            result = calls.call(workers[i % len(workers)], user, meta)
            predictions.append({**meta, "probabilities": result})
    dump(root / "interaction-transcripts.json", transcripts)
    save_predictions(root, "interactions", predictions)


def score(root, phase):
    prediction_path = root / f"{phase}-predictions.json"
    prediction_seal_path = root / f"{phase}-prediction-seal.json"
    prediction_seal = json.loads(prediction_seal_path.read_text())
    check_seal(prediction_seal)
    for name, digest in prediction_seal.get("artifact_hashes", {}).items():
        if _sha256_file(root / name) != digest:
            raise ValueError("Checkpoint or conversation artifact changed")
    if prediction_seal["predictions_sha256"] != _sha256_file(prediction_path):
        raise ValueError("Prediction hash mismatch")
    if prediction_seal["contract_sha256"] != _sha256_file(root / "contract.json"):
        raise ValueError("Contract hash mismatch")
    manifest = json.loads((root / "profile-seal.json").read_text())
    check_seal(manifest)
    targets_path = Path(manifest["targets_path"])
    if _sha256_file(targets_path) != manifest["targets_sha256"]:
        raise ValueError("Target hash mismatch")
    targets = {r["synthetic_person_id"]: r for r in json.loads(targets_path.read_text())}
    predictions = json.loads(prediction_path.read_text())
    contract = json.loads((root / "contract.json").read_text())
    check_seal(contract)
    for key, path in contract["bound_files"].items():
        if _sha256_file(resolve(path)) != contract["bound_hashes"][key]:
            raise ValueError(f"Bound input changed: {key}")
    config = contract["config"]
    cohort = json.loads((root / "cohort.json").read_text())
    expected_ids = {
        p["synthetic_person_id"]
        for p in (cohort if phase == "independent" else cohort[: config["interaction_n"]])
    }
    expected_repeats = set(range(config["repetitions"])) if phase == "independent" else {0}
    arms = sorted(ARMS if phase == "independent" else ["private_matched", "limited_network"])
    if {r["arm"] for r in predictions} != set(arms):
        raise ValueError("Missing or unexpected treatment arm")
    panels = {}
    for row in predictions:
        key = (row["synthetic_person_id"], row["repetition"])
        if row["arm"] in panels.setdefault(key, {}):
            raise ValueError("Duplicate prediction")
        panels[key][row["arm"]] = row
    if set(panels) != {(person, rep) for person in expected_ids for rep in expected_repeats}:
        raise ValueError("Missing planned profile/repetition")
    if any(set(panel) != set(arms) for panel in panels.values()):
        raise ValueError("Unbalanced comparison")
    if any(len({r["model_id"] for r in panel.values()}) != 1 for panel in panels.values()):
        raise ValueError("Unmatched model assignments")
    metrics, losses = [], {}
    for task, spec in TARGETS.items():
        keys = [
            key
            for key, panel in panels.items()
            if targets[key[0]][task] in spec["codes"]
            and all(r["probabilities"] is not None for r in panel.values())
        ]
        for arm in arms:
            if not keys:
                continue
            probabilities = np.array([panels[key][arm]["probabilities"][task] for key in keys])
            y = np.array([spec["codes"].index(targets[key[0]][task]) for key in keys])
            weights = np.array([targets[key[0]]["weight"] for key in keys])
            onehot = np.eye(3)[y]
            brier = 0.5 * ((probabilities - onehot) ** 2).sum(axis=1)
            losses[(task, arm)] = dict(zip(keys, brier.tolist()))
            predicted_share = np.average(probabilities, axis=0, weights=weights)
            observed_share = np.average(onehot, axis=0, weights=weights)
            metrics.append(
                {
                    "task": task,
                    "arm": arm,
                    "scored_rows": len(keys),
                    "unique_respondents": len({key[0] for key in keys}),
                    "brier_half_multiclass": float(np.average(brier, weights=weights)),
                    "agreement": float(
                        np.average(probabilities.argmax(axis=1) == y, weights=weights)
                    ),
                    "log_loss": float(
                        np.average(
                            -np.log(np.clip(probabilities[np.arange(len(y)), y], 1e-9, 1)),
                            weights=weights,
                        )
                    ),
                    "distribution_total_variation": float(
                        0.5 * abs(predicted_share - observed_share).sum()
                    ),
                    "predicted_shares": predicted_share.tolist(),
                    "observed_shares": observed_share.tolist(),
                }
            )
    contrasts = []
    pairs = (
        [
            ("sparse_no_evidence", "rich_no_evidence"),
            ("sparse_evidence", "rich_evidence"),
            ("sparse_no_evidence", "sparse_evidence"),
            ("rich_no_evidence", "rich_evidence"),
        ]
        if phase == "independent"
        else [("private_matched", "limited_network")]
    )
    rng = np.random.default_rng(20261011)
    for task in TARGETS:
        for before, after in pairs:
            if (task, before) not in losses:
                continue
            a, b = losses[(task, before)], losses[(task, after)]
            ids = sorted({key[0] for key in a})
            delta = np.array(
                [np.mean([b[k] - a[k] for k in a if k[0] == person]) for person in ids]
            )
            weights = np.array([targets[person]["weight"] for person in ids])
            draws = rng.integers(0, len(ids), size=(2000, len(ids)))
            bootstrap = (delta[draws] * weights[draws]).sum(axis=1) / weights[draws].sum(axis=1)
            contrasts.append(
                {
                    "task": task,
                    "before": before,
                    "after": after,
                    "brier_change": float(np.average(delta, weights=weights)),
                    "respondent_bootstrap_95_interval": np.quantile(
                        bootstrap, [0.025, 0.975]
                    ).tolist(),
                    "interval_scope": "Exploratory conditional on this sample/roster; "
                    "not ANES complex-survey or network-cluster inference.",
                }
            )
    report = {
        "phase": phase,
        "scientific_result": False,
        "engine": "live_llm_no_tools_host",
        "metrics": metrics,
        "contrasts": contrasts,
        "missing_predictions": sum(r["probabilities"] is None for r in predictions),
        "prediction_rows": len(predictions),
        "limitations": "Descriptive development experiment. Health/gun tasks are pre-election "
        "item imputation; vote is retrospective forecast validation. Evidence "
        "is a small economy-focused supplied pack, not known personal exposure.",
    }
    destination = root / f"{phase}-evaluation.json"
    dump(destination, report)
    dump(
        root / f"{phase}-evaluation-seal.json",
        seal(
            {
                "report_sha256": _sha256_file(destination),
                "targets_sha256": _sha256_file(targets_path),
                "prediction_seal_sha256": _sha256_file(prediction_seal_path),
                "evaluator_sha256": _sha256_file(Path(__file__)),
            }
        ),
    )
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "independent", "interactions", "score"])
    parser.add_argument("--config", default="config/anes2012-decision-context.yaml")
    parser.add_argument("--score-phase", default="independent")
    args = parser.parse_args()
    load_dotenv()
    config = load_yaml(args.config)
    root, contract = prepare(config)
    if args.phase == "prepare":
        print(json.dumps({"root": str(root), "profiles": contract["profile_count"]}))
        return
    if args.phase == "score":
        score(root, args.score_phase)
        return
    status = readiness(root)
    credit = status["credits"]["total_credits"] - status["credits"]["total_usage"]
    if (
        credit < config["max_usd"]
        or (status["auth/key"].get("limit_remaining") or 0) < config["max_usd"]
    ):
        raise RuntimeError("Insufficient confirmed budget")
    os.environ.update(
        PSBX_ENABLE_PAID_MODELS="1",
        PSBX_MOCK_LLM="0",
        PSBX_MAX_RUN_USD=str(config["max_usd"]),
        PSBX_MAX_PAID_REQUESTS=str(config["max_requests"]),
    )
    workers = [
        ModelConfig.model_validate(row) for row in json.loads((root / "workers.json").read_text())
    ]
    preflight_paid_requests([(worker, 220) for worker in workers])
    begin_spend_run(config["run_id"])
    cohort = json.loads((root / "cohort.json").read_text())
    pack = load_pack(root / "evidence-pack.json")
    calls = Calls(root)
    if args.phase == "independent":
        independent(root, config, cohort, workers, pack, calls)
    else:
        if not (root / "independent-evaluation.json").exists():
            raise ValueError("Complete independent comparison before running social pilot")
        interactions(root, config, cohort, workers, pack, calls)
    score(root, args.phase)


if __name__ == "__main__":
    main()
