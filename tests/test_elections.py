from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pandas as pd
import pytest
from typer.testing import CliRunner

from leaderboard.jobs import InvalidSwarm, _normalize_dataset_selection
from psbx.cli import app
from psbx.elections.census import (
    census_election_plan,
    execute_census_plan,
    parse_levels,
    parse_states,
    summarize_census_plan,
)
from psbx.elections.fec_adapter import import_fec_workbook, normalize_fec_workbook
from psbx.elections.federal import _validate_artifact_file, discover_federal_artifacts
from psbx.elections.importer import (
    REQUIRED_COLUMNS,
    filter_election_results,
    import_election_results,
)
from psbx.elections.registry import federal_coverage_plan, load_election_sources
from psbx.population.schemas import GeographySpec


def result_row(**updates):
    row = {
        "source_id": "fixture_official",
        "source_record_id": "row-1",
        "election_date": "2020-11-03",
        "election_year": "2020",
        "stage": "general",
        "office_level": "us_house",
        "office_name": "U.S. House",
        "contest_id": "ca-12-us-house-2020",
        "geography_level": "congressional_district",
        "geography_id": "district:06:12",
        "geography_name": "California Congressional District 12",
        "geography_vintage": "116th Congress",
        "state_fips": "06",
        "state_postal": "CA",
        "district": "12",
        "county_fips": "",
        "county_name": "",
        "municipality_name": "",
        "precinct": "",
        "candidate_id": "candidate-1",
        "candidate_name": "Example Candidate",
        "party": "Example Party",
        "votes": "1000",
        "vote_status": "reported",
        "total_votes_reported": "1900",
        "winner": "true",
        "certified": "true",
        "source_url": "https://elections.example.gov/results",
        "source_release_date": "2020-12-01",
    }
    row.update(updates)
    return row


def write_results(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows, columns=REQUIRED_COLUMNS).to_csv(path, index=False)


def _xlsx_cell(reference: str, value: str | int) -> str:
    if isinstance(value, int):
        return f'<c r="{reference}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    )


def _xlsx_sheet(rows: list[list[str | int]]) -> str:
    rendered = []
    for row_number, values in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(f"{chr(65 + column)}{row_number}", value)
            for column, value in enumerate(values)
        )
        rendered.append(f'<row r="{row_number}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rendered)}</sheetData></worksheet>"
    )


def write_fec_workbook(path: Path) -> None:
    headers = [
        "STATE ABBREVIATION",
        "STATE",
        "D",
        "FEC ID#",
        "CANDIDATE NAME",
        "PARTY",
        "GENERAL VOTES ",
        "GE WINNER INDICATOR",
    ]
    house = [
        headers,
        ["CA", "California", "12", "H1", "Candidate A", "DEM", 100, "W"],
        ["CA", "California", "12", "H1", "Candidate A", "WF", 5, ""],
        ["CA", "California", "12", "H2", "Candidate B", "REP", 90, ""],
        ["FL", "Florida", "05", "H3", "Candidate E", "REP", "Unopposed", "W"],
        ["IN", "Indiana", "02-Full Term", "H4", "Candidate F", "REP", 80, "W"],
        [
            "IN",
            "Indiana",
            "02-Unexpired Term",
            "H4",
            "Candidate F",
            "REP",
            70,
            "W",
        ],
    ]
    senate = [
        headers,
        ["PA", "Pennsylvania", "", "S1", "Candidate C", "DEM", 110, "W"],
        ["PA", "Pennsylvania", "", "S2", "Candidate D", "REP", 105, ""],
    ]
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="US House Results by State" sheetId="1" r:id="rId1"/>'
        '<sheet name="US Senate Results by State" sheetId="2" r:id="rId2"/>'
        "</sheets></workbook>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet2.xml"/>'
        "</Relationships>"
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(house))
        archive.writestr("xl/worksheets/sheet2.xml", _xlsx_sheet(senate))


