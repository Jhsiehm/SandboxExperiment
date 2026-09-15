"""Donor microdata loading and declared-universe filtering."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schemas import PopulationConstraint, PopulationUniverse
from .variables import canonicalize_donors


def load_donors(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    donors = canonicalize_donors(frame)
    donors = donors.loc[donors["donor_weight"] > 0].reset_index(drop=True)
    if donors.empty:
        raise ValueError("donor file has no positive-weight records")
    return donors


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"1", "true", "yes", "registered", "likely"})


def filter_to_universe(donors: pd.DataFrame, universe: PopulationUniverse) -> pd.DataFrame:
    frame = donors.copy()
    if universe == "all_residents":
        mask = pd.Series(True, index=frame.index)
    elif universe == "households":
        mask = pd.Series(True, index=frame.index)
    elif universe in {"adults_18_plus", "voting_age"}:
        mask = pd.to_numeric(frame["age"], errors="coerce") >= 18
    elif universe == "citizen_voting_age":
        mask = (pd.to_numeric(frame["age"], errors="coerce") >= 18) & (
            frame["citizenship"] == "citizen"
        )
    elif universe == "registered_voters":
        if "registered_voter" not in frame:
            raise ValueError(
                "registered_voters requires an explicit registered_voter field from an "
                "election-administration or survey behavior source"
            )
        mask = _truthy(frame["registered_voter"])
    elif universe == "likely_voters":
        if "likely_voter" not in frame:
            raise ValueError(
                "likely_voters requires an explicit likely_voter field from a documented "
                "behavior model"
            )
        mask = _truthy(frame["likely_voter"])
    else:
        raise ValueError(f"unsupported universe: {universe}")
    selected = frame.loc[mask].reset_index(drop=True)
    if selected.empty:
        raise ValueError(f"no donor records remain for universe={universe}")
    return selected


def validate_donor_support(
    donors: pd.DataFrame,
    constraints: list[PopulationConstraint],
) -> None:
    raking = [row for row in constraints if row.role == "raking"]
    missing_dimensions = {row.dimension for row in raking} - set(donors.columns)
    if missing_dimensions:
        raise ValueError(
            "donor data missing raking dimensions: " + ", ".join(sorted(missing_dimensions))
        )
    unsupported: list[str] = []
    for row in raking:
        if row.target_count <= 0:
            continue
        support = set(donors[row.dimension].astype(str))
        if row.category not in support:
            unsupported.append(f"{row.dimension}={row.category}")
    if unsupported:
        raise ValueError("positive target categories lack donor support: " + ", ".join(unsupported))
