import copy
import json
import sys

import pytest

from psbx.experiments.panel_development import audit, fit_transition, load_export, paired_values, person_fold, scores, validate_rows
from psbx.experiments.panel_development import main


def row(person, wave, value, reason=None):
    return dict(person_id=person, wave=wave, party_id=value, missing_reason=reason, mode="web",
                phase="pre", role="development", value_origin="observed", source_field="documented_field",
                source_sha256="a"*64)


def test_retains_missingness_and_distinguishes_absent_followup():
    rows=[row("a",2016,1), row("a",2020,2), row("b",2016,4), row("b",2020,None,"refused"),
          row("c",2016,7), row("d",2020,4), row("e",2016,None,"not_asked"), row("e",2020,3)]
    report=audit(rows)
    assert paired_values(rows)==[("a",1,2)]
    assert report["eligible_pairs"]==1 and report["no_later_row"]==1
    assert report["later_item_missing"]==1 and report["later_only_people"]==1
    assert report["changed_pairs"]==1 and report["missing_reasons"]["2020"]=={"refused":1}
    assert report["retention_by_initial_category"][3]["later_unavailable"]==1
    assert not report["structural_fivefold_ready"] and report["precision_sufficient"] is None
    assert "person_id" not in str(report)


@pytest.mark.parametrize("change", [dict(wave=2024), dict(role="confirmation"), dict(phase="post"),
    dict(value_origin="simulated"), dict(party_id=True), dict(party_id=4.0), dict(party_id=-8),
    dict(party_id=None), dict(party_id=4,missing_reason="refused"), dict(final_2024=3)])
def test_rejects_future_targets_wrong_scales_and_silent_missing_codes(change):
    example=row("p",2016,3)
    example.update(change)
    with pytest.raises(ValueError):
        validate_rows([example])


def test_duplicate_person_wave_fails_and_fold_does_not_use_answers():
    with pytest.raises(ValueError,match="Duplicate"):
        validate_rows([row("p",2016,1),row("p",2016,2)])
    rows=[row(f"p{i}",wave,value) for i in range(100) for wave,value in [(2016,1),(2020,7)]]
    altered=copy.deepcopy(rows)
    for record in altered:
        record["party_id"]=4
    assert audit(rows)["folds"] != audit(altered)["folds"]  # support changes, partitions do not
    assert [f["validation_people"] for f in audit(rows)["folds"]] == [f["validation_people"] for f in audit(altered)["folds"]]
    assert sum(f["validation_people"] for f in audit(rows)["folds"])==100
    assert all(0<=person_fold(f"p{i}")<5 for i in range(100))


def test_laplace_reference_and_scores_have_expected_extremes():
    table=fit_transition([("a",1,1),("b",1,7)])
    assert table[0]==[2/9,1/9,1/9,1/9,1/9,1/9,2/9]
    assert table[3]==[1/7]*7
    assert scores([1,0,0,0,0,0,0],1,1)==dict(rps=0,change_brier=0)
    assert scores([1,0,0,0,0,0,0],1,7)["rps"]==pytest.approx(1)
    assert scores([1,0,0,0,0,0,0],1,7)["change_brier"]==1
    assert scores([1,0,0,0,0,0,0],1,2)["rps"]==pytest.approx(1/6)
    with pytest.raises(ValueError,match="Repeated"):
        fit_transition([("a",1,1),("a",1,2)])


def test_zero_change_is_counted_and_unknown_mode_is_not_imputed():
    rows=[row("p",2016,4),row("p",2020,4)]
    rows[1]["mode"]=None
    report=audit(rows)
    assert report["changed_pairs"]==0 and report["mode_counts"]["2020"]=={"unknown":1}
    assert not report["source_crosswalk_verified"] and not report["model_training_enabled"]


def test_duplicate_json_keys_cannot_hide_future_wave_or_role():
    for ambiguous in ['{"wave":2024,"wave":2020}', '{"role":"confirmation","role":"development"}']:
        with pytest.raises(ValueError,match="Duplicate JSON key"):
            load_export('{"schema":"harmonized-panel-development-v1","rows":['+ambiguous+']}')


def test_no_interview_is_distinct_from_item_missing():
    rows=[row("p",2016,4),row("p",2020,None,"no_interview")]
    report=audit(rows)
    assert report["later_answer_missing"]==1 and report["later_item_missing"]==0
    assert report["later_documented_no_interview"]==1 and report["no_later_row"]==0


def test_cli_emits_aggregates_and_refuses_overwrite(monkeypatch,tmp_path):
    source,output=tmp_path/"synthetic.json",tmp_path/"audit.json"
    source.write_text(json.dumps(dict(schema="harmonized-panel-development-v1",rows=[row("person-secret",2016,1),row("person-secret",2020,2)])))
    monkeypatch.setattr(sys,"argv",["panel-development","--development-export",str(source),"--output",str(output)])
    main()
    result=json.loads(output.read_text())
    assert result["eligible_pairs"]==1 and len(result["export_sha256"])==64
    assert "person-secret" not in output.read_text()
    before=output.read_bytes()
    with pytest.raises(FileExistsError):
        main()
    assert output.read_bytes()==before


def test_cli_rejects_later_wave_without_writing_report(monkeypatch,tmp_path):
    source,output=tmp_path/"synthetic.json",tmp_path/"audit.json"
    source.write_text(json.dumps(dict(schema="harmonized-panel-development-v1",rows=[row("synthetic",2024,1)])))
    monkeypatch.setattr(sys,"argv",["panel-development","--development-export",str(source),"--output",str(output)])
    with pytest.raises(ValueError,match="development waves"):
        main()
    assert not output.exists()
