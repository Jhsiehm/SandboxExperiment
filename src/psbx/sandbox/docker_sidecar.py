"""Run the search sidecar with libfaketime and no outbound internet.

Docker Desktop on Mac cannot host a Unix socket on a bind-mounted folder
(`chmod` on the socket returns EINVAL). `--network none` also cannot publish
TCP ports. The sidecar therefore publishes 127.0.0.1:8766 and drops outbound
packets with iptables (needs NET_ADMIN). Vendor LLM calls stay on the host.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from psbx.config import load_epochs
from psbx.corpus.index import source_silo_path
from psbx.paths import repo_root, resolve
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
            raise RuntimeError(f"search sidecar exited ({status}):\n{logs.stdout}{logs.stderr}")
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


def _index_mount(epoch_id: str, source_type: str | None = None) -> tuple[str, str]:
    epoch = load_epochs()[epoch_id]
    host_path = (
        source_silo_path(epoch, source_type) if source_type else resolve(epoch.corpus_index_path)
    )
    if not (host_path / "meta.json").is_file():
        selection = f"/{source_type}" if source_type else ""
        raise RuntimeError(
            f"missing corpus index for {epoch_id}{selection}: {host_path}. "
            f"Run: psbx corpus build --epoch {epoch_id}"
        )
    container_path = f"/app/{epoch.corpus_index_path.strip('/')}"
    return str(host_path), container_path


def up(epoch_id: str = "e2012", source_type: str | None = None) -> str:
    epoch = load_epochs()[epoch_id]
    env = faketime_env(epoch.cutoff_date)
    root = repo_root()
    host_index, container_index = _index_mount(epoch_id, source_type)
    subprocess.run([docker_bin(), "rm", "-f", CONTAINER], check=False, capture_output=True)
    cmd = [
        docker_bin(),
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--security-opt",
        "no-new-privileges:true",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "NET_ADMIN",
        # These are used only by the root entrypoint to switch to the psbx
        # account after installing the firewall. setpriv and no-new-privs
        # ensure the long-running service cannot regain them.
        "--cap-add",
        "SETUID",
        "--cap-add",
        "SETGID",
        "--pids-limit",
        "128",
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
        f"PSBX_ACTIVE_SOURCE_TYPE={source_type or 'all'}",
        "-e",
        f"FAKETIME={env['FAKETIME']}",
        "-v",
        f"{host_index}:{container_index}:ro",
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
    proof = {
        "read_only_rootfs": False,
        "mounts_read_only": False,
        "no_new_privileges": False,
        "loopback_only": False,
        "egress_lock_requested": False,
        "pids_limit": None,
        "verified_controls": False,
    }
    if running:
        inspected = subprocess.run(
            [docker_bin(), "inspect", CONTAINER],
            capture_output=True,
            text=True,
        )
        if inspected.returncode == 0:
            try:
                info = json.loads(inspected.stdout)[0]
                host = info.get("HostConfig") or {}
                config = info.get("Config") or {}
                mounts = info.get("Mounts") or []
                env = {
                    item.split("=", 1)[0]: item.split("=", 1)[1]
                    for item in config.get("Env") or []
                    if "=" in item
                }
                bindings = host.get("PortBindings") or {}
                published = [row for rows in bindings.values() for row in (rows or [])]
                proof.update(
                    {
                        "read_only_rootfs": bool(host.get("ReadonlyRootfs")),
                        "mounts_read_only": bool(mounts)
                        and all(not bool(mount.get("RW")) for mount in mounts),
                        "no_new_privileges": any(
                            "no-new-privileges" in str(value)
                            for value in host.get("SecurityOpt") or []
                        ),
                        "loopback_only": bool(published)
                        and all(row.get("HostIp") == "127.0.0.1" for row in published),
                        "egress_lock_requested": env.get("PSBX_LOCK_EGRESS") == "1",
                        "pids_limit": host.get("PidsLimit"),
                    }
                )
                proof["verified_controls"] = all(
                    proof[key]
                    for key in (
                        "read_only_rootfs",
                        "mounts_read_only",
                        "no_new_privileges",
                        "loopback_only",
                        "egress_lock_requested",
                    )
                )
            except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
    return {
        "container": CONTAINER,
        "running": running,
        "url": f"http://127.0.0.1:{HOST_PORT}",
        "egress": "iptables-drop",
        **proof,
    }
