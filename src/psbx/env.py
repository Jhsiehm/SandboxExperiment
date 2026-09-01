"""Load repo-root .env without overriding already-set process env."""

from __future__ import annotations

import os

from psbx.paths import repo_root


def load_dotenv() -> None:
    path = repo_root() / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Process env wins, including an explicit empty value. Tests isolate by
        # setting keys to "" — do not refill those from .env.
        if key and key not in os.environ:
            os.environ[key] = value


def _present(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def provider_status() -> dict[str, bool]:
    load_dotenv()
    return {
        "anthropic": _present("ANTHROPIC_API_KEY"),
        "openai": _present("OPENAI_API_KEY"),
        "together": _present("TOGETHER_API_KEY"),
        "vllm": bool((os.environ.get("VLLM_BASE_URL") or "").strip()),
        "openrouter": _present("OPENROUTER_API_KEY"),
    }


def live_ready() -> bool:
    """True if OpenRouter is set, or both native Anthropic and OpenAI keys."""
    status = provider_status()
    if status["openrouter"]:
        return True
    return bool(status["anthropic"] and status["openai"])
