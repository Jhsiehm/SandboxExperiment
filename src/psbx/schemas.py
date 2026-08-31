"""Canonical record types. Everything serializes as JSONL via model_dump(mode='json')."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["economic", "legislative", "geopolitical", "electoral", "corporate"]
PriorKind = Literal["market", "poll", "analyst_consensus", "base_rate"]
SourceType = Literal["news", "wire", "wiki", "gov", "trade"]
CitationSupport = Literal["yes", "no", "context"]
Provider = Literal["openai", "anthropic", "together", "local_vllm"]
SandboxMode = Literal["host", "container"]


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
    source_url: Optional[str] = None
    prior_signal: Optional[PriorSignal] = None

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
    embedding: Optional[list[float]] = None
    gdelt_mention_count: int = 0
    front_page_minutes: float = 0.0

    @field_validator("prominence")
    @classmethod
    def prominence_unit(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("prominence must be in [0, 1]")
        return v


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
    max_tokens: int = 1024
    temperature: float = 0.2
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


class RunConfig(BaseModel):
    run_id: str
    epoch: str
    models: list[str]
    question_set: str
    max_tool_calls: int = 12
    min_prominence: float = 0.0
    n_questions: int = 50
    category_balance: dict[str, int] = Field(default_factory=dict)
    sandbox_mode: SandboxMode = "host"
    embedding_backend: Literal["hashing", "sentence-transformers"] = "hashing"
    allow_mock: bool = True


class SearchHit(BaseModel):
    document_id: str
    title: str
    outlet: str
    published_at: datetime
    snippet: str
    prominence: float


class SearchRequest(BaseModel):
    query: str
    k: int = 10
    min_prominence: float = 0.0


class FetchRequest(BaseModel):
    document_id: str


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
    mean_brier: float
    mean_accuracy: float


class ContaminationResult(BaseModel):
    """Accuracy vs cutoff-gap. Sharp improvement as gap crosses 0 is contamination."""

    model_id: str
    declared_pretraining_cutoff: date
    buckets: list[ContaminationBucket]
    pre_cutoff_mean_brier: Optional[float] = None
    post_cutoff_mean_brier: Optional[float] = None
    contamination_delta: Optional[float] = None


class ScoreReport(BaseModel):
    run_id: str
    n_predictions: int
    brier_by_model: dict[str, float]
    brier_index_by_model: dict[str, float]
    brier_by_category: dict[str, dict[str, float]]
    baselines: dict[str, float]
    models_beating_base_rate: list[str]
    models_beating_prior_signal: list[str] = Field(default_factory=list)
    calibration: dict[str, CalibrationResult]
    contamination: list[ContaminationResult]
    n_flagged: int
    c_index_by_model: dict[str, Optional[float]] = Field(default_factory=dict)
    c_index_pairs_by_model: dict[str, int] = Field(default_factory=dict)
    c_index_baselines: dict[str, Optional[float]] = Field(default_factory=dict)
