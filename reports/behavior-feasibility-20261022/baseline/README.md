# Oregon baseline readiness — 2026-10-22

The official archive was obtained through the authorized source workflow. **The full-sample administrative enrollment first stage is reproduced within published rounding precision.** No paid calls were made. All 74,922 public-use respondents contributed to reference reproduction, so this sample is historical development and **does not contain a pristine confirmation holdout**. ANES's separate reserve remains untouched.

## Actual results

| Outcome | Control mean | Adjusted lottery effect | Household-cluster SE |
|---|---:|---:|---:|
| Ever any Medicaid, matched notification through 30 September 2009 | 0.14096877 | 0.25586579 | 0.00350915 |
| Any Medicaid on 30 September 2009 | 0.10577094 | 0.14813924 | 0.00311152 |

N=74,922 people in 66,385 households. The source's `sample_hdd=1` includes the entire public-use sample; `noweight=1` specifies unit weights. OLS includes treatment plus lottery-draw and listed-household-size indicators, with a household-clustered sandwich covariance and Stata finite-sample correction. The two outcomes differ substantially; an endpoint is not an ever-enrollment trajectory.

`reference-targets.json` was saved before numerical execution from the official paper Table III: published ever-enrollment control mean .141, effect .256, SE .0035; endpoint .106, .148, .0031. All six checks pass with rounding tolerances .0005 for means/effects and .00005 for SE. This reproduces these two full-sample rows, not the entire paper or all public-use analyses.

Historical, five-fold household OOF prediction of ever-enrollment (selected-feature baselines, not strongest available models):

| Baseline | Brier | Log loss |
|---|---:|---:|
| Assignment-arm rate | 0.16769607 | 0.51126394 |
| Fixed-L2 logistic, eleven listed/matched administrative fields | 0.16421990 | 0.50097743 |

These are statistical development scores, not evidence that agents emulate behavior. The logistic input fields are `numhh_list`, `draw_lottery`, `have_phone_list`, `english_list`, `female_list`, `first_day_list`, `last_day_list`, `pobox_list`, `self_list`, `week_list`, `zip_msa_list`, plus assignment. Codebook and user guide identify list observations as January–February 2008 sign-up information. Missing values remain explicit null categories. Age is intentionally omitted from this first categorical harness. No outcomes, applications, approvals, death, or follow-up surveys are predictors. The matched control draw is an analyst-assigned alignment, not information the control person personally received. This retrospective design-frame predictor is not an admitted time-zero agent forecast.

## Reproduce these results

```sh
.venv/bin/python reports/behavior-feasibility-20261022/baseline/oregon_reference.py
.venv/bin/pytest -q reports/behavior-feasibility-20261022/baseline/test_baseline.py
```

`oregon_reference.py` pins both raw-data hashes before reading; joins by unique person ID; validates exact N, complete binary outcomes, and within-household assignment; records input/source-code hashes and reference differences. `oregon-results.json` contains aggregate-only results. No respondent-level predictions are exported.

## What is ready

`baseline.py` accepts a reviewed normalized development-only JSONL and explicit contract. It computes household-grouped, outcome-blind five-fold predictions for an assignment-arm rate baseline and a fixed-L2 logistic baseline on the same assignment and approved categorical predictors. It reports Brier, log loss, assignment-arm share errors, and a descriptive difference-in-shares error. This last statistic is **not** the source study's design-adjusted intent-to-treat estimator.

Development/reserve allocation uses a salted household hash (approximately 20% reserved); fold allocation uses a separately salted household hash. Membership depends on no outcomes. The harness rejects a reserved household, inconsistent within-household assignment, duplicate people, post-assignment or unavailable predictors, unsupported per-draw prediction cutoffs, and high-cardinality features requiring preprocessing. Evaluation rows cannot supply the training vocabulary. Fixed regularization avoids calibration/tuning against evaluated outcomes. The CLI requires the approved normalized-input SHA-256 before parsing rows and emits input, contract and implementation hashes.

