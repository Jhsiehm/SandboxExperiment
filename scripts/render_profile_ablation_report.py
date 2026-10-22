"""Render completed, audited profile ablation results; never creates provisional results."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from psbx.experiments.anes_society import _sha256_file
from psbx.experiments.decision_profiles import check_seal
from psbx.experiments.profile_ablation import RUN, read, verify
from psbx.experiments.profile_ablation_worker import ARMS
from psbx.paths import resolve


def interval(value):
    return f"[{value[0]:+.5f}, {value[1]:+.5f}]"


def render(evaluation, diagnostics, audit, ledger, config, run_name):
    rows = evaluation["metrics"]
    variants = ["direct", "hybrid", "party", "prevalence"]
    cost = sum(
        (e.get("reported_usage") or {}).get("provider_cost_usd", 0) or 0 for e in ledger["entries"]
    )
    unresolved = sum(e.get("reported_usage") is None for e in ledger["entries"])
    lines = [
        "# ANES 2012 profile ablation development results",
        "",
        f"Run: `{run_name}`.",
        "",
        f"Completed {audit['checkpoints']} forecasts for {audit['people']} previously inspected "
        f"development respondents across four profile arms and {config['repetitions']} repeats. "
        "This is development evidence, not fresh external validation. No automatic promotion "
        "was performed. The 50-person reserve remained excluded.",
        "",
        "## Individual prediction",
        "",
        "Lower weighted half-multiclass Brier is better. Macro scores equally average the three "
        "tasks. Direct predictions average the two probability vectors before scoring; "
        "this differs "
        "from the previous experiment's mean of repetition-level losses.",
        "",
        "| Profile | Direct | Hybrid | Party baseline | Prevalence baseline |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        scores = [
            np.mean(
                [
                    r["weighted"]["brier"]
                    for r in rows
                    if r["arm"] == arm and r["variant"] == variant
                ]
            )
            for variant in variants
        ]
        lines.append("| " + arm + " | " + " | ".join(f"{s:.5f}" for s in scores) + " |")
    lines += [
        "",
        "Party and hybrid predictions use five outer respondent folds and four inner "
        "folds. Each scored respondent's outcomes were excluded from their model fitting and "
        "parameter selection. The party baseline is repeated by profile for comparison; it uses "
        "the same party observations in every arm.",
        "",
        "## Profile contrasts",
        "",
        "Negative differences favor the second arm. These paired respondent bootstrap intervals "
        "condition on this development sample and model setup.",
        "",
        "| Before → after | Macro Brier difference | 95% interval |",
        "|---|---:|---:|",
    ]
    for row in evaluation["contrasts"]:
        lines.append(
            f"| {row['before']} → {row['after']} | "
            f"{row['macro_brier_delta']:+.5f} | "
            f"{interval(row['conditional_person_bootstrap95'])} |"
        )
    lines += [
        "",
        "The rich-to-reduced contrast tests removal of existing fields; "
        "the reduced-to-augmented contrast tests addition of four measured fields. "
        "The sparse original profile provides an additional reference.",
        "",
        "## Calibrated comparisons",
        "",
        "Negative differences favor the hybrid. Intervals resample people while holding the "
        "already fitted out-of-fold predictions fixed. They do not include calibration-refitting "
        "uncertainty and are exploratory multiple comparisons.",
        "",
        "| Profile | Reference | Hybrid minus reference | Conditional 95% interval |",
        "|---|---|---:|---:|",
    ]
    for row in diagnostics["conditional_hybrid_contrasts"]:
        lines.append(
            f"| {row['arm']} | {row['before']} | {row['macro_brier_delta']:+.5f} | "
            f"{interval(row['conditional_person_bootstrap95'])} |"
        )
    lines += [
        "",
        "## Population and cross-attitude diagnostics",
        "",
        "Share MAE is the mean absolute difference between predicted and observed category shares, "
        "equally averaged across tasks. Modal-pair TV compares observed response-pair frequencies "
        "with pairs of predicted most-likely answers, equally averaged across task pairs. "
        "The latter is a descriptive assignment proxy, **not a joint predictive distribution**.",
        "",
        "| Profile | Variant | Share MAE (percentage points) | Modal-pair TV |",
        "|---|---|---:|---:|",
    ]
    for arm in ARMS:
        for variant in variants:
            shares = [
                r["weighted_share_mae"]
                for r in diagnostics["answer_share_mae"]
                if r["arm"] == arm and r["variant"] == variant
            ]
            pairs = [
                r["weighted"]["modal_pair_table_total_variation"]
                for r in diagnostics["modal_response_pair_proxies"]
                if r["arm"] == arm and r["variant"] == variant
            ]
            lines.append(
                f"| {arm} | {variant} | {100 * np.mean(shares):.3f} | {np.mean(pairs):.5f} |"
            )
    lines += [
        "",
        "The machine-readable diagnostics also include observed and predicted "
        "Cramér’s V, full pair tables and unweighted counterparts. Undefined association for "
        "constant modal predictions is retained as missing. Modal ties use first-index argmax. "
        "The base evaluation includes task scores, log loss, repeat agreement, effective sample "
        "sizes and descriptive party subgroup results.",
        "",
        "## Execution and audit",
        "",
        f"Provider requests reserved: {ledger['reserved_requests']}. Provider-reported cost: "
        f"${cost:.6f}. Unresolved usage records: {unresolved}. Hard run ceiling: "
        f"${config['max_usd']}; request ceiling: {config['max_requests']}.",
        "",
        "Each prompt was built in a fresh non-root Docker worker with no network or credentials, "
        "read-only filesystem, dropped capabilities and no new privileges. The host broker and "
        "remote model inference remain outside that container boundary.",
        "",
        "The independent audit verified exact payloads, worker isolation, complete unique "
        "forecast panel, reserve exclusion, outer-fold boundaries and independently recomputed "
        "direct Brier scores. Statistical/hybrid behavior was additionally tested by adversarial "
        "held-out-label changes; it was not reimplemented independently.",
        "",
        f"Independent audit seal: `{audit['seal_sha256']}`.",
        "",
        "## Interpretation limits",
        "",
        "These are previously inspected Ohio development respondents, one model and two repeats. "
        "Survey weights within a state subset and small subgroups limit representativeness. "
        "Policy items reconstruct contemporaneous answers; they do not establish causal policy "
        "reception or longitudinal change. Interview completion is a provenance date, not an "
        "exact item timestamp; available information is not assumed to be personal exposure. "
        "There was no historical pack, private reflection or conversation in this comparison. "
        "A favorable development estimate requires frozen, larger external validation before "
        "generalization; statistical nonsignificance is not evidence of equivalence.",
        "",
        "No additional fine-tuning or AgentSociety installation was part of this run. "
        "Interaction value remains a separate comparison after individual fidelity is validated.",
        "",
    ]
    return "\n".join(lines)


def load_completed(root):
    """Fail closed before producing a report if any completion/audit artifact is absent."""
    required = [
        "contract.json",
        "prediction-seal.json",
        "evaluation.json",
        "evaluation-seal.json",
        "additional-diagnostics.json",
        "additional-diagnostics-seal.json",
        "independent-audit.json",
        "spend_ledger.json",
    ]
    for name in required:
        if not (root / name).is_file():
            raise ValueError("Completed audited run required; missing " + name)
    contract = verify(root)
    for name in ["prediction-seal.json", "additional-diagnostics-seal.json"]:
        boundary = read(root / name)
        check_seal(boundary)
        for path, digest in boundary["bindings"].items():
            if _sha256_file(Path(path)) != digest:
                raise ValueError("Bound artifact changed: " + path)
    boundary = read(root / "evaluation-seal.json")
    check_seal(boundary)
    if boundary["report_sha256"] != _sha256_file(root / "evaluation.json") or boundary[
        "prediction_seal_sha256"
    ] != _sha256_file(root / "prediction-seal.json"):
        raise ValueError("Evaluation seal mismatch")
    audit = read(root / "independent-audit.json")
    check_seal(audit)
    if (
        audit["verified"] is not True
        or audit["reserve_overlap"] != 0
        or audit["evaluation_seal_sha256"] != _sha256_file(root / "evaluation-seal.json")
    ):
        raise ValueError("Independent audit failed or refers to another evaluation")
    evaluation = read(root / "evaluation.json")
    diagnostics = read(root / "additional-diagnostics.json")
    if any(r["promotion"] or r["reserved_respondents_used"] for r in [evaluation, diagnostics]):
        raise ValueError("Unexpected promotion or reserve use")
    ledger = read(root / "spend_ledger.json")
    if any(e.get("reported_usage") is None for e in ledger["entries"]):
        raise ValueError("Provider usage must be reconciled before final report")
    return evaluation, diagnostics, audit, ledger, contract["config"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=resolve("data/runs") / RUN)
    parser.add_argument(
        "--output", type=Path, default=resolve("docs/ANES_PROFILE_ABLATION_RESULTS.md")
    )
    args = parser.parse_args()
    content = render(*load_completed(args.root), args.root.name)
    if args.output.exists() and args.output.read_text() != content:
        raise ValueError("Refusing to overwrite a different existing results report")
    args.output.write_text(content)


if __name__ == "__main__":
    main()
