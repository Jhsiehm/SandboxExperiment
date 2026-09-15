"""Resumable bulk sync for the cutoff-safe e2012 Census population pack.

The sync intentionally downloads only the historical tables needed by Track B. Raw files remain in
the ignored population-build zone and are never mounted into the forecast runtime or search corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

CUTOFF_DATE = date(2012, 6, 30)
DEFAULT_OUTPUT_ROOT = Path("data/population-input/e2012/census")
ACS_SUMMARY_ROOT = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/2010/data"
)
PUMS_ROOT = "https://www2.census.gov/programs-surveys/acs/data/pums/2010/5-Year"
DECENNIAL_DP_ROOT = "https://www2.census.gov/census_2010/03-Demographic_Profile"
CVAP_ROOT = "https://www2.census.gov/programs-surveys/rdo"
USER_AGENT = "PredictionSandbox/0.1.0 (Track B Census population-build sync)"

# These sequences cover the variables currently canonicalized by Track B. Each archive contains
# estimates and 90-percent margins of error for every non-tract geography in its area.
ACS_SEQUENCES = {
    10: ("B01001",),  # sex by age
    13: ("B03002",),  # Hispanic or Latino origin by race
    17: ("B05001",),  # citizenship
    33: ("B11016",),  # household type by household size
    35: ("B12001",),  # marital status
    40: ("B15001", "B15002"),  # educational attainment
    53: ("B19001",),  # household income
    69: ("B23001",),  # employment status
    95: ("B25003",),  # tenure
}


@dataclass(frozen=True)
class CensusArea:
    fips: str
    abbreviation: str
    name: str

    @property
    def acs_slug(self) -> str:
        if self.fips == "11":
            return "DistrictOfColumbia"
        return self.name.replace(" ", "")

    @property
    def decennial_slug(self) -> str:
        return self.name.replace(" ", "_")


AREAS = (
    CensusArea("01", "al", "Alabama"),
    CensusArea("02", "ak", "Alaska"),
    CensusArea("04", "az", "Arizona"),
    CensusArea("05", "ar", "Arkansas"),
    CensusArea("06", "ca", "California"),
    CensusArea("08", "co", "Colorado"),
    CensusArea("09", "ct", "Connecticut"),
    CensusArea("10", "de", "Delaware"),
    CensusArea("11", "dc", "District of Columbia"),
    CensusArea("12", "fl", "Florida"),
    CensusArea("13", "ga", "Georgia"),
    CensusArea("15", "hi", "Hawaii"),
    CensusArea("16", "id", "Idaho"),
    CensusArea("17", "il", "Illinois"),
    CensusArea("18", "in", "Indiana"),
    CensusArea("19", "ia", "Iowa"),
    CensusArea("20", "ks", "Kansas"),
    CensusArea("21", "ky", "Kentucky"),
    CensusArea("22", "la", "Louisiana"),
    CensusArea("23", "me", "Maine"),
    CensusArea("24", "md", "Maryland"),
    CensusArea("25", "ma", "Massachusetts"),
    CensusArea("26", "mi", "Michigan"),
    CensusArea("27", "mn", "Minnesota"),
    CensusArea("28", "ms", "Mississippi"),
    CensusArea("29", "mo", "Missouri"),
    CensusArea("30", "mt", "Montana"),
    CensusArea("31", "ne", "Nebraska"),
    CensusArea("32", "nv", "Nevada"),
    CensusArea("33", "nh", "New Hampshire"),
    CensusArea("34", "nj", "New Jersey"),
    CensusArea("35", "nm", "New Mexico"),
    CensusArea("36", "ny", "New York"),
    CensusArea("37", "nc", "North Carolina"),
    CensusArea("38", "nd", "North Dakota"),
    CensusArea("39", "oh", "Ohio"),
    CensusArea("40", "ok", "Oklahoma"),
    CensusArea("41", "or", "Oregon"),
    CensusArea("42", "pa", "Pennsylvania"),
    CensusArea("44", "ri", "Rhode Island"),
    CensusArea("45", "sc", "South Carolina"),
    CensusArea("46", "sd", "South Dakota"),
    CensusArea("47", "tn", "Tennessee"),
    CensusArea("48", "tx", "Texas"),
    CensusArea("49", "ut", "Utah"),
    CensusArea("50", "vt", "Vermont"),
    CensusArea("51", "va", "Virginia"),
    CensusArea("53", "wa", "Washington"),
    CensusArea("54", "wv", "West Virginia"),
    CensusArea("55", "wi", "Wisconsin"),
    CensusArea("56", "wy", "Wyoming"),
)


@dataclass(frozen=True)
class CensusArtifact:
    artifact_id: str
    source_id: str
    family: str
    geography_id: str
    url: str
    relative_path: str
    release_date: str
    release_verified: bool = True


def census_artifact_plan() -> list[CensusArtifact]:
    artifacts: list[CensusArtifact] = []
    for area in AREAS:
        abbr = area.abbreviation
        artifacts.extend(
            [
                CensusArtifact(
                    artifact_id=f"pums-person-{abbr}",
                    source_id="acs_pums_2006_2010",
                    family="pums_person",
                    geography_id=f"state:{area.fips}",
                    url=f"{PUMS_ROOT}/csv_p{abbr}.zip",
                    relative_path=f"raw/pums/{abbr}/csv_p{abbr}.zip",
                    release_date="2011-12-29",
                ),
                CensusArtifact(
                    artifact_id=f"pums-housing-{abbr}",
                    source_id="acs_pums_2006_2010",
                    family="pums_housing",
                    geography_id=f"state:{area.fips}",
                    url=f"{PUMS_ROOT}/csv_h{abbr}.zip",
                    relative_path=f"raw/pums/{abbr}/csv_h{abbr}.zip",
                    release_date="2011-12-29",
                ),
            ]
        )
        dp_name = f"{abbr}2010.dp.zip"
        dp_url = f"{DECENNIAL_DP_ROOT}/{area.decennial_slug}/{dp_name}"
        # Census's CDN currently caches a 200-status rejection page for the bare Ohio URL.
        # This benign query reaches the same official object and is validated as a ZIP below.
        if area.fips == "39":
            dp_url += "?download=1"
        artifacts.append(
            CensusArtifact(
                artifact_id=f"decennial-dp-{abbr}",
                source_id="census_2010_dp1",
                family="decennial_demographic_profile",
                geography_id=f"state:{area.fips}",
                url=dp_url,
                relative_path=f"raw/decennial-dp/{abbr}/{dp_name}",
                release_date="2011-08-25",
            )
        )
        for sequence in ACS_SEQUENCES:
            name = f"20105{abbr}{sequence:04d}000.zip"
            artifacts.append(
                CensusArtifact(
                    artifact_id=f"acs5-{abbr}-seq-{sequence:04d}",
                    source_id="acs5_2006_2010",
                    family="acs5_summary_sequence",
                    geography_id=f"state:{area.fips}",
                    url=(
                        f"{ACS_SUMMARY_ROOT}/5_year_seq_by_state/{area.acs_slug}/"
                        f"All_Geographies_Not_Tracts_Block_Groups/{name}"
                    ),
                    relative_path=f"raw/acs5-summary/{abbr}/{name}",
                    release_date="2011-12-08",
                )
            )

    national_dp = "us2010.dp.zip"
    artifacts.append(
        CensusArtifact(
            artifact_id="decennial-dp-us",
            source_id="census_2010_dp1",
            family="decennial_demographic_profile",
            geography_id="us:1",
            url=f"{DECENNIAL_DP_ROOT}/National/{national_dp}",
            relative_path=f"raw/decennial-dp/us/{national_dp}",
            release_date="2011-05-26",
        )
    )
    for sequence in ACS_SEQUENCES:
        name = f"20105us{sequence:04d}000.zip"
        artifacts.append(
            CensusArtifact(
                artifact_id=f"acs5-us-seq-{sequence:04d}",
                source_id="acs5_2006_2010",
                family="acs5_summary_sequence",
                geography_id="us:1",
                url=(
                    f"{ACS_SUMMARY_ROOT}/5_year_seq_by_state/UnitedStates/"
                    f"All_Geographies_Not_Tracts_Block_Groups/{name}"
                ),
                relative_path=f"raw/acs5-summary/us/{name}",
                release_date="2011-12-08",
            )
        )
    artifacts.extend(
        [
            CensusArtifact(
                artifact_id="acs5-geography-files",
                source_id="acs5_2006_2010",
                family="support",
                geography_id="us:all",
                url=(
                    f"{ACS_SUMMARY_ROOT}/5_year_entire_sf/"
                    "2010_ACS_Geography_Files.zip"
                ),
                relative_path="raw/acs5-summary/support/2010_ACS_Geography_Files.zip",
                release_date="2011-12-08",
            ),
            CensusArtifact(
                artifact_id="acs5-summary-templates",
                source_id="acs5_2006_2010",
                family="support",
                geography_id="us:all",
                url=f"{ACS_SUMMARY_ROOT}/2010_5yr_SummaryFileTemplates.zip",
                relative_path=(
                    "raw/acs5-summary/support/2010_5yr_SummaryFileTemplates.zip"
                ),
                release_date="2011-12-08",
            ),
            CensusArtifact(
                artifact_id="cvap-2006-2010",
                source_id="cvap_2006_2010",
                family="cvap",
                geography_id="us:all",
                url=f"{CVAP_ROOT}/CVAP_2006-2010_ACS_csv_files.zip",
                relative_path="raw/cvap/CVAP_2006-2010_ACS_csv_files.zip",
                release_date="2012-02-09",
            ),
        ]
    )
    return artifacts


def summarize_plan(artifacts: list[CensusArtifact] | None = None) -> dict:
    artifacts = artifacts or census_artifact_plan()
    families: dict[str, int] = {}
    for artifact in artifacts:
        families[artifact.family] = families.get(artifact.family, 0) + 1
    return {
        "epoch_id": "e2012",
        "cutoff_date": CUTOFF_DATE.isoformat(),
        "states_plus_dc": len(AREAS),
        "national_aggregate": True,
        "artifact_count": len(artifacts),
        "families": families,
        "acs_sequences": {
            str(sequence): list(tables) for sequence, tables in ACS_SEQUENCES.items()
        },
        "national_pums_derivation": (
            "Union the 51 state/D.C. person and housing archives; the redundant "
            "national PUMS archives are intentionally not downloaded."
        ),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"corrupt ZIP member {bad!r} in {path}")


def _download_one(
    client: httpx.Client,
    artifact: CensusArtifact,
    output_root: Path,
    *,
    retries: int = 3,
) -> dict:
    destination = output_root / artifact.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        try:
            _validate_zip(destination)
        except (ValueError, zipfile.BadZipFile):
            invalid = destination.with_suffix(
                destination.suffix + f".invalid-{int(time.time())}"
            )
            os.replace(destination, invalid)
        else:
            downloaded_at = datetime.fromtimestamp(
                destination.stat().st_mtime, timezone.utc
            ).isoformat()
            return {
                **asdict(artifact),
                "local_path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "downloaded_at": downloaded_at,
                "server_last_modified": None,
                "status": "existing_verified",
            }

    partial = destination.with_suffix(destination.suffix + ".part")
    error: Exception | None = None
    for attempt in range(retries):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with client.stream("GET", artifact.url, headers=headers) as response:
                response.raise_for_status()
                append = offset > 0 and response.status_code == 206
                mode = "ab" if append else "wb"
                with partial.open(mode) as handle:
                    for chunk in response.iter_bytes(1024 * 1024):
                        handle.write(chunk)
                last_modified = response.headers.get("last-modified")
            _validate_zip(partial)
            os.replace(partial, destination)
            return {
                **asdict(artifact),
                "local_path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "server_last_modified": last_modified,
                "status": "downloaded",
            }
        except (ValueError, zipfile.BadZipFile) as exc:
            error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(2**attempt)
        except (httpx.HTTPError, OSError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"failed to download {artifact.artifact_id}: {type(error).__name__}"
    ) from None


def _write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sync_census_pack(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    workers: int = 4,
    progress: Callable[[int, int, CensusArtifact], None] | None = None,
) -> dict:
    if workers < 1 or workers > 8:
        raise ValueError("workers must be between 1 and 8")
    root = Path(output_root)
    artifacts = census_artifact_plan()
    results: list[dict] = []
    failures: list[str] = []
    with httpx.Client(
        timeout=httpx.Timeout(180.0, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_download_one, client, artifact, root): artifact
                for artifact in artifacts
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                artifact = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    failures.append(str(exc))
                    results.append(
                        {
                            **asdict(artifact),
                            "local_path": str(root / artifact.relative_path),
                            "bytes": 0,
                            "sha256": None,
                            "downloaded_at": None,
                            "server_last_modified": None,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                if progress is not None:
                    progress(completed, len(artifacts), artifact)

    results.sort(key=lambda row: row["artifact_id"])
    payload = {
        "schema_version": 1,
        **summarize_plan(artifacts),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(root),
        "total_bytes": sum(int(row["bytes"]) for row in results),
        "downloaded": sum(row["status"] == "downloaded" for row in results),
        "existing_verified": sum(
            row["status"] == "existing_verified" for row in results
        ),
        "passed": not failures,
        "failures": failures,
        "artifact_release_review": (
            "Local SHA-256 values prove the downloaded bytes used by this workspace. "
            "Before a sealed build, copy reviewed records into a Population Artifact "
            "Manifest and independently confirm exact historical artifact versions."
        ),
        "artifacts": results,
    }
    manifest_path = root / "manifest.json"
    _write_manifest(manifest_path, payload)
    return {"manifest_path": str(manifest_path), **payload}


def verify_census_pack(manifest_path: str | Path) -> dict:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    total_bytes = 0
    artifacts = payload.get("artifacts", [])
    expected_ids = {row.artifact_id for row in census_artifact_plan()}
    actual_ids = {str(row.get("artifact_id")) for row in artifacts}
    for artifact_id in sorted(expected_ids - actual_ids):
        failures.append(f"manifest missing artifact: {artifact_id}")
    for artifact_id in sorted(actual_ids - expected_ids):
        failures.append(f"unexpected manifest artifact: {artifact_id}")
    if payload.get("artifact_count") != len(artifacts):
        failures.append("manifest artifact_count does not match its artifact records")
    output_root = Path(payload.get("output_root", path.parent)).resolve()
    for artifact in artifacts:
        if artifact.get("status") == "failed":
            failures.append(f"sync failed: {artifact['artifact_id']}")
            continue
        local_path = Path(artifact["local_path"]).resolve()
        if not local_path.is_relative_to(output_root):
            failures.append(f"path outside output root: {artifact['artifact_id']}")
            continue
        if not local_path.exists():
            failures.append(f"missing: {artifact['artifact_id']}")
            continue
        try:
            _validate_zip(local_path)
        except (ValueError, zipfile.BadZipFile):
            failures.append(f"invalid zip: {artifact['artifact_id']}")
            continue
        digest = _sha256(local_path)
        if digest != artifact.get("sha256"):
            failures.append(f"checksum mismatch: {artifact['artifact_id']}")
        total_bytes += local_path.stat().st_size
    if total_bytes != payload.get("total_bytes"):
        failures.append("manifest total_bytes does not match verified files")
    return {
        "manifest_path": str(path),
        "artifact_count": len(artifacts),
        "total_bytes": total_bytes,
        "passed": not failures,
        "failures": failures,
    }
