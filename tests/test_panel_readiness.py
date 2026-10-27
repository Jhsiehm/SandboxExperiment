import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("panel_readiness", ROOT/"scripts/assess_panel_readiness.py")
readiness=importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


def fixture():
    design=json.loads((ROOT/"config/anes-panel-design-v1.json").read_text())
    metadata=dict(schema_version=1,unresolved=[],verified=dict(endpoint_crosswalk=[dict(year=y,variable=v,phase="pre",valid_codes=list(range(1,8)))
        for y,v in [(2016,"V161158x"),(2020,"V201231x"),(2024,"V241227x")]]))
    metadata["verified"].update({key:True for key in readiness.POSITIVE_METADATA_GATES})
    design["endpoint"]["crosswalk_status"]="verified_for_development_projection"
    return metadata,design


def test_common_labels_do_not_clear_unresolved_construction():
    metadata,design=fixture()
    metadata["unresolved"]=[dict(id="summary_equivalence",blocking=True)]
    report=readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)
    assert not report["ready_for_development_ingestion"]
    assert report["source_blocker_count"]==1 and not report["model_training_enabled"]


def test_no_source_hashes_means_no_ingestion_and_resolved_metadata_does_not_enable_evaluation():
    metadata,design=fixture()
    report=readiness.assess(metadata,design,archived_sources_verified=False,reference_retained=True)
    assert report["status"]=="blocked_on_source_metadata"
    report=readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)
    assert report["source_metadata_ready"] and not report["ready_for_development_ingestion"]
    assert not report["development_projection_frozen"]
    assert not report["evaluation_contract_complete"] and not report["later_wave_readout_enabled"]
    assert "practical_improvement_margin" in report["unresolved_evaluation_decisions"]


def test_crosswalk_wrong_scale_or_future_execution_are_rejected():
    metadata,design=fixture()
    metadata["verified"]["endpoint_crosswalk"][0]["valid_codes"]=[1,2,3,4,5,6]
    assert not readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)["ready_for_development_ingestion"]
    design["execution"]["model_training_enabled"]=True
    with pytest.raises(ValueError,match="enable execution"):
        readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)


def test_archived_flag_alone_is_not_byte_verification(tmp_path):
    sources=[dict(source_id=s,original_bytes_archived=True,original_sha256="a"*64,local_path="made-up.pdf") for s in readiness.REQUIRED_SOURCES]
    assert not readiness.source_archives_verified(tmp_path,dict(sources=sources))
    folder=tmp_path/"reports/anes-panel-readiness-20261023/documentation"
    folder.mkdir(parents=True)
    for source in sources:
        path=folder/(source["source_id"]+".txt")
        path.write_text("synthetic documentation bytes")
        source.update(local_path=str(path.relative_to(tmp_path)),original_sha256=readiness.sha(path))
    assert readiness.source_archives_verified(tmp_path,dict(sources=sources))
    path.write_text("changed")
    assert not readiness.source_archives_verified(tmp_path,dict(sources=sources))


@pytest.mark.parametrize("flags", [{}, {"model_training_enabled":False}, {key:0 for key in readiness.EXECUTION_FLAGS}])
def test_missing_flags_or_numeric_false_never_enable_execution(flags):
    metadata,design=fixture()
    design["execution"]=flags
    with pytest.raises(ValueError,match="omit required flags"):
        readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)


def test_deleting_blocker_list_does_not_supply_positive_evidence():
    metadata,design=fixture()
    metadata["verified"].pop("summary_construction_equivalent")
    result=readiness.assess(metadata,design,archived_sources_verified=True,reference_retained=True)
    assert not result["source_metadata_ready"]
    assert {b["id"] for b in result["blockers"]}=={"summary_equivalence"}
