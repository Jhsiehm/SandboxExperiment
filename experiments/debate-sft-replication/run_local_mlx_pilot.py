"""Run one bounded, offline hardware pilot and retain logs and provenance."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root = Path(__file__).resolve().parent
    workspace = root.parents[1]
    data = workspace / "data/local-mlx-pilot"
    audit = json.loads((data / "preflight.json").read_text())
    for split in ("train", "valid"):
        path = data / f"{split}.jsonl"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == audit["splits"][split]["sha256"]
        assert audit["splits"][split]["max_tokens"] <= 2304
        assert audit["splits"][split]["all_prompt_prefix_masks_verified"]
    output = data / time.strftime("pilot-%Y%m%d-%H%M%S")
    output.mkdir()
    model = (data / "model-path.txt").read_text().strip()
    command = [sys.executable, "-m", "mlx_lm.lora", "--config",
               str(root / "local-mlx-pilot.yaml"), "--model", model,
               "--data", str(data), "--adapter-path", str(output / "adapters")]
    bindings = {}
    for path in [root / "local-mlx-pilot.yaml", Path(__file__), data / "preflight.json",
                 data / "requirements.lock", *sorted(Path(model).glob("*"))]:
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            bindings[str(path)] = digest.hexdigest()
    (output / "contract.json").write_text(json.dumps({
        "purpose": "development hardware pilot only", "command": command,
        "bindings": bindings, "wall_time_cap_seconds": 1800,
        "paid_calls": 0, "evaluation_reserve_access": False,
        "boundary": "Native host MLX, offline hub flags; not a Docker isolation claim",
    }, indent=2))
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "HF_HUB_DISABLE_TELEMETRY": "1", "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"}
    started = time.monotonic()
    print(f"Pilot output: {output}", flush=True)
    with (output / "training.log").open("w") as log:
        process = subprocess.Popen(command, cwd=workspace, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        try:
            returncode = process.wait(timeout=1800)
            status = "completed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            returncode, status = process.returncode, "wall_time_cap_reached"
    summary = {"status": status, "returncode": returncode,
               "elapsed_seconds": time.monotonic() - started,
               "output": str(output)}
    (output / "result.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if status == "completed" else 1)


if __name__ == "__main__":
    main()
