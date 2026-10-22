"""Reproduce full public-use administrative first stage; historical development only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from baseline import bucket, digest, fit_predict

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "oregon-data/source/OHIE_Public_Use_Files"
FEATURES = [
    "numhh_list",
    "draw_lottery",
    "have_phone_list",
    "english_list",
    "female_list",
    "first_day_list",
    "last_day_list",
    "pobox_list",
    "self_list",
    "week_list",
    "zip_msa_list",
]


def clustered_ols(x, y, group):
    n, k = x.shape
    assert np.linalg.matrix_rank(x) == k
    inverse = np.linalg.inv(x.T @ x)
    beta = inverse @ x.T @ y
    residual = y - x @ beta
    _, codes = np.unique(group, return_inverse=True)
    g = codes.max() + 1
    score = np.zeros((g, k))
    np.add.at(score, codes, x * residual[:, None])
    cov = inverse @ (score.T @ score) @ inverse * (g / (g - 1)) * ((n - 1) / (n - k))
    return beta, np.sqrt(np.diag(cov))


def main():
    targets = json.loads((HERE / "reference-targets.json").read_text())
    descriptive_path = SOURCE / "OHIE_Data/oregonhie_descriptive_vars.dta"
    programs_path = SOURCE / "OHIE_Data/oregonhie_stateprograms_vars.dta"
    expected_sources = {
        descriptive_path: "bc6167f6afbc26c80a70586d5793e37d0981780eb3e3e3c412f2f9bf305f08e8",
        programs_path: "cf0503b6a62358460d7bd3429de21ee7d1abc8b7bc5d659c38cb5cd4145465cf",
    }
    for path, expected in expected_sources.items():
        if digest(path) != expected:
            raise ValueError("Source changed; reviewed adapter no longer applies")
    outcomes = ["ohp_all_ever_matchn_30sep2009", "ohp_all_end_30sep2009"]
    d = pd.read_stata(
        descriptive_path,
        convert_categoricals=False,
        columns=["person_id", "household_id", "treatment", *FEATURES],
    )
    yframe = pd.read_stata(
        programs_path, convert_categoricals=False, columns=["person_id", *outcomes]
    )
    df = d.merge(yframe, on="person_id", validate="one_to_one")
    assert len(df) == 74922 and len(d) == len(yframe) == len(df)
    assert df[["person_id", "household_id", "treatment", *outcomes]].notna().all().all()
    assert df.groupby("household_id")["treatment"].nunique().max() == 1
    for field in outcomes + ["treatment"]:
        assert set(df[field].unique()) <= {0, 1}
    controls = pd.get_dummies(df[["numhh_list", "draw_lottery"]].astype(str), drop_first=True)
    x = np.column_stack([np.ones(len(df)), df.treatment.to_numpy(), controls.to_numpy(float)])
    reference = {}
    for outcome in outcomes:
        beta, se = clustered_ols(x, df[outcome].to_numpy(float), df.household_id.to_numpy())
        reference[outcome] = {
            "control_mean": float(df.loc[df.treatment == 0, outcome].mean()),
            "treatment_coefficient": float(beta[1]),
            "cluster_se": float(se[1]),
            "f_statistic": float((beta[1] / se[1]) ** 2),
        }
    checks = {}
    for outcome in outcomes:
        checks[outcome] = {}
        for metric, tolerance in targets["absolute_tolerance_from_published_rounding"].items():
            delta = abs(reference[outcome][metric] - targets[outcome][metric])
            checks[outcome][metric] = {
                "absolute_difference": delta,
                "tolerance": tolerance,
                "passed": bool(delta <= tolerance),
            }
    if not all(check["passed"] for row in checks.values() for check in row.values()):
        (HERE / "reference-failure.json").write_text(json.dumps(checks, indent=2) + "\n")
        raise ValueError("Published reference reproduction failed; see reference-failure.json")
    # All people have been used above: this is historical-development OOF, not pristine holdout.
    rows = []
    for r in df.to_dict("records"):
        features = {f: None if pd.isna(r[f]) else int(r[f]) for f in FEATURES}
        rows.append(
            {
                "household_id": str(int(r["household_id"])),
                "assignment": int(r["treatment"]),
                "outcome": int(r[outcomes[0]]),
                "weight": 1,
                "features": features,
            }
        )
    folds = np.array([bucket(r["household_id"], "oregon-historical-oof-20261022", 5) for r in rows])
    prediction = {
        "assignment_only": np.empty(len(rows)),
        "same_information_logistic": np.empty(len(rows)),
    }
    actual = df[outcomes[0]].to_numpy(float)
    assignment = df.treatment.to_numpy()
    for fold in range(5):
        train = [r for i, r in enumerate(rows) if folds[i] != fold]
        test = [r for i, r in enumerate(rows) if folds[i] == fold]
        for arm in (0, 1):
            prediction["assignment_only"][(folds == fold) & (assignment == arm)] = actual[
                (folds != fold) & (assignment == arm)
            ].mean()
        prediction["same_information_logistic"][folds == fold] = fit_predict(train, test, FEATURES)
    metrics = {}
    for name, p in prediction.items():
        metrics[name] = {
            "brier": float(np.mean((actual - p) ** 2)),
            "log_loss": float(
                np.mean(
                    -actual * np.log(np.clip(p, 1e-8, 1))
                    - (1 - actual) * np.log(np.clip(1 - p, 1e-8, 1))
                )
            ),
            "arm_shares": {
                str(arm): {
                    "actual": float(actual[assignment == arm].mean()),
                    "predicted": float(p[assignment == arm].mean()),
                }
                for arm in (0, 1)
            },
        }
    result = {
        "status": "historical_development_only",
        "n_people": len(df),
        "n_households": int(df.household_id.nunique()),
        "reference_specification": (
            "OLS treatment + lottery draw dummies + listed household size dummies; "
            "unit weights; Stata cluster finite-sample correction"
        ),
        "reference": reference,
        "source_code_sha256": {
            str(p.relative_to(SOURCE)): digest(p)
            for p in [
                SOURCE / "OHIE_QJE_Replication_Code/oregon_hie_qje_replication.do",
                SOURCE / "OHIE_QJE_Replication_Code/SubPrograms/prepare_data.do",
                SOURCE / "OHIE_QJE_Replication_Code/SubPrograms/tables_firststage.do",
            ]
        },
        "published_rounding_checks": checks,
        "reference_targets_sha256": digest(HERE / "reference-targets.json"),
        "prediction_target": outcomes[0],
        "prediction_features": FEATURES,
        "historical_oof_metrics": metrics,
        "fresh_holdout_claim": False,
        "causal_forecast_claim": False,
        "provider_calls": 0,
        "inputs_sha256": {
            str(p.relative_to(SOURCE)): digest(p) for p in [descriptive_path, programs_path]
        },
        "implementation_sha256": digest(__file__),
        "baseline_implementation_sha256": digest(HERE / "baseline.py"),
    }
    (HERE / "oregon-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
