"""Paired completion-only message scoring; one frozen model arm per process."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

for name in list(os.environ):
    if name.endswith("API_KEY") or name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        os.environ.pop(name)
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")

import mlx.core as mx
import mlx.nn as nn
from mlx_lm import load
from mlx_lm.tuner.datasets import ChatDataset


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def masked_nll(logits, tokens, offset):
    """Each position predicts the next token; supervise completion and EOS only."""
    if not 0 < offset < len(tokens):
        raise ValueError("Invalid prompt/completion boundary")
    targets = mx.array(tokens[offset:])
    completion_logits = logits[0, offset - 1:, :]
    if completion_logits.shape[0] != len(tokens) - offset:
        raise ValueError("Shifted loss shape mismatch")
    return nn.losses.cross_entropy(completion_logits.astype(mx.float32), targets).sum()


def swap_mib():
    return float(re.search(r"used = ([0-9.]+)M", subprocess.check_output(
        ["sysctl", "vm.swapusage"], text=True)).group(1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["base", "pilot_adapter"], required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    for path, expected in contract["bindings"].items():
        if digest(path) != expected:
            raise ValueError("Frozen binding mismatch: " + path)
    out = args.contract.parent / args.arm
    out.mkdir(exist_ok=False)
    started, baseline_swap = time.monotonic(), swap_mib()
    def timeout(signum, frame):
        raise TimeoutError("Frozen wall-time cap reached")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(contract["wall_seconds_per_arm"])
    mx.set_cache_limit(256 * 1024**2)
    mx.reset_peak_memory()
    model, tokenizer = load(contract["model_path"],
        adapter_path=contract["adapter_path"] if args.arm == "pilot_adapter" else None)
    model.eval()
    raw = Path(contract["validation_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == contract["validation_sha256"]
    records = [json.loads(line) for line in raw.decode().splitlines()]
    groups_by_row = json.loads(Path(contract["validation_groups_path"]).read_text())
    assert len(groups_by_row) == len(records)
    assert len(records) == 133
    dataset = ChatDataset(records, tokenizer, mask_prompt=True)
    rows = []
    for index, (record, group) in enumerate(zip(records, groups_by_row)):
        tokens, offset = dataset.process(record)
        prefix = tokenizer.apply_chat_template(record["messages"][:-1],
                    add_generation_prompt=True, return_dict=False)
        assert tokens[:offset] == prefix and len(tokens) <= 2304
        loss = masked_nll(model(mx.array(tokens[:-1])[None]), tokens, offset)
        mx.eval(loss)
        value = float(loss.item())
        if not bool(mx.isfinite(loss).item()):
            raise ValueError("Nonfinite message loss")
        row = dict(index=index, group=group, supervised_tokens=len(tokens) - offset,
                   completion_nll_sum=value, nll=value / (len(tokens) - offset),
                   peak_allocated_bytes=mx.get_peak_memory(), elapsed_seconds=time.monotonic() - started)
        rows.append(row)
        with (out / "scores.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        if row["peak_allocated_bytes"] > 14 * 1024**3 or swap_mib() - baseline_swap > 2048:
            raise RuntimeError("Resource gate exceeded")
        del loss
        mx.clear_cache()
        if (index + 1) % 20 == 0:
            print(f"{args.arm}: {index + 1}/133 scored", flush=True)
    groups = {}
    for group in sorted({r["group"] for r in rows}):
        group_rows = [r for r in rows if r["group"] == group]
        groups[group] = sum(r["nll"] for r in group_rows) / len(group_rows)
    result = dict(arm=args.arm, status="completed", examples=len(rows), groups=groups,
                  supervised_tokens=sum(r["supervised_tokens"] for r in rows),
                  token_weighted_nll=sum(r["completion_nll_sum"] for r in rows) / sum(r["supervised_tokens"] for r in rows),
                  equal_group_message_mean_nll=sum(groups.values()) / len(groups),
                  peak_allocated_bytes=mx.get_peak_memory(), elapsed_seconds=time.monotonic() - started,
                  baseline_swap_mib=baseline_swap, final_swap_mib=swap_mib(),
                  scores_sha256=digest(out / "scores.jsonl"), contract_sha256=digest(args.contract))
    (out / "summary.json").write_text(json.dumps(result, indent=2))
    signal.alarm(0)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
