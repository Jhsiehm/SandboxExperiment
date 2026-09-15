"""Fail-closed controls for paid model calls.

Rate limits control velocity, not total cost.  This module adds a separate,
process-wide request/cost budget and a small per-run audit ledger.  Estimates
are deliberately conservative: one UTF-8 byte is treated as one possible
input token, and the full configured output allowance is reserved before the
request leaves the process.
"""

from __future__ import annotations

import json
import math
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psbx.paths import run_dir
from psbx.schemas import ModelConfig

PAID_PROVIDERS = frozenset({"anthropic", "openai", "openrouter", "together"})
DEFAULT_MAX_RUN_USD = 1.0
DEFAULT_MAX_REQUEST_USD = 0.10
DEFAULT_MAX_PAID_REQUESTS = 100
DEFAULT_MAX_INPUT_TOKENS = 16_000
PREFLIGHT_INPUT_TOKENS = 8_000
_LEDGER_MAX_BYTES = 1_000_000
UTC = timezone.utc


class SpendGuardError(RuntimeError):
    """A paid request was blocked before network I/O."""


@dataclass(frozen=True)
class SpendLimits:
    enabled: bool
    max_run_usd: float
    max_request_usd: float
    max_paid_requests: int
    max_input_tokens: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_run_usd": self.max_run_usd,
            "max_request_usd": self.max_request_usd,
            "max_paid_requests": self.max_paid_requests,
            "max_input_tokens": self.max_input_tokens,
        }


@dataclass(frozen=True)
class Reservation:
    id: str
    estimated_usd: float
    model_id: str
    provider: str


