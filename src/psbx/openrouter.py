"""OpenRouter client with a hard process-wide rate limiter.

Never log the API key. Swarm/worker completions default to a short max_tokens cap.

A 12-agent swarm (8 mini + 4 Haiku) × N questions at MIN_INTERVAL 2s is slow
on purpose. Keep concurrency at 1. Do not weaken OPENROUTER_MIN_INTERVAL_SEC,
OPENROUTER_MAX_PER_MINUTE, or OPENROUTER_MAX_CONCURRENCY.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from psbx.env import load_dotenv

log = logging.getLogger("psbx.openrouter")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MIN_INTERVAL_SEC = 2.0
DEFAULT_MAX_PER_MINUTE = 20
DEFAULT_MAX_CONCURRENCY = 1
DEFAULT_MAX_TOKENS = 256
HTTP_REFERER = "http://127.0.0.1:8765"
X_TITLE = "Prediction Sandbox"
_429_BACKOFFS = (15.0, 30.0)
_MAX_429_RETRIES = 2


def _emit(msg: str) -> None:
    print(msg, flush=True)
    log.info(msg)


def _error_snippet(resp: httpx.Response) -> str:
    """Short provider error for logs. Never echo API keys or auth headers."""
    text = (resp.text or "").strip().replace("\r", " ").replace("\n", " ")
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if key and key in text:
        text = text.replace(key, "[redacted]")
    low = text.lower()
    if "bearer " in low or "authorization" in low:
        return "[redacted body]"
    if len(text) > 400:
        text = text[:400] + "…"
    return text or "(empty body)"


def min_interval_sec() -> float:
    raw = os.environ.get("OPENROUTER_MIN_INTERVAL_SEC", str(DEFAULT_MIN_INTERVAL_SEC))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_MIN_INTERVAL_SEC


def max_per_minute() -> int:
    raw = os.environ.get("OPENROUTER_MAX_PER_MINUTE", str(DEFAULT_MAX_PER_MINUTE))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_PER_MINUTE


def max_concurrency() -> int:
    raw = os.environ.get("OPENROUTER_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CONCURRENCY


def capped_max_tokens(requested: int | None) -> int:
    raw = os.environ.get("OPENROUTER_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
    try:
        cap = max(1, int(raw))
    except ValueError:
        cap = DEFAULT_MAX_TOKENS
    if requested is None:
        return cap
    return max(1, min(int(requested), cap))


def base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


class OpenRouterGate:
    """Global limiter: min spacing, rolling per-minute cap, and concurrency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._in_flight = 0
        self._last: float | None = None
        self._times: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._times and self._times[0] <= cutoff:
            self._times.popleft()

    def _delay_locked(self, now: float) -> float:
        wait = 0.0
        interval = min_interval_sec()
        if self._last is not None:
            wait = max(wait, interval - (now - self._last))
        fire_at = now + wait
        self._prune(fire_at)
        cap = max_per_minute()
        if len(self._times) >= cap:
            wait = max(wait, self._times[0] + 60.0 - now)
        if self._in_flight >= max_concurrency():
            wait = max(wait, 0.05)
        return wait

    def acquire(self) -> None:
        while True:
            with self._cv:
                now = time.monotonic()
                delay = self._delay_locked(now)
                if delay <= 0 and self._in_flight < max_concurrency():
                    self._in_flight += 1
                    stamp = time.monotonic()
                    self._last = stamp
                    self._times.append(stamp)
                    return
            _emit("openrouter rate-limit wait")
            time.sleep(max(delay, 0.05))

    def release(self) -> None:
        with self._cv:
            self._in_flight = max(0, self._in_flight - 1)
            self._cv.notify_all()

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


_GATE = OpenRouterGate()


def reset_gate_for_tests() -> None:
    global _GATE
    _GATE = OpenRouterGate()


def chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """POST /chat/completions. Rate-limited. Raises after two 429 retries."""
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY") or ""
    if not key.strip():
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": capped_max_tokens(max_tokens),
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    headers = {
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "HTTP-Referer": HTTP_REFERER,
        "X-Title": X_TITLE,
    }
    url = f"{base_url()}/chat/completions"
    retries = 0
    while True:
        with _GATE.slot():
            resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        _emit(f"openrouter status={resp.status_code}")
        if resp.status_code == 429:
            if retries >= _MAX_429_RETRIES:
                raise RuntimeError("openrouter status=429")
            backoff = _429_BACKOFFS[retries]
            _emit("openrouter rate-limit wait")
            time.sleep(backoff)
            retries += 1
            continue
        if resp.status_code >= 400:
            snippet = _error_snippet(resp)
            _emit(f"openrouter status={resp.status_code} body={snippet}")
            raise RuntimeError(f"openrouter status={resp.status_code} body={snippet}")
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("openrouter returned a non-object body")
        return data
