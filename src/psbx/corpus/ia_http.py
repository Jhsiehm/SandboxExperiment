"""Internet Archive HTTP client. Build-time only — not the agent search loop.

Follows archive.org bot guidance: descriptive User-Agent, delays, honor 429
and Retry-After. See https://archive.org/developers/bots.html
"""

from __future__ import annotations

import os
import time
from email.utils import parsedate_to_datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_UA = "PredictionSandbox/0.1.0 (psbx; corpus-builder)"
MAX_RETRY_AFTER_S = 120.0


class IARetry(Exception):
    """Raised after sleeping for a 429 so tenacity retries the request."""


def user_agent() -> str:
    """Product UA plus optional suffix (required when an AI agent drives the crawl)."""
    suffix = os.environ.get("PSBX_IA_USER_AGENT_SUFFIX", "").strip()
    if suffix:
        return f"{DEFAULT_UA} {suffix}"
    return DEFAULT_UA


def parse_retry_after(value: str | None) -> float:
    if not value:
        return 30.0
    raw = value.strip()
    try:
        seconds = float(raw)
        return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
        delta = when.timestamp() - time.time()
        return min(max(delta, 0.0), MAX_RETRY_AFTER_S)
    except (TypeError, ValueError, OverflowError):
        return 30.0


class Pace:
    def __init__(self, seconds: float) -> None:
        self.seconds = max(float(seconds), 0.0)
        self._last = 0.0

    def wait(self) -> None:
        if self.seconds <= 0:
            return
        now = time.monotonic()
        gap = self._last + self.seconds - now
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


def ia_client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=60.0,
        headers={"User-Agent": user_agent()},
    )


@retry(
    retry=retry_if_exception_type((IARetry, httpx.TransportError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(min=2, max=30),
)
def ia_get(client: httpx.Client, url: str, *, pace: Pace | None = None) -> httpx.Response:
    if pace is not None:
        pace.wait()
    resp = client.get(url)
    if resp.status_code == 429:
        time.sleep(parse_retry_after(resp.headers.get("Retry-After")))
        raise IARetry(f"429 {url}")
    if resp.status_code >= 500:
        raise IARetry(f"{resp.status_code} {url}")
    resp.raise_for_status()
    return resp
