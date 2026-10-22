"""Best-effort, content-free observations of experiment orchestration.

These operational files are not scientific inputs, checkpoints or result seals.
A model request is observable; private reasoning and human mental states are not.
"""
from __future__ import annotations

import contextvars
import functools
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

EVENTS = frozenset({
    "run_started", "agent_started", "model_requested", "response_received",
    "checkpoint_saved", "message_sent", "evaluation_ready", "run_completed", "run_failed",
})
PHASES = frozenset({"preparation", "final", "review", "message", "evaluation"})
LEASE_SECONDS = 20
_active = contextvars.ContextVar("experiment_visual_telemetry", default=None)


def process_identity(pid: int) -> str | None:
    """Return process birth identity, or None when it cannot be verified.

    Readers must also check a fresh lease. A reused PID alone is not sufficient.
    """
    try:
        if type(pid) is not int or pid <= 0:
            return None
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            body = stat.read_text().rsplit(")", 1)[1].split()
            if body[0] == "Z":
                return None
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            return f"linux:{boot}:{body[19]}"
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart=", "-o", "stat="],
            capture_output=True, text=True, timeout=1, check=True,
        )
        fields = result.stdout.strip().split()
        if len(fields) < 6 or fields[-1].startswith("Z"):
            return None
        return "ps:" + " ".join(fields[:-1])
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc).isoformat()


class Observer:
    """One invocation's anonymous action stream and expiring process lease."""

    def __init__(self, root, study_id=None):
        self.root = Path(root)
        self.study_id = study_id if study_id in {"individual", "ablation", "debate"} else None
        self.session_id = uuid4().hex
        self.pid = os.getpid()
        self.process_start = process_identity(self.pid)
        self.seq = 0
        self.agents = {}
        self.status = "running"
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None

    def _heartbeat(self):
        temporary = self.root / f".visual-status-{self.session_id}.tmp"
        try:
            record = dict(
                schema="psbx-visual-status-v1", session_id=self.session_id, study_id=self.study_id,
                pid=self.pid, process_start=self.process_start, at=_now(),
                lease_seconds=LEASE_SECONDS, status=self.status, seq=self.seq,
            )
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(record, handle)
            os.replace(temporary, self.root / "visual_status.json")
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass

    def emit(self, kind, *, agent_key=None, phase="preparation"):
        try:
            if kind not in EVENTS or phase not in PHASES:
                return
            with self.lock:
                actor = None
                if agent_key is not None:
                    # Mapping is memory-only; no respondent identifier is serialized.
                    actor = self.agents.setdefault(agent_key, len(self.agents) + 1)
                self.seq += 1
                record = dict(
                    schema="psbx-visual-events-v1", session_id=self.session_id,
                    seq=self.seq, at=_now(), kind=kind, phase=phase,
                )
                if actor is not None:
                    record["agent"] = actor
                fd = os.open(
                    self.root / "visual_events.jsonl",
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600,
                )
                with os.fdopen(fd, "w") as handle:
                    handle.write(json.dumps(record) + "\n")
                self._heartbeat()
        except Exception:
            pass

    def start(self):
        try:
            self.emit("run_started")
            def beat():
                while not self.stop.wait(5):
                    with self.lock:
                        self._heartbeat()
            self.thread = threading.Thread(target=beat, daemon=True, name="experiment-telemetry")
            self.thread.start()
        except Exception:
            pass

    def finish(self, failed=False):
        try:
            self.stop.set()
            if self.thread:
                self.thread.join(timeout=1)
            self.status = "failed" if failed else "completed"
            if not failed:
                self.emit("evaluation_ready", phase="evaluation")
            self.emit("run_failed" if failed else "run_completed")
        except Exception:
            pass


def observe(kind, *, agent_key=None, phase="preparation"):
    """Discard unknown fields by signature; never serialize arbitrary metadata."""
    try:
        current = _active.get()
        if current is not None:
            current.emit(kind, agent_key=agent_key, phase=phase)
    except Exception:
        pass


def observed_run(function=None, *, study_id=None):
    """Observe a prediction-producing runner without changing its result/errors."""
    if function is None:
        return lambda target: observed_run(target, study_id=study_id)

    @functools.wraps(function)
    def wrapped(root, *args, **kwargs):
        observer = None
        token = None
        try:
            observer = Observer(root, study_id=study_id)
            token = _active.set(observer)
            observer.start()
        except Exception:
            pass
        failed = True
        try:
            result = function(root, *args, **kwargs)
            failed = False
            return result
        finally:
            if observer is not None:
                observer.finish(failed)
            if token is not None:
                _active.reset(token)
    return wrapped