def test_registry_has_authoritative_federal_and_decentralized_local_sources():
    sources = load_election_sources("config/election_sources.yaml")
    assert sources["fec_federal_elections_1982_2022"].official
    assert sources["eac_state_and_local_office_directory"].status == "adapter_required"
    assert sources["census_acs5_electoral_geographies"].normalized


def test_federal_plan_keeps_2026_pending_before_general_election():
    plan = federal_coverage_plan(
        start_year=2024,
        through_year=2026,
        as_of=date(2026, 9, 14),
    )
    by_year = {row["year"]: row for row in plan["cycles"]}
    assert by_year[2024]["status"] == "official_documents_available"
    assert by_year[2025]["status"] == "not_scheduled_federal_cycle"
    assert by_year[2026]["status"] == "future_pending"
    assert by_year[2026]["election_day"] == "2026-11-03"


def test_federal_download_validation_rejects_extension_spoof(tmp_path: Path):
    valid = tmp_path / "valid.pdf"
    valid.write_bytes(b"%PDF-1.7\nfixture")
    _validate_artifact_file(valid, suffix=".pdf", max_bytes=1_000)

    spoofed = tmp_path / "spoofed.xlsx"
    spoofed.write_text("<html>not a workbook</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        _validate_artifact_file(spoofed, suffix=".xlsx", max_bytes=1_000)


def test_federal_discovery_filters_legacy_index_to_requested_cycle():
    class Client:
        def get(self, url):
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                text=(
                    '<a href="/documents/1547/federalelections82.pdf">1982</a>'
                    '<a href="/documents/1548/federalelections84.pdf">1984</a>'
                ),
            )

    artifacts = discover_federal_artifacts(Client(), 1982)
    assert [artifact["year"] for artifact in artifacts] == [1982]
    assert artifacts[0]["url"].endswith("federalelections82.pdf")


def test_census_plan_filters_states_and_electoral_geographies():
    plan = census_election_plan(
        year=2024,
        levels=parse_levels("congressional_district,state_legislative_upper"),
        states=parse_states("ca,48"),
    )
    summary = summarize_census_plan(plan)
    assert summary["request_count"] == 4
    assert summary["states"] == ["CA", "TX"]
    assert all(request.dataset == "2024/acs/acs5" for request in plan)
    assert all(request.in_clauses for request in plan)


def test_census_plan_rejects_unverified_future_release():
    with pytest.raises(ValueError, match="source-verified"):
        census_election_plan(year=2025)


