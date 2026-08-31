"""Host libfaketime search process when Docker is not installed.

Uses third_party/libfaketime (https://github.com/wolfcw/libfaketime.git)
via DYLD_INSERT_LIBRARIES on macOS / LD_PRELOAD on Linux. No --network none
on the host; that remains the Docker path.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from psbx.config import load_epochs
from psbx.paths import repo_root, resolve
from psbx.sandbox.clock import faketime_stamp

HOST_PORT = 8766
PID_FILE = "data/runs/.sandbox/host.pid"


def dylib_path() -> Path:
    root = repo_root()
    candidates = [
        root / "third_party/libfaketime/src/libfaketime.1.dylib",
        root / "third_party/libfaketime/src/libfaketime.so.1",
        Path("/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1"),
        Path("/usr/lib/aarch64-linux-gnu/faketime/libfaketime.so.1"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError(
        "libfaketime not built. Clone https://github.com/wolfcw/libfaketime.git "
        "into third_party/libfaketime and run make, or install Docker."
    )


def pid_path() -> Path:
    dest = resolve(PID_FILE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def up(epoch_id: str = "e2012") -> str:
    down()
    epoch = load_epochs()[epoch_id]
    lib = dylib_path()
    env = os.environ.copy()
    env["FAKETIME"] = faketime_stamp(epoch.cutoff_date)
    env["FAKETIME_NO_CACHE"] = "1"
    env["FAKETIME_DONT_FAKE_MONOTONIC"] = "1"
    env["PSBX_EPOCH"] = epoch_id
    env["PSBX_FAKETIME"] = f"{epoch.cutoff_date.isoformat()} 12:00:00"
    env["PSBX_SEARCH_HOST"] = "127.0.0.1"
    env["PSBX_SEARCH_PORT"] = str(HOST_PORT)
    env.pop("PSBX_SEARCH_UDS", None)
    if lib.suffix == ".dylib":
        env["DYLD_INSERT_LIBRARIES"] = str(lib)
        env["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
    else:
        env["LD_PRELOAD"] = str(lib)
    log = resolve("data/runs/.sandbox/host.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "psbx.sandbox.search_service"],
        cwd=str(repo_root()),
        env=env,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path().write_text(str(proc.pid), encoding="utf-8")
    url = f"http://127.0.0.1:{HOST_PORT}"
    import time

    import httpx

    for _ in range(40):
        try:
            resp = httpx.get(f"{url}/clock", timeout=0.5)
            if resp.status_code == 200:
                return url
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"search sidecar did not start; see {log}")


def down() -> None:
    path = pid_path()
    if not path.exists():
        return
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, OSError, ProcessLookupError):
        pass
    path.unlink(missing_ok=True)


def status() -> dict:
    path = pid_path()
    pid = None
    running = False
    if path.exists():
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            running = True
        except (ValueError, OSError, ProcessLookupError):
            running = False
    return {
        "mode": "host-libfaketime",
        "pid": pid,
        "running": running,
        "url": f"http://127.0.0.1:{HOST_PORT}",
        "lib": str(dylib_path()) if _lib_exists() else None,
    }


def _lib_exists() -> bool:
    try:
        dylib_path()
        return True
    except RuntimeError:
        return False
