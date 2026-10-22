"""Safe operational events and honest saved-checkpoint replay for study scenes.

No respondent rows, prompts, messages, predictions or outcome values are returned.
Historical replay records artifact availability, never invented intermediate actions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

from psbx.paths import repo_root

RUNS = {
    "individual": "anes2012-ohio-individual-development-20261020",
    "ablation": "anes2012-ohio-profile-ablation-development-v1",
    "debate": "debate-isolated-social-pilot-20261014",
}
STUDIES = {*RUNS, "forecast", "oregon", "reserve"}
PAGE_SIZE = 120
MAX_FILES = 10000
MAX_FILE_BYTES = 2_000_000
MAX_TELEMETRY_BYTES = 8_000_000
PHASES = {
    "preparation",
    "final",
    "review",
    "message",
    "evaluation",
    "forecast",
    "original_sparse",
    "original_rich",
    "reduced_existing",
    "reduced_plus_observed",
    "sparse_direct",
    "rich_direct",
    "focused_direct",
    "focused_review",
    "private",
    "swarm",
    "replay",
    "conversation",
    "retrieval",
    "reflection",
}
KINDS = {
    "run_started": "Study invocation started.",
    "agent_started": "Agent work started.",
    "model_requested": "Model response requested.",
    "response_received": "Model response received.",
    "checkpoint_saved": "Checkpoint saved.",
    "dialogue_phase": "Recorded dialogue phase advanced.",
    "message_sent": "Generated message saved; message content is hidden.",
    "evaluation_ready": "Predictions sealed and ready for evaluation.",
    "evaluated": "Saved evaluation report available.",
    "run_completed": "Study invocation completed.",
    "run_failed": "Study invocation reported a failure; inspect the local run log.",
}
_CACHE = {}
_LOCK = threading.Lock()


def _read(path, limit=MAX_FILE_BYTES):
    try:
        if path.is_symlink() or path.stat().st_size > limit:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _time(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _ordinal(label, value):
    return f"{label} {value:02d}" if type(value) is int and 0 < value <= MAX_FILES else None


def _event(seq, kind, *, at=None, actor=None, group=None, phase=None):
    return dict(
        seq=seq,
        id=str(seq),
        at=at,
        kind=kind,
        actor=actor,
        group=group,
        phase=phase if isinstance(phase, str) and phase in PHASES else None,
        model=None,
        summary=KINDS[kind],
    )


def _live(status):
    at = _time(status.get("heartbeat_at", status.get("at")))
    if status.get("status") != "running" or not at:
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds()
    lease = _number(status.get("lease_seconds"))
    if lease is None or not 0 <= age <= min(lease, 30):
        return False
    pid = status.get("pid")
    identity = status.get("process_start")
    if type(pid) is not int or pid <= 0 or not identity:
        return False
    try:
        from psbx.experiments.telemetry import process_identity

        return process_identity(pid) == identity
    except (ImportError, OSError, ValueError):
        return False


def _telemetry(directory):
    status = _read(directory / "visual_status.json")
    session = status.get("session_id")
    if not isinstance(session, str) or not session or len(session) > 80:
        return None
    path = directory / "visual_events.jsonl"
    events = []
    capped = False
    try:
        if path.is_symlink():
            return None
        with path.open("rb") as handle:
            consumed = 0
            for _ in range(MAX_FILES):
                line = handle.readline(16385)
                if not line:
                    break
                consumed += len(line)
                if len(line) > 16384 or consumed > MAX_TELEMETRY_BYTES:
                    capped = True
                    break
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeError):
                    continue  # Includes a partial last append.
                if not isinstance(row, dict) or row.get("session_id") != session:
                    continue
                seq, kind = row.get("seq"), row.get("kind")
                if (
                    type(seq) is not int
                    or seq <= 0
                    or not isinstance(kind, str)
                    or kind not in KINDS
                ):
                    continue
                events.append(
                    _event(
                        seq,
                        kind,
                        at=_time(row.get("at")),
                        actor=_ordinal("Agent", row.get("agent")),
                        group=_ordinal("Group", row.get("group")),
                        phase=row.get("phase"),
                    )
                )
            else:
                capped = bool(handle.read(1))
    except OSError:
        return None
    # Append order and sequence are supplied by the instrumented worker.
    events = sorted({e["seq"]: e for e in events}.values(), key=lambda e: e["seq"])
    return events, status, session, capped


def _replay(directory):
    """Append-only in-memory index makes cursors stable as new files arrive.

    New server processes get a new session ID; clients reset their cursor then.
    Ordering is discovery order, not historical execution chronology.
    """
    key = str(directory.resolve())
    with _LOCK:
        if key not in _CACHE:
            if len(_CACHE) >= 32:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = dict(
                session=uuid.uuid4().hex, seen=set(), events=[], actors={}, groups={}
            )
        cache = _CACHE[key]
        try:
            files = (
                []
                if (directory / "checkpoints").is_symlink()
                else list(islice((directory / "checkpoints").glob("*.json"), MAX_FILES + 1))
            )
        except OSError:
            files = []
        capped = len(files) > MAX_FILES
        for path in sorted(files[:MAX_FILES]):
            if path.name in cache["seen"]:
                continue
            row = _read(path)
            metadata = row.get("metadata")
            if not isinstance(metadata, dict):
                continue
            cache["seen"].add(path.name)
            aliases = {}
            for name, value in [
                ("actor", metadata.get("person", metadata.get("agent"))),
                ("group", metadata.get("group")),
            ]:
                mapping = cache["actors" if name == "actor" else "groups"]
                if isinstance(value, str) and len(value) <= 200:
                    opaque = hashlib.sha256(value.encode()).hexdigest()
                    mapping.setdefault(opaque, len(mapping) + 1)
                    aliases[name] = _ordinal(
                        "Agent" if name == "actor" else "Group", mapping[opaque]
                    )
            cache["events"].append(
                _event(
                    len(cache["events"]) + 1,
                    "checkpoint_saved",
                    phase=metadata.get("stage", metadata.get("arm")),
                    **aliases,
                )
            )
        if (directory / "evaluation.json").is_file() and "__evaluation__" not in cache["seen"]:
            cache["seen"].add("__evaluation__")
            cache["events"].append(
                _event(len(cache["events"]) + 1, "evaluated", phase="evaluation")
            )
        return list(cache["events"]), cache["session"], capped


def _run_options(base, study_id):
    options = []
    seen = set()
    candidates = [base / "data" / "runs" / RUNS[study_id]]
    try:
        candidates += list(islice((base / "data" / "runs").iterdir(), 2000))
    except OSError:
        pass
    for path in candidates:
        if path.name in seen or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", path.name):
            continue
        seen.add(path.name)
        if not path.is_dir() or not path.resolve().is_relative_to(base):
            continue
        status = _read(path / "visual_status.json", 16384)
        if path.name != RUNS[study_id] and status.get("study_id") != study_id:
            continue
        live = _live(status)
        options.append(
            dict(
                id=path.name,
                label=path.name,
                mode="live" if live else "replay",
                heartbeat_at=_time(status.get("heartbeat_at", status.get("at"))),
            )
        )
    return options


def build_research_activity(study_id, root: Path | None = None, after=0, run_id=None, tail=False):
    """Return up to 120 safe events after a session-scoped integer cursor."""
    if study_id not in STUDIES:
        raise ValueError("Unknown study")
    if type(after) is not int or after < 0:
        raise ValueError("after must be a non-negative integer")
    base = (root or repo_root()).resolve()
    result = dict(
        study_id=study_id,
        run_id=RUNS.get(study_id),
        mode="idle",
        status="unavailable",
        session_id=None,
        events=[],
        next_after=after,
        has_more=False,
        coverage=dict(
            source=None,
            available_events=0,
            returned_events=0,
            completed=None,
            total=None,
            truncated=False,
        ),
        limitations=[
            "Scenes depict recorded actions or saved checkpoints, not human behavior.",
            "No prompts, messages, private profiles, predictions "
            "or evaluation targets are exposed.",
        ],
    )
    if study_id in {"oregon", "reserve"}:
        result.update(
            mode="unsupported", status="offline_reference" if study_id == "oregon" else "protected"
        )
        result["limitations"].append("No instrumented agent execution is available for this study.")
        return result
    if study_id == "forecast":
        from leaderboard.jobs import get_job

        job = get_job() if root is None else {}
        status = job.get("status", "idle")
        result.update(
            run_id=job.get("run_id"), status=status, mode="live" if status == "running" else "idle"
        )
        result["session_id"] = str(job.get("started_at")) if job.get("started_at") else None
        result["coverage"]["source"] = "dashboard_job_state"
        result["limitations"].append(
            "Forecast job state is available; per-agent action telemetry is not recorded here."
        )
        return result
    options = _run_options(base, study_id)
    result["runs"] = options
    if run_id is not None and run_id not in {option["id"] for option in options}:
        raise ValueError("Unknown run for this study")
    live_options = sorted(
        (o for o in options if o["mode"] == "live"),
        key=lambda o: o["heartbeat_at"] or "",
        reverse=True,
    )
    chosen = run_id or (live_options[0]["id"] if live_options else RUNS[study_id])
    result["run_id"] = chosen
    directory = base / "data" / "runs" / chosen
    # Refuse symlink escapes even for the fixed allowlisted study paths.
    if not directory.resolve().is_relative_to(base):
        return result
    contract = _read(directory / "contract.json")
    config = contract.get("config") if isinstance(contract.get("config"), dict) else {}
    result["coverage"]["total"] = _number(config.get("planned_calls"))
    telemetry = _telemetry(directory)
    if telemetry is not None:
        events, status, session, capped = telemetry
        live = _live(status)
        result.update(
            mode="live" if live else ("replay" if events else "idle"),
            status="running"
            if live
            else (
                "recorded_" + status["status"]
                if isinstance(status.get("status"), str)
                and status.get("status") in {"completed", "failed", "error"}
                else "liveness_unconfirmed"
            ),
            session_id=session,
        )
        result["coverage"]["source"] = "visual_events"
        result["coverage"]["completed_scope"] = (
            "checkpoint events in this invocation; resumes exclude prior checkpoints"
        )
        result["limitations"].append(
            "Live requires a current explicit heartbeat and matching process identity."
        )
    else:
        events, session, capped = _replay(directory)
        result.update(
            mode="replay" if events else "idle",
            status="saved_artifacts" if events else "unavailable",
            session_id=session,
        )
        result["coverage"]["source"] = "checkpoint_inventory"
        result["coverage"]["completed_scope"] = "saved checkpoints across the run"
        result["limitations"].append(
            "Historic checkpoint discovery order is not execution time. "
            "Intermediate actions were not recorded."
        )
    recent_window = tail is True and result["mode"] == "live"
    page = (
        events[-PAGE_SIZE:]
        if recent_window
        else [e for e in events if e["seq"] > after][:PAGE_SIZE]
    )
    result.update(
        events=page,
        next_after=page[-1]["seq"] if page else after,
        has_more=False
        if recent_window
        else bool(page and any(e["seq"] > page[-1]["seq"] for e in events)),
    )
    result["coverage"].update(
        available_events=len(events),
        returned_events=len(page),
        first_seq=page[0]["seq"] if page else None,
        prior_events=sum(e["seq"] < page[0]["seq"] for e in events) if page else 0,
        recent_window=recent_window,
        completed=sum(e["kind"] == "checkpoint_saved" for e in events),
        truncated=capped,
    )
    return result
