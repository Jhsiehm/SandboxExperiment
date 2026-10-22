"""ANES 2012 silicon-sample and time-locked society experiment utilities.

The module deliberately separates three things that are easy to conflate:

* a faithful paper-style silicon-sample baseline;
* a forward, election-eve prediction treatment;
* a conversational society treatment.

Runtime profiles never contain held-out outcomes.  Evaluation opens the vault only after the
prediction artifact has been written and checksum-sealed.  The included simulator is a
provider-free structural test, not evidence that an LLM reproduces human behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader

from psbx.paths import resolve, run_dir, validate_run_id

AnesPhase = Literal["pre", "post"]
Treatment = Literal["independent", "society"]

_HEADER = re.compile(
    r'^\s*"(?P<label>[^"\n]+)"\s*\((?P<variable>[A-Z][A-Z0-9_]+)\)\s*$',
    re.MULTILINE,
)
_DOTS = re.compile(r"\.{20,}")
_PAGE = re.compile(r"\[\[PAGE (?P<page>\d+)\]\]")
_SECTION = re.compile(r"section:\s*([A-Z0-9_]+)", re.IGNORECASE)
_RESPONSE_TYPE = re.compile(r"response type:\s*([^\n]+)", re.IGNORECASE)
_RESPONSE_ORDER = re.compile(r"response order:\s*([^\n]+)", re.IGNORECASE)
_OPTION = re.compile(r"^\s*(-?\d+[A-Za-z]?)\.\s+(.+?)\s*$")

PAPER_STUDY_2_PROFILE_FIELDS = (
    "dem_raceeth_x",
    "gender_respondent_x",
    "dem_age_r_x",
    "libcpre_self",
    "pid_x",
    "paprofile_interestpolit",
    "relig_church",
    "discuss_disc",
    "patriot_flag",
    "sample_stfips",
)
STRICT_PRE_ELECTION_PROFILE_FIELDS = tuple(
    field for field in PAPER_STUDY_2_PROFILE_FIELDS if field not in {"discuss_disc", "patriot_flag"}
)
ANES_2012_PROFILE_TIMING = {
    "dem_raceeth_x": {
        "timing": "pre_election",
        "strict_allowed": True,
        "codebook_label": "PRE: SUMMARY- R race and ethnicity group",
        "codebook_pdf_page": 687,
        "evidence": "ANES 2012 user guide/codebook",
    },
    "gender_respondent_x": {
        "timing": "pre_election_or_preexisting_profile",
        "strict_allowed": True,
        "codebook_label": "SUMMARY: Gender of Respondent for both FTF and Web modes",
        "codebook_pdf_page": 98,
        "evidence": (
            "FTF gender observation is labeled PRE; web-panel profile data were collected before "
            "the ANES surveys."
        ),
    },
    "dem_age_r_x": {
        "timing": "pre_election",
        "strict_allowed": True,
        "codebook_label": "PRE: SUMMARY: Age of R",
        "codebook_pdf_page": 570,
        "evidence": "ANES 2012 user guide/codebook",
    },
    "libcpre_self": {
        "timing": "pre_election",
        "strict_allowed": True,
        "codebook_label": "7pt scale Liberal/conservative self-placement",
        "codebook_pdf_page": 292,
        "evidence": "Position: Pre and Post-election survey; this variable is the PRE measure.",
    },
    "pid_x": {
        "timing": "pre_election",
        "strict_allowed": True,
        "codebook_label": "PRE: SUMMARY- Party ID",
        "codebook_pdf_page": 371,
        "evidence": "ANES 2012 user guide/codebook",
    },
    "paprofile_interestpolit": {
        "timing": "preexisting_web_profile",
        "strict_allowed": True,
        "codebook_label": (
            "WEB ONLY: Polit Affairs profile- Q16: interest in politics and public affairs"
        ),
        "codebook_pdf_page": 2323,
        "evidence": (
            "The user guide states that internet respondents completed profile surveys before "
            "their ANES surveys. FTF cases are inapplicable and become missing."
        ),
    },
    "relig_church": {
        "timing": "pre_election",
        "strict_allowed": True,
        "codebook_label": "Ever attend church or religious services",
        "codebook_pdf_page": 528,
        "evidence": "Position: Pre-election survey, section-item 59-5.",
    },
    "discuss_disc": {
        "timing": "post_election",
        "strict_allowed": False,
        "codebook_label": "Ever discuss politics with family or friends",
        "codebook_pdf_page": 1344,
        "evidence": "Position: Post election survey, section-item 140-1.",
    },
    "patriot_flag": {
        "timing": "post_election",
        "strict_allowed": False,
        "codebook_label": "Emotion seeing flag fly",
        "codebook_pdf_page": 1189,
        "evidence": "Position: Post election survey, section-item 129.5-1.",
    },
    "sample_stfips": {
        "timing": "sampling_frame",
        "strict_allowed": True,
        "codebook_label": "Sample- state FIPS code",
        "codebook_pdf_page": 1792,
        "evidence": "Sampling-frame geography fixed before interview and election outcome.",
    },
}
PAPER_STUDY_2_TARGET = "presvote2012_x"
PAPER_STUDY_3_2016_FIELDS = (
    "V161342",
    "V161310x",
    "V161267",
    "V161270",
    "V161244",
    "V162125x",
    "V162174",
    "V162256",
    "V161126",
    "V161158x",
    "V162031x",
    "V162062x",
)


class AnesQuestion(BaseModel):
    schema_version: int = 1
    question_id: str
    variable: str
    occurrence: int = 1
    label: str
    phase: AnesPhase
    section: str = ""
    page: int
    wording: str = ""
    response_type: str = ""
    response_order: str = ""
    response_options: list[str] = Field(default_factory=list)
    mode: str = "both"
    experimental_eligible: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    vote_forecast_runtime_allowed: bool
    vote_forecast_exclusion_reasons: list[str] = Field(default_factory=list)
    temporal_role: Literal[
        "contemporaneous_profile_candidate",
        "contemporaneous_early_vote_outcome",
        "held_out_target",
    ]
    source_sha256: str


class AnesSocietySpec(BaseModel):
    schema_version: int = 1
    run_id: str
    design: Literal["paper_study2", "full_question_forward", "society_treatment"]
    information_cutoff: date
    election_date: date
    case_id_field: str = "caseid"
    weight_field: str | None = None
    profile_fields: list[str]
    target_fields: list[str]
    profile_timing_policy: Literal["unspecified", "paper_faithful", "strict_pre_election"] = (
        "unspecified"
    )
    missing_codes_below_zero: bool = True
    profile_collection_timing: str = "pre_election"
    source_release_date: date
    treatments: list[Treatment] = Field(default_factory=lambda: ["independent", "society"])
    replications: int = Field(default=5, ge=1, le=1000)
    seed: int = 220906899
    max_agents: int = Field(default=120, ge=2, le=100_000)
    group_size: int = Field(default=12, ge=2, le=100)
    interaction_rounds: int = Field(default=3, ge=1, le=25)

    @model_validator(mode="after")
    def validate_temporal_contract(self) -> AnesSocietySpec:
        self.run_id = validate_run_id(self.run_id)
        if self.information_cutoff >= self.election_date:
            raise ValueError("information_cutoff must precede election_date")
        overlap = set(self.profile_fields) & set(self.target_fields)
        if overlap:
            raise ValueError("profile_fields and target_fields overlap: " + ", ".join(overlap))
        if len(set(self.profile_fields)) != len(self.profile_fields):
            raise ValueError("profile_fields contains duplicates")
        if len(set(self.target_fields)) != len(self.target_fields):
            raise ValueError("target_fields contains duplicates")
        if not self.target_fields:
            raise ValueError("at least one held-out target field is required")
        if self.profile_timing_policy == "paper_faithful":
            if tuple(self.profile_fields) != PAPER_STUDY_2_PROFILE_FIELDS:
                raise ValueError(
                    "paper_faithful policy requires the exact reported ten-field profile"
                )
        if self.profile_timing_policy == "strict_pre_election":
            unknown = set(self.profile_fields) - set(ANES_2012_PROFILE_TIMING)
            if unknown:
                raise ValueError(
                    "strict_pre_election fields lack a timing audit: " + ", ".join(sorted(unknown))
                )
            prohibited = [
                field
                for field in self.profile_fields
                if not ANES_2012_PROFILE_TIMING[field]["strict_allowed"]
            ]
            if prohibited:
                raise ValueError(
                    "strict_pre_election policy rejects post-election fields: "
                    + ", ".join(prohibited)
                )
        return self


class PreparedAnesPaths(BaseModel):
    runtime_profiles: str
    runtime_manifest: str
    evaluation_targets: str
    split_seal: str
    timing_audit: str
    n_profiles: int
    weighting_status: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _clean_text(value: str) -> str:
    value = _PAGE.sub(" ", value)
    value = re.sub(r"(?m)^\s*\d+\s*$", " ", value)
    return " ".join(value.split())


def _question_eligibility(
    label: str,
    wording: str,
    response_type: str,
    response_options: list[str],
) -> list[str]:
    reasons: list[str] = []
    searchable = f"{label} {wording}".casefold()
    response = response_type.casefold()
    if "restricted" in searchable:
        reasons.append("restricted_or_identifying")
    if any(token in searchable for token in ("interviewer:", "iwr ", "checkpoint")):
        reasons.append("interviewer_or_administrative")
    if "display only" in response or not response_type:
        reasons.append("display_or_missing_response_type")
    if "text entry" in response:
        reasons.append("free_text_response")
    if "numeric entry" in response and not response_options:
        reasons.append("unbounded_numeric_response")
    if not wording:
        reasons.append("no_question_wording")
    return sorted(set(reasons))


def _vote_forecast_exclusions(
    phase: AnesPhase,
    variable: str,
    label: str,
    generic_reasons: list[str],
) -> list[str]:
    reasons = list(generic_reasons)
    if phase == "post":
        reasons.append("post_election_measure")
    early_vote_tokens = (
        "already voted",
        "confirmation voted",
        "howvote",
        "presvt",
        "hsevt",
        "senvt",
    )
    searchable = f"{variable} {label}".casefold()
    if phase == "pre" and any(token in searchable for token in early_vote_tokens):
        reasons.append("early_vote_outcome_for_vote_forecast")
    return sorted(set(reasons))


def _parse_questionnaire_text(
    text: str,
    phase: AnesPhase,
    source_sha256: str,
) -> list[AnesQuestion]:
    matches = list(_HEADER.finditer(text))
    if not matches:
        raise ValueError("no ANES questionnaire items found")
    questions: list[AnesQuestion] = []
    occurrences: dict[str, int] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        prefix = text[: match.start()]
        page_matches = list(_PAGE.finditer(prefix))
        page = int(page_matches[-1].group("page")) if page_matches else 1
        section_matches = list(_SECTION.finditer(prefix[-20_000:]))
        section = section_matches[-1].group(1).upper() if section_matches else ""
        pieces = _DOTS.split(block)
        wording = _clean_text(pieces[1]) if len(pieces) >= 2 else ""
        response_area = pieces[2] if len(pieces) >= 3 else ""
        response_type_match = _RESPONSE_TYPE.search(block)
        response_order_match = _RESPONSE_ORDER.search(block)
        response_type = _clean_text(response_type_match.group(1)) if response_type_match else ""
        response_order = _clean_text(response_order_match.group(1)) if response_order_match else ""
        option_limit = _RESPONSE_TYPE.split(response_area, maxsplit=1)[0]
        response_options = []
        for line in option_limit.splitlines():
            option = _OPTION.match(line)
            if option:
                response_options.append(f"{option.group(1)}. {_clean_text(option.group(2))}")
        label = _clean_text(match.group("label"))
        upper_label = label.upper()
        mode = "both"
        if upper_label.startswith("FTF ONLY"):
            mode = "ftf_only"
        elif upper_label.startswith("WEB ONLY"):
            mode = "web_only"
        elif upper_label.startswith("CASI ONLY"):
            mode = "casi_only"
        reasons = _question_eligibility(label, wording, response_type, response_options)
        variable = match.group("variable")
        occurrences[variable] = occurrences.get(variable, 0) + 1
        occurrence = occurrences[variable]
        vote_reasons = _vote_forecast_exclusions(phase, variable, label, reasons)
        early_vote = "early_vote_outcome_for_vote_forecast" in vote_reasons
        identifier = f"anes2012-{phase}-{variable.casefold()}"
        if occurrence > 1:
            identifier += f"-{occurrence}"
        questions.append(
            AnesQuestion(
                question_id=identifier,
                variable=variable,
                occurrence=occurrence,
                label=label,
                phase=phase,
                section=section,
                page=page,
                wording=wording,
                response_type=response_type,
                response_order=response_order,
                response_options=response_options,
                mode=mode,
                experimental_eligible=not reasons,
                exclusion_reasons=reasons,
                vote_forecast_runtime_allowed=not vote_reasons,
                vote_forecast_exclusion_reasons=vote_reasons,
                temporal_role=(
                    "contemporaneous_early_vote_outcome"
                    if early_vote
                    else (
                        "contemporaneous_profile_candidate" if phase == "pre" else "held_out_target"
                    )
                ),
                source_sha256=source_sha256,
            )
        )
    return questions


def parse_anes_questionnaire(path: str | Path, phase: AnesPhase) -> list[AnesQuestion]:
    """Parse every named instrument specification from an official ANES questionnaire PDF."""
    source = resolve(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    pages = PdfReader(source).pages
    text = "\n".join(
        f"\n[[PAGE {index}]]\n{page.extract_text() or ''}"
        for index, page in enumerate(pages, start=1)
    )
    try:
        return _parse_questionnaire_text(text, phase, _sha256_file(source))
    except ValueError as exc:
        raise ValueError(f"no ANES questionnaire items found in {source}") from exc


def write_question_bank(
    pre_path: str | Path,
    post_path: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    questions = parse_anes_questionnaire(pre_path, "pre") + parse_anes_questionnaire(
        post_path, "post"
    )
    destination = resolve(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for question in questions:
            handle.write(question.model_dump_json() + "\n")
    counts = {
        "total": len(questions),
        "pre": sum(question.phase == "pre" for question in questions),
        "post": sum(question.phase == "post" for question in questions),
        "experimental_eligible": sum(question.experimental_eligible for question in questions),
        "vote_forecast_runtime_allowed": sum(
            question.vote_forecast_runtime_allowed for question in questions
        ),
        "excluded": sum(not question.experimental_eligible for question in questions),
    }
    manifest = {
        "schema_version": 1,
        "artifact": str(destination),
        "artifact_sha256": _sha256_file(destination),
        "counts": counts,
        "definition": (
            "Full inventory of named ANES 2012 questionnaire specifications. Experimental "
            "eligibility excludes restricted, administrative, display-only, unbounded numeric, "
            "and free-text items."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_anes_frame(path: str | Path) -> pd.DataFrame:
    source = resolve(path)
    suffix = source.suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix == ".dta":
        return pd.read_stata(source, convert_categoricals=False)
    if suffix == ".sav":
        try:
            return pd.read_spss(source)
        except ImportError as exc:
            raise RuntimeError(
                "reading SAV files requires the optional pyreadstat package"
            ) from exc
    raise ValueError("ANES input must be CSV, DTA, or SAV")


def _json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _pseudonymous_id(value: Any) -> str:
    return "anes12-" + hashlib.sha256(f"anes2012:{value}".encode()).hexdigest()[:20]


def audit_runtime_payload(payload: Any, forbidden_fields: list[str] | set[str]) -> None:
    """Fail closed when a held-out field name occurs anywhere as a runtime object key."""
    forbidden = {field.casefold() for field in forbidden_fields}

    def visit(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key).casefold() in forbidden:
                    raise ValueError(
                        f"held-out field {key!r} leaked into runtime payload at {location}"
                    )
                visit(nested, f"{location}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, f"{location}[{index}]")

    visit(payload, "$")


def build_conditioning_field_timing_audit(spec: AnesSocietySpec) -> dict[str, Any]:
    """Return the codebook-backed timing decision for every conditioning field."""
    fields = []
    for field in spec.profile_fields:
        evidence = ANES_2012_PROFILE_TIMING.get(field)
        if evidence is None:
            fields.append(
                {
                    "field": field,
                    "timing": "not_audited",
                    "strict_allowed": False,
                    "codebook_label": "",
                    "codebook_pdf_page": None,
                    "evidence": "No ANES 2012 timing decision is registered.",
                }
            )
        else:
            fields.append({"field": field, **evidence})
    post_fields = [row["field"] for row in fields if row["timing"] == "post_election"]
    unaudited_fields = [row["field"] for row in fields if row["timing"] == "not_audited"]
    strict_allowed = all(bool(row["strict_allowed"]) for row in fields)
    return {
        "schema_version": 1,
        "run_id": spec.run_id,
        "profile_timing_policy": spec.profile_timing_policy,
        "information_cutoff": spec.information_cutoff.isoformat(),
        "source": "ANES 2012 Time Series Study user guide/codebook and questionnaires",
        "source_release_date": spec.source_release_date.isoformat(),
        "strict_pre_election_eligible": strict_allowed,
        "post_election_fields": post_fields,
        "unaudited_fields": unaudited_fields,
        "fields": fields,
    }


def prepare_anes_split(
    input_path: str | Path,
    spec: AnesSocietySpec,
    output_root: str | Path,
    *,
    evaluation_root: str | Path = "data/evaluation-vault",
) -> PreparedAnesPaths:
    """Split one ANES-like file into runtime profiles and a separately rooted outcome vault."""
    source = resolve(input_path)
    frame = load_anes_frame(source)
    required = {
        spec.case_id_field,
        *spec.profile_fields,
        *spec.target_fields,
    }
    if spec.weight_field:
        required.add(spec.weight_field)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("ANES input is missing columns: " + ", ".join(sorted(missing)))
    root = resolve(output_root)
    runtime_root = root / "runtime"
    vault_root = resolve(evaluation_root) / spec.run_id
    runtime_root.mkdir(parents=True, exist_ok=True)
    vault_root.mkdir(parents=True, exist_ok=True)
    weighting_status = "official_weight"
    if spec.weight_field is None:
        weights = pd.Series(np.ones(len(frame)), index=frame.index)
        weighting_status = "uniform_unweighted_validation_only"
    else:
        weights = pd.to_numeric(frame[spec.weight_field], errors="coerce")
        if weights.isna().any() or (weights <= 0).any():
            raise ValueError("ANES weight field must contain finite positive values")
    runtime_profiles = runtime_root / "profiles.jsonl"
    targets = vault_root / "targets.csv"
    timing_audit_path = root / "conditioning-field-timing-audit.json"
    timing_audit = build_conditioning_field_timing_audit(spec)
    timing_audit_path.write_text(json.dumps(timing_audit, indent=2) + "\n", encoding="utf-8")
    runtime_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    for row_index, row in frame.iterrows():
        person_id = _pseudonymous_id(row[spec.case_id_field])
        profile: dict[str, Any] = {}
        for field in spec.profile_fields:
            value = _json_value(row[field])
            if spec.missing_codes_below_zero and isinstance(value, (int, float)) and value < 0:
                value = None
            profile[field] = value
        runtime_row = {
            "schema_version": 1,
            "synthetic_person_id": person_id,
            "population_weight": float(weights.loc[row_index]),
            "profile": profile,
            "profile_collection_timing": spec.profile_collection_timing,
            "information_cutoff": spec.information_cutoff.isoformat(),
        }
        audit_runtime_payload(runtime_row, spec.target_fields)
        runtime_rows.append(runtime_row)
        target_row: dict[str, Any] = {
            "synthetic_person_id": person_id,
            "population_weight": float(weights.loc[row_index]),
        }
        for field in spec.target_fields:
            target_row[field] = _json_value(row[field])
        target_rows.append(target_row)
    with runtime_profiles.open("w", encoding="utf-8") as handle:
        for row in runtime_rows:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    pd.DataFrame(target_rows).to_csv(targets, index=False)
    runtime_manifest_path = runtime_root / "manifest.json"
    runtime_manifest = {
        "schema_version": 1,
        "run_id": spec.run_id,
        "design": spec.design,
        "n_profiles": len(runtime_rows),
        "profile_fields": spec.profile_fields,
        "profile_timing_policy": spec.profile_timing_policy,
        "strict_pre_election_eligible": timing_audit["strict_pre_election_eligible"],
        "post_election_profile_fields": timing_audit["post_election_fields"],
        "conditioning_field_timing_audit": str(timing_audit_path),
        "conditioning_field_timing_audit_sha256": _sha256_file(timing_audit_path),
        "information_cutoff": spec.information_cutoff.isoformat(),
        "election_date": spec.election_date.isoformat(),
        "source_release_date": spec.source_release_date.isoformat(),
        "source_was_public_at_cutoff": spec.source_release_date <= spec.information_cutoff,
        "profile_collection_timing": spec.profile_collection_timing,
        "weighting_status": weighting_status,
        "runtime_profiles_sha256": _sha256_file(runtime_profiles),
        "guardrail": "No held-out target columns or values are present in runtime profiles.",
        "interpretation": (
            "Pre-election respondent answers are contemporaneous private covariates, not public "
            "election-eve information, when the source release follows the cutoff."
        ),
    }
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest, indent=2) + "\n", encoding="utf-8"
    )
    seal_path = root / "split-seal.json"
    seal = {
        "schema_version": 1,
        "run_id": spec.run_id,
        "source_sha256": _sha256_file(source),
        "runtime_profiles_sha256": _sha256_file(runtime_profiles),
        "evaluation_targets_sha256": _sha256_file(targets),
        "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
        "conditioning_field_timing_audit_sha256": _sha256_file(timing_audit_path),
        "n_profiles": len(runtime_rows),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return PreparedAnesPaths(
        runtime_profiles=str(runtime_profiles),
        runtime_manifest=str(runtime_manifest_path),
        evaluation_targets=str(targets),
        split_seal=str(seal_path),
        timing_audit=str(timing_audit_path),
        n_profiles=len(runtime_rows),
        weighting_status=weighting_status,
    )


def _read_runtime_profiles(path: str | Path) -> list[dict[str, Any]]:
    profiles = []
    with resolve(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                profiles.append(json.loads(line))
    if not profiles:
        raise ValueError("runtime profile file is empty")
    return profiles


def verify_prepared_runtime_profiles(
    profiles_path: str | Path,
    *,
    cutoff: date,
    required_timing_policy: str | None = None,
) -> dict[str, Any]:
    """Verify that live input is the sealed output of ``prepare_anes_split``.

    A loose JSONL file is not sufficient for a paid experiment: the sibling
    runtime manifest and parent split seal must both hash the exact profile
    bytes, agree on the run identity and row count, and bind the declared
    election-eve cutoff.
    """
    profiles_source = resolve(profiles_path)
    manifest_path = profiles_source.parent / "manifest.json"
    split_seal_path = profiles_source.parent.parent / "split-seal.json"
    if not manifest_path.is_file() or not split_seal_path.is_file():
        raise ValueError(
            "live ANES profiles must have a sibling runtime manifest and parent split seal"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    split_seal = json.loads(split_seal_path.read_text(encoding="utf-8"))
    profiles_sha256 = _sha256_file(profiles_source)
    manifest_sha256 = _sha256_file(manifest_path)
    if manifest.get("runtime_profiles_sha256") != profiles_sha256:
        raise ValueError("runtime profile hash does not match its manifest")
    if split_seal.get("runtime_profiles_sha256") != profiles_sha256:
        raise ValueError("runtime profile hash does not match the split seal")
    if split_seal.get("runtime_manifest_sha256") != manifest_sha256:
        raise ValueError("runtime manifest hash does not match the split seal")
    sealed_digest = split_seal.get("seal_sha256")
    seal_payload = {key: value for key, value in split_seal.items() if key != "seal_sha256"}
    if sealed_digest != _canonical_json_sha256(seal_payload):
        raise ValueError("split seal checksum is invalid")
    if manifest.get("run_id") != split_seal.get("run_id"):
        raise ValueError("runtime manifest and split seal identify different preparation runs")
    if manifest.get("information_cutoff") != cutoff.isoformat():
        raise ValueError("runtime manifest cutoff does not match the live experiment cutoff")
    if required_timing_policy is not None:
        if manifest.get("profile_timing_policy") != required_timing_policy:
            raise ValueError(
                "runtime profile timing policy is not approved for this experiment: "
                f"expected {required_timing_policy!r}"
            )
        if not manifest.get("strict_pre_election_eligible"):
            raise ValueError("runtime profiles failed the strict pre-election timing audit")
        if manifest.get("post_election_profile_fields"):
            raise ValueError("runtime profiles contain post-election conditioning fields")
    profiles = _read_runtime_profiles(profiles_source)
    expected_n = int(manifest.get("n_profiles") or 0)
    if expected_n != len(profiles) or int(split_seal.get("n_profiles") or 0) != len(profiles):
        raise ValueError("runtime profile row count does not match the sealed preparation")
    profile_fields = list(manifest.get("profile_fields") or [])
    if not profile_fields or len(set(profile_fields)) != len(profile_fields):
        raise ValueError("runtime manifest has an invalid profile-field declaration")
    person_ids: set[str] = set()
    for row in profiles:
        person_id = str(row.get("synthetic_person_id") or "")
        if not person_id or person_id in person_ids:
            raise ValueError("runtime profiles require unique non-empty synthetic person IDs")
        person_ids.add(person_id)
        if row.get("information_cutoff") != cutoff.isoformat():
            raise ValueError("runtime profile has a cutoff inconsistent with its manifest")
        profile = row.get("profile")
        if not isinstance(profile, dict) or set(profile) != set(profile_fields):
            raise ValueError("runtime profile fields do not match the sealed manifest")
    return {
        "run_id": manifest["run_id"],
        "n_profiles": len(profiles),
        "profiles_sha256": profiles_sha256,
        "runtime_manifest": str(manifest_path),
        "runtime_manifest_sha256": manifest_sha256,
        "split_seal": str(split_seal_path),
        "split_seal_sha256": sealed_digest,
        "information_cutoff": cutoff.isoformat(),
        "profile_fields": profile_fields,
        "profile_timing_policy": manifest.get("profile_timing_policy", "unspecified"),
        "strict_pre_election_eligible": bool(manifest.get("strict_pre_election_eligible", False)),
    }


def _logit(probability: float) -> float:
    p = min(1 - 1e-9, max(1e-9, probability))
    return math.log(p / (1 - p))


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, value))))


def _mock_vote_probability(profile: dict[str, Any], noise: float) -> float:
    """Provider-free sanity model with residual heterogeneity; not a research baseline."""
    values = profile.get("profile", {})
    party = values.get("pid_x")
    ideology = values.get("libcpre_self")
    party_effect = {1: -2.6, 2: -1.8, 3: -0.8, 4: 0.0, 5: 0.8, 6: 1.8, 7: 2.6}
    ideology_effect = {1: -1.2, 2: -0.8, 3: -0.4, 4: 0.0, 5: 0.4, 6: 0.8, 7: 1.2}
    score = -0.15 + party_effect.get(party, 0.0) + ideology_effect.get(ideology, 0.0)
    return _sigmoid(score + noise)


def run_provider_free_society(
    profiles_path: str | Path,
    output_root: str | Path,
    *,
    seed: int,
    replications: int,
    max_agents: int,
    group_size: int,
    rounds: int,
) -> dict[str, Any]:
    """Exercise independent and society arms without a provider, tools, or network."""
    if min(replications, max_agents, group_size, rounds) < 1:
        raise ValueError("simulation dimensions must be positive")
    profiles = _read_runtime_profiles(profiles_path)
    output = resolve(output_root)
    output.mkdir(parents=True, exist_ok=True)
    predictions_path = output / "predictions.jsonl"
    transcript_path = output / "interaction_summaries.jsonl"
    predictions: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for replication in range(replications):
        rng = np.random.default_rng(seed + replication)
        sample_n = min(max_agents, len(profiles))
        # Draw respondents uniformly, then apply their survey weights once during scoring.
        # Probability-proportional sampling plus weighted scoring would double-weight cases.
        chosen = rng.choice(len(profiles), size=sample_n, replace=False)
        cohort = [profiles[int(index)] for index in chosen]
        initial = np.array(
            [_mock_vote_probability(row, float(rng.normal(0, 0.65))) for row in cohort]
        )
        for treatment in ("independent", "society"):
            current = initial.copy()
            if treatment == "society":
                ordering = rng.permutation(sample_n)
                groups = [
                    ordering[start : start + group_size] for start in range(0, sample_n, group_size)
                ]
                susceptibility = rng.uniform(0.15, 0.55, sample_n)
                for round_index in range(rounds):
                    public_stance = rng.binomial(1, current)
                    for group_index, group in enumerate(groups):
                        if len(group) < 2:
                            continue
                        peer_share = float(public_stance[group].mean())
                        before = float(current[group].mean())
                        for agent_index in group:
                            delta = susceptibility[agent_index] * (
                                peer_share - current[agent_index]
                            )
                            current[agent_index] = _sigmoid(
                                _logit(current[agent_index]) + 2.0 * delta
                            )
                        summaries.append(
                            {
                                "schema_version": 1,
                                "replication": replication,
                                "round": round_index + 1,
                                "group": group_index + 1,
                                "n_agents": len(group),
                                "public_romney_share": peer_share,
                                "mean_probability_before": before,
                                "mean_probability_after": float(current[group].mean()),
                            }
                        )
            for index, row in enumerate(cohort):
                predictions.append(
                    {
                        "schema_version": 1,
                        "engine": "provider_free_structural_mock",
                        "treatment": treatment,
                        "replication": replication,
                        "synthetic_person_id": row["synthetic_person_id"],
                        "population_weight": float(row.get("population_weight", 1.0)),
                        "predicted_probability": float(current[index]),
                    }
                )
    with predictions_path.open("w", encoding="utf-8") as handle:
        for row in predictions:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    with transcript_path.open("w", encoding="utf-8") as handle:
        for row in summaries:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    seal = {
        "schema_version": 1,
        "engine": "provider_free_structural_mock",
        "scientific_result": False,
        "network_access_required": False,
        "profiles_sha256": _sha256_file(resolve(profiles_path)),
        "predictions_sha256": _sha256_file(predictions_path),
        "interaction_summaries_sha256": _sha256_file(transcript_path),
        "seed": seed,
        "replications": replications,
        "max_agents": max_agents,
        "profile_sampling": "simple_random_without_replacement",
        "survey_weight_application": "evaluation_only",
        "group_size": group_size,
        "rounds": rounds,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path = output / "prediction-seal.json"
    seal_path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return {
        "predictions": str(predictions_path),
        "interaction_summaries": str(transcript_path),
        "prediction_seal": str(seal_path),
        "n_prediction_rows": len(predictions),
        "n_interaction_summaries": len(summaries),
    }


def _cohen_kappa(observed: np.ndarray, predicted: np.ndarray, weights: np.ndarray) -> float:
    agreement = float(np.average(observed == predicted, weights=weights))
    observed_rate = float(np.average(observed, weights=weights))
    predicted_rate = float(np.average(predicted, weights=weights))
    chance = observed_rate * predicted_rate + (1 - observed_rate) * (1 - predicted_rate)
    return (agreement - chance) / (1 - chance) if chance < 1 else 0.0


def _require_balanced_prediction_panel(predictions: pd.DataFrame) -> dict[str, Any]:
    """Fail closed unless every replication is an exact matched two-arm panel."""
    required = {
        "treatment",
        "replication",
        "synthetic_person_id",
        "predicted_probability",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError("prediction artifact is missing: " + ", ".join(sorted(missing)))
    if predictions.empty:
        raise ValueError("prediction artifact is empty")
    treatments = set(predictions["treatment"].astype(str))
    if treatments != {"independent", "society"}:
        raise ValueError("prediction artifact must contain exactly independent and society arms")
    duplicate_key = ["treatment", "replication", "synthetic_person_id"]
    if predictions.duplicated(duplicate_key).any():
        raise ValueError("prediction artifact contains duplicate treatment/profile rows")
    probabilities = pd.to_numeric(predictions["predicted_probability"], errors="coerce")
    if probabilities.isna().any() or not np.isfinite(probabilities).all():
        raise ValueError("predicted probabilities must be finite numbers")
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("predicted probabilities must be within [0, 1]")
    replications = sorted(int(value) for value in predictions["replication"].unique())
    if replications != list(range(len(replications))):
        raise ValueError("prediction replications must be contiguous and zero-based")
    coverage: list[dict[str, Any]] = []
    for replication in replications:
        group = predictions.loc[predictions["replication"] == replication]
        independent = group.loc[group["treatment"] == "independent"].copy()
        society = group.loc[group["treatment"] == "society"].copy()
        independent_ids = set(independent["synthetic_person_id"].astype(str))
        society_ids = set(society["synthetic_person_id"].astype(str))
        if independent_ids != society_ids or not independent_ids:
            raise ValueError(
                f"replication {replication} does not have exact matched profile coverage"
            )
        if "model_id" in predictions.columns:
            independent_models = independent.set_index("synthetic_person_id")["model_id"].astype(
                str
            )
            society_models = society.set_index("synthetic_person_id")["model_id"].astype(str)
            if independent_models.to_dict() != society_models.to_dict():
                raise ValueError(
                    f"replication {replication} changes model assignment between treatments"
                )
        coverage.append(
            {
                "replication": replication,
                "profiles_per_treatment": len(independent_ids),
                "profile_set_sha256": _canonical_json_sha256(sorted(independent_ids)),
            }
        )
    return {
        "balanced": True,
        "replications": len(replications),
        "coverage": coverage,
    }


def evaluate_vote_predictions(
    predictions_path: str | Path,
    targets_path: str | Path,
    output_path: str | Path,
    *,
    target_field: str = PAPER_STUDY_2_TARGET,
    democratic_code: int = 1,
    republican_code: int = 2,
) -> dict[str, Any]:
    """Open the evaluation vault only after verifying the prediction seal."""
    predictions_source = resolve(predictions_path)
    seal_path = predictions_source.parent / "prediction-seal.json"
    if not seal_path.is_file():
        raise ValueError("prediction artifact must be sealed before evaluation")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal_payload = {key: value for key, value in seal.items() if key != "seal_sha256"}
    if seal.get("seal_sha256") != _canonical_json_sha256(seal_payload):
        raise ValueError("prediction seal checksum is invalid")
    if seal.get("predictions_sha256") != _sha256_file(predictions_source):
        raise ValueError("prediction artifact changed after it was sealed")
    predictions = pd.read_json(predictions_source, lines=True)
    balanced_panel = _require_balanced_prediction_panel(predictions)
    engine = str(seal.get("engine", ""))
    if not engine or set(predictions["engine"].astype(str)) != {engine}:
        raise ValueError("prediction engine does not match sealed provenance")
    live = engine == "live_llm_no_tools_host"
    forbidden = {target_field, "ground_truth", "observed_vote", "outcome"}
    leaked = forbidden & set(predictions.columns)
    if leaked:
        raise ValueError("prediction artifact contains held-out columns: " + ", ".join(leaked))
    targets = pd.read_csv(resolve(targets_path))
    required_targets = {"synthetic_person_id", "population_weight", target_field}
    missing = required_targets - set(targets.columns)
    if missing:
        raise ValueError("evaluation target file is missing: " + ", ".join(sorted(missing)))
    merged = predictions.merge(
        targets,
        on="synthetic_person_id",
        how="left",
        validate="many_to_one",
        suffixes=("_prediction", "_target"),
    )
    raw_target = pd.to_numeric(merged[target_field], errors="coerce")
    mask = raw_target.isin([democratic_code, republican_code])
    merged = merged.loc[mask].copy()
    if merged.empty:
        raise ValueError("no valid two-party target observations are available")
    merged["observed_republican"] = (
        pd.to_numeric(merged[target_field], errors="raise") == republican_code
    ).astype(int)
    target_weights = pd.to_numeric(merged["population_weight_target"], errors="coerce")
    if target_weights.isna().any() or (target_weights <= 0).any():
        raise ValueError("evaluation-vault weights must contain finite positive values")
    merged["evaluation_weight"] = target_weights
    metrics = []
    for (treatment, replication), group in merged.groupby(["treatment", "replication"]):
        probability = group["predicted_probability"].to_numpy(dtype=float)
        observed = group["observed_republican"].to_numpy(dtype=int)
        predicted = (probability > 0.5).astype(int)
        weights = group["evaluation_weight"].to_numpy(dtype=float)
        metrics.append(
            {
                "treatment": str(treatment),
                "replication": int(replication),
                "n": len(group),
                "brier": float(np.average((probability - observed) ** 2, weights=weights)),
                "agreement": float(np.average(predicted == observed, weights=weights)),
                "cohen_kappa": _cohen_kappa(observed, predicted, weights),
                "predicted_republican_share": float(np.average(probability, weights=weights)),
                "observed_republican_share": float(np.average(observed, weights=weights)),
            }
        )
    metric_frame = pd.DataFrame(metrics)
    summary = []
    for treatment, group in metric_frame.groupby("treatment"):
        summary.append(
            {
                "treatment": str(treatment),
                "replications": len(group),
                "mean_brier": float(group["brier"].mean()),
                "mean_agreement": float(group["agreement"].mean()),
                "mean_cohen_kappa": float(group["cohen_kappa"].mean()),
                "mean_predicted_republican_share": float(
                    group["predicted_republican_share"].mean()
                ),
                "mean_observed_republican_share": float(group["observed_republican_share"].mean()),
            }
        )
    all_target_values = pd.to_numeric(targets[target_field], errors="coerce")
    valid_target_mask = all_target_values.isin([democratic_code, republican_code])
    valid_targets = targets.loc[valid_target_mask]
    all_target_weights = pd.to_numeric(valid_targets["population_weight"], errors="coerce")
    if all_target_weights.isna().any() or (all_target_weights <= 0).any():
        raise ValueError("evaluation-vault weights must contain finite positive values")
    full_observed = (
        pd.to_numeric(valid_targets[target_field], errors="raise") == republican_code
    ).astype(int)
    report = {
        "schema_version": 1,
        "scientific_result": False,
        "engine": engine,
        "execution_boundary": seal.get("execution_boundary", "provider-free structural run"),
        "warning": (
            "Live matched ANES pilot, not a powered scientific replication. Supplied context "
            "is cutoff-locked; modern model weights are not temporally isolated."
            if live else
            "Provider-free or injected-test validation only. It validates the split, treatments, "
            "sealing, and scoring path; it is not evidence of human-response fidelity."
        ),
        "target_field": target_field,
        "target_population_reference": {
            "n_valid_two_party": len(valid_targets),
            "weighted_observed_republican_share": float(
                np.average(full_observed, weights=all_target_weights)
            ),
            "weight_source": "evaluation_vault",
        },
        "prediction_seal_sha256": seal["seal_sha256"],
        "balanced_profile_coverage": balanced_panel,
        "per_replication": metrics,
        "summary": summary,
    }
    destination = resolve(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    evaluation_seal = {
        "schema_version": 1,
        "prediction_seal_sha256": _sha256_file(seal_path),
        "predictions_sha256": _sha256_file(predictions_source),
        "targets_sha256": _sha256_file(resolve(targets_path)),
        "evaluator_source_sha256": _sha256_file(Path(__file__)),
        "report_sha256": _sha256_file(destination),
        "target_field": target_field,
        "democratic_code": democratic_code,
        "republican_code": republican_code,
    }
    evaluation_seal["seal_sha256"] = _canonical_json_sha256(evaluation_seal)
    destination.with_suffix(".seal.json").write_text(
        json.dumps(evaluation_seal, indent=2) + "\n", encoding="utf-8"
    )
    return report


def evaluate_paper_study2_replication(
    source_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute the directly available 2012 Study 2 comparison from its public CSV."""
    frame = load_anes_frame(source_path)
    required = {"p_romney", "p_obama", PAPER_STUDY_2_TARGET}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Study 2 replication data is missing: " + ", ".join(sorted(missing)))
    probabilities = pd.to_numeric(frame["p_romney"], errors="coerce")
    valid_probability = probabilities.notna() & probabilities.between(0, 1)
    valid_vote = pd.to_numeric(frame[PAPER_STUDY_2_TARGET], errors="coerce").isin([1, 2])
    subset = frame.loc[valid_probability & valid_vote].copy()
    probability = pd.to_numeric(subset["p_romney"], errors="raise").to_numpy(dtype=float)
    observed = (pd.to_numeric(subset[PAPER_STUDY_2_TARGET]) == 2).to_numpy(dtype=int)
    predicted = (probability > 0.5).astype(int)
    weights = np.ones(len(subset))
    report = {
        "schema_version": 1,
        "source_sha256": _sha256_file(resolve(source_path)),
        "source": "Out of One, Many public Study2_Data/full_results_2012_2.csv",
        "n_all_rows": len(frame),
        "n_two_party_comparison": len(subset),
        "full_sample_mean_p_romney": float(probabilities.loc[valid_probability].mean()),
        "two_party_mean_p_romney": float(probability.mean()),
        "observed_two_party_romney_share": float(observed.mean()),
        "brier": float(np.mean((probability - observed) ** 2)),
        "agreement": float(np.mean(predicted == observed)),
        "cohen_kappa": _cohen_kappa(observed, predicted, weights),
        "threshold": "p_romney > 0.5",
        "weighting": "unweighted; public replication CSV does not contain ANES weights",
    }
    if output_path is not None:
        destination = resolve(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


_PARTY_LABELS = {
    1: "strong Democrat",
    2: "not very strong Democrat",
    3: "independent leaning Democratic",
    4: "independent",
    5: "independent leaning Republican",
    6: "not very strong Republican",
    7: "strong Republican",
}
_IDEOLOGY_LABELS = {
    1: "extremely liberal",
    2: "liberal",
    3: "slightly liberal",
    4: "moderate",
    5: "slightly conservative",
    6: "conservative",
    7: "extremely conservative",
}
_RACE_LABELS = {
    1: "White, non-Hispanic",
    2: "Black, non-Hispanic",
    3: "Asian or Pacific Islander, non-Hispanic",
    4: "Native American, non-Hispanic",
    5: "Hispanic",
    6: "other or multiple races, non-Hispanic",
}
_GENDER_LABELS = {1: "male", 2: "female"}
_YES_NO_LABELS = {1: "yes", 2: "no"}
_INTEREST_LABELS = {
    1: "very interested",
    2: "somewhat interested",
    3: "not very interested",
    4: "not at all interested",
}
_PATRIOTISM_LABELS = {
    1: "extremely good",
    2: "moderately good",
    3: "a little good",
    4: "neither good nor bad",
    5: "a little bad",
    6: "moderately bad",
    7: "extremely bad",
}


def render_anes_2012_profile(runtime_profile: dict[str, Any]) -> str:
    """Render the paper's ten-field 2012 backstory without inventing missing values."""
    values = runtime_profile.get("profile") or {}
    fragments: list[str] = []

    def add_label(field: str, template: str, mapping: dict[int, str]) -> None:
        raw = values.get(field)
        label = mapping.get(raw)
        if label:
            fragments.append(template.format(value=label))

    # Preserve the exact Study 2 conditioning-variable order reported in the paper.
    add_label("dem_raceeth_x", "I identify as {value}.", _RACE_LABELS)
    add_label("gender_respondent_x", "I am {value}.", _GENDER_LABELS)
    age = values.get("dem_age_r_x")
    if age is not None:
        fragments.append(f"I am {int(age)} years old.")
    add_label("libcpre_self", "Politically, I am {value}.", _IDEOLOGY_LABELS)
    add_label("pid_x", "My party identification is {value}.", _PARTY_LABELS)
    add_label(
        "paprofile_interestpolit",
        "I am {value} in politics.",
        _INTEREST_LABELS,
    )
    add_label("relig_church", "I attend religious services: {value}.", _YES_NO_LABELS)
    add_label(
        "discuss_disc",
        "I discuss politics with family or friends: {value}.",
        _YES_NO_LABELS,
    )
    add_label(
        "patriot_flag",
        "Seeing the American flag makes me feel {value}.",
        _PATRIOTISM_LABELS,
    )
    state = values.get("sample_stfips")
    if state is not None:
        fragments.append(f"My state FIPS code is {int(state):02d}.")
    return " ".join(fragments) or "No profile answers were available."


def load_cutoff_world(path: str | Path, cutoff: date) -> tuple[str, str]:
    """Load a small dated context pack and reject any document after the cutoff."""
    source = resolve(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError("world context must be an object containing a documents list")
    declared = date.fromisoformat(str(payload.get("cutoff_date")))
    if declared != cutoff:
        raise ValueError("world context cutoff does not match the requested experiment cutoff")
    lines = []
    for document in payload["documents"]:
        if not isinstance(document, dict):
            raise ValueError("world context documents must be objects")
        published = date.fromisoformat(str(document.get("published_at"))[:10])
        if published > cutoff:
            raise ValueError(f"world context contains post-cutoff document {document.get('id')}")
        text = " ".join(str(document.get("text") or "").split())[:1200]
        lines.append(
            f"[{document.get('id')}] {published.isoformat()} | "
            f"{document.get('title') or ''} | {text}"
        )
    return "\n".join(lines), _sha256_file(source)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    from psbx.agents.runner import FINAL_RE, ParseError

    try:
        payload = json.loads((raw or "").strip())
    except json.JSONDecodeError:
        match = FINAL_RE.search(raw or "")
        if not match:
            raise ParseError("model output contained no JSON object") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ParseError("model JSON must be an object")
    return payload


def _call_json_no_tools(
    model: Any,
    *,
    system: str,
    user: str,
    required_probability: bool,
    completion: Any,
) -> tuple[dict[str, Any], str, int]:
    from psbx.agents.runner import ParseError

    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    raw_chunks = []
    for attempt in range(1, 3):
        turn = completion(model, messages, system=system, tools=False)
        raw = str(turn.text or "")
        raw_chunks.append(raw)
        try:
            payload = _parse_llm_json(raw)
            if required_probability:
                probability = float(payload["probability_romney"])
                if not 0 <= probability <= 1:
                    raise ParseError("probability_romney must be in [0, 1]")
                payload["probability_romney"] = probability
            else:
                message = " ".join(str(payload["message"]).split())
                if not message:
                    raise ParseError("message cannot be empty")
                payload["message"] = " ".join(message.split()[:35])
            return payload, "\n---\n".join(raw_chunks), attempt
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, ParseError) as exc:
            if attempt == 2:
                error = ParseError(f"model JSON failed after retry: {exc}")
                error.raw_response = "\n---\n".join(raw_chunks)
                raise error from exc
            messages.extend(
                [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": f"Parse error: {exc}. Return only the required JSON object.",
                    },
                ]
            )
    raise ParseError("model produced no response")


