"""Audited observed ANES profiles, without invented life histories or evaluation answers."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from psbx.experiments.anes_society import (
    ANES_2012_PROFILE_TIMING,
    STRICT_PRE_ELECTION_PROFILE_FIELDS,
    _canonical_json_sha256,
    _pseudonymous_id,
    _sha256_file,
    load_anes_frame,
)
from psbx.paths import resolve

SPARSE = list(STRICT_PRE_ELECTION_PROFILE_FIELDS)
EXTRA = [
    "dem_edugroup_x",
    "finance_finpast",
    "finance_finnext",
    "health_insured",
    "econ_ecnow",
    "econ_ecpast",
    "econ_ecnext",
    "medsrc_campsrcs_tvnews",
    "medsrc_campsrcs_newsp",
    "medsrc_campsrcs_inet",
    "medsrc_campsrcs_radio",
    "medsrc_socmedia",
]
TARGETS = {
    "vote": {
        "field": "presvote2012_x",
        "codes": [1, 2, 5],
        "options": ["Barack Obama", "Mitt Romney", "Other"],
        "task": "Reported 2012 presidential vote among those reporting a vote",
    },
    "health_law": {
        "field": "health_2010hcr",
        "codes": [1, 2, 3],
        "options": ["Favor", "Oppose", "Neither favor nor oppose"],
        "task": "Pre-election opinion of the 2010 health care law",
    },
    "gun_policy": {
        "field": "gun_control",
        "codes": [1, 2, 3],
        "options": ["More difficult", "Easier", "Keep rules about the same"],
        "task": "Pre-election opinion: should federal government make buying a gun "
        "more difficult, easier, or keep rules about the same?",
    },
}
DATE_FIELDS = ["admin_pre_ftf_iwdatefin", "admin_pre_web1_iwdatefin", "admin_pre_web2_iwdatefin"]


def write_private(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    path.chmod(0o600)


def dump(path: Path, value):
    write_private(path, json.dumps(value, indent=2, default=str) + "\n")


def seal(payload):
    return {**payload, "seal_sha256": _canonical_json_sha256(payload)}


def check_seal(payload):
    if payload.get("seal_sha256") != _canonical_json_sha256(
        {k: v for k, v in payload.items() if k != "seal_sha256"}
    ):
        raise ValueError("Seal checksum mismatch")


def load_pack(path: Path):
    pack = json.loads(path.read_text())
    cutoff = date.fromisoformat(pack["cutoff"])
    for doc in pack["documents"]:
        if date.fromisoformat(doc["published_at"]) > cutoff:
            raise ValueError("Evidence published after cutoff")
        if not all(doc.get(k) for k in ["url", "verified_excerpt", "date_evidence", "provenance"]):
            raise ValueError("Evidence missing provenance")
        if doc.get("source_snapshot"):
            if _sha256_file(resolve(doc["source_snapshot"])) != doc["source_snapshot_sha256"]:
                raise ValueError("Evidence source snapshot changed")
    return pack


def profile_text(profile, rich=False):
    fields = SPARSE + (EXTRA if rich else [])
    return "\n".join(
        f"{profile['observed'][f]['label']}: {profile['observed'][f]['answer']}" for f in fields
    )


def prepare_profiles(root: Path, source: Path, pack_path: Path):
    destination = root / "profiles.jsonl"
    manifest_path = root / "profile-seal.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        check_seal(manifest)
        if manifest["profiles_sha256"] != _sha256_file(destination):
            raise ValueError("Profile bytes changed")
        return manifest
    reader = pd.io.stata.StataReader(source)
    labels = reader.variable_labels()
    value_labels = reader.value_labels()
    mappings = {
        field: value_labels.get(reader._lbllist[reader._varlist.index(field)], {})
        for field in SPARSE + EXTRA
    }
    fields = SPARSE + EXTRA
    if set(fields) & {item["field"] for item in TARGETS.values()}:
        raise ValueError("Target is present in runtime feature allowlist")
    for field in fields:
        if not labels[field].startswith("PRE:") and not ANES_2012_PROFILE_TIMING.get(field, {}).get(
            "strict_allowed"
        ):
            raise ValueError(f"Field lacks audited pre-election timing: {field}")
    pack = load_pack(pack_path)
    frame = load_anes_frame(source)
    vault = resolve("data/evaluation-vault") / root.name
    vault.mkdir(parents=True, exist_ok=True)
    vault.chmod(0o700)
    runtime, targets = [], []
    for _, row in frame.iterrows():
        observed = {}
        for field in fields:
            value = row[field]
            missing = pd.isna(value) or float(value) < 0
            answer = (
                "Not observed; do not invent an answer."
                if missing
                else re.sub(r"^-?\d+\.\s*", "", str(mappings[field].get(value, value)))
            )
            observed[field] = {
                "label": labels[field],
                "answer": answer,
                "code": None if missing else float(value),
                "status": "missing" if missing else "observed_pre_election",
            }
        dates = []
        for field in DATE_FIELDS:
            value = pd.to_numeric(row[field], errors="coerce")
            if pd.notna(value) and value > 0:
                dates.append(pd.to_datetime(str(int(value)), format="%Y%m%d").date().isoformat())
        person = _pseudonymous_id(row["caseid"])
        runtime.append(
            {
                "synthetic_person_id": person,
                "state_fips": int(row["sample_stfips"]),
                "weight": float(row["weight_full"]),
                "observed": observed,
                "baseline_date": max(dates) if dates else None,
                "exposure": {
                    "historically_available_document_ids": [d["id"] for d in pack["documents"]],
                    "actual_exposure": "unknown",
                    "belief_or_recall": "unknown",
                },
                "uncertainty": "Missing answers, news exposure, social ties, and influence "
                "susceptibility are unobserved; do not infer a factual biography.",
            }
        )
        targets.append(
            {
                "synthetic_person_id": person,
                "weight": float(row["weight_full"]),
                **{key: float(row[item["field"]]) for key, item in TARGETS.items()},
            }
        )
    write_private(destination, "".join(json.dumps(r) + "\n" for r in runtime))
    target_path = vault / "targets.json"
    dump(target_path, targets)
    audit = {
        "source_sha256": _sha256_file(source),
        "fields": {
            f: {
                "label": labels[f],
                "values": {int(k): v for k, v in mappings[f].items()},
                "timing": "pre-election; existing audit or official variable label",
            }
            for f in fields
        },
        "target_fields_excluded": [t["field"] for t in TARGETS.values()],
        "target_tasks": TARGETS,
        "scope": "Observed pre-election profile reconstruction. Health/gun evaluation is "
        "held-out pre-election item imputation, not longitudinal forecasting.",
    }
    dump(root / "field-audit.json", audit)
    manifest = seal(
        {
            "n_profiles": len(runtime),
            "source_sha256": _sha256_file(source),
            "profiles_sha256": _sha256_file(destination),
            "audit_sha256": _sha256_file(root / "field-audit.json"),
            "targets_path": str(target_path),
            "targets_sha256": _sha256_file(target_path),
            "pack_sha256": _sha256_file(pack_path),
        }
    )
    dump(manifest_path, manifest)
    return manifest


def previously_prompted(runs: Path):
    seen = set()
    for path in runs.glob("**/call-checkpoints.jsonl"):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("synthetic_person_id"):
                seen.add(row["synthetic_person_id"])
    return seen


def choose_cohort(rows, seen, state, n, seed, pack_cutoff):
    eligible = [
        row
        for row in rows
        if row["state_fips"] == state
        and row["synthetic_person_id"] not in seen
        and row["baseline_date"]
        and pack_cutoff <= row["baseline_date"] <= "2012-11-05"
    ]
    if len(eligible) < n:
        raise ValueError("Not enough previously unprompted, dated pre-election respondents")
    rng = np.random.default_rng(seed)
    return [eligible[int(i)] for i in rng.choice(len(eligible), size=n, replace=False)]
