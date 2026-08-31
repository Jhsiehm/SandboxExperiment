"""Run the search sidecar with libfaketime and no outbound internet.

Docker Desktop on Mac cannot host a Unix socket on a bind-mounted folder
(`chmod` on the socket returns EINVAL). `--network none` also cannot publish
TCP ports. The sidecar therefore publishes 127.0.0.1:8766 and drops outbound
packets with iptables (needs NET_ADMIN). Vendor LLM calls stay on the host.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request

from psbx.config import load_epochs
from psbx.paths import repo_root
from psbx.sandbox.clock import CONTAINER, IMAGE, faketime_env
from psbx.sandbox.host_sidecar import HOST_PORT

DOCKERFILE = "src/psbx/sandbox/Dockerfile"


def docker_bin() -> str:
    path = shutil.which("docker")
    if not path:
        raise RuntimeError(
            "Docker is required for the faketime search sidecar. "
            "Install Docker Desktop, then: psbx sandbox up --epoch e2012"
        )
    return path


def build_image() -> None:
    root = repo_root()
    subprocess.run(
        [docker_bin(), "build", "-f", str(root / DOCKERFILE), "-t", IMAGE, str(root)],
        check=True,
    )


def _wait_healthy(timeout: float = 40.0) -> None:
    url = f"http://127.0.0.1:{HOST_PORT}/health"
    deadline = time.time() + timeout
    last = "not started"
    while time.time() < deadline:
        inspect = subprocess.run(
            [docker_bin(), "inspect", "-f", "{{.State.Status}}", CONTAINER],
            capture_output=True,
            text=True,
        )
        status = inspect.stdout.strip()
        if status != "running":
            logs = subprocess.run(
                [docker_bin(), "logs", "--tail", "40", CONTAINER],
                capture_output=True,
                text=True,
            )
            raise RuntimeError(
                f"search sidecar exited ({status}):\n{logs.stdout}{logs.stderr}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = str(exc)
        time.sleep(0.4)
    logs = subprocess.run(
        [docker_bin(), "logs", "--tail", "40", CONTAINER],
        capture_output=True,
        text=True,
    )
    raise RuntimeError(
        f"search sidecar did not become healthy at {url}: {last}\n{logs.stdout}{logs.stderr}"
    )


def up(epoch_id: str = "e2012") -> str:
    epoch = load_epochs()[epoch_id]
    env = faketime_env(epoch.cutoff_date)
    root = repo_root()
    subprocess.run([docker_bin(), "rm", "-f", CONTAINER], check=False, capture_output=True)
    cmd = [
        docker_bin(),
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--cap-add",
        "NET_ADMIN",
        "-p",
        f"127.0.0.1:{HOST_PORT}:{HOST_PORT}",
        "-e",
        f"PSBX_EPOCH={epoch_id}",
        "-e",
        f"PSBX_FAKETIME={epoch.cutoff_date.isoformat()} 12:00:00",
        "-e",
        "PSBX_ROOT=/app",
        "-e",
        "PSBX_SEARCH_HOST=0.0.0.0",
        "-e",
        f"PSBX_SEARCH_PORT={HOST_PORT}",
        "-e",
        "PSBX_LOCK_EGRESS=1",
        "-e",
        f"FAKETIME={env['FAKETIME']}",
        "-v",
        f"{root / 'data' / 'corpus'}:/app/data/corpus:ro",
        "-v",
        f"{root / 'config'}:/app/config:ro",
        IMAGE,
    ]
    subprocess.run(cmd, check=True)
    _wait_healthy()
    return f"http://127.0.0.1:{HOST_PORT}"


def down() -> None:
    subprocess.run([docker_bin(), "rm", "-f", CONTAINER], check=False)


def status() -> dict:
    proc = subprocess.run(
        [docker_bin(), "inspect", "-f", "{{.State.Status}}", CONTAINER],
        capture_output=True,
        text=True,
    )
    running = proc.returncode == 0 and proc.stdout.strip() == "running"
    return {
        "container": CONTAINER,
        "running": running,
        "url": f"http://127.0.0.1:{HOST_PORT}",
        "egress": "iptables-drop",
    }
