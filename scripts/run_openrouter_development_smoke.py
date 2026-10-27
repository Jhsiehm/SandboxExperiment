"""Twelve-call development diagnostic; no evaluation outcomes or automatic retries."""

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

import httpx

from psbx import openrouter
from psbx.config import load_models
from psbx.experiments.anes_society import _parse_llm_json
from psbx.experiments.social_benchmark import docker_job, validate_result
from psbx.experiments.telemetry import observe, observed_run
from psbx.paths import repo_root, run_dir
from psbx.schemas import ModelConfig
from psbx.spending import begin_spend_run, preflight_paid_requests


def dump(path, value):
    path.write_text(json.dumps(value, indent=2))
    path.chmod(0o600)


@observed_run(study_id="debate")
def run(root):
    base = repo_root()
    source = base / "experiments/debate-sft-replication"
    manifest = json.loads((source / "inputs/manifest.json").read_text())
    audit = json.loads((source / "preparation-audit.json").read_text())
    group = next(g for g in manifest["groups"]
                 if g["partition"] == "train" and g["group_id"] in audit["per_group"])
    path = source / "inputs" / (group["group_id"] + ".csv")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == group["sha256"]
    with path.open() as stream:
        initial = [r for r in csv.DictReader(stream) if r["event_type"] == "Initial Opinion"]
    assert len(initial) == 4
    profiles = [dict(agent_id=f"p{i}", topic=group["topic"],
                     initial_score=int(float(r["sliderValue"])), initial_text=r["text"],
                     partners={"1": f"p{i ^ 1}"}) for i, r in enumerate(initial)]
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    catalog = next(x for x in response.json()["data"]
                   if x["id"] == "meta-llama/llama-3.1-8b-instruct")
    model = load_models()["openrouter-llama-3.1-8b"].model_copy(update={
        "max_tokens": 256, "temperature": 0.2, "json_output": True,
        "cost_per_1k_input": float(catalog["pricing"]["prompt"]) * 1000,
        "cost_per_1k_output": float(catalog["pricing"]["completion"]) * 1000,
    })
    os.environ.update(PSBX_ENABLE_PAID_MODELS="1", PSBX_MAX_PAID_REQUESTS="12",
                      PSBX_MAX_RUN_USD="0.25", PSBX_MAX_REQUEST_USD="0.02")
    # The provider client's retry reservations are not per-wire-attempt; disable
    # automatic retries so the twelve-request ceiling also bounds wire requests.
    openrouter._MAX_429_RETRIES = 0
    image = subprocess.check_output([
        "docker", "image", "inspect", "psbx-social-worker:local", "--format", "{{.Id}}"
    ], text=True).strip()
    contract = dict(purpose="development infrastructure smoke; no scientific scoring",
                    group=group["group_id"], profiles=profiles, model=model.model_dump(mode="json"),
                    image=image, max_requests=12, max_usd=.25, retries=0,
                    peer_schedule="assumed pairs p0-p1 and p2-p3; one synchronous pass",
                    limitations="No held-out claims, no human outcome scoring, no adapter comparison",
                    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    source_sha256=group["sha256"],
                    preflight=preflight_paid_requests([(model, 12)]))
    if (root / "contract.json").exists():
        original = json.loads((root / "contract.json").read_text())
        assert original["profiles"] == profiles and original["image"] == image
        model = ModelConfig.model_validate(original["model"])
        ledger = json.loads((root / "spend_ledger.json").read_text())
        assert ledger["reserved_requests"] == 3, "Only the documented three-call recovery is allowed"
        assert not (root / "continuation.json").exists(), "Continuation already attempted"
        dump(root / "continuation.json", dict(
            original_contract_sha256=hashlib.sha256((root / "contract.json").read_bytes()).hexdigest(),
            runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            reason="Continue after invalid third probability vector; do not retry or score it",
            additional_calls=9, total_request_cap=12, total_usd_cap=.25))
        dump(root / "response-03.json", dict(agent="p2", arm="private", stage="final",
             parsed=None, status="invalid_probability_vector", raw_response_retained=False,
             usage=ledger["entries"][2].get("reported_usage")))
    else:
        dump(root / "contract.json", contract)
        dump(root / "catalog.json", catalog)
    begin_spend_run(root.name)
    results = []
    def call(profile, arm, stage, history):
        saved = root / f"response-{len(results) + 1:02d}.json"
        if saved.exists():
            row = json.loads(saved.read_text())
            assert (row["agent"], row["arm"], row["stage"]) == (profile["agent_id"], arm, stage)
            results.append(row)
            return row["parsed"]
        payload = dict(profile=profile, arm=arm, stage=stage, round=1, history=history)
        job = docker_job(payload, image)
        observe("model_requested", agent_key=profile["agent_id"], phase=stage)
        result = openrouter.chat_completion(
            model=model.model_name, model_config=model,
            messages=[dict(role="system", content=job["system"]),
                      dict(role="user", content=job["user"])],
            max_tokens=256, temperature=.2, json_output=True)
        raw = result["choices"][0]["message"]["content"]
        try:
            parsed = validate_result(_parse_llm_json(raw), stage)
        except (ValueError, TypeError, KeyError):
            parsed = None
        row = dict(agent=profile["agent_id"], arm=arm, stage=stage, parsed=parsed,
                   raw=raw, status="valid" if parsed is not None else "invalid_format",
                   usage=result.get("usage"), provider_id=result.get("id"),
                   isolation=job["isolation"], prompt=job)
        results.append(row)
        dump(root / f"response-{len(results):02d}.json", row)
        observe("checkpoint_saved", agent_key=profile["agent_id"], phase=stage)
        print(f"Completed {len(results)}/12: {arm} {stage}", flush=True)
        if parsed is None and stage == "message":
            raise RuntimeError("Invalid peer message; stop rather than fabricate an interaction")
        return parsed
    for p in profiles:
        call(p, "private", "final", [])
    messages = {p["agent_id"]: call(p, "swarm", "message", [])["message"] for p in profiles}
    for p in profiles:
        own, peer = p["agent_id"], p["partners"]["1"]
        history = [dict(speaker=own, direction="own", round=1, text=messages[own]),
                   dict(speaker=peer, direction="received", round=1, text=messages[peer])]
        call(p, "swarm", "final", history)
    ledger = json.loads((root / "spend_ledger.json").read_text())
    costs = [r.get("reported_usage", {}).get("provider_cost_usd") for r in ledger["entries"]]
    dump(root / "summary.json", dict(status="completed_with_format_failures" if any(r["parsed"] is None for r in results) else "completed", calls=len(results),
         valid_responses=sum(r["parsed"] is not None for r in results),
         provider_reported_usd=sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None,
         scientific_evaluation=False))


if __name__ == "__main__":
    import sys
    credentials = Path(sys.argv[1])
    for line in credentials.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    root = run_dir("debate-openrouter-development-smoke-20261023")
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    run(root)
