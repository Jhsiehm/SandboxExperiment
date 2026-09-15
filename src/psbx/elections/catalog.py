"""Public, path-free catalog used by dataset filters in the dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from psbx.population.profiles import public_population_profiles

from .registry import load_election_sources


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest_layers(base: Path, kind: str) -> list[dict]:
    rows = []
    for path in sorted(base.glob("*/manifest.json")):
        payload = _read_json(path)
        if not payload:
            continue
        dataset_id = str(payload.get("dataset_id") or path.parent.name)
        years = payload.get("years") or ([payload["year"]] if payload.get("year") else [])
        rows.append(
            {
                "id": dataset_id,
                "kind": kind,
                "label": str(payload.get("label") or dataset_id),
                "status": "ready" if payload.get("passed", True) else "incomplete",
                "years": years,
                "states": payload.get("states") or [],
                "geography_levels": payload.get("geography_levels") or [],
                "office_levels": payload.get("office_levels") or [],
                "source_ids": payload.get("source_ids") or [],
                "coverage_by_state": payload.get("coverage_by_state") or {},
                "rows": payload.get("rows"),
                "contests": payload.get("contests"),
                "synthetic": False,
                "runtime_access": False,
                "use": "display_and_evaluation_comparison_only",
                "cutoff_date": payload.get("cutoff_date"),
                "certified_rows": payload.get("certified_rows"),
                "warnings": payload.get("warnings") or [],
                "note": (
                    "Official aggregate election returns."
                    if kind == "election"
                    else "Official Census estimates joined by explicit geography vintage."
                ),
            }
        )
    return rows


def public_data_layers(epoch_id: str, *, root: Path) -> dict:
    profiles = public_population_profiles(epoch_id, root=root)
    aggregate_coverage: dict[str, dict] = {}
    for profile in profiles:
        geography = profile["geography"]
        state_fips = geography["state_fips"]
        if state_fips == "00":
            continue
        row = aggregate_coverage.setdefault(
            state_fips, {"geography_levels": [], "geography_ids": {}}
        )
        level = geography["type"]
        row["geography_levels"].append(level)
        row["geography_ids"].setdefault(level, []).append(geography["id"])
    for row in aggregate_coverage.values():
        row["geography_levels"] = sorted(set(row["geography_levels"]))
        row["geography_ids"] = {
            level: sorted(set(ids)) for level, ids in row["geography_ids"].items()
        }
    aggregate = {
        "id": f"{epoch_id}-population-builds",
        "kind": "population",
        "label": f"All {epoch_id} population builds",
        "status": "ready" if any(profile["runnable"] for profile in profiles) else "incomplete",
        "years": [int(epoch_id.removeprefix("e"))] if epoch_id[1:].isdigit() else [],
        "states": sorted(aggregate_coverage),
        "geography_levels": sorted(
            {
                level
                for row in aggregate_coverage.values()
                for level in row["geography_levels"]
            }
        ),
        "coverage_by_state": aggregate_coverage,
        "synthetic": True,
        "runtime_access": True,
        "use": "population_weighting_after_profile_validation",
        "note": "Combined coverage view; only validated profiles are runnable.",
    }
    population_layers = [
        {
            "id": profile["population_id"],
            "kind": "population",
            "label": profile["label"],
            "status": "ready" if profile["runnable"] else "incomplete",
            "years": [int(epoch_id.removeprefix("e"))] if epoch_id[1:].isdigit() else [],
            "states": [profile["geography"]["state_fips"]],
            "geography_levels": [profile["geography"]["type"]],
            "coverage_by_state": {
                profile["geography"]["state_fips"]: {
                    "geography_levels": [profile["geography"]["type"]],
                    "geography_ids": {
                        profile["geography"]["type"]: [profile["geography"]["id"]]
                    },
                }
            },
            "synthetic": True,
            "runtime_access": bool(profile["runnable"]),
            "use": "population_weighting_after_profile_validation",
            "represented_population": profile.get("target_population"),
            "representative_cells": profile.get("representative_cells"),
            "note": profile.get("disclosure"),
        }
        for profile in profiles
    ]
    layers = (
        [aggregate]
        + population_layers
        + _manifest_layers(root / "data/elections/census", "census")
        + _manifest_layers(root / "data/elections/normalized", "election")
    )
    try:
        registered = load_election_sources(root / "config/election_sources.yaml")
    except (OSError, ValueError):
        registered = {}
    return {
        "layers": layers,
        "kinds": [
            {"id": "population", "label": "Synthetic population sets"},
            {"id": "census", "label": "Census demographic data"},
            {"id": "election", "label": "Election records"},
        ],
        "default_layer_id": aggregate["id"],
        "comparison_layer_policy": {
            "runtime_access": False,
            "use": "display_and_evaluation_comparison_only",
            "note": "Election outcomes and Census comparison layers never enter agent prompts.",
        },
        "registered_sources": [
            {
                "id": source.id,
                "kind": "census" if source.scope == "demographic" else "election",
                "label": source.title,
                "provider": source.provider,
                "scope": source.scope,
                "status": source.status,
                "official": source.official,
                "year_start": source.year_start,
                "year_end": source.year_end,
                "geography_levels": list(source.election_geographies),
                "office_levels": list(source.office_levels),
                "normalized": source.normalized,
                "url": source.url,
                "note": source.notes,
            }
            for source in registered.values()
        ],
    }
