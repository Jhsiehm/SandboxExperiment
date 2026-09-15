"""Path-free geography payloads for the local interactive map."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ASSET_ROOT = Path(__file__).resolve().parent / "static/geography"
STATE_FIPS = re.compile(r"^[0-9]{2}$")
LAYER_META = {
    "states": {
        "label": "United States",
        "short_label": "U.S. states",
        "geography_level": "state",
        "scope": "national",
    },
    "congressional": {
        "label": "U.S. House districts",
        "short_label": "U.S. House",
        "geography_level": "congressional_district",
        "scope": "state",
    },
    "state_senate": {
        "label": "State senate districts",
        "short_label": "State senate",
        "geography_level": "state_legislative_upper",
        "scope": "state",
    },
    "state_house": {
        "label": "State house / assembly districts",
        "short_label": "State house",
        "geography_level": "state_legislative_lower",
        "scope": "state",
    },
    "county": {
        "label": "Counties and equivalents",
        "short_label": "Counties",
        "geography_level": "county",
        "scope": "state",
    },
    "voting_district": {
        "label": "2010 Census voting districts",
        "short_label": "Voting districts",
        "geography_level": "voting_district",
        "scope": "state",
    },
}


def _epoch_root(epoch_id: str) -> Path:
    if epoch_id != "e2012":
        raise ValueError(f"geographic world is not built for epoch: {epoch_id}")
    return ASSET_ROOT / epoch_id


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("geographic asset is unavailable or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("geographic asset is invalid")
    return payload


def geography_catalog(epoch_id: str = "e2012") -> dict[str, Any]:
    """Return public coverage metadata without revealing filesystem paths."""
    manifest = _read_json(_epoch_root(epoch_id) / "manifest.json")
    built_layers = manifest.get("layers") or {}
    return {
        "schema_version": 1,
        "epoch_id": epoch_id,
        "world": {
            "id": "us",
            "label": "United States",
            "status": "active",
            "scope": "nation, states, D.C., and materialized sub-state boundaries",
        },
        "future_worlds": {
            "status": "not_built",
            "note": (
                "Global and non-U.S. demographic worlds require compatible boundaries, "
                "profiles, and validation before they can be selected."
            ),
        },
        "boundary_vintage": manifest.get("boundary_vintage"),
        "source_agency": manifest.get("source_agency"),
        "disclosure": manifest.get("disclosure"),
        "layers": [
            {
                "id": layer_id,
                **metadata,
                "feature_count": int((built_layers.get(layer_id) or {}).get("feature_count") or 0),
                "states": list((built_layers.get(layer_id) or {}).get("states") or []),
            }
            for layer_id, metadata in LAYER_META.items()
        ],
    }


def geography_payload(
    epoch_id: str = "e2012",
    *,
    layer_id: str = "states",
    state_fips: str | None = None,
) -> dict[str, Any]:
    """Load one allowlisted map layer and return an explicit unavailable state."""
    if layer_id not in LAYER_META:
        raise ValueError(f"unknown geography layer: {layer_id}")
    metadata = LAYER_META[layer_id]
    root = _epoch_root(epoch_id)
    if metadata["scope"] == "national":
        path = root / "states.json"
        state_fips = None
    else:
        if not state_fips or not STATE_FIPS.fullmatch(state_fips):
            raise ValueError("a two-digit state FIPS is required for this layer")
        path = root / layer_id / f"{state_fips}.json"

    if not path.is_file():
        features: dict[str, Any] = {"type": "FeatureCollection", "features": []}
        available = False
    else:
        features = _read_json(path)
        if features.get("type") != "FeatureCollection" or not isinstance(
            features.get("features"), list
        ):
            raise ValueError("geographic asset is invalid")
        available = bool(features["features"])

    catalog = geography_catalog(epoch_id)
    return {
        "schema_version": 1,
        "epoch_id": epoch_id,
        "layer": {"id": layer_id, **metadata},
        "state_fips": state_fips,
        "available": available,
        "feature_count": len(features["features"]),
        "boundary_vintage": catalog["boundary_vintage"],
        "source_agency": catalog["source_agency"],
        "disclosure": catalog["disclosure"],
        "feature_collection": features,
    }