def _append_jsonl_durable(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_call_checkpoints(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    completed: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return events, completed
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"call checkpoint is corrupt at line {line_number}; do not resume this run"
                ) from exc
            if not isinstance(event, dict) or not event.get("call_id"):
                raise ValueError(f"call checkpoint line {line_number} is invalid")
            events.append(event)
            if event.get("status") == "completed":
                prior = completed.get(str(event["call_id"]))
                if prior is not None and prior.get("result_sha256") != event.get("result_sha256"):
                    raise ValueError("call checkpoint contains conflicting completed results")
                completed[str(event["call_id"])] = event
    return events, completed


def _spend_ledger_snapshot(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "spend_ledger.json"
    if not path.is_file():
        return {
            "ledger_present": False,
            "reserved_requests": 0,
            "reserved_usd": 0.0,
            "reported_usage_entries": 0,
            "unreconciled_entries": 0,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = [row for row in (payload.get("entries") or []) if isinstance(row, dict)]
    return {
        "ledger_present": True,
        "reserved_requests": int(payload.get("reserved_requests") or len(entries)),
        "reserved_usd": float(payload.get("reserved_usd") or 0.0),
        "reported_usage_entries": sum(row.get("reported_usage") is not None for row in entries),
        "unreconciled_entries": sum(row.get("reported_usage") is None for row in entries),
    }


def _live_call_id(run_id: str, metadata: dict[str, Any]) -> str:
    return _canonical_json_sha256({"run_id": run_id, **metadata})[:32]


def _checkpointed_no_tools_call(
    model: Any,
    *,
    run_id: str,
    checkpoint_path: Path,
    completed_calls: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
    system: str,
    user: str,
    required_probability: bool,
    completion: Any,
) -> tuple[dict[str, Any], str, int, str, bool]:
    call_id = _live_call_id(run_id, metadata)
    cached = completed_calls.get(call_id)
    if cached is not None:
        return (
            dict(cached["parsed"]),
            str(cached.get("raw_response") or ""),
            int(cached.get("parse_attempts") or 1),
            call_id,
            True,
        )
    started_at = datetime.now(timezone.utc).isoformat()
    spend_before = _spend_ledger_snapshot(run_id)
    try:
        parsed, raw, attempts = _call_json_no_tools(
            model,
            system=system,
            user=user,
            required_probability=required_probability,
            completion=completion,
        )
    except Exception as exc:
        event = {
            "schema_version": 1,
            "call_id": call_id,
            **metadata,
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "raw_response": getattr(exc, "raw_response", None),
            "spend_before": spend_before,
            "spend_after": _spend_ledger_snapshot(run_id),
        }
        _append_jsonl_durable(checkpoint_path, event)
        raise
    event = {
        "schema_version": 1,
        "call_id": call_id,
        **metadata,
        "status": "completed",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "parsed": parsed,
        "raw_response": raw,
        "parse_attempts": attempts,
        "result_sha256": _canonical_json_sha256(parsed),
        "spend_before": spend_before,
        "spend_after": _spend_ledger_snapshot(run_id),
    }
    _append_jsonl_durable(checkpoint_path, event)
    completed_calls[call_id] = event
    return parsed, raw, attempts, call_id, False


def run_live_llm_vote_society(
    profiles_path: str | Path,
    output_root: str | Path,
    *,
    run_id: str,
    cutoff: date = date(2012, 11, 5),
    roster_path: str | Path = "config/swarm.yaml",
    world_context_path: str | Path | None = None,
    seed: int = 220906899,
    replications: int = 1,
    max_agents: int = 12,
    group_size: int = 12,
    rounds: int = 2,
    _completion: Any | None = None,
    _workers: list[Any] | None = None,
) -> dict[str, Any]:
    """Run matched independent and conversational LLM arms with private final ballots.

    Production calls are deliberately host-side and carry no tools. The result seal states that
    this is supplied-context isolation, not model-weight or full-process temporal isolation.
    Both arms receive the same number of calls: the independent control privately deliberates
    for the same number of rounds in which the society arm exchanges public peer messages.
    """
    run_id = validate_run_id(run_id)
    if replications < 1 or rounds < 1 or max_agents < 2 or group_size < 2:
        raise ValueError(
            "live society requires positive replications/rounds and at least two agents"
        )
    if os.environ.get("PSBX_MOCK_LLM") == "1" and _completion is None:
        raise RuntimeError("live ANES society refuses PSBX_MOCK_LLM=1")
    preparation = verify_prepared_runtime_profiles(
        profiles_path,
        cutoff=cutoff,
        required_timing_policy="strict_pre_election",
    )
    profiles = _read_runtime_profiles(profiles_path)
    from psbx.agents.runner import complete_turn, skip_reason
    from psbx.agents.swarm import load_roster, worker_models
    from psbx.spending import begin_spend_run, preflight_paid_requests

    workers = _workers or worker_models(load_roster(roster_path))
    sample_n = min(max_agents, len(profiles), len(workers))
    if sample_n < 2:
        raise ValueError("live society requires at least two profiles and callable workers")
    workers = workers[:sample_n]
    completion = _completion or complete_turn
    production = _completion is None
    world_context = "No external evidence was supplied in this arm."
    world_sha256 = None
    if world_context_path is not None:
        world_context, world_sha256 = load_cutoff_world(world_context_path, cutoff)
    system = (
        f"Today is {cutoff.isoformat()}. Role-play one de-identified 2012 survey respondent. "
        "Use only the supplied profile, dated context, and peer messages. Do not browse or call "
        "tools. Do not use events after today. Do not expose chain-of-thought. Peer messages are "
        "opinions, not facts. Your final ballot is private. Return only the requested JSON object."
    )
    output = resolve(output_root)
    output.mkdir(parents=True, exist_ok=True)
    worker_signature = [
        {
            "id": str(worker.id),
            "provider": str(getattr(worker, "provider", "injected")),
            "model_name": str(getattr(worker, "model_name", worker.id)),
            "temperature": getattr(worker, "temperature", None),
            "max_tokens": getattr(worker, "max_tokens", None),
            "json_output": bool(getattr(worker, "json_output", False)),
        }
        for worker in workers
    ]
    contract = {
        "schema_version": 1,
        "run_id": run_id,
        "protocol": "matched_private_deliberation_control_v1",
        "system_prompt_sha256": _canonical_json_sha256(system),
        "estimand": (
            "effect of anonymous peer-message exposure relative to equal-call private "
            "deliberation for the same sampled profiles and model assignments"
        ),
        "preparation": preparation,
        "world_context_sha256": world_sha256,
        "workers": worker_signature,
        "seed": seed,
        "replications": replications,
        "sample_n": sample_n,
        "group_size": group_size,
        "rounds": rounds,
        "cutoff": cutoff.isoformat(),
    }
    contract["contract_sha256"] = _canonical_json_sha256(contract)
    contract_path = output / "run-contract.json"
    if contract_path.is_file():
        existing_contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if existing_contract != contract:
            raise ValueError("run contract changed; resume requires an identical sealed design")
    else:
        _write_json_atomic(contract_path, contract)
    checkpoint_path = output / "call-checkpoints.jsonl"
    checkpoint_events, completed_calls = _read_call_checkpoints(checkpoint_path)
    preflight = None
    if production:
        calls_per_worker = replications * (rounds + 1) * 2 * 2
        for worker in workers:
            reason = skip_reason(worker)
            if reason:
                raise RuntimeError(f"{worker.id}: {reason}")
        preflight = preflight_paid_requests([(worker, calls_per_worker) for worker in workers])
        begin_spend_run(run_id)
    predictions_path = output / "predictions.jsonl"
    transcripts_path = output / "conversation.jsonl"
    predictions: list[dict[str, Any]] = []
    transcript_rows: list[dict[str, Any]] = []
    resumed_calls = 0
    for replication in range(replications):
        rng = np.random.default_rng(seed + replication)
        selected = rng.choice(len(profiles), size=sample_n, replace=False)
        cohort = [profiles[int(index)] for index in selected]
        rendered = [render_anes_2012_profile(row) for row in cohort]
        group_order = rng.permutation(sample_n)
        groups = [
            group_order[start : start + group_size] for start in range(0, sample_n, group_size)
        ]
        private_reflections: dict[int, list[str]] = {index: [] for index in range(sample_n)}
        for round_index in range(rounds):
            for index, (profile, model) in enumerate(zip(cohort, workers)):
                history_text = (
                    "\n".join(private_reflections[index])
                    or "No earlier private reflection is available."
                )
                user = (
                    f"Your profile:\n{rendered[index]}\n\nDated world context:\n"
                    f"{world_context}\n\nYour earlier private reflections:\n{history_text}\n\n"
                    "Privately reflect on your own election thinking. Do not imagine, infer, or "
                    "receive peer opinions. Return only "
                    '{"message": "at most 35 words"}.'
                )
                metadata = {
                    "replication": replication,
                    "treatment": "independent",
                    "stage": "private_deliberation",
                    "round": round_index + 1,
                    "synthetic_person_id": profile["synthetic_person_id"],
                    "model_id": model.id,
                }
                parsed, raw, attempts, call_id, cached = _checkpointed_no_tools_call(
                    model,
                    run_id=run_id,
                    checkpoint_path=checkpoint_path,
                    completed_calls=completed_calls,
                    metadata=metadata,
                    system=system,
                    user=user,
                    required_probability=False,
                    completion=completion,
                )
                resumed_calls += int(cached)
                private_reflections[index].append(f"Private reflection: {parsed['message']}")
                transcript_rows.append(
                    {
                        "schema_version": 1,
                        "treatment": "independent",
                        "visibility": "private_deliberation",
                        "replication": replication,
                        "round": round_index + 1,
                        "synthetic_person_id": profile["synthetic_person_id"],
                        "model_id": model.id,
                        "message": parsed["message"],
                        "parse_attempts": attempts,
                        "raw_response": raw,
                        "call_id": call_id,
                    }
                )
        for index, (profile, model) in enumerate(zip(cohort, workers)):
            history_text = "\n".join(private_reflections[index])
            user = (
                f"Your profile:\n{rendered[index]}\n\nDated world context:\n{world_context}\n\n"
                f"Your private deliberation:\n{history_text}\n\n"
                "Cast a private final estimate based only on your own profile and reflection. "
                "Estimate how likely you are to vote for Mitt Romney rather than Barack Obama. "
                'Return only {"probability_romney": <0-1>, "choice": "Romney|Obama|other"}.'
            )
            metadata = {
                "replication": replication,
                "treatment": "independent",
                "stage": "final_ballot",
                "round": rounds + 1,
                "synthetic_person_id": profile["synthetic_person_id"],
                "model_id": model.id,
            }
            parsed, raw, attempts, call_id, cached = _checkpointed_no_tools_call(
                model,
                run_id=run_id,
                checkpoint_path=checkpoint_path,
                completed_calls=completed_calls,
                metadata=metadata,
                system=system,
                user=user,
                required_probability=True,
                completion=completion,
            )
            resumed_calls += int(cached)
            predictions.append(
                {
                    "schema_version": 1,
                    "engine": "live_llm_no_tools_host" if production else "injected_test_llm",
                    "treatment": "independent",
                    "replication": replication,
                    "synthetic_person_id": profile["synthetic_person_id"],
                    "population_weight": float(profile.get("population_weight", 1.0)),
                    "model_id": model.id,
                    "predicted_probability": parsed["probability_romney"],
                    "choice": str(parsed.get("choice") or ""),
                    "parse_attempts": attempts,
                    "raw_response": raw,
                    "call_id": call_id,
                }
            )
        conversations: dict[int, list[str]] = {index: [] for index in range(sample_n)}
        for round_index in range(rounds):
            prior = {index: list(messages) for index, messages in conversations.items()}
            for group in groups:
                group_history = [message for index in group for message in prior[int(index)]]
                history_text = "\n".join(group_history) or "No peer messages yet."
                for index_value in group:
                    index = int(index_value)
                    model = workers[index]
                    user = (
                        f"Your profile:\n{rendered[index]}\n\nDated world context:\n"
                        f"{world_context}\n\nPrior-round anonymous peer messages:\n"
                        f"{history_text}\n\n"
                        "Contribute one short public message about your current election thinking. "
                        'Return only {"message": "at most 35 words"}.'
                    )
                    metadata = {
                        "replication": replication,
                        "treatment": "society",
                        "stage": "public_deliberation",
                        "round": round_index + 1,
                        "synthetic_person_id": cohort[index]["synthetic_person_id"],
                        "model_id": model.id,
                    }
                    parsed, raw, attempts, call_id, cached = _checkpointed_no_tools_call(
                        model,
                        run_id=run_id,
                        checkpoint_path=checkpoint_path,
                        completed_calls=completed_calls,
                        metadata=metadata,
                        system=system,
                        user=user,
                        required_probability=False,
                        completion=completion,
                    )
                    resumed_calls += int(cached)
                    message = f"Anonymous peer: {parsed['message']}"
                    conversations[index].append(message)
                    transcript_rows.append(
                        {
                            "schema_version": 1,
                            "treatment": "society",
                            "visibility": "public_peer_message",
                            "replication": replication,
                            "round": round_index + 1,
                            "synthetic_person_id": cohort[index]["synthetic_person_id"],
                            "model_id": model.id,
                            "message": parsed["message"],
                            "parse_attempts": attempts,
                            "raw_response": raw,
                            "call_id": call_id,
                        }
                    )
        for group in groups:
            group_history = [message for index in group for message in conversations[int(index)]]
            history_text = "\n".join(group_history) or "No peer messages were produced."
            for index_value in group:
                index = int(index_value)
                profile = cohort[index]
                model = workers[index]
                user = (
                    f"Your profile:\n{rendered[index]}\n\nDated world context:\n{world_context}\n\n"
                    f"Anonymous group discussion:\n{history_text}\n\n"
                    "Now cast a private final estimate. Do not merely copy a majority. Estimate "
                    "how likely you are to vote for Mitt Romney rather than Barack Obama. Return "
                    'only {"probability_romney": <0-1>, "choice": "Romney|Obama|other"}.'
                )
                metadata = {
                    "replication": replication,
                    "treatment": "society",
                    "stage": "final_ballot",
                    "round": rounds + 1,
                    "synthetic_person_id": profile["synthetic_person_id"],
                    "model_id": model.id,
                }
                parsed, raw, attempts, call_id, cached = _checkpointed_no_tools_call(
                    model,
                    run_id=run_id,
                    checkpoint_path=checkpoint_path,
                    completed_calls=completed_calls,
                    metadata=metadata,
                    system=system,
                    user=user,
                    required_probability=True,
                    completion=completion,
                )
                resumed_calls += int(cached)
                predictions.append(
                    {
                        "schema_version": 1,
                        "engine": ("live_llm_no_tools_host" if production else "injected_test_llm"),
                        "treatment": "society",
                        "replication": replication,
                        "synthetic_person_id": profile["synthetic_person_id"],
                        "population_weight": float(profile.get("population_weight", 1.0)),
                        "model_id": model.id,
                        "predicted_probability": parsed["probability_romney"],
                        "choice": str(parsed.get("choice") or ""),
                        "parse_attempts": attempts,
                        "raw_response": raw,
                        "call_id": call_id,
                    }
                )
    expected_predictions = replications * sample_n * 2
    expected_transcripts = replications * sample_n * rounds * 2
    if len(predictions) != expected_predictions or len(transcript_rows) != expected_transcripts:
        raise RuntimeError("live run completed with incomplete treatment coverage")
    balanced_panel = _require_balanced_prediction_panel(pd.DataFrame(predictions))
    _write_jsonl_atomic(predictions_path, predictions)
    _write_jsonl_atomic(transcripts_path, transcript_rows)
    all_checkpoint_events, completed_calls = _read_call_checkpoints(checkpoint_path)
    seal = {
        "schema_version": 1,
        "run_id": run_id,
        "engine": "live_llm_no_tools_host" if production else "injected_test_llm",
        "execution_boundary": "host_provider_calls; tools disabled; supplied context cutoff-locked",
        "full_process_container_isolation": False,
        "model_weight_temporal_isolation": False,
        "protocol": contract["protocol"],
        "estimand": contract["estimand"],
        "run_contract_sha256": contract["contract_sha256"],
        "prepared_runtime_verification": preparation,
        "profiles_sha256": _sha256_file(resolve(profiles_path)),
        "world_context_sha256": world_sha256,
        "predictions_sha256": _sha256_file(predictions_path),
        "conversation_sha256": _sha256_file(transcripts_path),
        "call_checkpoints_sha256": _sha256_file(checkpoint_path),
        "checkpoint_event_count": len(all_checkpoint_events),
        "completed_logical_calls": len(completed_calls),
        "resumed_logical_calls": resumed_calls,
        "spend_reconciliation": _spend_ledger_snapshot(run_id),
        "balanced_profile_coverage": balanced_panel,
        "workers": [worker.id for worker in workers],
        "seed": seed,
        "replications": replications,
        "profile_sampling": "simple_random_without_replacement",
        "survey_weight_application": "evaluation_only",
        "rounds": rounds,
        "preflight": preflight,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }
    seal["seal_sha256"] = _canonical_json_sha256(seal)
    seal_path = output / "prediction-seal.json"
    _write_json_atomic(seal_path, seal)
    return {
        "predictions": str(predictions_path),
        "conversation": str(transcripts_path),
        "prediction_seal": str(seal_path),
        "n_prediction_rows": len(predictions),
        "n_conversation_rows": len(transcript_rows),
        "call_checkpoints": str(checkpoint_path),
        "run_contract": str(contract_path),
        "resumed_logical_calls": resumed_calls,
        "balanced_profile_coverage": balanced_panel,
        "preflight": preflight,
    }


def sandbox_doctor() -> dict[str, Any]:
    docker = shutil.which("docker")
    daemon = False
    daemon_error = "docker executable not found"
    if docker:
        result = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        daemon = result.returncode == 0
        daemon_error = "" if daemon else (result.stderr.strip() or result.stdout.strip())
    return {
        "schema_version": 1,
        "docker_binary": docker,
        "docker_daemon_available": daemon,
        "docker_error": daemon_error,
        "existing_container_mode_scope": "frozen_retrieval_sidecar_only",
        "existing_llm_execution_location": "host",
        "existing_full_swarm_isolation": False,
        "provider_free_sealed_mode_supported": True,
        "hosted_model_weight_temporal_isolation_supported": False,
        "enforceable_claim": (
            "Models can be denied tools and supplied only cutoff-safe context. A modern hosted "
            "model cannot be made to forget post-2012 information in its weights."
        ),
    }


def sealed_container_command(
    profiles_path: str | Path,
    output_root: str | Path,
    *,
    image: str = "psbx-anes-society:local",
    seed: int = 220906899,
    replications: int = 5,
    max_agents: int = 120,
    group_size: int = 12,
    rounds: int = 3,
) -> list[str]:
    """Return a no-network, read-only-root Docker command with no evaluation-vault mount."""
    profiles = resolve(profiles_path).resolve()
    output = resolve(output_root).resolve()
    vault = resolve("data/evaluation-vault").resolve()
    if profiles == vault or profiles.is_relative_to(vault):
        raise ValueError("evaluation-vault files must never be mounted into the runtime container")
    output.mkdir(parents=True, exist_ok=True)
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "256",
        "--memory",
        "4g",
        "--cpus",
        "2",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--volume",
        f"{profiles}:/input/profiles.jsonl:ro",
        "--volume",
        f"{output}:/output:rw",
        image,
        "psbx",
        "experiment",
        "anes-simulate",
        "--profiles",
        "/input/profiles.jsonl",
        "--output",
        "/output",
        "--seed",
        str(seed),
        "--replications",
        str(replications),
        "--max-agents",
        str(max_agents),
        "--group-size",
        str(group_size),
        "--rounds",
        str(rounds),
    ]
