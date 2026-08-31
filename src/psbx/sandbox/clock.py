"""libfaketime stamp for the search sidecar.

We do not vendor https://github.com/wolfcw/libfaketime.git — Debian/Ubuntu
`libfaketime` is enough inside Docker. The agent/LLM stays on the host.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from psbx.paths import repo_root

LIB_CANDIDATES = (
    "/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1",
    "/usr/lib/aarch64-linux-gnu/faketime/libfaketime.so.1",
    "/usr/lib/faketime/libfaketime.so.1",
)

# Built from https://github.com/wolfcw/libfaketime.git (not vendored in git).
REPO_DYLIBS = (
    "third_party/libfaketime/src/libfaketime.1.dylib",
    "third_party/libfaketime/src/libfaketime.so.1",
)

DEFAULT_SOCKET = "data/runs/.sandbox/search.sock"
IMAGE = "psbx-search:local"
CONTAINER = "psbx-search"


def faketime_stamp(cutoff: date) -> str:
    """Frozen wall clock at end of cutoff day. Leading @ means 'do not advance'."""
    return f"@{cutoff.isoformat()} 12:00:00"


def _existing_lib() -> str | None:
    for rel in REPO_DYLIBS:
        path = repo_root() / rel
        if path.exists():
            return str(path)
    for path in LIB_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def faketime_env(cutoff: date, lib: str | None = None) -> dict[str, str]:
    chosen = lib or _existing_lib() or LIB_CANDIDATES[0]
    env = {
        "FAKETIME": faketime_stamp(cutoff),
        "FAKETIME_NO_CACHE": "1",
        "FAKETIME_DONT_FAKE_MONOTONIC": "1",
        "PSBX_FAKETIME": f"{cutoff.isoformat()} 12:00:00",
    }
    if chosen.endswith(".dylib"):
        env["DYLD_INSERT_LIBRARIES"] = chosen
        env["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
    else:
        env["LD_PRELOAD"] = chosen
    return env


def clock_payload(cutoff: date) -> dict[str, str | None]:
    import os

    now = datetime.now().astimezone()
    return {
        "now": now.isoformat(),
        "today": date.today().isoformat(),
        "cutoff": cutoff.isoformat(),
        "faketime": os.environ.get("FAKETIME"),
        "ld_preload": os.environ.get("LD_PRELOAD") or os.environ.get("DYLD_INSERT_LIBRARIES"),
    }