def _enabled(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def paid_models_enabled() -> bool:
    """Paid traffic requires a deliberate second switch in addition to API keys."""
    return _enabled(os.environ.get("PSBX_ENABLE_PAID_MODELS"))


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SpendGuardError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise SpendGuardError(f"{name} must be a positive finite number")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SpendGuardError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise SpendGuardError(f"{name} must be a positive integer")
    return value


def spend_limits() -> SpendLimits:
    return SpendLimits(
        enabled=paid_models_enabled(),
        max_run_usd=_positive_float("PSBX_MAX_RUN_USD", DEFAULT_MAX_RUN_USD),
        max_request_usd=_positive_float(
            "PSBX_MAX_REQUEST_USD", DEFAULT_MAX_REQUEST_USD
        ),
        max_paid_requests=_positive_int(
            "PSBX_MAX_PAID_REQUESTS", DEFAULT_MAX_PAID_REQUESTS
        ),
        max_input_tokens=_positive_int(
            "PSBX_MAX_INPUT_TOKENS", DEFAULT_MAX_INPUT_TOKENS
        ),
    )


def spend_guard_status() -> dict[str, Any]:
    """Dashboard-safe status. Never returns credentials or provider responses."""
    try:
        return {**spend_limits().public_dict(), "error": None}
    except SpendGuardError as exc:
        return {
            "enabled": False,
            "max_run_usd": None,
            "max_request_usd": None,
            "max_paid_requests": None,
            "max_input_tokens": None,
            "error": str(exc),
        }


def is_paid_model(model: ModelConfig) -> bool:
    return model.provider in PAID_PROVIDERS and model.model_name != "swarm-median"


def _require_pricing(model: ModelConfig) -> None:
    if model.cost_per_1k_input < 0 or model.cost_per_1k_output < 0:
        raise SpendGuardError(f"{model.id}: model pricing cannot be negative")
    if model.cost_per_1k_input == 0 and model.cost_per_1k_output == 0:
        raise SpendGuardError(
            f"{model.id}: paid model has no price metadata; refusing an unbudgeted request"
        )


def conservative_input_tokens(payload: Any) -> int:
    """Upper-bound common byte-level tokenizers without importing vendor SDKs."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return max(1, len(encoded) + 256)


def estimate_request_usd(
    model: ModelConfig,
    *,
    input_tokens: int,
    output_tokens: int | None = None,
) -> float:
    _require_pricing(model)
    completion_tokens = model.max_tokens if output_tokens is None else output_tokens
    return (
        input_tokens * model.cost_per_1k_input
        + completion_tokens * model.cost_per_1k_output
    ) / 1000.0


def preflight_paid_requests(
    requests: list[tuple[ModelConfig, int]],
) -> dict[str, Any]:
    """Reject a run whose conservative maximum shape exceeds local ceilings."""
    paid = [(model, int(count)) for model, count in requests if is_paid_model(model)]
    if not paid:
        return {
            "paid": False,
            "maximum_requests": 0,
            "estimated_max_usd": 0.0,
            "assumed_input_tokens_per_request": PREFLIGHT_INPUT_TOKENS,
        }
    limits = spend_limits()
    if not limits.enabled:
        raise SpendGuardError(
            "paid models are disabled; set PSBX_ENABLE_PAID_MODELS=1 only for an "
            "intentional live run"
        )
    total_requests = 0
    estimated = 0.0
    by_model: list[dict[str, Any]] = []
    for model, count in paid:
        if count < 0:
            raise SpendGuardError("paid request counts cannot be negative")
        per_request = estimate_request_usd(
            model,
            input_tokens=PREFLIGHT_INPUT_TOKENS,
        )
        if per_request > limits.max_request_usd:
            raise SpendGuardError(
                f"{model.id}: estimated request ${per_request:.4f} exceeds "
                f"PSBX_MAX_REQUEST_USD=${limits.max_request_usd:.4f}"
            )
        total_requests += count
        estimated += count * per_request
        by_model.append(
            {
                "model_id": model.id,
                "maximum_requests": count,
                "estimated_max_usd": round(count * per_request, 6),
            }
        )
    if total_requests > limits.max_paid_requests:
        raise SpendGuardError(
            f"run can make up to {total_requests} paid requests; "
            f"PSBX_MAX_PAID_REQUESTS={limits.max_paid_requests}"
        )
    if estimated > limits.max_run_usd:
        raise SpendGuardError(
            f"run preflight estimate ${estimated:.4f} exceeds "
            f"PSBX_MAX_RUN_USD=${limits.max_run_usd:.4f}"
        )
    return {
        "paid": True,
        "maximum_requests": total_requests,
        "estimated_max_usd": round(estimated, 6),
        "assumed_input_tokens_per_request": PREFLIGHT_INPUT_TOKENS,
        "by_model": by_model,
        "limits": limits.public_dict(),
        "note": "Conservative ceiling, not a bill; runtime reserves full output capacity.",
    }


class _SpendGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_id = "unscoped"
        self._ledger_path: Path | None = None
        self._request_count = 0
        self._reserved_usd = 0.0
        self._entries: list[dict[str, Any]] = []

    def begin_run(self, run_id: str) -> None:
        path = run_dir(run_id) / "spend_ledger.json"
        request_count = 0
        reserved = 0.0
        entries: list[dict[str, Any]] = []
        if path.is_file() and path.stat().st_size > _LEDGER_MAX_BYTES:
            raise SpendGuardError(
                f"{run_id}: spend ledger is unexpectedly large; choose a new run id or repair it"
            )
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("run_id") == run_id:
                    request_count = max(0, int(payload.get("reserved_requests") or 0))
                    reserved = max(0.0, float(payload.get("reserved_usd") or 0.0))
                    raw_entries = payload.get("entries") or []
                    if isinstance(raw_entries, list):
                        entries = [row for row in raw_entries if isinstance(row, dict)]
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # A malformed ledger must never erase prior spend assumptions.
                raise SpendGuardError(
                    f"{run_id}: spend ledger is unreadable; choose a new run id or repair it"
                ) from None
        with self._lock:
            self._run_id = run_id
            self._ledger_path = path
            self._request_count = request_count
            self._reserved_usd = reserved
            self._entries = entries

    def reserve(self, model: ModelConfig, payload: Any) -> Reservation | None:
        if not is_paid_model(model):
            return None
        limits = spend_limits()
        if not limits.enabled:
            raise SpendGuardError(
                "paid models are disabled; set PSBX_ENABLE_PAID_MODELS=1 only for an "
                "intentional live run"
            )
        input_tokens = conservative_input_tokens(payload)
        if input_tokens > limits.max_input_tokens:
            raise SpendGuardError(
                f"{model.id}: conservative input size {input_tokens} tokens exceeds "
                f"PSBX_MAX_INPUT_TOKENS={limits.max_input_tokens}"
            )
        estimated = estimate_request_usd(model, input_tokens=input_tokens)
        if estimated > limits.max_request_usd:
            raise SpendGuardError(
                f"{model.id}: request estimate ${estimated:.4f} exceeds "
                f"PSBX_MAX_REQUEST_USD=${limits.max_request_usd:.4f}"
            )
        reservation = Reservation(
            id=uuid.uuid4().hex,
            estimated_usd=estimated,
            model_id=model.id,
            provider=model.provider,
        )
        with self._lock:
            if self._request_count + 1 > limits.max_paid_requests:
                raise SpendGuardError(
                    f"paid request limit reached ({limits.max_paid_requests}); request blocked"
                )
            projected = self._reserved_usd + estimated
            if projected > limits.max_run_usd:
                raise SpendGuardError(
                    f"run spend reservation would reach ${projected:.4f}; "
                    f"PSBX_MAX_RUN_USD=${limits.max_run_usd:.4f}"
                )
            self._request_count += 1
            self._reserved_usd = projected
            self._entries.append(
                {
                    "reservation_id": reservation.id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "provider": model.provider,
                    "model_id": model.id,
                    "model_name": model.model_name,
                    "conservative_input_tokens": input_tokens,
                    "max_output_tokens": model.max_tokens,
                    "estimated_usd": round(estimated, 8),
                    "reported_usage": None,
                }
            )
            self._write_locked(limits)
        return reservation

    def record_usage(
        self,
        reservation: Reservation | None,
        usage: Any,
        model: ModelConfig,
    ) -> None:
        if reservation is None or not isinstance(usage, dict):
            return
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        reported_cost = usage.get("cost")
        safe: dict[str, Any] = {}
        try:
            if prompt is not None:
                safe["input_tokens"] = max(0, int(prompt))
            if completion is not None:
                safe["output_tokens"] = max(0, int(completion))
            if reported_cost is not None:
                value = float(reported_cost)
                if math.isfinite(value) and value >= 0:
                    safe["provider_cost_usd"] = round(value, 8)
            elif "input_tokens" in safe and "output_tokens" in safe:
                safe["calculated_cost_usd"] = round(
                    estimate_request_usd(
                        model,
                        input_tokens=safe["input_tokens"],
                        output_tokens=safe["output_tokens"],
                    ),
                    8,
                )
        except (TypeError, ValueError):
            return
        with self._lock:
            for entry in reversed(self._entries):
                if entry.get("reservation_id") == reservation.id:
                    entry["reported_usage"] = safe
                    break
            self._write_locked(spend_limits())

    def _write_locked(self, limits: SpendLimits) -> None:
        if self._ledger_path is None:
            return
        payload = {
            "schema_version": 1,
            "run_id": self._run_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "reserved_requests": self._request_count,
            "reserved_usd": round(self._reserved_usd, 8),
            "limits": limits.public_dict(),
            "entries": self._entries,
        }
        path = self._ledger_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)


_GUARD = _SpendGuard()


def begin_spend_run(run_id: str) -> None:
    _GUARD.begin_run(run_id)


def reserve_paid_request(model: ModelConfig, payload: Any) -> Reservation | None:
    return _GUARD.reserve(model, payload)


def record_paid_usage(
    reservation: Reservation | None,
    usage: Any,
    model: ModelConfig,
) -> None:
    _GUARD.record_usage(reservation, usage, model)


def reset_spend_guard_for_tests() -> None:
    global _GUARD
    _GUARD = _SpendGuard()
