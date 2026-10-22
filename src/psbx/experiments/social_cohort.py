"""Strict DEBATE admission and development-only ordinal baseline preparation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from psbx.experiments import social_benchmark
from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import dump
from psbx.experiments.social_benchmark import parse_group

ALPHAS = (0.0, 1.0, 4.0, 16.0, 64.0)
DEV = {"known_inspected_development", "additional_development_candidate"}
RUN_ID = "debate-social-comparison-20261022"


def rps(probabilities, score):
    return float(np.mean((np.cumsum(probabilities)[:5] - (np.arange(1, 6) >= score)) ** 2))


def transition(rows, alpha):
    # One total uniform pseudo-observation plus alpha persistence pseudo-observations.
    counts = np.full((6, 6), 1 / 6) + alpha * np.eye(6)
    for row in rows:
        counts[row["initial_score"] - 1, row["final_score"] - 1] += 1
    return counts / counts.sum(axis=1, keepdims=True)


def tune(rows):
    groups = sorted({r["group_id"] for r in rows})
    losses = {}
    for alpha in ALPHAS:
        scores = []
        for group in groups:
            model = transition([r for r in rows if r["group_id"] != group], alpha)
            scores.append(
                np.mean(
                    [
                        rps(model[r["initial_score"] - 1], r["final_score"])
                        for r in rows
                        if r["group_id"] == group
                    ]
                )
            )
        losses[alpha] = float(np.mean(scores))
    chosen = min(ALPHAS, key=lambda a: (losses[a], a))
    return chosen, losses


def fit_baseline(development):
    """Only development observations accepted; confirmation labels are not an argument."""
    groups = sorted({r["group_id"] for r in development})
    if len(groups) < 3:
        raise ValueError("At least three development groups required")
    outer = []
    for group in groups:
        train = [r for r in development if r["group_id"] != group]
        alpha, _ = tune(train)
        model = transition(train, alpha)
        held = [r for r in development if r["group_id"] == group]
        outer.append(
            dict(
                group_id=group,
                alpha=alpha,
                transition_rps=float(
                    np.mean([rps(model[r["initial_score"] - 1], r["final_score"]) for r in held])
                ),
                persistence_rps=float(
                    np.mean(
                        [rps(np.eye(6)[r["initial_score"] - 1], r["final_score"]) for r in held]
                    )
                ),
            )
        )
    losses = {
        name: float(np.mean([r[name + "_rps"] for r in outer]))
        for name in ("transition", "persistence")
    }
    chosen = min(("persistence", "transition"), key=lambda name: losses[name])
    alpha, tuning = tune(development)
    return dict(
        selected_baseline=chosen,
        alpha=alpha,
        alpha_grid=list(ALPHAS),
        prior=(
            "1 total uniform pseudo-observation + alpha diagonal "
            "pseudo-observations per initial category"
        ),
        development_groups=groups,
        development_people=len(development),
        nested_leave_group_out_scores=losses,
        outer_folds=outer,
        full_development_tuning_scores=tuning,
        transition_matrix=transition(development, alpha).tolist(),
    )


def predict(fit, cases, baseline=None):
    selected = baseline or fit["selected_baseline"]
    matrix = np.eye(6) if selected == "persistence" else np.asarray(fit["transition_matrix"])
    return [
        dict(
            agent_id=c["profile"]["agent_id"],
            probabilities=matrix[c["profile"]["initial_score"] - 1].tolist(),
        )
        for c in cases
    ]


def prepare(repo: Path, root: Path):
    if (root / "cohort-manifest.json").exists():
        raise FileExistsError("Cohort exists; do not overwrite frozen preparation")
    audit_dir = repo / "reports/behavior-feasibility-20261022/debate"
    split_path = audit_dir / "split-proposal.frozen-before-admission.json"
    audit_path = audit_dir / "participant-admission.json"
    split = json.loads(split_path.read_text())
    audit = json.loads(audit_path.read_text())
    if _sha256_file(split_path) != audit["proposal_sha256"]:
        raise ValueError("Frozen split does not match admission audit")
    if audit["repeated_participant_identifiers"] or audit["cross_development_reserve_components"]:
        raise ValueError("Participant overlap requires new design")
    lookup = {r["group_id"]: r for r in split["groups"]}
    prior = {
        json.loads(p.read_text())["path"]: p.with_name(p.name.replace(".source.json", ".csv"))
        for p in (repo / "data/corpus-cache/debate-20261014").glob("*.source.json")
    }
    cases, targets, development, included, excluded, bindings = [], [], [], [], [], {}
    bindings[str(split_path)] = _sha256_file(split_path)
    bindings[str(audit_path)] = _sha256_file(audit_path)
    bindings[str(audit_dir / "LICENSE")] = _sha256_file(audit_dir / "LICENSE")
    bindings[str(Path(__file__).resolve())] = _sha256_file(Path(__file__))
    bindings[str(Path(social_benchmark.__file__).resolve())] = _sha256_file(
        Path(social_benchmark.__file__)
    )
    for meta in audit["groups"]:
        if meta["assignment"] not in DEV | {"confirmation_topic_candidate"}:
            continue
        original = lookup[meta["group_id"]]
        if original["assignment"] != meta["assignment"] or original["path"] != meta["path"]:
            raise ValueError("Admission assignment changed")
        if not meta["admissible_presence"]:
            excluded.append(
                dict(
                    group_id=meta["group_id"],
                    assignment=meta["assignment"],
                    reasons=[k for k, v in meta["presence_flags"].items() if not v],
                    replacement=None,
                )
            )
            continue
        source = prior.get(meta["path"], audit_dir / "raw-cache" / (meta["group_id"] + ".csv"))
        digest = _sha256_file(source)
        if digest != meta["source_sha256"]:
            raise ValueError("Source checksum changed")
        bindings[str(source)] = digest
        with source.open(encoding="utf-8-sig", newline="") as handle:
            group, labels = parse_group(
                list(csv.DictReader(handle)), meta["topic"], meta["group_id"]
            )
        included.append(
            dict(
                group_id=meta["group_id"],
                assignment=meta["assignment"],
                topic=meta["topic"],
                source_path=meta["path"],
                source_sha256=digest,
            )
        )
        if meta["assignment"] in DEV:
            for case, label in zip(group, labels):
                development.append(
                    dict(
                        group_id=case["group_id"],
                        agent_id=case["profile"]["agent_id"],
                        initial_score=case["profile"]["initial_score"],
                        final_score=label["final_score"],
                    )
                )
        else:
            cases.extend(group)
            targets.extend(labels)
    if len(development) != 188 or len(cases) != 116:
        raise ValueError("Expected strict 47 development and 29 confirmation groups")
    dev_topics = {r["topic"] for r in included if r["assignment"] in DEV}
    confirm_topics = {
        r["topic"] for r in included if r["assignment"] == "confirmation_topic_candidate"
    }
    if dev_topics & confirm_topics:
        raise ValueError("Development/confirmation topic overlap")
    fit = fit_baseline(development)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    vault = repo / "data/evaluation-vault" / root.name
    vault.mkdir(parents=True, exist_ok=True)
    vault.chmod(0o700)
    artifacts = {
        "cases.json": cases,
        "forecast-cases.json": [
            {"group_id": c["group_id"], "profile": c["profile"]} for c in cases
        ],
        "development-baseline-data.json": development,
        "baseline-fit.json": fit,
        "baseline-predictions.json": predict(fit, cases),
        "transition-predictions.json": predict(fit, cases, "transition"),
        "persistence-predictions.json": predict(fit, cases, "persistence"),
    }
    for name, value in artifacts.items():
        dump(root / name, value)
        (root / name).chmod(0o600)
    dump(vault / "targets.json", targets)
    (vault / "targets.json").chmod(0o600)
    manifest = dict(
        schema="debate-social-cohort-v1",
        run_id=root.name,
        source_revision=split["revision"],
        groups=29,
        people=116,
        development_groups=47,
        development_confirmation_topics_disjoint=True,
        included=included,
        excluded=excluded,
        no_replacements=True,
        parser="Unchanged social_benchmark.parse_group; last numeric post per event_order",
        source_bindings=bindings,
        artifact_hashes={name: _sha256_file(root / name) for name in artifacts},
        targets_path=str(vault / "targets.json"),
        targets_sha256=_sha256_file(vault / "targets.json"),
        selected_baseline=fit["selected_baseline"],
        exposure={
            "preparation": (
                "Automated parser reads source including labels and conversation; "
                "confirmation values/text not emitted to developer model. "
                "Development numeric outcomes fit baseline."
            ),
            "forecast": (
                "Initial own score and explanation plus recorded partner schedule; "
                "no final ratings or human future messages."
            ),
            "replay": (
                "Actual incoming human messages; conditional post-start "
                "diagnostic, not prospective forecast."
            ),
            "cases_file": (
                "Contains real_incoming for replay; runner must restrict use to replay arm."
            ),
        },
        caveats=[
            (
                "Recorded randomized partner schedule is conditioned on, not a "
                "predicted social network; availability at a true forecast cutoff "
                "unverified."
            ),
            (
                "Source pseudonym equality-disjointness does not establish "
                "distinct humans if identifiers are regenerated."
            ),
            (
                "Public data model pretraining exposure and unknown prior "
                "inspection cannot be ruled out."
            ),
            (
                "Golden complete-session selection limits generalization; project "
                "topic split is not official source split."
            ),
            "Research-only DEBATE terms apply to derivatives; 29 topics provide limited power.",
            (
                "Nested leave-group CV tunes shrinkage without held-out group "
                "labels; final selection/fitting use development only."
            ),
        ],
    )
    dump(root / "cohort-manifest.json", manifest)
    return {
        k: manifest[k]
        for k in ("groups", "people", "development_groups", "selected_baseline", "excluded")
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.resolve()
    print(json.dumps(prepare(repo, repo / "data/runs" / RUN_ID), indent=2))
