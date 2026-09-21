#!/usr/bin/env python3
"""Export and restore the local research assets that intentionally stay out of Git.

The bundle is a directory, not a compressed archive. Large Census ZIPs and PDFs are
already compressed, and a directory remains easy to resume with ordinary file-copy
tools. Every regular file is pinned by size and SHA-256 in the bundle manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = 1
MANIFEST_NAME = "workspace-transfer-manifest.json"
PAYLOAD_DIR = "payload"
COPY_CHUNK_BYTES = 8 * 1024 * 1024

# These are the ignored, machine-local assets needed to continue research and
# experiments. Code, documentation, configs, questions, source snapshots, and test
# fixtures are already carried by Git and must not be duplicated here.
DEFAULT_ASSET_PATHS = (
    "data/corpus-cache",
    "data/corpus",
    "data/elections",
    "data/evaluation-vault",
    "data/population-input",
    "data/population",
    "data/census-cache",
    "data/survey-microdata",
    "data/runs",
    "config/population-artifacts.local.yaml",
)

EXCLUDED_DIRECTORY_NAMES = {
    ".sandbox",  # PID files, sockets, and host-specific sidecar state
    "__pycache__",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
}
FORBIDDEN_RELATIVE_PATHS = {
    ".env",
    ".git",
    ".venv",
    "build",
    "dist",
}


class TransferError(RuntimeError):
    """A transfer cannot be completed without risking an incomplete workspace."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalize_relative_path(value: str | Path) -> Path:
    raw = str(value).replace("\\", "/")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise TransferError(f"asset path must be a safe repository-relative path: {value}")
    normalized = Path(*pure.parts)
    first = normalized.parts[0]
    if first in FORBIDDEN_RELATIVE_PATHS or normalized.name == ".env":
        raise TransferError(f"refusing to transfer sensitive or generated path: {value}")
    return normalized


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _iter_regular_files(root: Path, relative_roots: Iterable[Path]) -> tuple[list[Path], list[str]]:
    files: set[Path] = set()
    missing: list[str] = []
    resolved_root = root.resolve()
    for relative in relative_roots:
        source = root / relative
        if not source.exists():
            missing.append(relative.as_posix())
            continue
        if source.is_symlink():
            raise TransferError(f"refusing to follow asset symlink: {relative.as_posix()}")
        if source.is_file():
            files.add(relative)
            continue
        for directory, names, filenames in os.walk(source, followlinks=False):
            directory_path = Path(directory)
            names[:] = sorted(name for name in names if name not in EXCLUDED_DIRECTORY_NAMES)
            for name in sorted(filenames):
                if (
                    name in EXCLUDED_FILE_NAMES
                    or name == ".env"
                    or name.startswith(".env.")
                    or name.endswith(".part")
                ):
                    continue
                candidate = directory_path / name
                if candidate.is_symlink():
                    raise TransferError(
                        "refusing to follow asset symlink: "
                        + candidate.relative_to(root).as_posix()
                    )
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if not _inside(resolved, resolved_root):
                    raise TransferError(f"asset escapes repository root: {candidate}")
                files.add(resolved.relative_to(resolved_root))
    return sorted(files, key=lambda path: path.as_posix()), sorted(missing)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _safe_remote_url(value: str | None) -> str | None:
    if not value or "://" not in value:
        return value
    parsed = urlsplit(value)
    if "@" not in parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname += f":{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, parsed.query, parsed.fragment))


def git_state(root: Path) -> dict[str, Any]:
    status = _git_value(root, "status", "--porcelain", "--untracked-files=all") or ""
    remote = _git_value(root, "remote", "get-url", "origin")
    return {
        "commit": _git_value(root, "rev-parse", "HEAD"),
        "branch": _git_value(root, "branch", "--show-current"),
        "origin": _safe_remote_url(remote),
        "dirty": bool(status),
        "status": status.splitlines(),
    }


