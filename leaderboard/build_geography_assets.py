"""Build compact, browser-ready geography assets from official Census files.

This is an offline maintainer tool, not an application dependency. Install
``pyshp`` in the active development environment before running it. The output
keeps only public boundary geometry and a small allowlist of display fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import shapefile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "leaderboard/static/geography/e2012"
BASE = "https://www2.census.gov/geo/tiger/TIGERrd13"
BASE_BY_STATE = "https://www2.census.gov/geo/tiger/TIGERrd13_st"
US_FIPS = {
    "01",
    "02",
    "04",
    "05",
    "06",
    "08",
    "09",
    "10",
    "11",
    "12",
    "13",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
    "41",
    "42",
    "44",
    "45",
    "46",
    "47",
    "48",
    "49",
    "50",
    "51",
    "53",
    "54",
    "55",
    "56",
}
PILOT_FIPS = ("06", "11", "34", "56")


def _download(url: str, destination: Path) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Polisim geography builder"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            handle.write(chunk)
    return digest.hexdigest()


def _distance(point: list[float], start: list[float], end: list[float]) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    position = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    position = max(0.0, min(1.0, position))
    projected = [start[0] + position * dx, start[1] + position * dy]
    return math.hypot(point[0] - projected[0], point[1] - projected[1])


def _rdp(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(points) <= 2:
        return points
    furthest = 0.0
    index = 0
    for candidate in range(1, len(points) - 1):
        distance = _distance(points[candidate], points[0], points[-1])
        if distance > furthest:
            furthest = distance
            index = candidate
    if furthest <= tolerance:
        return [points[0], points[-1]]
    return _rdp(points[: index + 1], tolerance)[:-1] + _rdp(points[index:], tolerance)


def _simplify_ring(raw: Iterable[Iterable[float]], tolerance: float) -> list[list[float]]:
    points = [[float(point[0]), float(point[1])] for point in raw]
    if not points:
        return []
    closed = points[0] == points[-1]
    work = points[:-1] if closed else points
    if len(work) > 3:
        # Rotate away from an arbitrary closure point so narrow coastal rings
        # do not collapse into a single segment during simplification.
        pivot = max(range(len(work)), key=lambda index: _distance(work[index], work[0], work[-1]))
        work = work[pivot:] + work[:pivot] + [work[pivot]]
        work = _rdp(work, tolerance)
        if work and work[0] == work[-1]:
            work = work[:-1]
    rounded = [[round(point[0], 5), round(point[1], 5)] for point in work]
    if len(rounded) < 3:
        rounded = [[round(point[0], 5), round(point[1], 5)] for point in points[:-1]]
    if rounded and (closed or rounded[0] != rounded[-1]):
        rounded.append(rounded[0])
    return rounded


def _simplify_geometry(geometry: dict[str, Any], tolerance: float) -> dict[str, Any]:
    kind = geometry["type"]
    coordinates = geometry["coordinates"]
    if kind == "Polygon":
        simplified = [_simplify_ring(ring, tolerance) for ring in coordinates]
    elif kind == "MultiPolygon":
        simplified = [
            [_simplify_ring(ring, tolerance) for ring in polygon] for polygon in coordinates
        ]
    else:
        raise ValueError(f"unsupported boundary geometry: {kind}")
    return {"type": kind, "coordinates": simplified}


def _first(record: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return default


def _feature_properties(layer: str, record: dict[str, Any]) -> dict[str, Any]:
    state_fips = str(_first(record, "STATEFP", "STATEFP10", default="")).zfill(2)
    area_land = int(float(_first(record, "ALAND", "ALAND10", default=0)))
    area_water = int(float(_first(record, "AWATER", "AWATER10", default=0)))
    if layer == "states":
        code = state_fips
        abbreviation = str(_first(record, "STUSPS", "STUSPS10", default=""))
        label = str(_first(record, "NAME", "NAME10", default=abbreviation))
        geography_id = f"state:{state_fips}"
    elif layer == "congressional":
        code = str(_first(record, "CD113FP", "CD113", default="00")).zfill(2)
        abbreviation = code
        label = str(_first(record, "NAMELSAD", "NAMELSAD10", default=f"District {code}"))
        geography_id = f"congressional_district:{state_fips}:{code}"
    elif layer == "state_senate":
        code = str(_first(record, "SLDUST", "SLDUST10", default="000"))
        abbreviation = code
        label = str(_first(record, "NAMELSAD", "NAMELSAD10", default=f"District {code}"))
        geography_id = f"state_legislative_upper:{state_fips}:{code}"
    elif layer == "state_house":
        code = str(_first(record, "SLDLST", "SLDLST10", default="000"))
        abbreviation = code
        label = str(_first(record, "NAMELSAD", "NAMELSAD10", default=f"District {code}"))
        geography_id = f"state_legislative_lower:{state_fips}:{code}"
    elif layer == "county":
        code = str(_first(record, "COUNTYFP", "COUNTYFP10", default="000")).zfill(3)
        abbreviation = code
        label = str(_first(record, "NAMELSAD", "NAMELSAD10", "NAME", "NAME10", default=code))
        geography_id = f"county:{state_fips}:{code}"
    elif layer == "voting_district":
        county = str(_first(record, "COUNTYFP", "COUNTYFP10", default="000")).zfill(3)
        code = str(_first(record, "VTDST", "VTDST10", default=""))
        abbreviation = code
        label = str(_first(record, "NAMELSAD", "NAMELSAD10", "NAME", "NAME10", default=code))
        geography_id = f"voting_district:{state_fips}:{county}:{code}"
    else:
        raise ValueError(f"unknown layer: {layer}")
    return {
        "id": geography_id,
        "state_fips": state_fips,
        "code": code,
        "abbreviation": abbreviation,
        "label": label,
        "land_m2": area_land,
        "water_m2": area_water,
    }


def _read_features(archive: Path, layer: str, tolerance: float) -> list[dict[str, Any]]:
    unpacked = archive.parent / archive.stem
    unpacked.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(unpacked)
    shapefile_path = next(unpacked.glob("*.shp"))
    features = []
    with shapefile.Reader(str(shapefile_path), encoding="latin1") as reader:
        fields = [field[0] for field in reader.fields[1:]]
        for shape_record in reader.iterShapeRecords():
            record = dict(zip(fields, shape_record.record))
            properties = _feature_properties(layer, record)
            if properties["state_fips"] not in US_FIPS:
                continue
            if layer not in {"states", "county"} and properties["code"].startswith("Z"):
                continue
            geometry = _simplify_geometry(shape_record.shape.__geo_interface__, tolerance)
            features.append(
                {
                    "type": "Feature",
                    "id": properties["id"],
                    "properties": properties,
                    "geometry": geometry,
                }
            )
    return features


def _write_collection(path: Path, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, Any]] = []
    layer_states: dict[str, set[str]] = defaultdict(set)
    layer_counts: dict[str, int] = defaultdict(int)
    with tempfile.TemporaryDirectory(prefix="polisim-geography-") as directory:
        temporary = Path(directory)

        national_specs = (
            ("states", f"{BASE}/STATE10/tl_rd13_us_state10.zip", 0.02),
            ("congressional", f"{BASE}/CD113/tl_rd13_us_cd113.zip", 0.006),
        )
        for layer, url, tolerance in national_specs:
            archive = temporary / f"{layer}.zip"
            digest = _download(url, archive)
            features = _read_features(archive, layer, tolerance)
            if layer == "states":
                _write_collection(OUTPUT / "states.json", features)
            else:
                grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for feature in features:
                    grouped[feature["properties"]["state_fips"]].append(feature)
                for state_fips, rows in grouped.items():
                    _write_collection(OUTPUT / layer / f"{state_fips}.json", rows)
                    layer_states[layer].add(state_fips)
            layer_counts[layer] += len(features)
            if layer == "states":
                layer_states[layer] = {feature["properties"]["state_fips"] for feature in features}
            sources.append({"layer": layer, "url": url, "sha256": digest})

        pilot_specs = (
            ("state_senate", "SLDU", "sldu", 0.0025, ("06", "34", "56")),
            ("state_house", "SLDL", "sldl", 0.0025, ("06", "34", "56")),
            ("county", "COUNTY10", "county10", 0.003, PILOT_FIPS),
        )
        for layer, census_directory, suffix, tolerance, state_fips_values in pilot_specs:
            for state_fips in state_fips_values:
                url = f"{BASE}/{census_directory}/tl_rd13_{state_fips}_{suffix}.zip"
                archive = temporary / f"{layer}-{state_fips}.zip"
                digest = _download(url, archive)
                features = _read_features(archive, layer, tolerance)
                _write_collection(OUTPUT / layer / f"{state_fips}.json", features)
                layer_states[layer].add(state_fips)
                layer_counts[layer] += len(features)
                sources.append(
                    {
                        "layer": layer,
                        "state_fips": state_fips,
                        "url": url,
                        "sha256": digest,
                    }
                )

        # Voting districts are published as county-based files. New Jersey is
        # the intentionally small first proof because it is the state used in
        # the dashboard's dense drill-down example.
        county_payload = json.loads((OUTPUT / "county/34.json").read_text(encoding="utf-8"))
        voting_features: list[dict[str, Any]] = []
        for county in county_payload["features"]:
            county_fips = county["properties"]["code"]
            county_geoid = f"34{county_fips}"
            url = f"{BASE_BY_STATE}/34/{county_geoid}/tl_rd13_{county_geoid}_vtd10.zip"
            archive = temporary / f"voting-district-{county_geoid}.zip"
            digest = _download(url, archive)
            features = _read_features(archive, "voting_district", 0.001)
            voting_features.extend(features)
            sources.append(
                {
                    "layer": "voting_district",
                    "state_fips": "34",
                    "county_fips": county_fips,
                    "url": url,
                    "sha256": digest,
                }
            )
        _write_collection(OUTPUT / "voting_district/34.json", voting_features)
        layer_states["voting_district"].add("34")
        layer_counts["voting_district"] = len(voting_features)

    manifest = {
        "schema_version": 1,
        "epoch_id": "e2012",
        "boundary_vintage": "2012 election cycle / 113th Congress TIGER/Line release",
        "source_agency": "U.S. Census Bureau",
        "generated_by": "leaderboard/build_geography_assets.py",
        "layers": {
            layer: {
                "feature_count": layer_counts[layer],
                "states": sorted(layer_states[layer]),
            }
            for layer in (
                "states",
                "congressional",
                "state_senate",
                "state_house",
                "county",
                "voting_district",
            )
        },
        "sources": sources,
        "disclosure": (
            "Boundaries are for statistical display and selection. Voting-district geometry does "
            "not imply that municipal election results have been imported."
        ),
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
