"""Frozen direct-only belief forecasts. No evaluator labels loaded in this process."""

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import time

for name in list(os.environ):
    if name.endswith("API_KEY") or name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        os.environ.pop(name)
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")

import mlx.core as mx
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler
from score_local_message_loss import digest, swap_mib


def strict_probabilities(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"probabilities"}:
        raise ValueError("Expected probabilities object only")
    p = value["probabilities"]
    if not isinstance(p, list) or len(p) != 6:
        raise ValueError("Expected six probabilities")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
           not math.isfinite(x) or not 0 <= x <= 1 for x in p):
        raise ValueError("Invalid probability value")
    if abs(sum(p) - 1) > 1e-6:
        raise ValueError("Probabilities do not sum to one")
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["base", "pilot_adapter"], required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    for path, expected in contract["bindings"].items():
        if digest(path) != expected:
            raise ValueError("Frozen binding mismatch: " + path)
    output = args.contract.parent / ("direct-" + args.arm)
    output.mkdir(exist_ok=False)
    worker_path = Path(contract["prompt_worker_path"])
    spec = importlib.util.spec_from_file_location("allowed_prompt_worker", worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    cases = json.loads(Path(contract["cases_path"]).read_text())
    assert len(cases) == 16
    started, initial_swap = time.monotonic(), swap_mib()
    mx.set_cache_limit(256 * 1024**2)
    mx.reset_peak_memory()
    mx.random.seed(20261023)
    model, tokenizer = load(contract["model_path"],
        adapter_path=contract["adapter_path"] if args.arm == "pilot_adapter" else None)
    model.eval()
    prompts = []
    for case in cases:
        assert set(case) == {"group_id", "profile"}
        job = worker.build_prompt(dict(profile=case["profile"], arm="private", stage="final",
                                       round=3, history=[]))
        messages = [dict(role="system", content=job["system"]), dict(role="user", content=job["user"])]
        tokens = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_dict=False)
        if len(tokens) + 256 > 4096:
            raise ValueError("Context cap exceeded; no truncation")
        prompts.append((case, job, tokens))
    records, failure = [], None
    for case, job, tokens in prompts:
        raw = generate(model, tokenizer, prompt=tokens, max_tokens=256,
                       sampler=make_sampler(temp=0), verbose=False)
        record = dict(agent=case["profile"]["agent_id"], group=case["group_id"],
                      arm=args.arm, prompt=job, prompt_tokens=len(tokens), raw=raw,
                      peak_allocated_bytes=mx.get_peak_memory())
        try:
            record["probabilities"] = strict_probabilities(raw)
            record["status"] = "valid"
        except (ValueError, TypeError) as exc:
            record.update(status="invalid_format", error=str(exc))
            failure = "invalid_format"
        records.append(record)
        with (output / "predictions.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        print(f"{args.arm}: {len(records)}/16 {record['status']}", flush=True)
        if failure:
            break
        if mx.get_peak_memory() > 14 * 1024**3 or swap_mib() - initial_swap > 2048:
            failure = "resource_gate_exceeded"
            break
        mx.clear_cache()
    summary = dict(status="completed" if failure is None else "stopped", reason=failure,
                   completed=len(records), valid=sum(r["status"] == "valid" for r in records),
                   elapsed_seconds=time.monotonic() - started, peak_allocated_bytes=mx.get_peak_memory(),
                   predictions_sha256=digest(output / "predictions.jsonl"),
                   contract_sha256=digest(args.contract), outcome_scoring_performed=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    if failure:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
