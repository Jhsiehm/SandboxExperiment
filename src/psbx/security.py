"""Small, explicit security boundaries shared by local PSBX processes."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

_BASE_CHILD_ENV = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "NO_COLOR",
        "PATH",
        "PYTHONPATH",
        "PSBX_AGENTSOCIETY_ROOT",
        "PSBX_ROOT",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
        "VIRTUAL_ENV",
    }
)

# Dashboard model jobs need only these named credentials/settings. In particular,
# unrelated tokens and cloud credentials must not cross the subprocess boundary.
_MODEL_CHILD_ENV = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_MAX_CONCURRENCY",
        "OPENROUTER_MAX_PER_MINUTE",
        "OPENROUTER_MAX_TOKENS",
        "OPENROUTER_MIN_INTERVAL_SEC",
        "PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL",
        "PSBX_ENABLE_PAID_MODELS",
        "PSBX_MAX_INPUT_TOKENS",
        "PSBX_MAX_PAID_REQUESTS",
        "PSBX_MAX_REQUEST_USD",
        "PSBX_MAX_RUN_USD",
        "TOGETHER_API_KEY",
        "VLLM_API_KEY",
        "VLLM_BASE_URL",
    }
)

_TRUSTED_PROVIDER_ORIGINS = {
    "anthropic": ("https", "api.anthropic.com", 443),
    "openai": ("https", "api.openai.com", 443),
    "openrouter": ("https", "openrouter.ai", 443),
    "together": ("https", "api.together.xyz", 443),
}


def allowlisted_subprocess_env(
    *,
    include_model_access: bool,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Copy only explicitly supported values into a child process environment."""
    values = os.environ if source is None else source
    allowed = _BASE_CHILD_ENV | (_MODEL_CHILD_ENV if include_model_access else frozenset())
    return {name: values[name] for name in sorted(allowed) if name in values}


def require_loopback_host(host: str) -> str:
    """Return a normalized local bind host or reject an unauthenticated remote bind."""
    value = str(host).strip()
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    if candidate.lower() == "localhost":
        return candidate
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise ValueError(
            "the viewer is local-only; --host must be localhost, 127.0.0.0/8, or ::1"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            "the viewer is local-only; remote binds require an authenticated reverse proxy"
        )
    return candidate


def require_safe_provider_base_url(url: str, provider: str) -> str:
    """Prevent paid credentials from being redirected to an unintended origin."""
    value = str(url).strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        not parsed.scheme
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"unsafe {provider} base URL")
    expected = _TRUSTED_PROVIDER_ORIGINS.get(provider)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    origin = (parsed.scheme.lower(), parsed.hostname.lower(), port)
    if expected is not None and origin == expected:
        return value
    allow_custom = str(os.environ.get("PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL") or "").lower()
    if allow_custom not in {"1", "true", "yes", "on"}:
        raise ValueError(
            f"refusing custom {provider} base URL; set "
            "PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL=1 only for an intentional HTTPS proxy"
        )
    if parsed.scheme.lower() != "https":
        raise ValueError(f"custom {provider} base URL must use HTTPS")
    return value


def require_loopback_base_url(url: str, label: str = "local service") -> str:
    """Keep services described as local from silently becoming remote egress."""
    value = str(url).strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"unsafe {label} URL")
    try:
        require_loopback_host(parsed.hostname)
    except ValueError as exc:
        raise ValueError(f"{label} must use a loopback URL") from exc
    return value
