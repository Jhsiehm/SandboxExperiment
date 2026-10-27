"""Verify the October 27 documentation snapshot without running experiments.

Only indexed documents, selected aggregate reports, and the frozen statistical
table are read. Respondent exports, credentials, and reserved labels are excluded.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "reports/research-register-20261027"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ledger = read_json(REGISTER / "experiment-ledger.json")
    inventory = read_json(REGISTER / "source-inventory.json")
    errors: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else errors).append(label)

    entries = {entry["id"]: entry for entry in ledger["entries"]}
    check(len(entries) == len(ledger["entries"]), "unique study identifiers")
    sources = {source["id"]: source for source in inventory["sources"]}
    check(len(sources) == len(inventory["sources"]), "unique source identifiers")
    for source in sources.values():
        path = Path(inventory["roots"][source["root"]]) / source["path"]
        check(path.is_file(), f"source exists: {source['id']}")
        if path.is_file():
            check(digest(path) == source.get("sha256"), f"source digest: {source['id']}")
    for entry in entries.values():
        check(bool(entry["sources"]), f"supporting sources: {entry['id']}")
        for source in entry["sources"]:
            check(
                source["root"] + ":" + source["path"] in sources,
                f"indexed source: {entry['id']} / {source['path']}",
            )
        for key in ("provider_reported_usd", "provider_calls"):
            value = entry[key]
            check(
                value is None or (math.isfinite(value) and value >= 0),
                f"nonnegative or unknown {key}: {entry['id']}",
            )

    covered = {path for entry in entries.values() for path in entry["artifact_directories"]}
    present = set()
    for directory in ("data/runs", "data/local-mlx-pilot"):
        for path in (ROOT / directory).iterdir():
            if path.is_dir():
                present.add(str(path.relative_to(ROOT)))
    check(not (present - covered), "all materialized research run/stage directories indexed")
    check(not (covered - present), "all indexed run/stage directories present")

    oregon = read_json(ROOT / "reports/behavior-feasibility-20261022/baseline/oregon-results.json")
    reproduced = entries["oregon-reproduction"]["metrics"]
    check(oregon["n_people"] == reproduced["people"] == 74922, "Oregon people reconciled")
    check(
        oregon["n_households"] == reproduced["households"] == 66385, "Oregon households reconciled"
    )
    for field, metric in (
        ("ohp_all_ever_matchn_30sep2009", "ever_enrollment_adjusted_assignment_effect"),
        ("ohp_all_end_30sep2009", "endpoint_adjusted_assignment_effect"),
    ):
        check(
            oregon["reference"][field]["treatment_coefficient"] == reproduced[metric],
            f"Oregon adjusted effect reconciled: {field}",
        )
    rounds = [
        item["passed"]
        for row in oregon["published_rounding_checks"].values()
        for item in row.values()
    ]
    check(len(rounds) == 6 and all(rounds), "six saved Oregon rounding checks passed")
    predictive = entries["oregon-prediction"]["metrics"]
    for arm, prefix in (
        ("assignment_only", "assignment"),
        ("same_information_logistic", "logistic"),
    ):
        for metric in ("brier", "log_loss"):
            check(
                oregon["historical_oof_metrics"][arm][metric] == predictive[f"{prefix}_{metric}"],
                f"Oregon {arm} {metric} reconciled",
            )
    relative_gain = 100 * (1 - predictive["logistic_brier"] / predictive["assignment_brier"])
    check(round(relative_gain, 2) == 2.07, "Oregon relative Brier gain reconciled")

    classifier = read_json(
        ROOT / "data/local-mlx-pilot/outcome-classifier-v1-20261023/internal-evaluation.json"
    )
    for arm, metric in (
        ("base", "base_rps"),
        ("pilot_classifier", "candidate_rps"),
        ("persistence", "persistence_rps"),
        ("transition", "transition_rps"),
    ):
        check(
            round(classifier["arms"][arm]["rps"], 6)
            == entries["local-outcome-classifier"]["metrics"][metric],
            f"classifier aggregate reconciled: {arm}",
        )
    check(classifier["numerical_nonworsening_gate"] is False, "classifier failed gate retained")

    residual = read_json(
        ROOT / "data/local-mlx-pilot/residual-calibration-v1-20261023/oof-evaluation.json"
    )
    for arm, metric in (
        ("transition", "transition_rps"),
        ("control", "calibrated_control_rps"),
        ("extension", "extension_rps"),
    ):
        check(
            residual["gate"]["mean_rps"][arm] == entries["residual-calibration"]["metrics"][metric],
            f"residual aggregate reconciled: {arm}",
        )
    check(residual["gate"]["passed"] is False, "residual failed gate retained")
    decision = read_json(
        ROOT / "data/local-mlx-pilot/residual-calibration-v1-20261023/decision.json"
    )
    check(
        decision["internal_readout"] is False and decision["outer_validation"] is False,
        "residual later stages remained stopped",
    )

    frozen = read_json(ROOT / "reports/statistical-reference-20261023/manifest.json")
    baseline = Path(frozen["baseline"]["path"])
    check(
        digest(baseline) == frozen["baseline"]["sha256"],
        "original statistical table digest preserved",
    )
    readiness = read_json(ROOT / "reports/anes-panel-readiness-20261023/readiness.json")
    check(readiness["source_blocker_count"] == 5, "five panel source blockers retained")
    check(
        readiness["real_panel_records_audited"] == 0
        and not readiness["model_training_enabled"]
        and not readiness["later_wave_readout_enabled"],
        "panel preparation-only state retained",
    )

    log_path = ROOT / "docs/RESEARCH_LOG.md"
    log = log_path.read_text()
    links = re.findall(r"\]\((?:<([^>]+)>|([^\s)]+))\)", log)
    for angled, plain in links:
        target = angled or plain
        if target.startswith(("https://", "http://", "#")):
            continue
        path = Path(target.split("#", 1)[0])
        if not path.is_absolute():
            path = log_path.parent / path
        # The receipt is generated below; every other local link must exist.
        check(
            path.resolve() == (REGISTER / "verification.json").resolve() or path.exists(),
            f"local document link: {target}",
        )
    check(
        len(re.findall(r"^### \d+\.", log, re.MULTILINE)) == len(entries),
        "document and ledger study counts agree",
    )
    check(
        "docs/RESEARCH_LOG.md" in (ROOT / "README.md").read_text(), "README links to research log"
    )
    generated = [
        log_path,
        REGISTER / "experiment-ledger.json",
        REGISTER / "source-inventory.json",
        Path(__file__).resolve(),
    ]
    for path in generated:
        check(
            re.search(r"sk-or-v1-[A-Za-z0-9]{20,}", path.read_text()) is None,
            f"no OpenRouter credential copied: {path.name}",
        )

    result = {
        "schema": "polisim-research-register-verification-v1",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not errors else "failed",
        "scope": (
            "Documentation snapshot and selected saved aggregate reconciliation; "
            "no experiment rerun or independent statistical replication."
        ),
        "study_count": len(entries),
        "source_count": len(sources),
        "materialized_run_stage_directories": sorted(present),
        "uncovered_directories": sorted(present - covered),
        "checks_passed": len(checks),
        "errors": errors,
        "checks": checks,
        "oregon_relative_brier_reduction_percent": relative_gain,
        "baseline_sha256": frozen["baseline"]["sha256"],
        "generated_file_sha256": {str(path.relative_to(ROOT)): digest(path) for path in generated},
        "not_performed": [
            "provider calls",
            "training",
            "respondent/reserve reads",
            "scientific evaluation reruns",
            "browser liveness check",
        ],
    }
    (REGISTER / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "study_count", "source_count", "checks_passed", "errors")
            },
            indent=2,
        )
    )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
