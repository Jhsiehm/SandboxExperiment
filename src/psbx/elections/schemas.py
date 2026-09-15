"""Canonical records for election results and their source registry.

Election returns are aggregate public records.  They are deliberately kept separate from
synthetic population records and may enter evaluation only after their release date.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ElectionGeography = Literal[
    "nation",
    "state",
    "congressional_district",
    "state_legislative_upper",
    "state_legislative_lower",
    "county",
    "municipality",
    "precinct",
]
OfficeLevel = Literal[
    "president",
    "us_senate",
    "us_house",
    "statewide",
    "state_senate",
    "state_house",
    "county",
    "municipal",
]
ElectionStage = Literal["primary", "runoff", "general", "special", "other"]
VoteStatus = Literal["reported", "unopposed_no_vote_total"]
SourceScope = Literal["federal", "state", "local", "demographic"]
SourceStatus = Literal[
    "ready",
    "partial",
    "adapter_required",
    "future_pending",
]

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")


class ElectionSource(BaseModel):
    id: str
    provider: str
    title: str
    scope: SourceScope
    official: bool = True
    status: SourceStatus
    year_start: int | None = None
    year_end: int | None = None
    election_geographies: list[ElectionGeography] = Field(default_factory=list)
    office_levels: list[OfficeLevel] = Field(default_factory=list)
    access: str = "public"
    url: str
    release_date: date | None = None
    release_verified: bool = False
    normalized: bool = False
    notes: str = ""

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        value = str(value).strip()
        if not _ID.fullmatch(value):
            raise ValueError("source id contains unsafe characters")
        return value

    @field_validator("year_start", "year_end")
    @classmethod
    def plausible_year(cls, value: int | None) -> int | None:
        if value is not None and not 1788 <= value <= 2200:
            raise ValueError("source years must be between 1788 and 2200")
        return value

    @model_validator(mode="after")
    def years_are_ordered(self) -> ElectionSource:
        if (
            self.year_start is not None
            and self.year_end is not None
            and self.year_end < self.year_start
        ):
            raise ValueError("year_end must be on or after year_start")
        if self.release_verified and self.release_date is None:
            raise ValueError("release_verified requires release_date")
        return self


class ElectionResultRow(BaseModel):
    """One candidate/result-option row in one contest and reporting geography."""

    source_id: str
    source_record_id: str | None = None
    election_date: date
    election_year: int
    stage: ElectionStage
    office_level: OfficeLevel
    office_name: str
    contest_id: str
    geography_level: ElectionGeography
    geography_id: str
    geography_name: str
    geography_vintage: str
    state_fips: str | None = None
    state_postal: str | None = None
    district: str | None = None
    county_fips: str | None = None
    county_name: str | None = None
    municipality_name: str | None = None
    precinct: str | None = None
    candidate_id: str | None = None
    candidate_name: str
    party: str | None = None
    votes: int
    vote_status: VoteStatus = "reported"
    total_votes_reported: int | None = None
    winner: bool | None = None
    certified: bool
    source_url: str
    source_release_date: date

    @field_validator("source_id", "contest_id", "geography_id")
    @classmethod
    def safe_identifier(cls, value: str) -> str:
        value = str(value).strip()
        if not _ID.fullmatch(value):
            raise ValueError("identifier contains unsafe characters")
        return value

    @field_validator("state_fips")
    @classmethod
    def normalize_state_fips(cls, value: str | None) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        normalized = str(value).strip().zfill(2)
        if len(normalized) != 2 or not normalized.isdigit():
            raise ValueError("state_fips must be two digits")
        return normalized

    @field_validator("state_postal")
    @classmethod
    def normalize_state_postal(cls, value: str | None) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        normalized = str(value).strip().upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("state_postal must be two letters")
        return normalized

    @field_validator("votes", "total_votes_reported")
    @classmethod
    def nonnegative_votes(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("vote counts must be nonnegative")
        return value

    @field_validator("geography_vintage", "source_url", "candidate_name", "office_name")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @model_validator(mode="after")
    def internal_consistency(self) -> ElectionResultRow:
        if self.election_year != self.election_date.year:
            raise ValueError("election_year must match election_date")
        if self.source_release_date < self.election_date:
            raise ValueError("source_release_date cannot precede election_date")
        if self.total_votes_reported is not None and self.votes > self.total_votes_reported:
            raise ValueError("candidate votes exceed total_votes_reported")
        if self.vote_status == "unopposed_no_vote_total" and (
            self.votes != 0 or self.winner is not True
        ):
            raise ValueError(
                "unopposed_no_vote_total requires zero votes and an explicit winner"
            )
        if self.geography_level != "nation" and not self.state_fips:
            raise ValueError("non-national results require state_fips")
        if self.geography_level in {
            "congressional_district",
            "state_legislative_upper",
            "state_legislative_lower",
        } and not self.district:
            raise ValueError("district geography requires district")
        if self.geography_level in {"county", "precinct"} and not self.county_name:
            raise ValueError("county/precinct geography requires county_name")
        if self.geography_level == "municipality" and not self.municipality_name:
            raise ValueError("municipality geography requires municipality_name")
        return self


class ElectionImportManifest(BaseModel):
    schema_version: int = 1
    dataset_id: str
    label: str
    created_at: datetime
    cutoff_date: date
    input_sha256: str
    output_sha256: str
    rows: int
    contests: int
    certified_rows: int
    source_ids: list[str]
    years: list[int]
    stages: list[ElectionStage]
    office_levels: list[OfficeLevel]
    geography_levels: list[ElectionGeography]
    states: list[str]
    coverage_by_state: dict[str, dict]
    normalized_output: str
    warnings: list[str] = Field(default_factory=list)
