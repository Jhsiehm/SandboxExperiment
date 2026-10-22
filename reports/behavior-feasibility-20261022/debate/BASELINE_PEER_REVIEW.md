# Independent baseline infrastructure review — 22 October 2026

Read-only review of sibling `baseline/baseline.py`, `test_baseline.py`, and `source-contract.unresolved.json`, before any real-data result was available. No sibling files changed and no human-data experiment run. Findings were sent to baseline owner and coordinator; owner may subsequently resolve them. Line references describe the reviewed version, not a permanent frozen source.

## Findings before source admission

1. **Reject missing identity keys (medium).** `validate`, reviewed lines65–83, checks duplicate persons and assignment consistency but does not reject null/empty person or household IDs. A single missing person ID passes duplicate checks; unrelated people with missing household IDs can collapse into one artificial household. Require normalized nonempty identifiers and tests covering missing/blank keys before actual import. Otherwise household counting and independence claims are not reliable.
2. **Clarify and enforce raw-source binding (medium admission requirement).** `source_sha256` is only checked as nonempty in `validate`. CLI does correctly verify normalized-input SHA-256 before parsing, and reports normalized/contract/implementation hashes. That protects normalized content but does not prove correspondence to the declared raw source. Adapter must verify actual archive/member hashes and record transform version, or clearly identify the approved adapter as a trusted upstream boundary. Do not call a nonempty source hash a verified source binding.
3. **Require assignment/outcome timing evidence (medium admission requirement).** The generic harness checks feature availability against a common cutoff and rejects variable-cutoff configurations. It does not itself validate assignment-known dates or that the measured outcome follows cutoff. These must be enforced by the reviewed source adapter/contract. Oregon lottery draws vary; a convenient common cutoff could include decisions already made by earlier cohorts. Source evidence, not renamed role strings, must establish temporal admissibility.
4. **Make missingness normalization explicit (low).** Null features become categorical levels; unseen categories are all-zero and alias the reference category. This is a defensible conservative implementation only if documented. Reject nonfinite/unsupported values and normalize source missing-value sentinels consistently. For missing outcomes, reject rather than encode missing as failure; current binary validation already rejects ordinary null outcomes.

## Positive checks

- Household hashes determine reserve and folds without labels. All members with the same valid ID stay together. Reserved households cause refusal, rather than silent scoring.
- Evaluation-fold labels do not enter training rates or logistic fits. The adversarial test flips held-out outcomes and requires identical predictions for that fold.
- Vocabulary is fit on training rows only. Fixed L2 avoids hidden hyperparameter selection; no calibration benefit is claimed.
- Weighted Brier, clipped log loss and assignment-arm share calculations are internally consistent. Weights are finite/positive; their scientific validity remains a source-admission question.
- Output explicitly says development-only, descriptive assigned-arm difference, no design-adjusted ITT/reference replication, and no uncertainty. Those are appropriate limits.
- Unresolved source contract blocks the CLI; synthetic fixture passing is not presented as empirical human performance.

## Remaining tests and scientific limits

Add identity rejection, mixed within-household assignment, nonfinite weights/features, malformed source binding, and assignment/outcome timing checks as the adapter becomes concrete. Preserve the held-out-label mutation test. Reference-estimate reproduction and design-adjusted household-cluster uncertainty belong in the real-data adapter, not in claims about this generic harness. A split reserve becomes historical development if the same people/outcomes are used in a full-sample replication first; the existing unresolved contract correctly warns of that.

This review does not certify unseen source transformations or later real-data reproduction. Re-review the finalized adapter and result artifacts after they exist.
