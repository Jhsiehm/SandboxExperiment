"""Assess source/documentation readiness without opening respondent datasets."""
import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_SOURCES = {"merged", "2016", "2020", "2024", "repeated", "errata"}
EXECUTION_FLAGS = {"raw_ingestion_enabled", "model_training_enabled", "paid_api_calls_enabled",
                   "later_wave_readout_enabled", "protected_existing_reserve_access_enabled"}
POSITIVE_METADATA_GATES = {
    "summary_construction_equivalent": "summary_equivalence",
    "repeated_variable_archive_verified": "repeated_variable_archive",
    "release_alignment_verified": "release_alignment",
    "merged_schema_verified": "merged_missingness",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def assess(metadata, design, *, archived_sources_verified, reference_retained):
    require(metadata.get("schema_version") == 1 and design.get("schema") == "panel-design-readiness-v1", "Unexpected metadata/design schema")
    require(design["endpoint"]["categories"] == 7 and design["design"]["development"] == [2016,2020]
            and design["design"]["later_evaluation"] == [2020,2024], "Unexpected panel endpoint or temporal boundary")
    require(isinstance(design.get("execution"),dict) and set(design["execution"]) == EXECUTION_FLAGS
            and all(value is False for value in design["execution"].values()), "Readiness assessment must not enable execution or omit required flags")
    unresolved = metadata.get("unresolved")
    require(isinstance(unresolved, list) and all(isinstance(item,dict) and type(item.get("blocking")) is bool
            and isinstance(item.get("id"),str) for item in unresolved), "Unresolved metadata must be explicit")
    blockers = [{"id":item["id"], "stage":"source_metadata"} for item in unresolved if item["blocking"]]
    def block(identifier):
        if identifier not in {item["id"] for item in blockers}:
            blockers.append(dict(id=identifier, stage="source_metadata"))
    if not archived_sources_verified:
        block("original_document_bytes")
    for flag, identifier in POSITIVE_METADATA_GATES.items():
        if metadata.get("verified",{}).get(flag) is not True:
            block(identifier)
    if design["endpoint"].get("crosswalk_status") != "verified_for_development_projection":
        block("summary_equivalence")
    crosswalk = metadata.get("verified",{}).get("endpoint_crosswalk",[])
    mapping = {row.get("year"):row for row in crosswalk if isinstance(row,dict)}
    expected = {2016:"V161158x",2020:"V201231x",2024:"V241227x"}
    if len(crosswalk) != 3 or set(mapping) != set(expected) or any(
        mapping[year].get("variable") != variable or mapping[year].get("phase") != "pre"
        or mapping[year].get("valid_codes") != list(range(1,8)) for year,variable in expected.items()):
        block("endpoint_crosswalk")
    if not reference_retained:
        blockers.append(dict(id="statistical_reference_integrity",stage="reference"))
    source_count = sum(item["stage"] == "source_metadata" for item in blockers)
    return dict(schema="panel-readiness-v1", status="blocked_on_source_metadata" if blockers else "source_metadata_ready_projection_pending",
        reference_retained=bool(reference_retained), development_export_tool_ready=True,
        source_blocker_count=source_count, blockers=blockers,
        source_metadata_ready=not bool(blockers), ready_for_development_ingestion=False,
        development_projection_frozen=False,
        real_panel_records_audited=0, raw_panel_downloaded=False,
        model_training_enabled=False, later_wave_readout_enabled=False,
        evaluation_contract_complete=False,
        unresolved_evaluation_decisions=[name for name,value in design["unresolved_evaluation_decisions"].items() if value is None],
        scope="Preparation assessment only; no new respondent data, candidate fit or evaluation",
        next_action="Resolve source metadata and freeze the development-only projection before ingestion" if blockers else "Freeze and verify the raw-to-development projection before ingestion",
        primary_scope=design["design"]["primary_scope"])


def source_archives_verified(root, metadata):
    sources = metadata.get("sources", [])
    require(isinstance(sources,list), "Sources must be listed")
    mapping = {s.get("source_id"):s for s in sources if isinstance(s,dict)}
    if not REQUIRED_SOURCES <= set(mapping):
        return False
    for source_id in REQUIRED_SOURCES:
        source = mapping[source_id]
        if source.get("original_bytes_archived") is not True or not source.get("original_sha256") or not source.get("local_path"):
            return False
        path = (root / source["local_path"]).resolve()
        archive_root = (root / "reports/anes-panel-readiness-20261023/documentation").resolve()
        if archive_root not in path.parents or not path.is_file() or sha(path) != source["original_sha256"]:
            return False
    return True


def build(root):
    root = Path(root).resolve()
    metadata_path = root / "reports/anes-panel-readiness-20261023/metadata.json"
    design_path = root / "config/anes-panel-design-v1.json"
    reference_path = root / "reports/statistical-reference-20261023/manifest.json"
    metadata, design, reference = read(metadata_path), read(design_path), read(reference_path)
    baseline = reference["baseline"]
    baseline_path = Path(baseline["path"])
    quality_path = Path(reference["data_quality"]["path"])
    require(reference["status"] == "frozen_statistical_reference_development_only", "Reference status changed")
    require(baseline["categories"] == 6 and sha(baseline_path) == baseline["sha256"], "Existing baseline changed")
    require(sha(quality_path) == reference["data_quality"]["sha256"], "Reference audit changed")
    result = assess(metadata, design, archived_sources_verified=source_archives_verified(root,metadata), reference_retained=True)
    bindings = [metadata_path,design_path,reference_path,baseline_path,quality_path,
                root/"src/psbx/experiments/panel_development.py",Path(__file__).resolve(),
                root/"docs/ANES_PANEL_METADATA_READINESS.md",root/"docs/PANEL_EXPERIMENT_DESIGN_REVIEW.md"]
    result["bindings"] = {str(p):sha(p) for p in bindings}
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=build(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write("\n")
    args.output.chmod(0o444)
    print(json.dumps({key:result[key] for key in ("status","reference_retained","source_blocker_count","ready_for_development_ingestion")}))
