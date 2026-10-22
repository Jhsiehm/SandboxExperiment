"""Independent post-run boundary, pairing, baseline and score audit."""

import json
import statistics
from pathlib import Path

from psbx.experiments.anes_society import _canonical_json_sha256, _sha256_file
from psbx.experiments.decision_profiles import TARGETS, check_seal, dump, seal
from psbx.experiments.individual_validation import RUN_ID, read, validate_panel, verify
from psbx.experiments.individual_worker import ARMS, build_prompt, fields
from psbx.paths import resolve

root = resolve("data/runs") / RUN_ID
c = verify(root)
ps = read(root / "prediction-seal.json")
es = read(root / "evaluation-seal.json")
check_seal(ps)
check_seal(es)
for p, h in ps["bindings"].items():
    assert _sha256_file(Path(p)) == h
assert es["report_sha256"] == _sha256_file(root / "evaluation.json")
assert es["prediction_seal_sha256"] == _sha256_file(root / "prediction-seal.json")
cohort = read(root / "cohort.json")
predictions = read(root / "predictions.json")
validate_panel(cohort, predictions)
ids = {p["synthetic_person_id"] for p in cohort}
people = {p["synthetic_person_id"]: p for p in cohort}
train = set(read(root / "baseline-training-ids.json"))
old = resolve("data/runs/anes2012-ohio-reserved-validation-20261012")
reserve = set(read(old / "reserved-respondent-ids.json"))
assert len(ids) == 24 and len(train) == 96 and not ids & train and not (ids | train) & reserve
oldc = read(old / "contract.json")
check_seal(oldc)
assert oldc["bindings"][str(old / "input/cohort.json")] == _sha256_file(old / "input/cohort.json")
cp = [read(p) for p in (root / "checkpoints").glob("*.json")]
assert len(cp) == 240
index = {
    (
        x["metadata"]["person"],
        x["metadata"]["arm"],
        x["metadata"]["repetition"],
        x["metadata"]["stage"],
    ): x
    for x in cp
}
assert len(index) == 240
for x in cp:
    assert x["status"] == "completed"
    assert x["fingerprint"] == _canonical_json_sha256(
        dict(payload=x["payload"], model=read(root / "worker.json"))
    )
    assert x["prompt_sha256"] == _canonical_json_sha256(build_prompt(x["payload"]))
    iso = x["isolation"]
    assert iso["uid"] == 10001 and iso["root_readonly"] and iso["no_new_privileges"]
    assert not iso["active_external_interfaces"] and not int(iso["effective_capabilities"], 16)
    assert not iso["provider_key_present"] and not iso["forbidden_paths_present"]
    meta = x["metadata"]
    person = people[meta["person"]]
    assert x["payload"]["baseline_date"] == person["baseline_date"]
    assert x["payload"]["arm"] == meta["arm"] and x["payload"]["stage"] == meta["stage"]
    assert x["payload"]["observations"] == {
        f: {k: person["observed"][f][k] for k in ["label", "answer", "status"]}
        for f in fields(meta["arm"])
    }
    if meta["arm"] == "focused_review" and meta["stage"] == "final":
        assert (
            x["payload"]["review"]
            == index[meta["person"], meta["arm"], meta["repetition"], "review"]["parsed"]["review"]
        )
    else:
        assert x["payload"]["review"] == ""
for row in predictions:
    m = row["metadata"]
    assert row["probabilities"] == index[m["person"], m["arm"], m["repetition"], "final"]["parsed"]
# Only now open evaluation labels, after both seals and full panel verification.
manifest = read(c["targets_manifest"])
assert es["targets_sha256"] == manifest["targets_sha256"]
assert _sha256_file(Path(manifest["targets_path"])) == manifest["targets_sha256"]
targets = {p["synthetic_person_id"]: p for p in read(manifest["targets_path"])}
report = read(root / "evaluation.json")
recomputed = {}
for arm in ARMS:
    task_scores = []
    for task, spec in TARGETS.items():
        weighted = []
        weights = []
        for p in cohort:
            pid = p["synthetic_person_id"]
            y = targets[pid][task]
            if y not in spec["codes"]:
                continue
            outcome = spec["codes"].index(y)
            values = []
            for rep in range(2):
                probs = index[pid, arm, rep, "final"]["parsed"][task]
                values.append(sum((v - float(k == outcome)) ** 2 for k, v in enumerate(probs)) / 2)
            weighted.append(statistics.mean(values) * p["weight"])
            weights.append(p["weight"])
        score = sum(weighted) / sum(weights)
        task_scores.append(score)
        original = next(
            x["brier"] for x in report["metrics"] if x["arm"] == arm and x["task"] == task
        )
        assert abs(score - original) < 1e-12
    recomputed[arm] = statistics.mean(task_scores)
    assert abs(recomputed[arm] - report["macro_brier"][arm]) < 1e-12
# Recompute training-only baselines, without relying on evaluation implementation.
pool = [p for p in read(c["baseline_pool"]) if p["synthetic_person_id"] in train]
for arm in ["training_prevalence", "party_smoothed"]:
    for task, spec in TARGETS.items():
        valid = [p for p in pool if targets[p["synthetic_person_id"]][task] in spec["codes"]]
        average = statistics.mean(p["weight"] for p in valid)
        totals = [
            sum(
                p["weight"] / average
                for p in valid
                if targets[p["synthetic_person_id"]][task] == code
            )
            for code in spec["codes"]
        ]
        prior = [(v + 1) / (sum(totals) + 3) for v in totals]
        loss = 0
        totalweight = 0
        for p in cohort:
            y = targets[p["synthetic_person_id"]][task]
            if y not in spec["codes"]:
                continue
            peers = (
                [
                    q
                    for q in valid
                    if q["observed"]["pid_x"]["code"] == p["observed"]["pid_x"]["code"]
                ]
                if arm == "party_smoothed"
                else []
            )
            counts = [
                sum(
                    q["weight"] / average
                    for q in peers
                    if targets[q["synthetic_person_id"]][task] == code
                )
                for code in spec["codes"]
            ]
            probs = [(v + 5 * prior[k]) / (sum(counts) + 5) for k, v in enumerate(counts)]
            loss += (
                p["weight"]
                * sum((v - float(spec["codes"][k] == y)) ** 2 for k, v in enumerate(probs))
                / 2
            )
            totalweight += p["weight"]
        expected = next(
            x["brier"] for x in report["metrics"] if x["arm"] == arm and x["task"] == task
        )
        assert abs(loss / totalweight - expected) < 1e-12
words = [len(x["parsed"]["review"].split()) for x in cp if x["metadata"]["stage"] == "review"]
audit = seal(
    dict(
        verified=True,
        checkpoints=240,
        final_forecasts=192,
        private_reviews=48,
        evaluation_people=24,
        baseline_training_people=96,
        reserve_overlap=0,
        paired_review_memory_verified=True,
        independent_llm_and_baseline_scores_verified=True,
        independent_macro_brier=recomputed,
        format_attempts=sum(x["attempts"] for x in cp),
        reviews_over_80_words=sum(n > 80 for n in words),
        max_review_words=max(words),
        source_sha256=_sha256_file(Path(__file__)),
        evaluation_seal_sha256=_sha256_file(root / "evaluation-seal.json"),
    )
)
dump(root / "audit.json", audit)
print(json.dumps(audit, indent=2))