def inventory(
    root: Path,
    asset_paths: Iterable[str | Path] = DEFAULT_ASSET_PATHS,
) -> dict[str, Any]:
    root = root.resolve()
    normalized = [_normalize_relative_path(path) for path in asset_paths]
    files, missing = _iter_regular_files(root, normalized)
    total_bytes = sum((root / path).stat().st_size for path in files)
    by_root = []
    for relative in normalized:
        selected = [path for path in files if path == relative or relative in path.parents]
        by_root.append(
            {
                "path": relative.as_posix(),
                "present": (root / relative).exists(),
                "files": len(selected),
                "bytes": sum((root / path).stat().st_size for path in selected),
            }
        )
    return {
        "repository": str(root),
        "git": git_state(root),
        "asset_roots": by_root,
        "missing_optional_roots": missing,
        "file_count": len(files),
        "total_bytes": total_bytes,
    }


def _copy_and_hash(
    source: Path,
    destination: Path,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".transfer-part")
    digest = hashlib.sha256()
    size = 0
    try:
        with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
            for chunk in iter(lambda: input_handle.read(COPY_CHUNK_BYTES), b""):
                output_handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        actual_digest = digest.hexdigest()
        if expected_size is not None and size != expected_size:
            raise TransferError(
                f"source size changed while copying {source} ({size} != {expected_size})"
            )
        if expected_sha256 is not None and actual_digest != expected_sha256:
            raise TransferError(f"source checksum does not match the manifest: {source}")
        shutil.copystat(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


def export_assets(
    root: Path,
    destination: Path,
    asset_paths: Iterable[str | Path] = DEFAULT_ASSET_PATHS,
) -> dict[str, Any]:
    root = root.resolve()
    destination = destination.expanduser().resolve()
    normalized = [_normalize_relative_path(path) for path in asset_paths]
    sources = [(root / relative).resolve() for relative in normalized if (root / relative).exists()]
    if any(_inside(destination, source) for source in sources):
        raise TransferError("bundle destination cannot be inside a transferred asset directory")
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise TransferError(f"bundle destination must be an empty directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    payload = destination / PAYLOAD_DIR
    files, missing = _iter_regular_files(root, normalized)
    rows: list[dict[str, Any]] = []
    copied_bytes = 0
    for index, relative in enumerate(files, start=1):
        size, digest = _copy_and_hash(root / relative, payload / relative)
        rows.append({"path": relative.as_posix(), "bytes": size, "sha256": digest})
        copied_bytes += size
        if index == 1 or index % 100 == 0 or index == len(files):
            print(
                f"[{index}/{len(files)}] copied {copied_bytes / (1024**3):.2f} GiB",
                file=sys.stderr,
            )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_repository": str(root),
        "source_git": git_state(root),
        "asset_roots": [path.as_posix() for path in normalized],
        "missing_optional_roots": missing,
        "file_count": len(rows),
        "total_bytes": copied_bytes,
        "files": rows,
        "security": {
            "env_files_included": False,
            "virtual_environment_included": False,
            "git_metadata_included": False,
            "transient_sidecar_state_included": False,
        },
    }
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _load_manifest(bundle: Path) -> dict[str, Any]:
    path = bundle / MANIFEST_NAME
    if not path.is_file():
        raise TransferError(f"bundle manifest is missing: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise TransferError(f"cannot read bundle manifest: {exc}") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise TransferError(
            f"unsupported bundle schema {manifest.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise TransferError("bundle manifest files must be a list")
    for row in rows:
        if not isinstance(row, dict):
            raise TransferError("bundle manifest contains an invalid file record")
        _normalize_relative_path(str(row.get("path", "")))
        digest = str(row.get("sha256", "")).casefold()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise TransferError(f"invalid SHA-256 for bundle path {row.get('path')!r}")
        if not isinstance(row.get("bytes"), int) or row["bytes"] < 0:
            raise TransferError(f"invalid byte size for bundle path {row.get('path')!r}")
    return manifest


def verify_bundle(bundle: Path) -> dict[str, Any]:
    bundle = bundle.expanduser().resolve()
    manifest = _load_manifest(bundle)
    failures: list[str] = []
    checked_bytes = 0
    for row in manifest["files"]:
        relative = _normalize_relative_path(row["path"])
        source = bundle / PAYLOAD_DIR / relative
        if source.is_symlink() or not source.is_file():
            failures.append(f"missing: {relative.as_posix()}")
            continue
        size = source.stat().st_size
        if size != row["bytes"]:
            failures.append(
                f"size mismatch: {relative.as_posix()} ({size} != {row['bytes']})"
            )
            continue
        digest = _sha256(source)
        if digest != row["sha256"]:
            failures.append(f"checksum mismatch: {relative.as_posix()}")
            continue
        checked_bytes += size
    return {
        "passed": not failures,
        "bundle": str(bundle),
        "checked_files": len(manifest["files"]) - len(failures),
        "checked_bytes": checked_bytes,
        "failures": failures,
        "source_git": manifest.get("source_git", {}),
    }


def import_assets(bundle: Path, root: Path, *, replace: bool = False) -> dict[str, Any]:
    bundle = bundle.expanduser().resolve()
    root = root.resolve()
    manifest = _load_manifest(bundle)
    imported = 0
    skipped = 0
    imported_bytes = 0
    for row in manifest["files"]:
        relative = _normalize_relative_path(row["path"])
        source = bundle / PAYLOAD_DIR / relative
        if source.is_symlink() or not source.is_file():
            raise TransferError(f"bundle file is missing: {relative.as_posix()}")
        destination = root / relative
        if not _inside(destination.parent.resolve(), root):
            raise TransferError(f"destination escapes repository root: {relative.as_posix()}")
        if destination.exists():
            if not destination.is_file():
                raise TransferError(f"destination is not a regular file: {destination}")
            same = (
                destination.stat().st_size == row["bytes"]
                and _sha256(destination) == row["sha256"]
            )
            if same:
                skipped += 1
                continue
            if not replace:
                raise TransferError(
                    f"destination differs: {relative.as_posix()}; rerun with --replace "
                    "only if the bundle should win"
                )
        size, digest = _copy_and_hash(
            source,
            destination,
            expected_size=row["bytes"],
            expected_sha256=row["sha256"],
        )
        imported += 1
        imported_bytes += size
        if imported == 1 or imported % 100 == 0:
            print(
                f"imported {imported} file(s), {imported_bytes / (1024**3):.2f} GiB",
                file=sys.stderr,
            )
    return {
        "passed": True,
        "repository": str(root),
        "bundle": str(bundle),
        "imported_files": imported,
        "skipped_matching_files": skipped,
        "imported_bytes": imported_bytes,
        "source_git": manifest.get("source_git", {}),
    }


def _json_output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move ignored Prediction Sandbox research assets between laptops safely."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repository_root(),
        help="repository root (defaults to the parent of this script)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory", help="show what the default transfer would include")
    export_parser = commands.add_parser("export", help="copy assets into a verified bundle")
    export_parser.add_argument("destination", type=Path)
    verify_parser = commands.add_parser("verify", help="verify every file in a bundle")
    verify_parser.add_argument("bundle", type=Path)
    import_parser = commands.add_parser("import", help="restore a bundle into this repository")
    import_parser.add_argument("bundle", type=Path)
    import_parser.add_argument(
        "--replace",
        action="store_true",
        help="replace differing destination files; matching files are always skipped",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            _json_output(inventory(args.root))
            return 0
        if args.command == "export":
            _json_output(export_assets(args.root, args.destination))
            return 0
        if args.command == "verify":
            result = verify_bundle(args.bundle)
            _json_output(result)
            return 0 if result["passed"] else 2
        if args.command == "import":
            _json_output(import_assets(args.bundle, args.root, replace=args.replace))
            return 0
    except (OSError, TransferError) as exc:
        print(f"transfer error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
