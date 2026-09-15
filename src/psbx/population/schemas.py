"""Canonical Track B population records.

These models are intentionally separate from forecast/prediction schemas. They describe
synthetic-population construction and validation, not actual residents.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PopulationUniverse = Literal[
    "all_residents",
    "households",
    "adults_18_plus",
    "voting_age",
    "citizen_voting_age",
    "registered_voters",
    "likely_voters",
]
ExperimentMode = Literal["sealed_forecast", "retrospective_reconstruction"]
SourceRole = Literal[
    "population_constraint",
    "donor_microdata",
    "geography",
    "behavior_prior",
    "evaluation_target",
]
DataZone = Literal[
    "population_build",
    "behavior_training",
    "runtime_profile",
    "evaluation",
]
ConstraintRole = Literal["raking", "validation"]


class PopulationSource(BaseModel):
    id: str
    provider: str
    title: str
    role: SourceRole
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    release_date: date | None = None
    release_verified: bool = False
    geography_vintage: str = ""
    access: str = "public"
    url: str = ""
    allowed_zones: list[DataZone] = Field(default_factory=list)
    requires_artifact_release_verification: bool = True
    notes: str = ""

    @model_validator(mode="after")
    def dates_are_ordered(self) -> PopulationSource:
        if (
            self.reference_period_start is not None
            and self.reference_period_end is not None
            and self.reference_period_end < self.reference_period_start
        ):
            raise ValueError("reference_period_end must be on or after reference_period_start")
        return self


class ArtifactRecord(BaseModel):
    source_id: str
    artifact_id: str
    local_path: str
    reference_period_start: date | None = None
    reference_period_end: date | None = None
    release_date: date
    release_verified: bool = True
    downloaded_at: datetime | None = None
    sha256: str
    geography_vintage: str = ""
    zone: DataZone = "population_build"
    access_note: str = ""
    transformation_note: str = ""

    @field_validator("sha256")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        lowered = value.lower().strip()
        if len(lowered) != 64 or any(ch not in "0123456789abcdef" for ch in lowered):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return lowered


class ArtifactManifest(BaseModel):
    id: str
    artifacts: list[ArtifactRecord]
    notes: str = ""


class GeographySpec(BaseModel):
    id: str
    label: str
    geography_type: Literal[
        "state",
        "county",
        "county_subdivision",
        "place",
        "municipality",
        "congressional_district",
        "state_legislative_upper",
        "state_legislative_lower",
        "tract",
        "block_group",
        "voting_district",
        "custom",
    ]
    state_fips: str
    county_fips: str | None = None
    county_subdivision: str | None = None
    place: str | None = None
    municipality: str | None = None
    congressional_district: str | None = None
    state_legislative_district: str | None = None
    tract: str | None = None
    block_group: str | None = None
    voting_district: str | None = None
    vintage: str = ""

    @field_validator("state_fips")
    @classmethod
    def state_fips_two_characters(cls, value: str) -> str:
        value = str(value).zfill(2)
        if len(value) != 2 or not value.isdigit():
            raise ValueError("state_fips must contain exactly two digits")
        return value

    @model_validator(mode="after")
    def required_geography_key(self) -> GeographySpec:
        requirements = {
            "county": self.county_fips,
            "county_subdivision": self.county_subdivision,
            "place": self.place,
            "municipality": self.municipality,
            "congressional_district": self.congressional_district,
            "state_legislative_upper": self.state_legislative_district,
            "state_legislative_lower": self.state_legislative_district,
            "tract": self.tract,
            "block_group": self.block_group,
            "voting_district": self.voting_district,
        }
        required = requirements.get(self.geography_type)
        if self.geography_type in requirements and not str(required or "").strip():
            raise ValueError(
                f"geography_type={self.geography_type} requires its explicit geography key"
            )
        return self


class PopulationConstraint(BaseModel):
    dimension: str
    category: str
    target_count: float
    source_id: str
    universe: PopulationUniverse = "all_residents"
    role: ConstraintRole = "raking"
    moe90: float | None = None
    notes: str = ""

    @field_validator("target_count")
    @classmethod
    def nonnegative_target(cls, value: float) -> float:
        if value < 0:
            raise ValueError("target_count must be nonnegative")
        return float(value)

    @field_validator("moe90")
    @classmethod
    def nonnegative_moe(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("moe90 must be nonnegative")
        return value


class PopulationSpec(BaseModel):
    id: str
    epoch_id: str
    cutoff_date: date
    experiment_mode: ExperimentMode = "sealed_forecast"
    geography: GeographySpec
    universe: PopulationUniverse = "all_residents"
    target_population: int
    source_registry: str = "config/population_sources.yaml"
    source_ids: list[str]
    artifact_manifest_path: str | None = None
    required_artifact_ids: list[str] = Field(default_factory=list)
    constraints_path: str
    donors_path: str
    output_root: str = "data/population"
    seed: int = 0
    max_iterations: int = 500
    tolerance: float = 1e-5
    validation_tvd_tolerance: float = 0.02
    validation_moe_ratio_tolerance: float | None = None
    sample_moe_realization: bool = False
    donor_weight_column: str = "donor_weight"
    profile_fields: list[str] = Field(default_factory=list)
    representative_cell_fields: list[str] = Field(default_factory=list)
    reasoning_call_budget: int = 0
    controlled_integerization_max_donors: int = 5000
    notes: str = ""

    @field_validator("id", "epoch_id")
    @classmethod
    def filesystem_safe_identifiers(cls, value: str) -> str:
        from psbx.paths import validate_run_id

        return validate_run_id(value)

    @field_validator("target_population")
    @classmethod
    def positive_population(cls, value: int) -> int:
        if value < 1:
            raise ValueError("target_population must be at least 1")
        return value

    @field_validator("max_iterations")
    @classmethod
    def positive_iterations(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_iterations must be at least 1")
        return value

    @field_validator("tolerance", "validation_tvd_tolerance")
    @classmethod
    def valid_tolerance(cls, value: float) -> float:
        if not 0 <= value < 1:
            raise ValueError("tolerances must be in [0, 1)")
        return float(value)

    @field_validator("validation_moe_ratio_tolerance")
    @classmethod
    def valid_moe_ratio_tolerance(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("validation_moe_ratio_tolerance must be nonnegative")
        return value

    @field_validator("reasoning_call_budget", "controlled_integerization_max_donors")
    @classmethod
    def nonnegative_budget(cls, value: int) -> int:
        if value < 0:
            raise ValueError("reasoning_call_budget must be nonnegative")
        return value


class SourceDecision(BaseModel):
    source_id: str
    eligible: bool
    zone: DataZone
    decision: str
    release_date: date | None = None


class RakingIteration(BaseModel):
    iteration: int
    max_relative_error: float
    total_weight: float


class MarginalError(BaseModel):
    role: ConstraintRole = "raking"
    dimension: str
    category: str
    target_count: float
    actual_count: float
    absolute_error: float
    relative_error: float | None = None
    moe90: float | None = None
    error_over_moe90: float | None = None


class PopulationValidationReport(BaseModel):
    population_id: str
    epoch_id: str
    geography_id: str
    universe: PopulationUniverse
    target_population: int
    actual_population: int
    passed: bool
    max_absolute_error: float
    max_relative_error: float
    max_error_over_moe90: float | None = None
    acceptance_rule: str = "total variation distance"
    total_variation_by_dimension: dict[str, float]
    marginal_errors: list[MarginalError]
    unsupported_categories: list[str] = Field(default_factory=list)
    household_integrity: Literal["not_guaranteed", "separate_household_model", "preserved"] = (
        "not_guaranteed"
    )
    notes: list[str] = Field(default_factory=list)


class RepresentativeCell(BaseModel):
    cell_id: str
    attributes: dict[str, Any]
    population_weight: int
    population_share: float
    reasoning_calls: int = 0


class PopulationBuildManifest(BaseModel):
    population_id: str
    epoch_id: str
    cutoff_date: date
    experiment_mode: ExperimentMode
    geography: GeographySpec
    universe: PopulationUniverse
    target_population: int
    synthetic_records: int
    representative_cells: int
    reasoning_calls: int
    seed: int
    source_ids: list[str]
    input_sha256: dict[str, str]
    output_sha256: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    algorithm: str = "person-level iterative proportional fitting plus exact integerization"
    representation_mode: Literal["expanded_records", "weighted_cells"] = "expanded_records"
    represented_population: int | None = None
    parent_population_ids: list[str] = Field(default_factory=list)
    claims: list[str] = Field(
        default_factory=lambda: [
            "synthetic records are not actual residents",
            "donor records are anonymized source rows, not local identities",
            "exact household membership is not guaranteed in the person-level MVP",
        ]
    )

    @model_validator(mode="after")
    def represented_total_defaults_to_target(self) -> PopulationBuildManifest:
        if self.represented_population is None:
            self.represented_population = self.target_population
        if self.represented_population != self.target_population:
            raise ValueError("represented_population must equal target_population")
        return self


class SurveyTarget(BaseModel):
    target_id: str
    task_id: str
    group_field: str = "__all__"
    group_value: str = "__all__"
    observed_probability: float
    sample_size: int | None = None
    population_universe: str = "unspecified"
    published_moe95: float | None = None
    observed_ci95_lower: float | None = None
    observed_ci95_upper: float | None = None
    uncertainty_method: str = ""
    source_id: str = ""
    notes: str = ""

    @field_validator("observed_probability")
    @classmethod
    def target_probability(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("observed_probability must be in [0, 1]")
        return value

    @field_validator("published_moe95")
    @classmethod
    def valid_moe(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("published_moe95 must be in [0, 1]")
        return value

    @model_validator(mode="after")
    def valid_confidence_interval(self) -> SurveyTarget:
        values = (self.observed_ci95_lower, self.observed_ci95_upper)
        if (values[0] is None) != (values[1] is None):
            raise ValueError("both observed CI bounds must be supplied together")
        if values[0] is not None and not (0 <= values[0] <= values[1] <= 1):
            raise ValueError("observed CI bounds must be ordered within [0, 1]")
        return self


class BehaviorTargetResult(BaseModel):
    target_id: str
    task_id: str
    group_field: str
    group_value: str
    observed_probability: float
    predicted_probability: float
    absolute_error: float
    squared_error: float
    represented_weight: float
    n_simulated_records: int
    sample_size: int | None = None
    observed_ci95_lower: float | None = None
    observed_ci95_upper: float | None = None
    predicted_within_observed_ci95: bool | None = None
    support_status: Literal["reported", "weak", "unknown"] = "unknown"
    population_universe: str = "unspecified"
    uncertainty_method: str = "none"
    uncertainty_is_approximate: bool = False
    synthetic_population_weight: float = 0.0
    synthetic_coverage: float = 0.0
    synthetic_effective_sample_size: float = 0.0
    synthetic_support_status: Literal["complete", "partial", "none"] = "none"


class TrackBBehaviorValidationReport(BaseModel):
    run_id: str
    n_targets: int
    mean_absolute_error: float
    root_mean_squared_error: float
    sample_size_weighted_mae: float | None = None
    mean_signed_error: float = 0.0
    max_absolute_error: float = 0.0
    targets_within_observed_ci95: int | None = None
    weak_support_targets: int = 0
    weak_survey_support_targets: int = 0
    weak_synthetic_support_targets: int = 0
    metrics_frozen: bool = False
    targets: list[BehaviorTargetResult]
    notes: list[str] = Field(default_factory=list)
