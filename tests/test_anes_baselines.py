import json

import pandas as pd

from psbx.experiments.anes_baselines import evaluate_anes_statistical_baselines
from psbx.experiments.anes_society import (
    PAPER_STUDY_2_PROFILE_FIELDS,
    STRICT_PRE_ELECTION_PROFILE_FIELDS,
)


def _write_profiles(path, fields, policy, n=20):
    path.parent.mkdir(parents=True)
    rows = []
    for index in range(n):
        republican = index % 2 == 1
        values = {
            "dem_raceeth_x": 1,
            "gender_respondent_x": 1 + (index % 2),
            "dem_age_r_x": 30 + index,
            "libcpre_self": 6 if republican else 2,
            "pid_x": 6 if republican else 2,
            "paprofile_interestpolit": 1 + (index % 4),
            "relig_church": 1 + (index % 2),
            "discuss_disc": 1 + (index % 2),
            "patriot_flag": 1 + (index % 5),
            "sample_stfips": 6,
        }
        rows.append(
            {
                "synthetic_person_id": f"person-{index}",
                "profile": {field: values[field] for field in fields},
            }
        )
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (path.parent / "manifest.json").write_text(
        json.dumps({"profile_timing_policy": policy}) + "\n",
        encoding="utf-8",
    )


def test_full_sample_baselines_are_cross_fitted_and_compare_profile_policies(tmp_path):
    strict_path = tmp_path / "strict" / "profiles.jsonl"
    paper_path = tmp_path / "paper" / "profiles.jsonl"
    _write_profiles(
        strict_path,
        STRICT_PRE_ELECTION_PROFILE_FIELDS,
        "strict_pre_election",
    )
    _write_profiles(paper_path, PAPER_STUDY_2_PROFILE_FIELDS, "paper_faithful")
    targets = tmp_path / "vault" / "targets.csv"
    targets.parent.mkdir()
    pd.DataFrame(
        {
            "synthetic_person_id": [f"person-{index}" for index in range(20)],
            "population_weight": [1.0] * 20,
            "presvote2012_x": [1 if index % 2 == 0 else 2 for index in range(20)],
        }
    ).to_csv(targets, index=False)

    report = evaluate_anes_statistical_baselines(
        strict_path,
        paper_path,
        targets,
        tmp_path / "baseline-report.json",
        folds=2,
        expected_n=20,
    )

    assert report["n_valid_two_party"] == 20
    assert report["target_access_required"] is True
    assert report["runtime_eligible"] is False
    assert len(report["results"]) == 6
    assert all(row["n"] == 20 for row in report["results"])
    predictions = (tmp_path / "statistical-baseline-predictions.jsonl").read_text().splitlines()
    assert len(predictions) == 120
    assert "observed_republican" not in json.loads(predictions[0])
