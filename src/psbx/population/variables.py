"""Canonicalize ACS PUMS-style donor columns.

The categories here are modeling bins. The original raw codes should remain in the controlled input
artifact and its provenance manifest.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

AGE_BANDS = [
    "under_18",
    "18_24",
    "25_34",
    "35_44",
    "45_54",
    "55_64",
    "65_plus",
]


def age_band(age: float | int | None) -> str:
    if age is None or pd.isna(age):
        return "unknown"
    value = int(age)
    if value < 18:
        return "under_18"
    if value <= 24:
        return "18_24"
    if value <= 34:
        return "25_34"
    if value <= 44:
        return "35_44"
    if value <= 54:
        return "45_54"
    if value <= 64:
        return "55_64"
    return "65_plus"


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _column(frame: pd.DataFrame, names: Iterable[str]) -> pd.Series | None:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return None


def _race_ethnicity(hispanic: pd.Series, race: pd.Series) -> pd.Series:
    hisp = _numeric(hispanic)
    rac = _numeric(race)
    result = pd.Series("unknown", index=hisp.index, dtype="object")
    result.loc[hisp > 1] = "hispanic_any_race"
    non_hispanic = hisp == 1
    mapping = {
        1: "white_non_hispanic",
        2: "black_non_hispanic",
        6: "asian_non_hispanic",
        7: "native_hawaiian_pacific_islander_non_hispanic",
        8: "other_non_hispanic",
        9: "two_or_more_non_hispanic",
    }
    for code, label in mapping.items():
        result.loc[non_hispanic & (rac == code)] = label
    result.loc[non_hispanic & rac.isin([3, 4, 5])] = (
        "american_indian_alaska_native_non_hispanic"
    )
    return result


def _education(age: pd.Series, school: pd.Series) -> pd.Series:
    """Recode the legacy 2006-2010 ACS PUMS SCHL values (01 through 16)."""
    ages = _numeric(age)
    codes = _numeric(school)
    result = pd.Series("unknown", index=ages.index, dtype="object")
    result.loc[ages < 18] = "under_18_or_not_applicable"
    adult = ages >= 18
    result.loc[adult & codes.between(1, 8)] = "less_than_high_school"
    result.loc[adult & (codes == 9)] = "high_school_or_equivalent"
    result.loc[adult & codes.isin([10, 11, 12])] = "some_college_or_associate"
    result.loc[adult & (codes == 13)] = "bachelors"
    result.loc[adult & codes.isin([14, 15, 16])] = "graduate_or_professional"
    return result


def _income_band(series: pd.Series) -> pd.Series:
    values = _numeric(series)
    result = pd.Series("unavailable", index=values.index, dtype="object")
    result.loc[values < 25_000] = "under_25k"
    result.loc[(values >= 25_000) & (values < 50_000)] = "25k_49k"
    result.loc[(values >= 50_000) & (values < 75_000)] = "50k_74k"
    result.loc[(values >= 75_000) & (values < 100_000)] = "75k_99k"
    result.loc[(values >= 100_000) & (values < 150_000)] = "100k_149k"
    result.loc[(values >= 150_000) & (values < 200_000)] = "150k_199k"
    result.loc[values >= 200_000] = "200k_plus"
    return result


def canonicalize_donors(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    if "age" not in out:
        raw_age = _column(out, ["AGEP", "age_years"])
        out["age"] = _numeric(raw_age) if raw_age is not None else np.nan
    else:
        out["age"] = _numeric(out["age"])
    if "age_band" not in out:
        out["age_band"] = out["age"].map(age_band)

    if "census_sex" not in out:
        raw_sex = _column(out, ["SEX", "sex"])
        if raw_sex is None:
            out["census_sex"] = "unknown"
        else:
            out["census_sex"] = _numeric(raw_sex).map({1: "male", 2: "female"}).fillna(
                "unknown"
            )

    if "race_ethnicity" not in out:
        raw_hisp = _column(out, ["HISP", "hispanic_code"])
        raw_race = _column(out, ["RAC1P", "race_code"])
        if raw_hisp is None or raw_race is None:
            out["race_ethnicity"] = "unknown"
        else:
            out["race_ethnicity"] = _race_ethnicity(raw_hisp, raw_race)

    if "citizenship" not in out:
        raw_cit = _column(out, ["CIT", "citizenship_code"])
        if raw_cit is None:
            out["citizenship"] = "unknown"
        else:
            cit = _numeric(raw_cit)
            out["citizenship"] = np.where(
                cit.isin([1, 2, 3, 4]), "citizen", np.where(cit == 5, "noncitizen", "unknown")
            )

    if "education" not in out:
        raw_school = _column(out, ["SCHL", "education_code"])
        if raw_school is None:
            out["education"] = "unknown"
        else:
            out["education"] = _education(out["age"], raw_school)

    if "household_income_band" not in out:
        raw_income = _column(out, ["HINCP", "household_income"])
        out["household_income_band"] = (
            _income_band(raw_income) if raw_income is not None else "unavailable"
        )

    if "employment" not in out:
        raw_esr = _column(out, ["ESR", "employment_code"])
        if raw_esr is None:
            out["employment"] = "unknown"
        else:
            esr = _numeric(raw_esr)
            out["employment"] = esr.map(
                {
                    1: "employed",
                    2: "employed_absent",
                    3: "unemployed",
                    4: "armed_forces",
                    5: "armed_forces_absent",
                    6: "not_in_labor_force",
                }
            ).fillna("not_applicable_or_unknown")

    if "tenure" not in out:
        raw_tenure = _column(out, ["TEN", "tenure_code"])
        if raw_tenure is None:
            out["tenure"] = "unknown"
        else:
            out["tenure"] = _numeric(raw_tenure).map(
                {
                    1: "owner_with_mortgage",
                    2: "owner_free_and_clear",
                    3: "renter",
                    4: "occupied_without_rent",
                }
            ).fillna("unknown")

    if "marital_status" not in out:
        raw_mar = _column(out, ["MAR", "marital_code"])
        if raw_mar is None:
            out["marital_status"] = "unknown"
        else:
            out["marital_status"] = _numeric(raw_mar).map(
                {
                    1: "married",
                    2: "widowed",
                    3: "divorced",
                    4: "separated",
                    5: "never_married",
                }
            ).fillna("unknown")

    if "household_size" not in out:
        raw_size = _column(out, ["NP", "household_persons"])
        out["household_size"] = _numeric(raw_size) if raw_size is not None else np.nan

    if "donor_weight" not in out:
        raw_weight = _column(out, ["PWGTP", "weight"])
        out["donor_weight"] = _numeric(raw_weight) if raw_weight is not None else 1.0
    out["donor_weight"] = _numeric(out["donor_weight"]).fillna(0.0)

    if "donor_id" not in out:
        serial = _column(out, ["SERIALNO", "serialno"])
        order = _column(out, ["SPORDER", "person_order"])
        if serial is not None and order is not None:
            out["donor_id"] = serial.astype(str) + ":" + order.astype(str)
        else:
            out["donor_id"] = [f"donor-{idx:08d}" for idx in range(len(out))]

    if "source_household_id" not in out:
        serial = _column(out, ["SERIALNO", "serialno", "household_id"])
        if serial is not None:
            out["source_household_id"] = serial.astype(str)

    string_fields = [
        "age_band",
        "census_sex",
        "race_ethnicity",
        "citizenship",
        "education",
        "household_income_band",
        "employment",
        "tenure",
        "marital_status",
        "donor_id",
    ]
    for field in string_fields:
        out[field] = out[field].fillna("unknown").astype(str)
    return out
