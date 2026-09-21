"""Paired evidence ablation with persisted assignment and cluster uncertainty.

This is the causal companion to the descriptive declared-cutoff diagnostic. Every
model/question/replication unit is run under the same budget in three conditions:
no factual evidence, matched authenticated evidence, and a shuffled-evidence placebo.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from psbx.agents.runner import (
    ANTHROPIC_TOOLS,
    OPENAI_TOOLS,
    skip_reason,
    system_prompt,
    user_prompt,
)
from psbx.agents.single_agent import run_single_agent
from psbx.corpus.index import HybridIndex
from psbx.io import read_json, read_jsonl, write_json, write_jsonl
from psbx.paths import run_dir, validate_run_id
from psbx.schemas import Document, Epoch, ModelConfig, Prediction, Question, SearchHit
from psbx.spending import begin_spend_run, preflight_paid_requests

UTC = timezone.utc
_IMPLEMENTATION_SOURCE_PATHS = frozenset(
    {
        Path(__file__).resolve(),
        Path(inspect.getsourcefile(run_single_agent) or "").resolve(),
        Path(inspect.getsourcefile(system_prompt) or "").resolve(),
    }
)
_FAILURE_SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
    "VLLM_API_KEY",
)
CONDITIONS = (
    "no_evidence",
    "matched_authenticated",
    "shuffled_eligible",
)
EvidenceCondition = Literal[
    "no_evidence",
    "matched_authenticated",
    "shuffled_eligible",
]


class EvidenceExperimentSpec(BaseModel):
    experiment_id: str
    epoch: str
    models: list[str]
    question_set: str
    model_design: Literal["single", "mixed"] = "single"
    n_questions: int = Field(default=10, ge=2, le=50)
    replications: int = Field(default=1, ge=1, le=20)
    evidence_documents: int = Field(default=3, ge=1, le=5)
    max_tool_calls: int = Field(default=4, ge=2, le=12)
    max_tokens: int = Field(default=512, ge=64, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    random_seed: int = 12062012
    bootstrap_replicates: int = Field(default=2000, ge=100, le=10_000)
    conditions: tuple[EvidenceCondition, ...] = CONDITIONS
    allow_mock: bool = True

    @model_validator(mode="after")
    def validate_design(self) -> EvidenceExperimentSpec:
        self.experiment_id = validate_run_id(self.experiment_id)
        if set(self.conditions) != set(CONDITIONS) or len(self.conditions) != len(CONDITIONS):
            raise ValueError(f"conditions must be exactly: {', '.join(CONDITIONS)}")
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must not contain duplicates")
        if self.model_design == "single" and len(self.models) != 1:
            raise ValueError("single design requires exactly one model")
        if self.model_design == "mixed" and len(self.models) < 2:
            raise ValueError("mixed design requires at least two models")
        return self


class EvidenceAssignment(BaseModel):
    trial_id: str
    unit_id: str
    question_id: str
    model_id: str
    replication: int
    condition: EvidenceCondition
    condition_order: int
    random_seed: int
    source_question_id: str | None
    evidence_document_ids: list[str]
    evidence_sha256: str
    protocol_only: bool = False


class EvidenceObservation(BaseModel):
    trial_id: str
    unit_id: str
    question_id: str
    model_id: str
    replication: int
    condition: EvidenceCondition
    condition_order: int
    probability: float
    ground_truth: bool
    brier: float
    n_tool_calls: int
    search_queries: list[str]
    evidence_document_ids: list[str]
    citation_document_ids: list[str]
    citation_verification_failed: bool
    raw_prediction: dict[str, Any]


class EvidenceFailure(BaseModel):
    """Durable history for a trial attempt that did not produce an observation."""

    trial_id: str
    unit_id: str
    question_id: str
    model_id: str
    replication: int
    condition: EvidenceCondition
    condition_order: int
    attempt: int
    failed_at: datetime
    error_type: str
    error_message: str


class PairedEstimate(BaseModel):
    contrast: str
    condition_a: EvidenceCondition
    condition_b: EvidenceCondition
    mean_brier_difference_a_minus_b: float
    confidence_interval_95: tuple[float, float]
    n_paired_units: int
    n_question_clusters: int
    uncertainty_method: str = "question-cluster bootstrap"
    bootstrap_replicates: int


class FixedEvidenceClient:
    """A trial-scoped, read-only pool that cannot retrieve outside its assignment."""

    def __init__(self, documents: list[Document]):
        self.documents = list(documents)
        self.by_id = {document.id: document for document in documents}
        self._queries: list[str] = []
        self._n_calls = 0

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    @property
    def n_calls(self) -> int:
        return self._n_calls

    def search(
        self,
        query: str,
        k: int = 10,
        min_prominence: float = 0.0,
        source_types: list[str] | None = None,
    ) -> list[SearchHit]:
        self._n_calls += 1
        self._queries.append(query)
        allowed = set(source_types) if source_types else None
        selected = [
            document
            for document in self.documents
            if document.prominence >= min_prominence
            and (allowed is None or document.source_type in allowed)
        ]
        return [
            SearchHit(
                document_id=document.id,
                title=document.title,
                outlet=document.outlet,
                published_at=document.published_at,
                snippet=document.text[:240],
                prominence=document.prominence,
                source_type=document.source_type,
                authenticity=document.authenticity,
            )
            for document in selected[:k]
        ]

    def fetch(self, document_id: str) -> dict:
        self._n_calls += 1
        document = self.by_id.get(document_id)
        if document is None:
            raise KeyError(f"document {document_id!r} is outside this trial's evidence pool")
        return document.model_dump(mode="json", exclude={"embedding"})


def run_evidence_experiment(
    spec: EvidenceExperimentSpec,
    questions: list[Question],
    models: list[ModelConfig],
    epoch: Epoch,
    index: HybridIndex,
    *,
    destination: str | Path | None = None,
) -> dict[str, Any]:
    """Execute or resume the complete paired experiment and write an audit bundle."""
    chosen_questions = questions[: spec.n_questions]
    _validate_inputs(spec, chosen_questions, models, epoch, index)
    chosen_models = [
        model.model_copy(
            update={
                "max_tokens": spec.max_tokens,
                "temperature": spec.temperature,
            }
        )
        for model in models
    ]
    dest = Path(destination) if destination is not None else run_dir(spec.experiment_id)
    dest.mkdir(parents=True, exist_ok=True)
    packs, sources = _matched_and_shuffled_packs(spec, chosen_questions, index)
    assignments = _assignments(spec, chosen_questions, chosen_models, packs, sources)
    manifest = _manifest(spec, chosen_questions, chosen_models, epoch, index, assignments)
    _ensure_manifest(dest / "experiment_manifest.json", manifest)
    write_jsonl(dest / "assignments.jsonl", assignments)
    write_json(
        dest / "evidence_packs.json",
        {
            assignment.trial_id: {
                "condition": assignment.condition,
                "question_id": assignment.question_id,
                "source_question_id": assignment.source_question_id,
                "evidence_document_ids": assignment.evidence_document_ids,
                "evidence_sha256": assignment.evidence_sha256,
                "protocol_only": assignment.protocol_only,
            }
            for assignment in assignments
        },
    )
    _preflight(spec, chosen_models, len(assignments))
    observations_path = dest / "observations.jsonl"
    observations = (
        read_jsonl(observations_path, EvidenceObservation)
        if observations_path.is_file() and observations_path.stat().st_size
        else []
    )
    failures_path = dest / "failures.jsonl"
    failures = (
        read_jsonl(failures_path, EvidenceFailure)
        if failures_path.is_file() and failures_path.stat().st_size
        else []
    )
    completed = {observation.trial_id for observation in observations}
    questions_by_id = {question.id: question for question in chosen_questions}
    models_by_id = {model.id: model for model in chosen_models}
    for assignment in sorted(assignments, key=lambda row: (row.unit_id, row.condition_order)):
        if assignment.trial_id in completed:
            continue
        trial_docs = _trial_documents(assignment, packs, index, epoch)
        try:
            prediction = run_single_agent(
                questions_by_id[assignment.question_id],
                models_by_id[assignment.model_id],
                epoch,
                spec.experiment_id,
                FixedEvidenceClient(trial_docs),
                max_tool_calls=spec.max_tool_calls,
            )
        except Exception as exc:
            failures.append(
                _failure_record(
                    assignment,
                    exc,
                    attempt=(
                        1
                        + sum(
                            1
                            for failure in failures
                            if failure.trial_id == assignment.trial_id
                        )
                    ),
                )
            )
            write_jsonl(failures_path, failures)
            raise
        citation_failed = not _citations_match_pool(prediction, trial_docs)
        truth = questions_by_id[assignment.question_id].ground_truth
        observation = EvidenceObservation(
            trial_id=assignment.trial_id,
            unit_id=assignment.unit_id,
            question_id=assignment.question_id,
            model_id=assignment.model_id,
            replication=assignment.replication,
            condition=assignment.condition,
            condition_order=assignment.condition_order,
            probability=prediction.probability,
            ground_truth=truth,
            brier=(prediction.probability - float(truth)) ** 2,
            n_tool_calls=prediction.n_tool_calls,
            search_queries=prediction.search_queries,
            evidence_document_ids=assignment.evidence_document_ids,
            citation_document_ids=[citation.document_id for citation in prediction.citations],
            citation_verification_failed=citation_failed,
            raw_prediction=prediction.model_dump(mode="json"),
        )
        observations.append(observation)
        completed.add(assignment.trial_id)
        write_jsonl(observations_path, observations)
    report = analyze_evidence_experiment(spec, observations, failures=failures)
    report["manifest_fingerprint"] = manifest["fingerprint"]
    write_json(dest / "experiment_results.json", report)
    return report


def analyze_evidence_experiment(
    spec: EvidenceExperimentSpec,
    observations: list[EvidenceObservation],
    *,
    failures: list[EvidenceFailure] | None = None,
) -> dict[str, Any]:
    """Require complete paired cells, then estimate question-cluster uncertainty."""
    cells: dict[str, dict[str, EvidenceObservation]] = defaultdict(dict)
    for observation in observations:
        if observation.condition in cells[observation.unit_id]:
            raise ValueError(
                f"duplicate observation for {observation.unit_id}/{observation.condition}"
            )
        cells[observation.unit_id][observation.condition] = observation
    incomplete = sorted(
        unit_id
        for unit_id, by_condition in cells.items()
        if set(by_condition) != set(CONDITIONS)
    )
    if incomplete:
        raise ValueError("incomplete paired experiment units: " + ", ".join(incomplete[:10]))
    contrasts = [
        _paired_estimate(
            spec,
            cells,
            "authenticated evidence minus no evidence",
            "matched_authenticated",
            "no_evidence",
            seed_offset=0,
        ),
        _paired_estimate(
            spec,
            cells,
            "matched evidence minus shuffled-evidence placebo",
            "matched_authenticated",
            "shuffled_eligible",
            seed_offset=1,
        ),
    ]
    by_condition: dict[str, dict[str, float | int]] = {}
    for condition in CONDITIONS:
        rows = [row for row in observations if row.condition == condition]
        by_condition[condition] = {
            "mean_brier": sum(row.brier for row in rows) / len(rows),
            "n": len(rows),
            "citation_verification_failures": sum(
                1 for row in rows if row.citation_verification_failed
            ),
        }
    failures = failures or []
    completed_trials = {observation.trial_id for observation in observations}
    failed_trials = {failure.trial_id for failure in failures}
    return {
        "experiment_id": spec.experiment_id,
        "status": "complete",
        "causal_scope": (
            "Randomized within-unit evidence-condition contrasts under the declared "
            "protocol; no claim extends beyond these questions, models, or evidence packs."
        ),
        "model_design": spec.model_design,
        "conditions": list(CONDITIONS),
        "common_budget": {
            "max_tool_calls": spec.max_tool_calls,
            "max_tokens": spec.max_tokens,
            "temperature": spec.temperature,
        },
        "random_seed_scope": (
            "Condition assignment and question-cluster bootstrap only; provider "
            "sampling is not claimed deterministic."
        ),
        "n_observations": len(observations),
        "n_paired_units": len(cells),
        "n_question_clusters": len({row.question_id for row in observations}),
        "by_condition": by_condition,
        "paired_contrasts": [contrast.model_dump(mode="json") for contrast in contrasts],
        "failure_history": {
            "n_failed_attempts": len(failures),
            "trials_with_failures": len(failed_trials),
            "resolved_trial_ids": sorted(failed_trials & completed_trials),
            "unresolved_trial_ids": sorted(failed_trials - completed_trials),
        },
    }


def _validate_inputs(
    spec: EvidenceExperimentSpec,
    questions: list[Question],
    models: list[ModelConfig],
    epoch: Epoch,
    index: HybridIndex,
) -> None:
    if len(questions) < 2:
        raise ValueError("evidence experiment requires at least two questions")
    if [model.id for model in models] != spec.models:
        raise ValueError("models must match spec.models in declared order")
    if any(question.epoch_id != epoch.id for question in questions):
        raise ValueError("all experiment questions must match the selected epoch")
    if index.cutoff != epoch.cutoff_date:
        raise ValueError("experiment corpus cutoff does not match epoch cutoff")
    if not any(document.research_eligible for document in index.docs):
        raise ValueError("experiment requires authenticated research-eligible evidence")


def _matched_and_shuffled_packs(
    spec: EvidenceExperimentSpec,
    questions: list[Question],
    index: HybridIndex,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    packs: dict[str, list[str]] = {}
    for question in questions:
        hits = index.search(question.text, k=25)
        eligible = [
            hit.document_id
            for hit in hits
            if index.get(hit.document_id).research_eligible
        ][: spec.evidence_documents]
        if not eligible:
            raise ValueError(
                f"question {question.id!r} has no matched authenticated evidence"
            )
        packs[question.id] = eligible
    order = [question.id for question in questions]
    rng = random.Random(spec.random_seed)
    rng.shuffle(order)
    shift = 1 + rng.randrange(len(order) - 1)
    rotated = order[shift:] + order[:shift]
    shuffled_sources = dict(zip(order, rotated))
    return packs, shuffled_sources


def _assignments(
    spec: EvidenceExperimentSpec,
    questions: list[Question],
    models: list[ModelConfig],
    packs: dict[str, list[str]],
    shuffled_sources: dict[str, str],
) -> list[EvidenceAssignment]:
    rows: list[EvidenceAssignment] = []
    for question in questions:
        for model in models:
            for replication in range(spec.replications):
                unit_id = f"{model.id}:{question.id}:r{replication}"
                unit_seed = _stable_seed(spec.random_seed, unit_id)
                order = list(CONDITIONS)
                random.Random(unit_seed).shuffle(order)
                for condition_order, condition in enumerate(order):
                    source_question_id: str | None = question.id
                    ids = packs[question.id]
                    protocol_only = False
                    if condition == "no_evidence":
                        source_question_id = None
                        ids = []
                        protocol_only = True
                    elif condition == "shuffled_eligible":
                        source_question_id = shuffled_sources[question.id]
                        ids = packs[source_question_id]
                    trial_id = f"{unit_id}:{condition}"
                    rows.append(
                        EvidenceAssignment(
                            trial_id=trial_id,
                            unit_id=unit_id,
                            question_id=question.id,
                            model_id=model.id,
                            replication=replication,
                            condition=condition,
                            condition_order=condition_order,
                            random_seed=unit_seed,
                            source_question_id=source_question_id,
                            evidence_document_ids=list(ids),
                            evidence_sha256=_digest_json(ids),
                            protocol_only=protocol_only,
                        )
                    )
    return rows


def _trial_documents(
    assignment: EvidenceAssignment,
    packs: dict[str, list[str]],
    index: HybridIndex,
    epoch: Epoch,
) -> list[Document]:
    del packs
    if assignment.condition != "no_evidence":
        return [index.get(document_id) for document_id in assignment.evidence_document_ids]
    text = (
        "Protocol notice: factual historical evidence is intentionally withheld in this "
        "experimental condition. Forecast from the question alone."
    )
    return [
        Document(
            id=f"protocol-{hashlib.sha256(assignment.trial_id.encode()).hexdigest()[:16]}",
            url="urn:psbx:evidence-ablation:no-evidence",
            outlet="PSBX experiment protocol",
            published_at=datetime.combine(epoch.cutoff_date, datetime.min.time(), tzinfo=UTC),
            title="No factual evidence condition",
            text=text,
            source_type="academic",
            authenticity="reconstructed_fixture",
            timestamp_basis="fixture_as_of",
            provenance="Protocol marker only; contains no historical factual evidence.",
        )
    ]


def _citations_match_pool(prediction: Prediction, documents: list[Document]) -> bool:
    by_id = {document.id: document for document in documents}
    return bool(prediction.citations) and all(
        citation.document_id in by_id
        and citation.quoted_span in by_id[citation.document_id].text
        for citation in prediction.citations
    )


def _preflight(
    spec: EvidenceExperimentSpec,
    models: list[ModelConfig],
    n_assignments: int,
) -> None:
    if os.environ.get("PSBX_MOCK_LLM", "0") == "1":
        return
    for model in models:
        reason = skip_reason(model)
        if reason:
            raise RuntimeError(f"{model.id}: {reason}")
    trials_per_model = n_assignments // max(len(models), 1)
    preflight_paid_requests(
        [(model, trials_per_model * (spec.max_tool_calls + 4)) for model in models]
    )
    begin_spend_run(spec.experiment_id)


def _manifest(
    spec: EvidenceExperimentSpec,
    questions: list[Question],
    models: list[ModelConfig],
    epoch: Epoch,
    index: HybridIndex,
    assignments: list[EvidenceAssignment],
) -> dict[str, Any]:
    prompt_protocol = {
        "system_prompt": system_prompt(epoch.cutoff_date),
        "user_prompts_by_question": {
            question.id: user_prompt(question) for question in questions
        },
        "openai_tools": OPENAI_TOOLS,
        "anthropic_tools": ANTHROPIC_TOOLS,
        "implementation_sha256": _implementation_sha256(),
    }
    contract = {
        "schema_version": 2,
        "spec": spec.model_dump(mode="json"),
        "epoch": epoch.model_dump(mode="json"),
        "prompt_protocol": prompt_protocol,
        "questions_sha256": _digest_json(
            [question.model_dump(mode="json") for question in questions]
        ),
        "models_sha256": _digest_json([model.model_dump(mode="json") for model in models]),
        "eligible_corpus_sha256": _digest_json(
            [
                document.model_dump(mode="json", exclude={"embedding"})
                for document in index.docs
                if document.research_eligible
            ]
        ),
        "assignments_sha256": _digest_json(
            [assignment.model_dump(mode="json") for assignment in assignments]
        ),
    }
    return {**contract, "fingerprint": _digest_json(contract)}


def _ensure_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if path.is_file():
        previous = read_json(path)
        if previous.get("fingerprint") != manifest["fingerprint"]:
            raise RuntimeError(
                "existing evidence experiment has different inputs, assignments, or "
                "execution protocol; choose a new experiment_id"
            )
        return
    write_json(path, manifest)


def _failure_record(
    assignment: EvidenceAssignment,
    exc: Exception,
    *,
    attempt: int,
) -> EvidenceFailure:
    message = _safe_failure_message(exc)
    return EvidenceFailure(
        trial_id=assignment.trial_id,
        unit_id=assignment.unit_id,
        question_id=assignment.question_id,
        model_id=assignment.model_id,
        replication=assignment.replication,
        condition=assignment.condition,
        condition_order=assignment.condition_order,
        attempt=attempt,
        failed_at=datetime.now(UTC),
        error_type=type(exc).__name__,
        error_message=message[:500],
    )


def _safe_failure_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or "no error message"
    for name in _FAILURE_SECRET_ENV_NAMES:
        secret = os.environ.get(name) or ""
        if secret:
            message = message.replace(secret, "[redacted]")
    lowered = message.lower()
    if "authorization:" in lowered or "bearer " in lowered:
        return "provider failure details redacted"
    return message


def _implementation_sha256() -> str:
    """Fingerprint source that can change execution while prompts stay identical."""
    digest = hashlib.sha256()
    for path in sorted(_IMPLEMENTATION_SOURCE_PATHS, key=str):
        if not path.is_file():
            raise RuntimeError(f"cannot fingerprint evidence protocol source: {path}")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _paired_estimate(
    spec: EvidenceExperimentSpec,
    cells: dict[str, dict[str, EvidenceObservation]],
    contrast: str,
    condition_a: EvidenceCondition,
    condition_b: EvidenceCondition,
    *,
    seed_offset: int,
) -> PairedEstimate:
    differences = [
        (
            by_condition[condition_a].question_id,
            by_condition[condition_a].brier - by_condition[condition_b].brier,
        )
        for by_condition in cells.values()
    ]
    estimate = sum(value for _, value in differences) / len(differences)
    by_question: dict[str, list[float]] = defaultdict(list)
    for question_id, value in differences:
        by_question[question_id].append(value)
    clusters = sorted(by_question)
    rng = random.Random(spec.random_seed + 10_000 + seed_offset)
    boot: list[float] = []
    for _ in range(spec.bootstrap_replicates):
        sampled = [rng.choice(clusters) for _ in clusters]
        values = [value for cluster in sampled for value in by_question[cluster]]
        boot.append(sum(values) / len(values))
    boot.sort()
    lo = boot[int(0.025 * (len(boot) - 1))]
    hi = boot[int(0.975 * (len(boot) - 1))]
    return PairedEstimate(
        contrast=contrast,
        condition_a=condition_a,
        condition_b=condition_b,
        mean_brier_difference_a_minus_b=estimate,
        confidence_interval_95=(lo, hi),
        n_paired_units=len(differences),
        n_question_clusters=len(clusters),
        bootstrap_replicates=spec.bootstrap_replicates,
    )


def _stable_seed(seed: int, value: str) -> int:
    digest = hashlib.sha256(f"{seed}:{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _digest_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
