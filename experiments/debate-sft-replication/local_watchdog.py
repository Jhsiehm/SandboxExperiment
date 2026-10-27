"""Bounded, offline subprocess supervisor; never imports a model runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def budget_reason(elapsed, rss_kib, swap_growth_mib, *, wall_seconds,
                  max_rss_gib, max_swap_growth_mib):
    """Return the first exhausted budget; equality exhausts a budget."""
    if elapsed >= wall_seconds:
        return "wall_seconds"
    if rss_kib >= max_rss_gib * 1024 * 1024:
        return "rss_gib"
    if swap_growth_mib >= max_swap_growth_mib:
        return "swap_growth_mib"
    return None


def child_environment():
    env = {k: v for k, v in os.environ.items()
           if not k.upper().endswith("_API_KEY")
           and k.upper() not in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    return env


def swap_used_mib():
    if sys.platform == "darwin":
        output = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True)
        match = re.search(r"used\s*=\s*([\d.]+)([KMG])", output)
        if not match:
            raise RuntimeError("Cannot parse system swap usage")
        return float(match[1]) * {"K": 1 / 1024, "M": 1, "G": 1024}[match[2]]
    # Allows small supervisor integration tests on Linux as well as macOS.
    fields = dict(re.findall(r"^(SwapTotal|SwapFree):\s+(\d+)",
                             Path("/proc/meminfo").read_text(), re.M))
    return (int(fields["SwapTotal"]) - int(fields["SwapFree"])) / 1024


def group_rss_kib(pgid):
    output = subprocess.check_output(["ps", "-axo", "pgid=,rss="], text=True)
    return sum(int(parts[1]) for line in output.splitlines()
               if len(parts := line.split()) == 2 and int(parts[0]) == pgid)


def cleanup_group(process):
    """Clean surviving descendants too, even when the group leader has exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-seconds", type=int, required=True)
    parser.add_argument("--max-rss-gib", type=float, default=18)
    parser.add_argument("--max-swap-growth-mib", type=float, default=2048)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command after -- is required")
    if any(not (0 < x < float("inf")) for x in
           (args.wall_seconds, args.max_rss_gib, args.max_swap_growth_mib)):
        parser.error("budgets must be finite and positive")
    try:
        args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError:
        parser.error("output directory already exists; refusing to overwrite")
    start = time.monotonic()
    process = None
    reason = None
    error = None
    peak_rss = 0
    peak_swap_growth = 0.0
    exit_code = 1
    baseline = None
    try:
        baseline = swap_used_mib()
        with (args.output / "child.log").open("w") as log, \
                (args.output / "telemetry.jsonl").open("w") as telemetry:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=child_environment(), start_new_session=True)
            while True:
                elapsed = time.monotonic() - start
                rss = group_rss_kib(process.pid)
                swap = swap_used_mib()
                growth = max(0, swap - baseline)
                peak_rss = max(peak_rss, rss)
                peak_swap_growth = max(peak_swap_growth, growth)
                telemetry.write(json.dumps(dict(elapsed_seconds=elapsed,
                    process_group=process.pid, group_rss_kib=rss,
                    system_swap_used_mib=swap, swap_growth_mib=growth)) + "\n")
                telemetry.flush()
                reason = budget_reason(elapsed, rss, growth,
                    wall_seconds=args.wall_seconds, max_rss_gib=args.max_rss_gib,
                    max_swap_growth_mib=args.max_swap_growth_mib)
                if reason:
                    exit_code = 124
                    break
                result = process.poll()
                if result is not None:
                    exit_code = result if result >= 0 else 128 - result
                    break
                time.sleep(min(2, max(0.01, args.wall_seconds - elapsed)))
    except KeyboardInterrupt:
        reason, exit_code = "keyboard_interrupt", 130
    except Exception as exc:
        reason, error, exit_code = "supervisor_error", str(exc), 1
    finally:
        if process is not None:
            cleanup_group(process)
        summary = dict(exit_code=exit_code, child_returncode=None if process is None
                       else process.returncode, stop_reason=reason, error=error,
                       elapsed_seconds=time.monotonic() - start,
                       baseline_system_swap_mib=baseline, peak_group_rss_kib=peak_rss,
                       peak_swap_growth_mib=peak_swap_growth,
                       budgets=dict(wall_seconds=args.wall_seconds,
                           max_rss_gib=args.max_rss_gib,
                           max_swap_growth_mib=args.max_swap_growth_mib),
                       note="RSS is summed over the process group; swap is system-wide. "
                            "2-second polling is not a hard memory allocation limit.")
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
