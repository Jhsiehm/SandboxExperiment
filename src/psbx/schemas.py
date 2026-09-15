"""Canonical record types. Everything serializes as JSONL via model_dump(mode='json')."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["economic", "legislative", "geopolitical", "electoral", "corporate"]
PriorKind = Literal["market", "poll", "analyst_consensus", "base_rate"]
SourceType = Literal["news", "wire", "wiki", "gov", "trade", "survey", "ad", "academic"]
CitationSupport = Literal["yes", "no", "context"]
Provider = Literal["openai", "anthropic", "together", "local_vllm", "openrouter"]
SandboxMode = Literal["host", "container"]
Urbanicity = Literal["urban", "suburban", "rural", "unspecified"]
PartyId = Literal["democrat", "republican", "independent", "unspecified"]
ResponseKind = Literal["binary_outcome", "poll_share"]
StimulusKind = Literal["contemporaneous_media"]
EvidenceAuthenticity = Literal[
    "reconstructed_fixture",
    "unverified",
    "authenticated_capture",
    "authenticated_artifact",
]
EvidenceUse = Literal["practice", "research"]
TimestampBasis = Literal[
    "unknown",
    "fixture_as_of",
    "archive_capture",
    "publication_date",
]

AUTHENTICATED_EVIDENCE = frozenset({"authenticated_capture", "authenticated_artifact"})

# Conditioners for the demographic swarm (Track B). Headlines remain the stimulus (Track A).
CONDITIONER_SOURCE_TYPES = frozenset({"survey", "ad", "academic"})
MEDIA_STIMULUS_SOURCE_TYPES = frozenset({"news", "wire", "wiki", "gov", "trade"})


class Epoch(BaseModel):
    id: str
    cutoff_date: date
    resolution_window_end: date
    corpus_index_path: str

    @model_validator(mode="after")
    def window_after_cutoff(self) -> Epoch:
        if self.resolution_window_end <= self.cutoff_date:
            raise ValueError("resolution_window_end must be after cutoff_date")
        return self


class PriorSignal(BaseModel):
    """Contemporaneous uncertainty. Used for difficulty filtering and as a baseline."""

    kind: PriorKind
    probability: float
    source: str

    @field_validator("probability")
    @classmethod
    def unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        return v


class Question(BaseModel):
    id: str
    epoch_id: str
    category: Category
    text: str
    resolution_criteria: str
    cutoff_date: date
    resolution_date: date
    ground_truth: bool
    generator: str
    source_url: str | None = None
    prior_signal: PriorSignal | None = None

    @model_validator(mode="after")
    def phrasing_and_dates(self) -> Question:
        if self.resolution_date <= self.cutoff_date:
            raise ValueError("resolution_date must be after cutoff_date")
        lowered = self.text.strip().lower()
        if lowered.startswith("did ") or " did " in f" {lowered}":
            raise ValueError("hindsight phrasing leaks the answer; use will-by framing")
        if not lowered.startswith("will "):
            raise ValueError("question text must be present-tense will-by framing")
        return self


class Document(BaseModel):
    id: str
    url: str
    outlet: str
    published_at: datetime
    title: str
    text: str
    source_type: SourceType
    prominence: float = 0.0
    syndication_count: int = 1
    embedding: list[float] | None = None
    gdelt_mention_count: int = 0
    front_page_minutes: float = 0.0
    provenance: str | None = None
    authenticity: EvidenceAuthenticity = "unverified"
    timestamp_basis: TimestampBasis = "unknown"
    captured_at: datetime | None = None
    source_reference: str | None = None
    content_sha256: str | None = None
    capture_verified: bool = False
    publication_date_verified: bool = False
    release_verified: bool = False

    @field_validator("prominence")
    @classmethod
    def prominence_unit(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("prominence must be in [0, 1]")
        return v

    @model_validator(mode="after")
    def verify_evidence_provenance(self) -> Document:
        calculated = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.content_sha256 is not None and self.content_sha256.lower() != calculated:
            raise ValueError("content_sha256 does not match document text")
        self.content_sha256 = calculated
        if self.authenticity == "authenticated_capture":
            if not (
                self.capture_verified
                and self.captured_at is not None
                and self.source_reference
                and self.timestamp_basis == "archive_capture"
            ):
                raise ValueError(
                    "authenticated_capture requires a verified capture timestamp, "
                    "archive timestamp basis, and source reference"
                )
        if self.authenticity == "authenticated_artifact":
            if not (
                self.release_verified
                and self.publication_date_verified
                and self.source_reference
                and self.timestamp_basis == "publication_date"
            ):
                raise ValueError(
                    "authenticated_artifact requires verified release/publication metadata "
                    "and a source reference"
                )
        return self

    @property
    def research_eligible(self) -> bool:
        """Whether provenance is strong enough for a research evidence condition."""
        return self.authenticity in AUTHENTICATED_EVIDENCE


class Citation(BaseModel):
    document_id: str
    quoted_span: str
    supports: CitationSupport

    @field_validator("quoted_span")
    @classmethod
    def non_empty_span(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("quoted_span must be non-empty")
        return v


class Prediction(BaseModel):
    run_id: str
    question_id: str
    model_id: str
    probability: float
    reasoning: str
    citations: list[Citation]
    search_queries: list[str] = Field(default_factory=list)
    n_tool_calls: int = 0
    latency_s: float = 0.0
    raw_response: str = ""
    parse_attempts: int = 1
    flagged_for_contamination_review: bool = False
    flag_reasons: list[str] = Field(default_factory=list)
    citation_verification_failed: bool = False
    citation_verification_reasons: list[str] = Field(default_factory=list)

    @field_validator("probability")
    @classmethod
    def unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        return v

    @field_validator("citations")
    @classmethod
    def citations_required(cls, v: list[Citation]) -> list[Citation]:
        if not v:
            raise ValueError("citations must be non-empty")
        return v


class ModelConfig(BaseModel):
    id: str
    provider: Provider
    model_name: str
    declared_pretraining_cutoff: date
    is_instruction_tuned: bool
    max_tokens: int = Field(default=1024, ge=1, le=32_768)
    temperature: float = 0.2
    cost_per_1k_input: float = Field(default=0.0, ge=0)
    cost_per_1k_output: float = Field(default=0.0, ge=0)
    label: str = ""
    notes: str = ""
    needs_endpoint: bool = False
    openrouter_fallback: str | None = None


class SwarmVote(BaseModel):
    """One worker forecast. Written to swarm_votes.jsonl, not scored as its own series."""

    run_id: str
    question_id: str
    agent_index: int
    agent_id: str
    model_id: str
    model_slug: str
    temperature: float
    max_tokens: int
    probability: float
    rationale: str = ""
    raw_response: str = ""
    parse_attempts: int = 1
    system_prompt: str = ""
    search_queries: list[str] = Field(default_factory=list)
    perspective_id: str = ""
    perspective_label: str = ""

    @field_validator("probability")
    @classmethod
    def unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        return v


class SwarmSpecies(BaseModel):
    """One species in the default swarm. count expands to sequential bodies."""

    model_id: str
    count: int = 1
    temperature: float = 0.8
    json_forecast: bool = True
    chain_of_thought: bool = False
    max_tokens: int = 256
    notes: str = ""

    @field_validator("count")
    @classmethod
    def positive_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError("count must be >= 1")
        return v


class SwarmRoster(BaseModel):
    """Source of truth for a bounded, explicitly composed agent swarm."""

    name: str = "default-12"
    n_agents: int = 12
    n_questions_default: int = 1
    bodies: list[SwarmSpecies]
    optional_scale_up: list[SwarmSpecies] = Field(default_factory=list)
    local_scale_up: list[SwarmSpecies] = Field(default_factory=list)
    shared_retrieval: str = "one search pack per question; agents only read"
    serialize_openrouter: bool = True
    rate_limit_note: str = ""

    @model_validator(mode="after")
    def counts_match_n_agents(self) -> SwarmRoster:
        total = sum(b.count for b in self.bodies)
        if total != self.n_agents:
            raise ValueError(f"bodies counts sum to {total}, expected n_agents={self.n_agents}")
        if not 1 <= self.n_agents <= 100:
            raise ValueError("n_agents must be between 1 and 100")
        return self


class RunConfig(BaseModel):
    run_id: str
    epoch: str
    source_type: SourceType | None = None
    models: list[str]
    question_set: str
    max_tool_calls: int = Field(default=12, ge=0, le=25)
    min_prominence: float = 0.0
    n_questions: int = Field(default=50, ge=1, le=500)
    category_balance: dict[str, int] = Field(default_factory=dict)
    sandbox_mode: SandboxMode = "host"
    embedding_backend: Literal["hashing", "sentence-transformers"] = "hashing"
    allow_mock: bool = True
    swarm_roster: str | None = None
    use_swarm: bool = False
    perspectives: str | None = None
    evidence_use: EvidenceUse = "practice"

    @field_validator("run_id")
    @classmethod
    def filesystem_safe_run_id(cls, value: str) -> str:
        from psbx.paths import validate_run_id

        return validate_run_id(value)


class SearchHit(BaseModel):
    document_id: str
    title: str
    outlet: str
    published_at: datetime
    snippet: str
    prominence: float
    source_type: SourceType | None = None
    authenticity: EvidenceAuthenticity = "unverified"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=10, ge=1, le=25)
    min_prominence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_types: list[str] = Field(default_factory=list, max_length=10)


class FetchRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=256)


class CalibrationBin(BaseModel):
    lo: float
    hi: float
    mean_forecast: float
    mean_outcome: float
    n: int


class CalibrationResult(BaseModel):
    """ForecastBench-compatible reliability bins for binary Brier."""

    n_bins: int
    bins: list[CalibrationBin]
    ece: float


class ContaminationBucket(BaseModel):
    gap_lo_days: int
    gap_hi_days: int
    n: int
    mean_brier: float | None
    mean_accuracy: float | None


class ContaminationResult(BaseModel):
    """Descriptive performance grouped by distance from declared cutoff metadata."""

    model_id: str
    declared_pretraining_cutoff: date
    buckets: list[ContaminationBucket]
    pre_cutoff_mean_brier: float | None = None
    post_cutoff_mean_brier: float | None = None
    contamination_delta: float | None = None
    diagnostic_label: str = "declared-cutoff gap diagnostic"
    causal_interpretation_supported: bool = False
    cutoff_is_declared_metadata: bool = True


class ScoreCoverage(BaseModel):
    expected_questions: int
    answered_questions: int
    coverage_fraction: float | None = None
    answered_question_ids: list[str] = Field(default_factory=list)
    missing_question_ids: list[str] = Field(default_factory=list)
    # Prediction files do not contain attempt history. Keep this undefined rather
    # than inventing failures from questions that merely lack a scored prediction.
    failed_question_ids: list[str] | None = None
    failure_history_available: bool = False


class ScoreReport(BaseModel):
    run_id: str
    n_predictions: int
    question_count: int = 0
    brier_by_model: dict[str, float | None]
    brier_index_by_model: dict[str, float | None]
    brier_by_category: dict[str, dict[str, float]]
    baselines: dict[str, float]
    baseline_scope: str = "full_question_set_reference"
    baselines_by_model: dict[str, dict[str, float]] = Field(default_factory=dict)
    models_beating_base_rate: list[str]
    models_beating_prior_signal: list[str] = Field(default_factory=list)
    coverage_by_model: dict[str, ScoreCoverage] = Field(default_factory=dict)
    matched_question_ids: list[str] = Field(default_factory=list)
    matched_brier_by_model: dict[str, float | None] = Field(default_factory=dict)
    matched_c_index_by_model: dict[str, float | None] = Field(default_factory=dict)
    matched_c_index_pairs_by_model: dict[str, int] = Field(default_factory=dict)
    calibration: dict[str, CalibrationResult]
    contamination: list[ContaminationResult]
    n_flagged: int
    n_citation_verification_failed: int = 0
    c_index_by_model: dict[str, float | None] = Field(default_factory=dict)
    c_index_pairs_by_model: dict[str, int] = Field(default_factory=dict)
    c_index_baselines: dict[str, float | None] = Field(default_factory=dict)
    c_index_baselines_by_model: dict[str, dict[str, float | None]] = Field(
        default_factory=dict
    )


class PerspectivePersona(BaseModel):
    """Explicit simulation persona. Never inferred from names, zips, or protected-class proxies."""

    id: str
    slot: int | None = None
    label: str
    region: str
    urbanicity: Urbanicity
    party_id: PartyId
    age_band: str
    education: str
    media_diet: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)
    notes: str = ""

    def prompt_block(self) -> str:
        diet = ", ".join(self.media_diet) if self.media_diet else "unspecified"
        extra = ""
        if self.extra:
            bits = ", ".join(f"{k}={v}" for k, v in self.extra.items())
            extra = f" Extra labeled fields (explicit config only): {bits}."
        return (
            f"Simulation persona (not a real person; not inferred from a name or zip): "
            f"{self.label}. Region={self.region}; urbanicity={self.urbanicity}; "
            f"party_id={self.party_id}; age_band={self.age_band}; education={self.education}; "
            f"media_diet={diet}.{extra} {self.notes} "
            "Do not invent facts about identifiable people. Do not infer additional "
            "protected-class attributes that are not in this card."
        )


class PerspectiveCatalog(BaseModel):
    """Config-driven demographic roster. Expand by adding personas; do not infer them."""

    name: str
    simulation_only: bool = True
    not_inferred: bool = True
    notes: str = ""
    personas: list[PerspectivePersona]

    def assigned(self, n: int) -> list[PerspectivePersona]:
        slotted = sorted(
            [p for p in self.personas if p.slot is not None],
            key=lambda p: int(p.slot or 0),
        )
        if len(slotted) < n:
            raise ValueError(f"need {n} slotted personas, have {len(slotted)}")
        slots = [int(p.slot or 0) for p in slotted[:n]]
        if slots != list(range(n)):
            raise ValueError(f"slotted personas must be 0..{n - 1}, got {slots}")
        return slotted[:n]

    def catalog_only(self) -> list[PerspectivePersona]:
        return [p for p in self.personas if p.slot is None]


class EpochAdvanceSpec(BaseModel):
    """Year-step hook. Does not ingest future documents or enable PolicySim."""

    from_epoch: str = "e2012"
    step_years: int = 1
    enabled: bool = False
    ingests_documents: bool = False
    policy_sim: bool = False
    note: str = ""


class MediaStimulusItem(BaseModel):
    """Track A: headlines as stimulus; score predicted public response vs later history."""

    id: str
    question_id: str
    epoch_id: str
    stimulus_kind: StimulusKind = "contemporaneous_media"
    response_kind: ResponseKind = "binary_outcome"
    score_field: str = "ground_truth"
    note: str = ""


class TrackScore(BaseModel):
    track_id: str
    label: str
    n: int = 0
    brier_vs_later_outcomes: float | None = None
    mae_vs_prior_signal: float | None = None
    vote_spread: float | None = None
    note: str = ""


class HumanBaselineReport(BaseModel):
    """Closeness to historical human/public response — not an impressiveness contest."""

    run_id: str
    epoch_id: str
    n_questions: int
    tracks: dict[str, TrackScore] = Field(default_factory=dict)
    brier_by_model: dict[str, float] = Field(default_factory=dict)
    note: str = ""