The future agent source adapter is deliberately unresolved; the separate retrospective reference adapter is complete. `source-contract.unresolved.json` is not executable approval. Exact raw variable names, weights, analysis exclusions, endpoint dates and lottery-batch cutoffs must come from the downloaded documentation/code. The generic harness supports a single common cutoff only; it must not be used to silently collapse differing assignment dates. A proper source-specific adapter can provide per-person cutoff validation before a normalized export, followed by an explicitly revised contract/harness if needed.

## Requirements before an agent forecast

The verified source code and paper identify Table III of [the first-year Oregon paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC3535298/) as a candidate reference, with household-size/lottery-draw controls and household-clustered uncertainty. The source analysis code was inspected and implemented for the two full-sample rows above. Do not substitute an end-of-window enrollment endpoint for “ever enrolled” during a follow-up window. Do not use the post-lottery initial survey as pre-assignment evidence. Numerical reference targets are frozen separately in `reference-targets.json`; the generic future agent source contract remains unapproved.

1. Hash the source archive and extracted codebooks, code and data; identify the precise first-year data release.
2. Resolve analysis sample, person/household IDs, lottery assignment and batch, listed-household size, enrollment window and weights from code.
3. Choose one coherent validation route: reproduce the whole published sample and label it historical development, **or** partition by household before outcome analysis and label the subset estimate a development calculation rather than exact full-sample replication. Do not claim both full-sample reproduction and a pristine holdout inside that sample.
4. Export only development household outcomes to the normalized input. Keep reserved outcomes out of this harness, logs and prompts. Confirm overlap counts without exposing row-level outcomes.
5. Separately implement the source's documented regression/standard-error specification and compare coefficient, uncertainty, N and weighted/sample means at declared tolerances.
6. Run development statistical predictions on an admitted feature set. Then decide whether pre-event evidence is rich enough to justify an agent comparison. No current output authorizes a paid run.

## Commands

From the project root:

```sh
.venv/bin/pytest -q reports/behavior-feasibility-20261022/baseline/test_baseline.py
.venv/bin/ruff check reports/behavior-feasibility-20261022/baseline/baseline.py reports/behavior-feasibility-20261022/baseline/test_baseline.py
```

Only after source mapping, timing, provenance and input checksums are approved:

```sh
.venv/bin/python reports/behavior-feasibility-20261022/baseline/baseline.py --input PATH_TO_APPROVED_DEVELOPMENT_JSONL --contract PATH_TO_APPROVED_CONTRACT --output PATH_TO_DEVELOPMENT_RESULTS
```

Each normalized row requires `person_id`, `household_id`, binary `assignment`, binary observed `outcome`, positive finite `weight`, and `features` whose keys exactly match the contract. Missing predictor values must remain explicit nulls. Missing outcome exclusions require documentation in the adapter, rather than treating nonresponse as zero. The template has no guessed source mappings.

## Validation and limitations

Seventeen synthetic fixture tests and one saved-reference integrity test pass, including an adversarial change of all outcomes in one held-out fold that leaves that fold's predictions unchanged. Tests also check reserve refusal, field timing, training-only vocabulary, high-cardinality rejection, unapproved input, and CLI checksum refusal before parsing. Scoped Ruff passes.

No human fidelity or agent superiority result follows from fixture tests; reference reproduction evidence comes from the separate actual-data comparison above. This small harness does not yet include design-aware confidence intervals, continuous-feature preprocessing, nested calibration, or treatment-effect uncertainty. Those require the actual source design. No ANES reserve or sealed previous artifact was accessed or changed. The raw-source binding is enforced by `oregon_reference.py`; the generic harness only binds its normalized input and trusts a reviewed adapter for raw provenance. Missing values are null categories; unseen categories use the training reference representation. These conventions must be reviewed before agent admission.
