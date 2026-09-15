"""Browser-side protections for local viewer mutations."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from psbx.security import require_loopback_host

CSRF_HEADER = "X-PSBX-CSRF"
CSRF_VALUE = "1"


def _origin_key(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("malformed browser origin")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def require_local_mutation(request: Request) -> None:
    """Reject simple/cross-site browser requests before any local state is changed."""
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail="missing local mutation header")

    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise HTTPException(status_code=403, detail="cross-site mutation blocked")

    origin = request.headers.get("origin")
    if origin:
        try:
            matches = _origin_key(origin) == _origin_key(str(request.base_url))
        except ValueError:
            matches = False
        if not matches:
            raise HTTPException(status_code=403, detail="cross-origin mutation blocked")


def require_local_request_host(request: Request) -> None:
    """Require both a loopback Host header and a loopback socket peer."""
    try:
        require_loopback_host(request.url.hostname or "")
        require_loopback_host(request.client.host if request.client else "")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="non-loopback viewer request blocked") from exc
