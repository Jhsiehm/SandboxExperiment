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
        if key and key not in os.environ:
            os.environ[key] = value


def provider_status() -> dict[str, bool]:
    load_dotenv()
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "together": bool(os.environ.get("TOGETHER_API_KEY")),
        "vllm": bool(os.environ.get("VLLM_BASE_URL")),
    }


def live_ready() -> bool:
    status = provider_status()
    return bool(status["anthropic"] and status["openai"])
