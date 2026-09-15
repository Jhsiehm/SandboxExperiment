"""Fail-closed provenance checks for resumable prediction runs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from psbx.corpus.index import HybridIndex
from psbx.io import read_json, write_json
from psbx.paths import resolve, run_dir
from psbx.schemas import Epoch, Question, RunConfig

PROVENANCE_FILENAME = "provenance.json"


class RunProvenanceMismatch(RuntimeError):
    """Existing outputs were produced under an unknown or different run contract."""


def _sha256_file(path: Path) -> str | None:
    source = resolve(path)
    if not source.is_file():
        return None
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _corpus_fingerprint(index: HybridIndex) -> str:
    digest = hashlib.sha256()
    digest.update(index.cutoff.isoformat().encode("ascii"))
    for document in index.docs:
        digest.update(document.model_dump_json(exclude={"embedding"}).encode("utf-8"))
        digest.update(b"\n")
    embeddings = index.embeddings
    digest.update(str(embeddings.dtype).encode("ascii"))
    digest.update(str(tuple(embeddings.shape)).encode("ascii"))
    digest.update(embeddings.tobytes(order="C"))
    return digest.hexdigest()


def build_run_provenance(
    run: RunConfig,
    epoch: Epoch,
    index: HybridIndex,
    questions: list[Question],
) -> dict[str, Any]:
    """Describe every input that can change a resumed forecast."""
    referenced_files: dict[str, str | None] = {
        "models": _sha256_file(resolve("config/models.yaml")),
        "question_set": _sha256_file(resolve(run.question_set)),
    }
    if run.swarm_roster:
        referenced_files["swarm_roster"] = _sha256_file(resolve(run.swarm_roster))
    if run.perspectives:
        referenced_files["perspectives"] = _sha256_file(resolve(run.perspectives))
    contract: dict[str, Any] = {
        "schema_version": 2,
        "run_id": run.run_id,
        "epoch_id": epoch.id,
        "cutoff": epoch.cutoff_date.isoformat(),
        "sandbox_mode": run.sandbox_mode,
        "source_type": run.source_type or "all",
        "run_config": run.model_dump(mode="json"),
        "referenced_files": referenced_files,
        "questions_sha256": _json_digest(
            [question.model_dump(mode="json") for question in questions]
        ),
        "corpus_sha256": _corpus_fingerprint(index),
        "evidence_policy": {
            "use": run.evidence_use,
            "total_documents": len(index.docs),
            "research_eligible_documents": sum(
                1 for document in index.docs if document.research_eligible
            ),
            "authenticity_counts": dict(
                sorted(Counter(document.authenticity for document in index.docs).items())
            ),
        },
    }
    return {**contract, "fingerprint": _json_digest(contract)}


def ensure_run_provenance(
    run: RunConfig,
    epoch: Epoch,
    index: HybridIndex,
    questions: list[Question],
    existing_outputs: Iterable[Path],
) -> Path:
    """Write a new contract or verify it before reusing any saved output."""
    destination = run_dir(run.run_id) / PROVENANCE_FILENAME
    current = build_run_provenance(run, epoch, index, questions)
    has_existing = any(path.is_file() and path.stat().st_size > 0 for path in existing_outputs)
    if has_existing:
        if not destination.is_file():
            if run.sandbox_mode == "host" and run.source_type is None:
                # Legacy host runs predate provenance tracking and make no
                # sealed-container claim. Adopt them once so existing local
                # smoke/test workflows remain resumable; isolated runs fail
                # closed because their access boundary cannot be inferred.
                write_json(destination, current)
                return destination
            raise RunProvenanceMismatch(
                f"run {run.run_id!r} has existing outputs without {PROVENANCE_FILENAME}; "
                "choose a new run_id instead of treating unverifiable data as resumable"
            )
        try:
            previous = read_json(destination)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RunProvenanceMismatch(
                f"run {run.run_id!r} has unreadable provenance: {exc}"
            ) from exc
        if previous.get("fingerprint") != current["fingerprint"]:
            raise RunProvenanceMismatch(
                f"run {run.run_id!r} was created with a different config, corpus, "
                "question set, model catalog, or isolation scope; choose a new run_id"
            )
        return destination
    write_json(destination, current)
    return destination
