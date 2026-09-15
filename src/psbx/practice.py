"""Explicit, provider-free preparation and status for the local practice workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psbx.config import load_epochs
from psbx.corpus.build_index import build_index
from psbx.io import read_json
from psbx.paths import repo_root, resolve
from psbx.population.profiles import public_population_profiles
from psbx.population.runner import run_population_build


def practice_status(epoch_id: str = "e2012", *, root: Path | None = None) -> dict[str, Any]:
    """Read practice prerequisites without generating files or starting services."""
    root = (root or repo_root()).resolve()
    epoch = load_epochs(root / "config" / "epochs.yaml")[epoch_id]
    corpus_root = root / epoch.corpus_index_path
    documents = corpus_root / "documents.jsonl"
    embeddings = corpus_root / "embeddings.npy"
    meta_path = corpus_root / "meta.json"
    questions = root / "data" / "questions" / f"{epoch.id}.jsonl"
    meta = read_json(meta_path) if meta_path.is_file() else {}
    corpus_built = all(path.is_file() and path.stat().st_size > 0 for path in (
        documents,
        embeddings,
        meta_path,
    ))
    question_set_built = questions.is_file() and questions.stat().st_size > 0
    profiles = public_population_profiles(epoch.id, root=root)
    fixture = next(
        (
            profile
            for profile in profiles
            if profile["population_id"] == "fixture-township-e2012"
        ),
        None,
    )
    fixture_ready = bool(fixture and fixture["runnable"])
    return {
        "epoch_id": epoch.id,
        "cutoff_date": epoch.cutoff_date.isoformat(),
        "question_set_built": question_set_built,
        "corpus_built": corpus_built,
        "corpus_documents": int(meta.get("n_docs") or 0) if corpus_built else 0,
        "authenticity_counts": meta.get("authenticity_counts") or {},
        "research_eligible_documents": int(
            meta.get("research_eligible_documents") or 0
        ),
        "fixture_profile_ready": fixture_ready,
        "fixture_population_id": fixture["population_id"] if fixture_ready else None,
        "viewer_ready": question_set_built,
        "isolated_run_assets_ready": question_set_built and corpus_built,
        "prepare_command": f"psbx practice prepare --epoch {epoch.id}",
        "seal_command": f"psbx sandbox up --epoch {epoch.id}",
        "note": (
            "Viewer inspection can use tracked in-memory practice fixtures. An isolated "
            "practice run additionally requires the generated corpus and verified sidecar."
        ),
    }


def prepare_practice(epoch_id: str = "e2012") -> dict[str, Any]:
    """Build deterministic practice assets only; never invoke a model provider."""
    root = repo_root().resolve()
    epoch = load_epochs(root / "config" / "epochs.yaml")[epoch_id]
    index = build_index(epoch, live=False, backend="hashing")
    population = run_population_build(
        root / "config" / "track_b_fixture.yaml",
        base_dir=root,
        output_override=resolve("data/population"),
    )
    status = practice_status(epoch.id, root=root)
    return {
        **status,
        "prepared": bool(
            status["isolated_run_assets_ready"]
            and status["fixture_profile_ready"]
            and population["validation"]["passed"]
        ),
        "built_documents": len(index.docs),
        "population_validation_passed": bool(population["validation"]["passed"]),
        "next_step": status["seal_command"],
        "provider_calls": 0,
    }
