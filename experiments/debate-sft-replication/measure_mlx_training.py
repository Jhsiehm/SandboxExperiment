"""Eight longest training examples: instrumented hardware probe, not model selection."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from types import SimpleNamespace

# No hosted credentials are needed by this native, offline MLX process.
for name in list(os.environ):
    if name.endswith("API_KEY") or name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        os.environ.pop(name)
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")

import mlx.core as mx
import numpy as np
import yaml
from transformers import AutoTokenizer
from mlx_lm import lora
from mlx_lm.tuner.datasets import ChatDataset


def swap_mib():
    text = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
    return float(re.search(r"used = ([0-9.]+)M", text).group(1))


def main():
    source = Path(__file__).resolve().parent
    data = source.parents[1] / "data/local-mlx-pilot"
    output = data / time.strftime("memory-probe-%Y%m%d-%H%M%S")
    output.mkdir()
    model = (data / "model-path.txt").read_text().strip()
    preflight = json.loads((data / "preflight.json").read_text())
    train = data / "train.jsonl"
    assert hashlib.sha256(train.read_bytes()).hexdigest() == preflight["splits"]["train"]["sha256"]
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    records = [json.loads(line) for line in train.read_text().splitlines()]
    dataset = ChatDataset(records, tokenizer, mask_prompt=True)
    ranked = sorted(enumerate(records), key=lambda item: len(dataset.process(item[1])[0]), reverse=True)
    selected = ranked[:8]
    (output / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for _, r in selected))
    # Loader expects validation; this single training example is only a GPU warmup.
    (output / "valid.jsonl").write_text(json.dumps(selected[0][1]) + "\n")
    config = copy.deepcopy(lora.CONFIG_DEFAULTS)
    config.update(yaml.safe_load((source / "local-mlx-pilot.yaml").read_text()))
    config.update(model=model, data=str(output), adapter_path=str(output / "discarded-adapters"),
                  iters=8, val_batches=1, steps_per_report=1, steps_per_eval=8,
                  save_every=8, clear_cache_threshold=256 * 1024**2)
    config["steps_per_report"] = 1
    start_swap = swap_mib()
    started = time.monotonic()
    contract = dict(purpose="hardware-only worst-context probe; adapters not selection candidates",
                    config=config, train_sha256=hashlib.sha256(train.read_bytes()).hexdigest(),
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    selected_training_row_indices=[i for i, _ in selected],
                    sequence_lengths=[len(dataset.process(r)[0]) for _, r in selected],
                    baseline_swap_mib=start_swap, peak_limit_bytes=14 * 1024**3,
                    swap_growth_limit_mib=2048, wall_seconds_limit=900,
                    model_source=json.loads((data / "model-source.json").read_text()))
    (output / "contract.json").write_text(json.dumps(contract, indent=2))
    mx.set_cache_limit(256 * 1024**2)
    mx.reset_peak_memory()

    class Callback:
        def record(self, kind, metrics):
            row = dict(kind=kind, elapsed_seconds=time.monotonic() - started,
                       peak_allocated_bytes=mx.get_peak_memory(), active_bytes=mx.get_active_memory(),
                       cache_bytes=mx.get_cache_memory(), swap_mib=swap_mib(), **metrics)
            with (output / "metrics.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
            if any(not math.isfinite(float(value)) for key, value in metrics.items()
                   if key.endswith("loss")):
                raise RuntimeError("Nonfinite measured loss")
            if row["peak_allocated_bytes"] > contract["peak_limit_bytes"]:
                raise RuntimeError("Measured MLX allocation exceeded hardware gate")
            if row["swap_mib"] - start_swap > contract["swap_growth_limit_mib"]:
                raise RuntimeError("System swap growth exceeded hardware gate")

        def on_train_loss_report(self, metrics):
            self.record("training", metrics)

        def on_val_loss_report(self, metrics):
            self.record("warmup_not_validation", metrics)

    def timeout(signum, frame):
        raise TimeoutError("Hardware probe wall-time cap reached")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(900)
    status, error = "completed", None
    try:
        # mlx-lm 0.32.2 run() replaces its supplied callback. Use the public
        # lower-level entry point so our resource gates actually execute.
        args = SimpleNamespace(**config)
        np.random.seed(args.seed)
        loaded_model, loaded_tokenizer = lora.load(args.model, trust_remote_code=False)
        train_set, valid_set, _ = lora.load_dataset(args, loaded_tokenizer)
        lora.train_model(args, loaded_model, train_set, valid_set, training_callback=Callback())
        measured = [json.loads(line) for line in (output / "metrics.jsonl").read_text().splitlines()]
        assert sum(row["kind"] == "training" for row in measured) == 8
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        summary = dict(status=status, error=error, elapsed_seconds=time.monotonic() - started,
                       peak_allocated_bytes=mx.get_peak_memory(), final_swap_mib=swap_mib(),
                       baseline_swap_mib=start_swap, output=str(output), paid_calls=0)
        (output / "result.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)
    if status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
