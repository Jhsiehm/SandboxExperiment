"""Safe discovery and download of official FEC federal-election publications."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .registry import federal_coverage_plan

FEC_ROOT = "https://www.fec.gov"
FEC_RESULTS_INDEX = (
    "https://www.fec.gov/introduction-campaign-finance/"
    "election-results-and-voting-information/"
)
USER_AGENT = "PredictionSandbox/0.1.0 (official election-results sync)"
_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def federal_source_page(year: int) -> str:
    if year <= 1994 or year == 2024:
        return FEC_RESULTS_INDEX
    return f"{FEC_RESULTS_INDEX}federal-elections-{year}/"


def _allowed_artifact(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"fec.gov", "www.fec.gov"}
        and Path(parsed.path).suffix.casefold() in {".pdf", ".xlsx", ".xls"}
    )


def _primary_publication(url: str, year: int) -> bool:
    stem = Path(urlparse(url).path).stem.casefold()
    compact = re.sub(r"[^a-z0-9]", "", stem)
    suffixes = {str(year), f"{year % 100:02d}"}
    if any(compact == f"federalelections{suffix}" for suffix in suffixes):
        return True
    if compact == f"{year}fedresults":
        return True
    return year == 2024 and compact == "2024presgeresults"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_artifact_file(path: Path, *, suffix: str, max_bytes: int) -> None:
    size = path.stat().st_size
    if not 1 <= size <= max_bytes:
        raise ValueError("artifact file size is outside the allowed range")
    with path.open("rb") as handle:
        signature = handle.read(8)
    expected = suffix.casefold()
    valid = (
        expected == ".pdf"
        and signature.startswith(b"%PDF-")
        or expected == ".xlsx"
        and signature.startswith(b"PK")
        or expected == ".xls"
        and signature == _OLE_SIGNATURE
    )
    if not valid:
        raise ValueError(f"artifact content does not match its {expected} extension")


def discover_federal_artifacts(
    client: httpx.Client,
    year: int,
    *,
    include_supplements: bool = False,
) -> list[dict]:
    page = federal_source_page(year)
    response = client.get(page)
    response.raise_for_status()
    if urlparse(str(response.url)).hostname not in {"fec.gov", "www.fec.gov"}:
        raise ValueError("FEC source page redirected outside the official host")
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    seen = set()
    for anchor in soup.select("a[href]"):
        url = urljoin(page, str(anchor.get("href") or ""))
        label = " ".join(anchor.get_text(" ", strip=True).split())
        if not _allowed_artifact(url) or url in seen:
            continue
        if (year <= 1994 or year == 2024) and str(year) not in (label + " " + url):
            continue
        if not include_supplements and not _primary_publication(url, year):
            continue
        seen.add(url)
        rows.append(
            {
                "artifact_id": f"fec-{year}-{len(rows) + 1:02d}",
                "year": year,
                "label": label or Path(urlparse(url).path).name,
                "url": url,
                "source_page": page,
            }
        )
    return rows


def sync_federal_documents(
    years: list[int],
    *,
    output_root: str | Path = "data/elections/raw/federal",
    as_of: date | None = None,
    max_artifact_bytes: int = 250_000_000,
    max_total_bytes: int = 500_000_000,
    max_artifacts: int = 100,
    include_supplements: bool = False,
    force: bool = False,
) -> dict:
    """Download official source documents and pin the exact bytes in a local manifest."""
    as_of = as_of or date.today()
    if max_artifact_bytes < 1 or max_total_bytes < 1 or max_artifacts < 1:
        raise ValueError("artifact and byte limits must be positive")
    plan = federal_coverage_plan(
        start_year=min(years), through_year=max(years), as_of=as_of
    )
    by_year = {row["year"]: row for row in plan["cycles"]}
    blocked = [year for year in years if by_year[year]["status"] == "future_pending"]
    if blocked:
        raise ValueError(
            "cannot download results for future election cycles: "
            + ", ".join(str(year) for year in blocked)
        )
    root = Path(output_root)
    artifacts = []
    failures = []
    total_bytes = 0
    with httpx.Client(
        timeout=httpx.Timeout(120.0, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for year in sorted(set(years)):
            if year % 2:
                failures.append(f"{year}: not a regular federal election cycle")
                continue
            try:
                discovered = discover_federal_artifacts(
                    client,
                    year,
                    include_supplements=include_supplements,
                )
            except httpx.HTTPError as exc:
                failures.append(f"{year}: source discovery failed: {type(exc).__name__}")
                continue
            if not discovered:
                failures.append(f"{year}: no official PDF/Excel artifacts discovered")
                continue
            for artifact in discovered:
                if len(artifacts) >= max_artifacts:
                    failures.append(
                        f"download stopped at max_artifacts={max_artifacts}; narrow the year range"
                    )
                    break
                destination: Path | None = None
                temporary: Path | None = None
                try:
                    filename = Path(urlparse(artifact["url"]).path).name
                    destination = root / str(year) / filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    status = "existing_pinned"
                    if force or not destination.is_file():
                        temporary = destination.with_suffix(destination.suffix + ".part")
                        written = 0
                        with client.stream("GET", artifact["url"]) as response:
                            response.raise_for_status()
                            if not _allowed_artifact(str(response.url)):
                                raise ValueError(
                                    "official artifact redirected outside the allowed FEC host"
                                )
                            declared = int(response.headers.get("content-length") or 0)
                            if declared > max_artifact_bytes:
                                raise ValueError("artifact exceeds max_artifact_bytes")
                            with temporary.open("wb") as handle:
                                for chunk in response.iter_bytes(1024 * 1024):
                                    written += len(chunk)
                                    if written > max_artifact_bytes:
                                        raise ValueError("artifact exceeds max_artifact_bytes")
                                    if total_bytes + written > max_total_bytes:
                                        raise ValueError("sync exceeds max_total_bytes")
                                    handle.write(chunk)
                        _validate_artifact_file(
                            temporary,
                            suffix=destination.suffix,
                            max_bytes=max_artifact_bytes,
                        )
                        os.replace(temporary, destination)
                        status = "downloaded"
                    _validate_artifact_file(
                        destination,
                        suffix=destination.suffix,
                        max_bytes=max_artifact_bytes,
                    )
                    if total_bytes + destination.stat().st_size > max_total_bytes:
                        raise ValueError("sync exceeds max_total_bytes")
                    total_bytes += destination.stat().st_size
                    artifacts.append(
                        {
                            **artifact,
                            "local_path": str(destination.relative_to(root)),
                            "bytes": destination.stat().st_size,
                            "sha256": _sha256(destination),
                            "downloaded_at": datetime.now(timezone.utc).isoformat(),
                            "status": status,
                        }
                    )
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                    failures.append(
                        f"{artifact['artifact_id']}: {type(exc).__name__}: {exc}"
                    )
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of.isoformat(),
        "years": sorted(set(years)),
        "passed": not failures,
        "artifacts": artifacts,
        "failures": failures,
        "limits": {
            "max_artifact_bytes": max_artifact_bytes,
            "max_total_bytes": max_total_bytes,
            "max_artifacts": max_artifacts,
        },
        "include_supplements": include_supplements,
        "normalization_status": "not_started",
        "note": "Downloaded documents are raw evidence, not normalized result rows.",
    }
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.json"
    temporary = manifest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, manifest)
    return {"manifest_path": str(manifest), **payload}
