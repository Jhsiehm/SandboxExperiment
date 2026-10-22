# Cleanup and individual-emulation implementation audit — 2026-10-20

This record concerns the current cleanup and next development experiment. It does not replace the sealed records of earlier experiments. Status below is updated as checks complete; implementation is not evidence of improved behavioral fidelity.

## Baseline and ownership

- The working project is the nested `SandboxExperiment` Git repository. At initial inspection it contained 21 modified tracked files and numerous untracked files from previous work; the outer repository lists this whole project as untracked.
- No `AGENTS.md` was found under the enclosing ChatGPT workspace.
- `reports/implementation-audit-20261020/baseline.json` records Git status and SHA-256 hashes for 346 source/document files and 849 files in three prior frozen run directories. It contains hashes and paths, not credentials or respondent contents. The snapshot was taken while collaborating agents were inspecting the workspace.
- Interface agent owns `leaderboard/static/*`; experiment agent owns new ablation/calibration modules and their tests/protocol; independent audit agent owns this record and audit-specific files. Root coordinates integration and execution. Existing uncommitted work must be preserved.
- No destructive cleanup, replacement of old experiment implementations, or editing of previous frozen run outputs is authorized by this audit.

## Scientific boundaries

The 120 Ohio respondents are previously inspected development data. Out-of-fold predictions can exclude a person's outcome from model fitting, but cannot erase researcher exposure. The separate 50-person reserve must remain excluded from all development fitting, selection and evaluation. All stochastic repetitions from a respondent must remain in one fold.

Primary profile comparisons must separate reduction of existing fields from addition of measured fields. Calibration and statistical–agent blending must be selected using only each outer training partition, with inner folds where selection uses predicted errors. Baseline fitting must exclude the evaluated person's labels. Uncertainty must respect respondent clustering; repeated calls are not additional human observations.

Provenance must distinguish source field, measurement wave, date resolution and missingness. A PRE label alone does not establish input precedence within an interview. Historical availability does not establish personal exposure. Matching marginal answer shares does not establish individual accuracy or a valid joint distribution of attitudes.

## Current checklist

| Check | Status |
|---|---|
| Baseline status and frozen-artifact hash snapshot | Complete |
| Existing full test suite | Final full rerun: 309 passed, two existing dependency warnings, 141 seconds |
| Interface cleanup and visual review before new live execution | Setup cleanup checked before launch; independent progress panel subsequently verified at desktop/mobile widths |
| New profile/provenance and calibration implementation review | Reviewed; requested core safeguards implemented before final preparation |
| New tests and independent leakage checks | Seven combined profile tests pass, including three independent audit tests; broader suite pending |
| Frozen-artifact hashes unchanged after cleanup | All 849 baseline files unchanged in the final post-run audit |
| New live execution, results and seal | 960 calls completed; predictions and evaluation sealed; independent audit passed |

## Limits

Docker prompt-worker isolation does not encompass remote model inference or the trusted host broker. A code or container check establishes an execution property, not human fidelity. Future historical-context and social-interaction experiments remain separate from this individual development comparison, and no fresh-cohort or deployment-validity claim follows from development results.

## Independent implementation review

The new implementation lives in `profile_ablation.py` and `profile_ablation_worker.py`, preserving the previous frozen individual runner. The four conditions contain 8 original fields, 20 original rich fields, 11 reduced existing fields, and those same 11 plus four measured fields. Thus the primary adjacent comparisons isolate removal and addition respectively.

`tests/test_profile_ablation_audit.py` independently alters every outer fold's outcome labels and confirms that predictions and selected hyperparameters for that fold remain identical. It also checks profile-set differences, uniqueness and ordering independence of fold assignments. Three tests passed; focused Ruff checks passed. This checks leakage through the implemented fitting algorithm, not pretrained-model contamination or prior researcher exposure.

Review requested improvements before freezing: validate inherited cohort bytes against its prior contract; randomize condition execution order; report paired primary contrasts; seal evaluation; strengthen provenance parsing; validate actual worker isolation before inference; bind broker dependencies. All seven were observed in the implementation before final preparation. No remaining scientific blocker to this development run was identified. This does not predict whether its results will improve.

The evaluator averages each respondent's two probability vectors before scoring. Earlier experiments averaged the two losses instead. Within-run comparisons use the same estimator, but absolute scores should not be compared across runs without recomputation under a common estimator.

Root additionally owns a curated `leaderboard/individual.py` endpoint, its route and tests; the interface agent integrates its display. This extension must omit respondent IDs, raw predictions, fitting-audit IDs, local paths and credentials.

## Cleanup scope and interface evidence

The interface agent removed stale fixed-size swarm descriptions, shortened setup instructions, made preparation commands follow the chosen era, moved source diagnostics into a disclosure, and improved wrapping/link styling. It reports 14 dashboard/ANES tests and JavaScript syntax checks passing. Setup was viewed at 1280px and 390px widths with no document horizontal overflow; the disclosure and Runs link worked.

