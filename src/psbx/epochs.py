"""Year-step / epoch-advance hook. Does not ingest future documents."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from psbx.config import load_epochs, load_yaml
from psbx.schemas import Document, Epoch, EpochAdvanceSpec


def load_advance_spec(path: str | Path = "config/epoch-advance.yaml") -> EpochAdvanceSpec:
    return EpochAdvanceSpec.model_validate(load_yaml(path))


def next_cutoff(cutoff: date, years: int = 1) -> date:
    try:
        return cutoff.replace(year=cutoff.year + years)
    except ValueError:
        return date(cutoff.year + years, 2, 28)


def propose_year_step(
    epoch: Epoch | str = "e2012",
    *,
    years: int | None = None,
    spec: EpochAdvanceSpec | None = None,
) -> dict:
    """Describe the next epoch. Does not build an index or load future docs."""
    spec = spec or load_advance_spec()
    if isinstance(epoch, str):
        epoch = load_epochs()[epoch]
    step = years if years is not None else spec.step_years
    nxt = next_cutoff(epoch.cutoff_date, step)
    nxt_end = next_cutoff(epoch.resolution_window_end, step)
    return {
        "from_epoch": epoch.id,
        "from_cutoff": epoch.cutoff_date.isoformat(),
        "from_resolution_window_end": epoch.resolution_window_end.isoformat(),
        "to_cutoff": nxt.isoformat(),
        "to_resolution_window_end": nxt_end.isoformat(),
        "step_years": step,
        "enabled": spec.enabled,
        "ingests_documents": False,
        "policy_sim": False,
        "note": (
            spec.note
            or "Hook only. Later phases add yearly corpora. "
            "Do not leak published_at > to_cutoff. PolicySim is later."
        ),
    }


def documents_allowed_for_advance(
    docs: list[Document],
    old_cutoff: date,
    new_cutoff: date,
) -> list[Document]:
    """Keep only (old_cutoff, new_cutoff]. Reject anything after the new cutoff."""
    if new_cutoff <= old_cutoff:
        raise ValueError("new_cutoff must be after old_cutoff")
    kept: list[Document] = []
    for doc in docs:
        published = doc.published_at
        if isinstance(published, datetime):
            day = published.date()
        else:
            day = published
        if day > new_cutoff:
            continue
        if day <= old_cutoff:
            continue
        kept.append(doc)
    return kept