def test_census_execute_requires_key_before_creating_output(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    plan = census_election_plan(
        year=2024,
        levels=("state",),
        states=parse_states("ca"),
    )
    output = tmp_path / "census"
    with pytest.raises(RuntimeError, match="CENSUS_API_KEY"):
        execute_census_plan(plan, output_root=output)
    assert not output.exists()


def test_import_results_validates_pins_and_catalogs_coverage(tmp_path: Path):
    source = tmp_path / "official.csv"
    write_results(
        source,
        [
            result_row(),
            result_row(
                source_record_id="row-2",
                candidate_id="candidate-2",
                candidate_name="Other Candidate",
                votes="900",
                winner="false",
            ),
        ],
    )
    manifest = import_election_results(
        source,
        dataset_id="federal-2020-fixture",
        label="Federal 2020 fixture",
        cutoff_date=date(2021, 1, 1),
        output_root=tmp_path / "normalized",
    )
    assert manifest.rows == 2
    assert manifest.contests == 1
    assert manifest.states == ["CA"]
    assert manifest.coverage_by_state["CA"]["geography_ids"] == {
        "congressional_district": ["district:06:12"]
    }
    output = tmp_path / "normalized/federal-2020-fixture/results.csv"
    assert output.is_file()
    assert len(manifest.output_sha256) == 64


def test_fec_workbook_adapter_normalizes_house_and_senate(tmp_path: Path):
    workbook = tmp_path / "fec.xlsx"
    write_fec_workbook(workbook)
    frame, warnings = normalize_fec_workbook(
        workbook,
        year=2022,
        source_release_date=date(2023, 1, 1),
    )
    assert len(frame) == 7
    assert set(frame["office_level"]) == {"us_house", "us_senate"}
    assert set(frame["geography_id"]) == {
        "district:06:12",
        "district:12:05",
        "district:18:02",
        "state:42",
    }
    assert set(frame["total_votes_reported"]) == {0, 70, 80, 195, 215}
    assert (
        frame.loc[frame["candidate_id"] == "H1", "votes"].astype(int).tolist() == [105]
    )
    unopposed = frame.loc[frame["vote_status"] == "unopposed_no_vote_total"].iloc[0]
    assert unopposed["votes"] == 0
    assert bool(unopposed["winner"])
    assert {
        "2022-in-us-house-02-full-term-general",
        "2022-in-us-house-02-unexpired-term-general",
    }.issubset(set(frame["contest_id"]))
    assert any("caller-supplied" in warning for warning in warnings)
    assert any("ballot-party" in warning for warning in warnings)

    manifest = import_fec_workbook(
        workbook,
        year=2022,
        source_release_date=date(2023, 1, 1),
        dataset_id="fec-2022-fixture",
        label="FEC 2022 fixture",
        cutoff_date=date(2023, 1, 2),
        output_root=tmp_path / "normalized",
    )
    assert manifest.rows == 7
    assert manifest.contests == 5
    assert manifest.states == ["CA", "FL", "IN", "PA"]


def test_import_results_fails_closed_on_future_or_uncertified_rows(tmp_path: Path):
    future = tmp_path / "future.csv"
    write_results(future, [result_row(source_release_date="2021-02-01")])
    with pytest.raises(ValueError, match="after cutoff"):
        import_election_results(
            future,
            dataset_id="future",
            label="Future",
            cutoff_date=date(2021, 1, 1),
            output_root=tmp_path / "normalized",
        )
    uncertified = tmp_path / "uncertified.csv"
    write_results(uncertified, [result_row(certified="false")])
    with pytest.raises(ValueError, match="uncertified"):
        import_election_results(
            uncertified,
            dataset_id="uncertified",
            label="Uncertified",
            cutoff_date=date(2021, 1, 1),
            output_root=tmp_path / "normalized",
        )


def test_result_filters_are_conjunctive():
    frame = pd.DataFrame(
        [
            result_row(),
            result_row(
                election_date="2022-11-08",
                election_year="2022",
                contest_id="tx-07-us-house-2022",
                geography_id="district:48:07",
                geography_name="Texas Congressional District 7",
                state_fips="48",
                state_postal="TX",
                district="07",
                source_release_date="2022-12-01",
            ),
        ]
    )
    selected = filter_election_results(
        frame,
        years={2022},
        states={"tx"},
        office_levels={"us_house"},
    )
    assert len(selected) == 1
    assert selected.iloc[0]["state_postal"] == "TX"


def test_district_population_geographies_are_explicit():
    geography = GeographySpec(
        id="district:06:12",
        label="California Congressional District 12",
        geography_type="congressional_district",
        state_fips="06",
        congressional_district="12",
        vintage="116th Congress",
    )
    assert geography.congressional_district == "12"
    with pytest.raises(ValueError, match="explicit geography key"):
        GeographySpec(
            id="district:06:12",
            label="Missing district",
            geography_type="congressional_district",
            state_fips="06",
        )


def test_election_commands_are_mounted_on_main_cli():
    result = CliRunner().invoke(
        app,
        [
            "elections",
            "plan",
            "--start-year",
            "2024",
            "--through-year",
            "2026",
            "--as-of",
            "2026-09-14",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"status": "future_pending"' in result.output


def test_run_dataset_selection_is_provenance_only():
    selected = _normalize_dataset_selection(
        {
            "kind": "election",
            "layer_id": "federal-2020",
            "year": "2020",
            "geography_level": "congressional_district",
            "source_ids": ["fec_federal_elections_1982_2022"],
        }
    )
    assert selected["runtime_access"] is False
    assert selected["use"] == "display_and_evaluation_comparison_only"
    with pytest.raises(InvalidSwarm, match="safe layer_id"):
        _normalize_dataset_selection(
            {"kind": "election", "layer_id": "../../outside"}
        )