A separate independent-development panel was then added, clearly separated from the structural ANES comparison. Its results are aggregate-only, unavailable after integrity errors, and labelled as development rather than fresh validation. Its first browser check timed out under host load. A later Chrome check succeeded at desktop 882px and mobile 390px: live saved-response counts refreshed, evaluation remained explicitly pending, the reserve report was not prematurely described as verified, the empty metrics disclosure worked, and there was no document horizontal overflow. Prepared-state rendering was not tested because the real run was already underway. Screenshot: `reports/ui-20261020/individual-progress-desktop.png`. The design detector ran in degraded regex-only mode and still reported legacy/palette warnings; no exhaustive visual-cleanliness claim is made.

`scripts/audit_profile_ablation.py` completed successfully after evaluation. It checked all 960 checkpoint payloads and isolation records, seals, fitting partitions and reserve exclusion, then independently recomputed all 12 direct-arm weighted Brier scores. Statistical/hybrid fitting is covered by adversarial label tests rather than a second independent fitting implementation.

## Live launch and additional diagnostics

Root reported 27 targeted tests passing and verified a live Docker probe before launching inference. Image ID: `sha256:5fbb3f7ff1f1109addbc67082cfff54c5f449c6c61a9ca36a4b66b471f300827`. The probe checked read-only root, no external network, non-root user, no effective capabilities and no provider credentials. The historical implementation files are frozen and must not change during execution.

An initial broad test run overlapped interface editing: 295 tests passed and one asset-version assertion failed because it had loaded the old expected version before the edit. The relevant updated tests passed afterwards. The final full rerun passed all 309 tests with two existing dependency warnings in 141 seconds; log: `reports/implementation-audit-20261020/final-tests.log`. Following the final CSS version update, the interface agent also reported 14 targeted tests passing with the same two warnings. The initial failure remains recorded rather than silently counted as an original clean run.

The standalone `scripts/profile_ablation_diagnostics.py` was reviewed. It verifies seals and reserve exclusion, reconstructs the same out-of-fold decisions/scores, computes answer-share errors and modal response-pair tables, and reports hybrid-minus-direct/party contrasts. Its modal tables are explicitly proxies rather than joint probability predictions; bootstrap intervals condition on already fitted predictions and do not account for calibration refitting. These are exploratory diagnostics, not additional predeclared primary comparisons. No issue requiring a frozen-source modification was identified.

Root exported the worker image as a 43,552,256-byte archive and verified 14 OCI blobs. Archive SHA-256: `60eb20fb248d0f34978a10bd8f05740c226aa54383f503c0dd6b4e8d97a4d8a9`. This preserves the worker image; it does not package the remote inference service.

Final root-reported execution: 960 saved forecasts and 960 provider requests, USD 0.6672136 provider-reported cost, zero unresolved usage records. Two Docker startup timeouts occurred before provider calls at 154 and 880 saved forecasts. Execution resumed with the same frozen contract and image; `execution-events.json` records those incidents. Do not describe execution as having no failures: there were two recoverable infrastructure failures, with no extra paid calls from those incidents.

## Completed independent audit and interpretation

The independent audit verified 120 unique respondents, exact correspondence between each checkpoint and that person's allowed profile, all recorded worker isolation probes, complete 960-cell prediction coverage, prediction/evaluation seals, zero overlap with the reserved 50, and outer training/evaluation separation. All twelve direct weighted Brier scores agreed with the evaluator within 1e-12. Audit seal: `919f708811714e28a692f5e4c4677569852762fa72c4faad69d3da557664a68c`. Prediction seal: `ba94ff75138bc047530f75ee8df9c754a2ebcc50c18fe523c6419ab411dad06d`.

| Profile | Direct macro Brier | Hybrid macro Brier |
|---|---:|---:|
| Original sparse | 0.237858 | 0.228215 |
| Original rich | 0.237785 | 0.222347 |
| Reduced existing | 0.238706 | 0.225904 |
| Reduced plus observed | 0.231844 | 0.224831 |

The party baseline scored 0.220867 in every arm, lower than every agent and hybrid point estimate. Reducing the rich profile changed direct macro Brier by +0.000922, with conditional paired 95% interval [-0.009441, +0.011271]. Adding the four measured fields to the reduced profile changed it by -0.006862, interval [-0.018667, +0.003497]. Both intervals cross zero. The latter is a promising development point estimate, not established improvement; the experiment does not establish superiority over the party baseline. It also does not establish equivalence or general harm from added fields.

The standalone result renderer was spot-checked: it requires completed evaluation, diagnostics, a matching independent audit and resolved provider usage before writing a report. Additional diagnostics and final completion packaging are coordinated by root. No historical source or prior frozen artifact was modified by this audit.
