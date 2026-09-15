"""Cutoff-aware sync for public survey materials and gated-data manifests."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, model_validator

from psbx.config import load_yaml
from psbx.corpus.ia_http import Pace, ia_client, ia_get, user_agent
from psbx.corpus.normalize import document_id_for, html_to_text, normalize_text
from psbx.io import read_json, write_json
from psbx.paths import repo_root, resolve
from psbx.schemas import Document, Epoch

UTC = timezone.utc
CATALOG_PATH = "config/survey_sources.yaml"
CACHE_ROOT = "data/corpus-cache/survey-sources"


class SurveyArtifact(BaseModel):
    id: str
    provider: str
    outlet: str
    title: str
    url: str
    fieldwork_year_start: int
    fieldwork_year_end: int
    released_at: datetime | None = None
    access: Literal["public", "account", "registration"]
    retrieval: Literal["wayback", "direct", "manual"]
    format: Literal["html", "pdf"] = "html"
    expected_marker: str | None = None
    expected_sha256: str | None = None
    index: bool = False
    note: str = ""

    @model_validator(mode="after")
    def validate_access_and_dates(self) -> SurveyArtifact:
        if self.fieldwork_year_end < self.fieldwork_year_start:
            raise ValueError("fieldwork_year_end must be >= fieldwork_year_start")
        if self.access != "public" and self.retrieval != "manual":
            raise ValueError("account/registration artifacts must use manual retrieval")
        if self.index and (self.access != "public" or self.released_at is None):
            raise ValueError("indexed artifacts must be public with a verified release date")
        if self.retrieval == "direct" and self.format == "pdf" and not self.expected_marker:
            raise ValueError("direct PDFs require expected_marker validation")
        if self.retrieval == "direct":
            digest = str(self.expected_sha256 or "").casefold()
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("direct artifacts require a pinned expected_sha256")
            self.expected_sha256 = digest
        return self


def load_survey_catalog(path: str | Path = CATALOG_PATH) -> list[SurveyArtifact]:
    raw = load_yaml(path)
    return [SurveyArtifact.model_validate(row) for row in raw.get("artifacts", [])]


def survey_cache_dir(epoch: Epoch, cache_root: str | Path = CACHE_ROOT) -> Path:
    return resolve(cache_root) / epoch.id


def survey_manifest_path(epoch: Epoch, cache_root: str | Path = CACHE_ROOT) -> Path:
    return survey_cache_dir(epoch, cache_root) / "manifest.json"


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root().resolve()))
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_cutoff_snapshot(
    artifact: SurveyArtifact,
    epoch: Epoch,
    destination: Path,
) -> dict[str, Any]:
    """Fetch the newest Wayback copy between release and the epoch cutoff."""
    assert artifact.released_at is not None
    params = [
        ("url", artifact.url),
        ("from", artifact.released_at.strftime("%Y%m%d")),
        ("to", epoch.cutoff_date.strftime("%Y%m%d")),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("output", "json"),
        ("fl", "timestamp,original,digest,statuscode,mimetype"),
        ("limit", "50"),
    ]
    cdx_url = f"https://web.archive.org/cdx/search/cdx?{urlencode(params)}"
    pace = Pace(2.0)
    with ia_client() as client:
        response = ia_get(client, cdx_url, pace=pace)
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            raise RuntimeError("no cutoff-safe Wayback snapshot found")
        columns = payload[0]
        rows = [dict(zip(columns, row)) for row in payload[1:] if isinstance(row, list)]
        rows = [row for row in rows if str(row.get("timestamp", ""))[:8]]
        if not rows:
            raise RuntimeError("no cutoff-safe Wayback snapshot found")
        selected = max(rows, key=lambda row: str(row["timestamp"]))
        timestamp = str(selected["timestamp"])
        if timestamp[:8] > epoch.cutoff_date.strftime("%Y%m%d"):
            raise RuntimeError("Wayback returned a post-cutoff capture")
        archived_url = f"https://web.archive.org/web/{timestamp}id_/{artifact.url}"
        snapshot = ia_get(client, archived_url, pace=pace)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(snapshot.content)
    return {
        "snapshot_url": archived_url,
        "snapshot_timestamp": timestamp,
        "content_type": snapshot.headers.get("content-type", "text/html"),
    }


def _extract_artifact_text(path: Path, file_format: str) -> str:
    if file_format == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        return normalize_text(" ".join(page.extract_text() or "" for page in reader.pages))
    raw = path.read_text(encoding="utf-8", errors="replace")
    return normalize_text(html_to_text(raw))


def _download_direct_artifact(
    artifact: SurveyArtifact,
    epoch: Epoch,
    destination: Path,
) -> dict[str, Any]:
    """Download a dated, immutable public artifact and validate its internal marker."""
    del epoch
    import httpx

    with httpx.Client(
        follow_redirects=True,
        timeout=60.0,
        headers={"User-Agent": user_agent()},
    ) as client:
        response = client.get(artifact.url)
        response.raise_for_status()
    digest = hashlib.sha256(response.content).hexdigest()
    if digest != artifact.expected_sha256:
        raise RuntimeError(
            f"downloaded file checksum {digest} does not match pinned "
            f"expected_sha256 {artifact.expected_sha256}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    text = _extract_artifact_text(destination, artifact.format)
    if artifact.expected_marker and artifact.expected_marker.casefold() not in text.casefold():
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file lacks expected marker {artifact.expected_marker!r}")
    return {
        # A checksum-pinned direct release is not an archival capture. Keep the
        # two kinds of evidence distinct instead of inventing a snapshot time.
        "source_url": artifact.url,
        "content_type": response.headers.get("content-type", "application/octet-stream"),
    }


def _download_artifact(
    artifact: SurveyArtifact,
    epoch: Epoch,
    destination: Path,
) -> dict[str, Any]:
    if artifact.retrieval == "wayback":
        return _download_cutoff_snapshot(artifact, epoch, destination)
    if artifact.retrieval == "direct":
        return _download_direct_artifact(artifact, epoch, destination)
    raise RuntimeError("manual artifacts cannot be downloaded automatically")


Fetcher = Callable[[SurveyArtifact, Epoch, Path], dict[str, Any]]


def sync_survey_sources(
    epoch: Epoch,
    *,
    provider: str = "all",
    catalog_path: str | Path = CATALOG_PATH,
    cache_root: str | Path = CACHE_ROOT,
    plan: bool = False,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    """Sync eligible public artifacts and inventory gated/future versions."""
    catalog = load_survey_catalog(catalog_path)
    providers = sorted({item.provider for item in catalog})
    if provider != "all" and provider not in providers:
        raise ValueError(f"unknown provider {provider!r}; choose all or: {', '.join(providers)}")
    selected = [item for item in catalog if provider == "all" or item.provider == provider]
    fetcher = fetcher or _download_artifact
    manifest = survey_manifest_path(epoch, cache_root)
    previous_rows: dict[str, dict[str, Any]] = {}
    if manifest.is_file():
        previous_rows = {
            str(row["id"]): row
            for row in read_json(manifest).get("artifacts", [])
            if isinstance(row, dict) and row.get("id")
        }
    rows: list[dict[str, Any]] = []
    for artifact in selected:
        applies_to_year = artifact.fieldwork_year_start <= epoch.cutoff_date.year
        row: dict[str, Any] = {
            **artifact.model_dump(mode="json"),
            "epoch": epoch.id,
            "cutoff": epoch.cutoff_date.isoformat(),
            "applies_to_year": applies_to_year,
            "eligible_for_index": False,
            "status": "not_applicable",
        }
        if not applies_to_year:
            row["reason"] = "fieldwork begins after this epoch"
            rows.append(row)
            continue
        if artifact.released_at is None:
            row["status"] = "blocked_unverified_release"
            row["reason"] = "exact release/version date is not verified"
            rows.append(row)
            continue
        if artifact.released_at.date() > epoch.cutoff_date:
            row["status"] = "blocked_future_release"
            row["reason"] = f"released {artifact.released_at.date()} after cutoff"
            rows.append(row)
            continue
        if artifact.access != "public" or artifact.retrieval == "manual":
            row["status"] = "manual_required"
            row["reason"] = f"{artifact.access} access must be completed by the user"
            rows.append(row)
            continue
        destination = (
            survey_cache_dir(epoch, cache_root)
            / artifact.provider
            / f"{artifact.id}.{artifact.format}"
        )
        if plan:
            row["status"] = "ready"
            row["eligible_for_index"] = artifact.index
            row["local_path"] = _repo_relative(destination)
            rows.append(row)
            continue
        previous = previous_rows.get(artifact.id) or {}
        destination_sha = _sha256(destination) if destination.is_file() else None
        if (
            destination_sha is not None
            and previous.get("sha256") == destination_sha
            and previous.get("url") == artifact.url
            and previous.get("released_at") == artifact.model_dump(mode="json")["released_at"]
            and (
                artifact.expected_sha256 is None
                or destination_sha == artifact.expected_sha256
            )
        ):
            text = _extract_artifact_text(destination, artifact.format)
            marker_ok = not artifact.expected_marker or (
                artifact.expected_marker.casefold() in text.casefold()
            )
            if marker_ok:
                row.update(previous)
                row.update(artifact.model_dump(mode="json"))
                if artifact.retrieval == "direct":
                    row.pop("snapshot_url", None)
                    row.pop("snapshot_timestamp", None)
                    row["source_url"] = artifact.url
                row["epoch"] = epoch.id
                row["cutoff"] = epoch.cutoff_date.isoformat()
                row["status"] = "cached"
                row["eligible_for_index"] = artifact.index
                rows.append(row)
                continue
        try:
            extra = fetcher(artifact, epoch, destination)
            downloaded_sha = _sha256(destination)
            if artifact.expected_sha256 and downloaded_sha != artifact.expected_sha256:
                destination.unlink(missing_ok=True)
                raise RuntimeError(
                    f"downloaded file checksum {downloaded_sha} does not match pinned "
                    f"expected_sha256 {artifact.expected_sha256}"
                )
            row.update(extra)
            if artifact.retrieval == "direct":
                # Custom fetchers and older manifests may use Wayback-shaped
                # fields. Never represent a current direct fetch as a dated
                # archival snapshot.
                row.pop("snapshot_url", None)
                row.pop("snapshot_timestamp", None)
                row["source_url"] = artifact.url
            row["status"] = "downloaded"
            row["eligible_for_index"] = artifact.index
            row["local_path"] = _repo_relative(destination)
            row["sha256"] = downloaded_sha
            row["bytes"] = destination.stat().st_size
        except Exception as exc:
            row["status"] = "error"
            row["reason"] = str(exc)
        rows.append(row)
    if not plan and provider != "all":
        selected_ids = {item.id for item in selected}
        rows.extend(
            row
            for key, row in previous_rows.items()
            if key not in selected_ids and row.get("provider") != provider
        )
        rows.sort(key=lambda row: str(row["id"]))
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    payload = {
        "epoch": epoch.id,
        "cutoff": epoch.cutoff_date.isoformat(),
        "provider": provider,
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": dict(sorted(counts.items())),
        "artifacts": rows,
    }
    if not plan:
        write_json(manifest, payload)
    return payload


def ingest_synced_survey_sources(
    epoch: Epoch,
    *,
    manifest_path: str | Path | None = None,
    catalog_path: str | Path = CATALOG_PATH,
) -> list[Document]:
    """Convert only manifest-approved, cutoff-safe public pages to Documents."""
    path = resolve(manifest_path) if manifest_path else survey_manifest_path(epoch)
    if not path.is_file():
        return []
    payload = read_json(path)
    if payload.get("epoch") != epoch.id or payload.get("cutoff") != epoch.cutoff_date.isoformat():
        raise ValueError(f"survey manifest does not match epoch {epoch.id}")
    catalog = {artifact.id: artifact for artifact in load_survey_catalog(catalog_path)}
    docs: list[Document] = []
    for row in payload.get("artifacts", []):
        if row.get("status") not in {"downloaded", "cached"} or not row.get("eligible_for_index"):
            continue
        artifact = catalog.get(str(row.get("id") or ""))
        if artifact is None or not artifact.index:
            raise ValueError(
                f"survey artifact is no longer approved by the catalog: {row.get('id')}"
            )
        catalog_row = artifact.model_dump(mode="json")
        checked_fields = (
            "provider",
            "outlet",
            "title",
            "url",
            "fieldwork_year_start",
            "fieldwork_year_end",
            "released_at",
            "retrieval",
            "format",
        )
        if any(row.get(field) != catalog_row[field] for field in checked_fields):
            raise ValueError(f"survey manifest metadata is stale: {row['id']}")
        released = datetime.fromisoformat(str(row["released_at"]).replace("Z", "+00:00"))
        if released.date() > epoch.cutoff_date:
            raise AssertionError(f"survey release leakage: {row['id']}")
        snapshot_timestamp = ""
        if artifact.retrieval == "wayback":
            snapshot_timestamp = str(row.get("snapshot_timestamp") or "")
            if not snapshot_timestamp:
                raise ValueError(f"archived survey artifact lacks snapshot time: {row['id']}")
            if snapshot_timestamp[:8] > epoch.cutoff_date.strftime("%Y%m%d"):
                raise AssertionError(f"survey snapshot leakage: {row['id']}")
        local_path = resolve(row["local_path"])
        local_sha = _sha256(local_path) if local_path.is_file() else None
        if local_sha is None or local_sha != row.get("sha256"):
            raise ValueError(f"survey artifact missing or checksum mismatch: {row['id']}")
        expected_sha = artifact.expected_sha256
        if expected_sha and local_sha != expected_sha:
            raise ValueError(f"survey artifact differs from pinned checksum: {row['id']}")
        text = _extract_artifact_text(local_path, artifact.format)
        expected_marker = str(artifact.expected_marker or "")
        if expected_marker and expected_marker.casefold() not in text.casefold():
            raise ValueError(f"survey artifact marker mismatch: {row['id']}")
        if len(text) < 200:
            continue
        verification = (
            f"Wayback snapshot {snapshot_timestamp}"
            if artifact.retrieval == "wayback"
            else f"checksum-pinned direct release sha256={expected_sha}"
        )
        provenance = (
            f"Cutoff-safe public summary from {artifact.provider}; "
            f"fieldwork {artifact.fieldwork_year_start}-{artifact.fieldwork_year_end}; "
            f"release {released.date()}; {verification}"
        )
        evidence_fields: dict[str, Any]
        if artifact.retrieval == "wayback":
            captured_at = datetime.strptime(
                snapshot_timestamp[:14], "%Y%m%d%H%M%S"
            ).replace(tzinfo=UTC)
            evidence_fields = {
                "authenticity": "authenticated_capture",
                "timestamp_basis": "archive_capture",
                "captured_at": captured_at,
                "source_reference": str(row.get("snapshot_url") or artifact.url),
                "capture_verified": True,
            }
        else:
            evidence_fields = {
                "authenticity": "authenticated_artifact",
                "timestamp_basis": "publication_date",
                "source_reference": artifact.url,
                "publication_date_verified": True,
                "release_verified": True,
            }
        docs.append(
            Document(
                id=document_id_for(text),
                url=artifact.url,
                outlet=artifact.outlet,
                published_at=released,
                title=artifact.title,
                text=text[:20000],
                source_type="survey",
                prominence=0.0,
                provenance=provenance,
                **evidence_fields,
            )
        )
    return docs
