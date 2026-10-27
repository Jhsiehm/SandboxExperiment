import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name("local_watchdog.py")
spec = importlib.util.spec_from_file_location("local_watchdog", SCRIPT)
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


@pytest.mark.parametrize("values,expected", [
    ((9, 1024, 1), None), ((10, 1024, 1), "wall_seconds"),
    ((1, 1048576, 1), "rss_gib"), ((1, 1024, 2), "swap_growth_mib"),
])
def test_budget_boundaries(values, expected):
    assert watchdog.budget_reason(*values, wall_seconds=10,
        max_rss_gib=1, max_swap_growth_mib=2) == expected


@pytest.mark.parametrize("code", [0, 7])
def test_subprocess_result_and_environment(tmp_path, code, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "never-forward-this")
    monkeypatch.setenv("HF_TOKEN", "never-forward-this")
    output = tmp_path / "run"
    child = ("import os,sys; assert 'OPENROUTER_API_KEY' not in os.environ; "
             "assert 'HF_TOKEN' not in os.environ; "
             "assert os.environ['HF_HUB_OFFLINE']=='1'; print('ok'); "
             f"sys.exit({code})")
    result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output),
        "--wall-seconds", "15", "--", sys.executable, "-c", child])
    assert result.returncode == code
    summary = json.loads((output / "summary.json").read_text())
    assert summary["child_returncode"] == code
    assert summary["stop_reason"] is None
    assert (output.stat().st_mode & 0o777) == 0o700
    assert (output / "child.log").read_text().strip() == "ok"
    assert (output / "telemetry.jsonl").read_text()


def test_wall_timeout_and_refusal_to_overwrite(tmp_path):
    output = tmp_path / "run"
    args = [sys.executable, str(SCRIPT), "--output", str(output),
            "--wall-seconds", "1", "--", sys.executable, "-c",
            "import time; time.sleep(30)"]
    result = subprocess.run(args, timeout=10)
    assert result.returncode == 124
    summary_bytes = (output / "summary.json").read_bytes()
    assert json.loads(summary_bytes)["stop_reason"] == "wall_seconds"
    assert subprocess.run(args, capture_output=True).returncode == 2
    assert (output / "summary.json").read_bytes() == summary_bytes


def test_surviving_child_in_group_is_terminated(tmp_path):
    output = tmp_path / "run"
    marker = tmp_path / "terminated"
    ready = tmp_path / "ready"
    descendant = ("import signal,time,pathlib,sys; "
        f"signal.signal(signal.SIGTERM, lambda *_: (pathlib.Path({str(marker)!r}).write_text('yes'), sys.exit(0))); "
        f"pathlib.Path({str(ready)!r}).write_text('yes'); time.sleep(30)")
    parent = ("import subprocess,sys,pathlib,time; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); "
        f"p=pathlib.Path({str(ready)!r})\n"
        "while not p.exists(): time.sleep(0.01)\n")
    result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output),
        "--wall-seconds", "15", "--", sys.executable, "-c", parent], timeout=15)
    assert result.returncode == 0
    assert marker.read_text() == "yes"
