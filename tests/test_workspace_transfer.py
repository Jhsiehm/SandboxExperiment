import json
from pathlib import Path

import pytest

from scripts.transfer_workspace import (
    MANIFEST_NAME,
    TransferError,
    export_assets,
    import_assets,
    inventory,
    verify_bundle,
)


def _source_workspace(root: Path) -> None:
    (root / "data/corpus/e2012").mkdir(parents=True)
    (root / "data/corpus/e2012/documents.jsonl").write_text(
        '{"id":"fixture"}\n', encoding="utf-8"
    )
    (root / "data/population-input/e2012").mkdir(parents=True)
    (root / "data/population-input/e2012/source.zip").write_bytes(b"PK fixture")
    (root / "data/runs/completed").mkdir(parents=True)
    (root / "data/runs/completed/results.json").write_text("{}\n", encoding="utf-8")
    (root / "data/runs/completed/.env.local").write_text(
        "TOKEN=secret\n", encoding="utf-8"
    )
    (root / "data/runs/.sandbox").mkdir(parents=True)
    (root / "data/runs/.sandbox/host.pid").write_text("123\n", encoding="utf-8")
    (root / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv/marker").write_text("local only\n", encoding="utf-8")


def test_export_verify_and_import_workspace_assets(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source)
    bundle = tmp_path / "bundle"

    before = inventory(source)
    assert before["file_count"] == 3
    manifest = export_assets(source, bundle)
    assert manifest["file_count"] == 3
    assert manifest["security"]["env_files_included"] is False
    assert not (bundle / "payload/.env").exists()
    assert not (bundle / "payload/.venv").exists()
    assert not (bundle / "payload/data/runs/completed/.env.local").exists()
    assert not (bundle / "payload/data/runs/.sandbox").exists()

    verification = verify_bundle(bundle)
    assert verification["passed"] is True
    assert verification["checked_files"] == 3

    destination = tmp_path / "destination"
    destination.mkdir()
    restored = import_assets(bundle, destination)
    assert restored["imported_files"] == 3
    assert (
        destination / "data/corpus/e2012/documents.jsonl"
    ).read_text(encoding="utf-8") == '{"id":"fixture"}\n'
    assert (destination / "data/population-input/e2012/source.zip").read_bytes() == b"PK fixture"

    second = import_assets(bundle, destination)
    assert second["imported_files"] == 0
    assert second["skipped_matching_files"] == 3


def test_import_refuses_differing_destination_without_replace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source)
    bundle = tmp_path / "bundle"
    export_assets(source, bundle)
    destination = tmp_path / "destination"
    target = destination / "data/corpus/e2012/documents.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("different\n", encoding="utf-8")

    with pytest.raises(TransferError, match="destination differs"):
        import_assets(bundle, destination)

    result = import_assets(bundle, destination, replace=True)
    assert result["imported_files"] == 3
    assert target.read_text(encoding="utf-8") == '{"id":"fixture"}\n'


def test_corrupt_bundle_is_rejected_without_replacing_existing_file(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _source_workspace(source)
    bundle = tmp_path / "bundle"
    export_assets(source, bundle)
    corrupted = bundle / "payload/data/corpus/e2012/documents.jsonl"
    corrupted.write_text("corrupted\n", encoding="utf-8")
    assert verify_bundle(bundle)["passed"] is False

    destination = tmp_path / "destination"
    target = destination / "data/corpus/e2012/documents.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(TransferError, match="source size changed|source checksum"):
        import_assets(bundle, destination, replace=True)
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_bundle_manifest_rejects_paths_outside_repository(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "../outside",
                        "bytes": 0,
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TransferError, match="safe repository-relative path"):
        verify_bundle(bundle)
