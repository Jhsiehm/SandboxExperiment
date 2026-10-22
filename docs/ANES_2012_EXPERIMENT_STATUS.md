# ANES 2012 experiment status

Last updated: **2026-10-20 20:59 EDT (America/New_York, UTC-04:00)**
Repository snapshot: `42e3608dae8d809b552109501658bb3427587c2e` on
`codex/reproducibility-correctness`, with related uncommitted work present
Scientific status: **No live scientific result is established**

This is a contemporaneous lab log, not a results paper or preregistration. It records what was
planned, attempted, blocked, or completed and points to the evidence available in this checkout.
It must not contain provider credentials or other secrets.

## Current phase ledger

| Phase | Status | Current evidence and interpretation |
| --- | --- | --- |
| Protocol and source inventory | Attempted | The protocol, source inventory, questionnaire parser, and milestone documents exist. The protocol remains a draft rather than a frozen preregistration. |
| Official runtime/target split | Completed | The official structural bundle contains 5,914 runtime profiles and a separately rooted evaluation vault. The split seal records the source, runtime, target, and manifest hashes. |
| Conditioning-field timing audit | Completed | The ten paper fields were checked against the ANES codebook. Eight are approved for the strict pre-election design; `discuss_disc` and `patriot_flag` are post-election. Separate sealed paper-faithful and strict-pre-election profile sets now exist with 5,914 rows each. |
| Full-sample statistical baselines | Completed / review pending | Six retrospective comparators produced out-of-fold predictions for all 4,188 valid two-party respondents. The artifacts are explicitly target-accessing and runtime-ineligible. A later review found that the baseline entry point trusts sibling manifest policy labels instead of verifying the split seal itself, and its categorical preprocessing is constructed before fold separation; these should be hardened before publication claims. |
| Provider-free official structural run | Completed | Five independent and five society replications completed with 1,200 prediction rows. The evaluator explicitly records `scientific_result: false`; these outputs validate plumbing, not human-response fidelity or a causal society effect. |
| Ohio provider-free Docker area run | Completed | `anes2012-ohio-20261004` ran the sealed structural mock in a non-root, network-disabled, read-only container: 226 Ohio profiles, 30 paired replications, and 13,560 prediction rows. This validates the hardened container path, not model behavior. |
| Six-model live smoke test, `anes2012-live-vote-smoke-6` | Attempted / blocked | The first OpenRouter request failed with HTTP 402 because the previously loaded credential had approximately `-$0.481481` available. No prediction or conversation artifact was produced. The run directory contains one local spend reservation with `reported_usage: null`; this is not evidence of a provider charge. |
| Pre-retry correctness gates | Completed | Sealed runtime verification, durable per-logical-call checkpoints and idempotent resume, exact matched profile/model coverage, and an equal-call private-deliberation control are implemented. Full repository lint and pytest were reported passing after the hardening changes. |
| Credential and funding transition | Superseded | The Sep. 24 credential had negative account availability and was unauthorized by Sep. 29. A later replacement credential authenticated and funded the bounded Oct. 4 smoke. Secret material is intentionally omitted. |
| Funded Ohio live smoke | Completed / superseded | `anes2012-ohio-live-20261004-v3` completed its pipeline, but later review found that the generic OpenRouter route had not forwarded the experiment system/date instruction. Its outputs are useful only as engineering evidence and are not protocol-faithful results. |
| Corrected Ohio live dialogue pilot | Completed / limited | `anes2012-ohio-live-dialogue-corrected-20261004` forwarded and sealed the system prompt, used provider JSON mode, completed 144 calls with no retries or unreconciled reservations, and scored 22 matched respondents across two replications. It is a descriptive pilot, not a powered causal result. |
| Respondent-context factorial | Completed / limited | `anes2012-decision-context-20261011` compared sparse/rich audited profiles with/without a fixed historical pack across 24 previously unprompted Ohio respondents and two repeats. All 192 independent calls completed, but the small development cohort and multiple exploratory contrasts do not support general causal claims. |
| Limited-network interaction pilot | Completed / limited | A predefined 12-person subset compared equal-call private reflection with a synthetic sparse network. All 48 calls completed; outcomes were mixed across vote and policy tasks, with no default swarm advantage established. |
| Reserved-cohort Docker validation | Completed / limited | `anes2012-ohio-reserved-validation-20261012` compared sparse and rich profiles for 120 development respondents while preserving a separate 50-ID reserve. All 480 planned logical calls produced valid predictions; the predeclared improvement gate failed. This is a stronger development result, not a powered or externally validated scientific finding. |
| Individual profile-selection development study | Completed / limited | `anes2012-ohio-individual-development-20261020` compared sparse, rich, focused, and focused-plus-private-review conditions for 24 previously inspected development respondents. All 240 calls completed and sealed. Focused direct improved descriptively over rich direct, but its paired interval crossed zero and the predeclared gate failed; the party-smoothed baseline remained best overall. |
| Full development-cohort profile ablation | Completed / limited | `anes2012-ohio-profile-ablation-development-v1` completed 960 forecasts for all 120 previously inspected development respondents across four profile arms and two repeats. Added observed fields improved the direct point estimate by `0.00686` Brier, but its interval crossed zero; the party baseline remained best and no arm was promoted. The separate 50-person reserve remained unused. |
| Full scientific study | Planned | The full model-powered question matrix, authenticated election-eve evidence treatment, powered replication design, frozen protocol, and final scientific analysis have not run. |

## Completed structural bundle

The structural run is `anes2012-society-official-structural`. Its information cutoff is
2012-11-05, the election date is 2012-11-06, and the source release date recorded in the runtime
manifest is 2016-05-24. The manifest therefore records `source_was_public_at_cutoff: false` and
classifies the included respondent fields as pre-election private covariates.

Verified inventory:

- 5,914 runtime profile rows.
- 5,914 target rows plus one CSV header.
- 1,200 sealed structural prediction rows.
- 150 interaction-summary rows.
- Five replications per arm, at most 120 agents per replication, groups of 12, and three rounds.
- Official survey weights are applied during evaluation only.
- 4,188 valid two-party targets in the evaluation report.
- The engine is `provider_free_structural_mock`; network access was not required.

The evaluation report warns that the run is provider-free structural validation and not evidence
of human-response fidelity. The displayed arm differences must not be described as a live-model
conversation effect.

## Live smoke attempt log

### 2026-09-23 20:55 EDT — first request blocked

- Run ID: `anes2012-live-vote-smoke-6`.
- Intended scope: six hosted-model families, one matched cohort, and a bounded pipeline smoke test;
  it was not intended to estimate a scientific treatment effect.
- Observed outcome: the first OpenRouter call returned HTTP 402.
- Provider output: no prediction file and no conversation transcript were produced.
- Local accounting outcome: one request was reserved locally for an estimated `$0.0008724`, but
  `reported_usage` is `null`.
- Durable failure evidence limitation: the HTTP response itself was reported in the active thread
  but was not persisted in the run directory. Only the spend ledger remains. This is why durable
  attempt/failure checkpointing is a pre-retry gate.
- Credential state at failure: the previously loaded credential reported approximately
  `-$0.481481` available. A replacement credential was later supplied to the active thread; its
  value is not recorded here.

## Completed runner-hardening gates

The four correctness gates identified after the first failed smoke attempt are now implemented:

1. **Crash-safe attempt ledger and resume — completed.** Each logical call durably appends a
   completed or failed JSONL checkpoint with spend snapshots. Completed call IDs can be resumed
   idempotently, and a changed run contract is rejected.
2. **Verified runtime boundary — completed.** The live runner requires prepared profiles whose
   bytes, row count, cutoff, fields, runtime manifest, and parent split seal agree; arbitrary or
   changed profile JSONL input is rejected.
3. **Balanced evaluation coverage — completed.** Scoring requires exact matched profile coverage
   across both treatments and every replication, rejects duplicates and gaps, and checks matched
   model assignment when model IDs are present.
4. **Identifiable treatment contrast — completed.** The independent arm now receives a private
   deliberation call for every public-message round in the society arm. Both arms therefore receive
   equal logical call counts before their private final answers. The recorded protocol is
   `matched_private_deliberation_control_v1`.

For the six-worker smoke roster with one replication and two rounds, the equal-call design reserves
up to 72 requests: three deliberation/message-plus-final calls per arm, for both arms and six
workers, with the existing retry allowance included in preflight.

The active thread owns the runner, CLI, tests, smoke roster, and credential handling. This report
does not modify those files and should be updated only from their durable outputs and explicit
status reports.

## Hardening and provider checkpoint log

### 2026-09-24 01:21 EDT — correctness gates verified; provider credits still blocking

- The active thread reported that full repository lint passed after the runner changes.
- The active thread reported that the full pytest suite passed after the runner changes.
- Source inspection confirmed implementations and focused tests for sealed-profile verification,
  durable call checkpoints, idempotent resume, balanced panel validation, and matched private
  deliberation.
- The six-species roster remains `config/anes2012-live-smoke-swarm.yaml`.
- The replacement credential is stored only in ignored `.env`, authenticated successfully, and is
  not reproduced in this report.
- The provider credit endpoint still reports approximately `-$0.481481` available.
- No second model request was attempted. The paid phase remains `BLOCKED_PROVIDER_CREDITS`.
- No live prediction, transcript, treatment effect, or scientific result was produced by this
  checkpoint.

### 2026-09-24 01:27 EDT — key-limit/account-credit reconciliation

- Both provider status endpoints authenticated with HTTP 200 using the currently loaded credential;
  no credential text was logged.
- `/api/v1/auth/key` returned `limit: 50`, `usage: 0`, `limit_remaining: 50`, and
  `is_free_tier: false`. These are the spending limit and usage for this API key, not the account's
  available funded balance.
- `/api/v1/credits` returned `total_credits: 65489.0` and
  `total_usage: 65489.481480779`. Their difference is `-0.481480779`, so the account remains
  unfunded for another paid request.
- The prior HTTP 402 occurred while the key-limit endpoint showed the same apparently healthy
  per-key values. The account-level credit result is therefore the controlling readiness signal.
- No model request was made during this reconciliation. The paid phase remains
  `BLOCKED_PROVIDER_CREDITS`.

### 2026-09-24 02:11 EDT — timing split and retrospective baselines completed

- The conditioning-field audit classified eight fields as strict-pre-election eligible and
  classified `discuss_disc` and `patriot_flag` as post-election.
- A strict-pre-election sealed profile set and a paper-faithful sealed profile set were generated,
  each with 5,914 respondents. The strict split contains eight fields; the paper-faithful split
  retains all ten and is marked ineligible for strict live forecasting.
- Six full-sample retrospective comparators emitted 25,128 prediction rows: one deterministic
  party-ID rule and five five-fold outcome-fitted logistic or categorical Naive Bayes models over
  4,188 valid two-party respondents.
- The best weighted Brier score in this baseline artifact was `0.076340` for the two-field
  party-ID-and-ideology logistic model. The strict eight-field logistic and Naive Bayes models
  recorded `0.076892` and `0.077047`, respectively. Their paper-faithful counterparts were
  slightly worse at `0.077907` and `0.078138`; this is a retrospective sensitivity result, not
  permission to use post-election fields at runtime.
- The baseline report correctly records `scientific_result: false`, `target_access_required:
  true`, and `runtime_eligible: false`. No hosted-model request was made.

### 2026-09-26 14:39 EDT — professional-code review checkpoint

- Both 5,914-row profile files independently passed the repository's runtime-manifest and split-seal
  verifier. Their profile and canonical seal hashes are recorded below.
- The complete repository suite collected and passed 256 tests with paid models disabled and the
  pytest cache disabled. Ruff, JavaScript syntax checks, `git diff --check`, and an isolated wheel
  build also passed.
- The new baseline test exercises model production, out-of-fold row counts, target omission from
  prediction artifacts, and policy comparison. It does not test cryptographic manifest/split-seal
  rejection, and the baseline entry point does not invoke the existing sealed-profile verifier.
- Logistic dummy columns and Naive Bayes vocabularies are currently derived from the full feature
  frame before fold fitting. Outcomes remain out of fold, but fold-local preprocessing (including
  an unknown-category path) would make the cross-fitting claim stricter and easier to defend.
- No runner, CLI, test, configuration, dashboard, credential, model-provider, commit, or push action
  was taken during the code checks. The subsequent read-only provider status check is recorded
  separately below.

### 2026-09-26 14:40 EDT — provider status regressed to unauthorized

- A read-only check sent no model request and printed no credential material.
- Both `/api/v1/auth/key` and `/api/v1/credits` returned HTTP 401 using the credential currently
  loaded from the ignored local `.env`.
- The current paid-phase state is therefore `BLOCKED_PROVIDER_AUTH`. Even after authentication is
  restored, account funding must be checked again because the last authenticated credit result was
  approximately `-$0.481481`.
- No model request, prediction, transcript, charge, treatment effect, or scientific result was
  produced.

### 2026-09-29 15:29 EDT — readiness recheck remains blocked

- The credential currently loaded from ignored `.env` remains configured, but both
  `/api/v1/auth/key` and `/api/v1/credits` returned HTTP 401. No credential material was printed.
- No repository source changes or new commits were present after the 2026-09-26 review checkpoint.
- All 23 focused ANES society, baseline, and viewer tests passed with paid models disabled. Ruff,
  JavaScript syntax, and `git diff --check` also passed.
- The engineering path remains ready for an offline/preflight gate, but the paid live experiment is
  not executable until provider authentication is restored and account credit is revalidated.
- No model request, provider charge, prediction, transcript, or scientific result was produced.

### 2026-09-29 15:31 EDT — Docker boundary revalidated

- Docker Engine `29.7.2` is available and the existing `psbx-anes-society:local` image resolves to
  `sha256:dc27f7fa8dbc1f3cd109cff855fe8189d5e5e5e2d29de739928f47a10be07703`.
- A fresh provider-free smoke completed inside a no-network, read-only-root container with all
  capabilities dropped, `no-new-privileges`, bounded PIDs/memory/CPU, a read-only strict-profile
  mount, and a separate writable output mount.
- The smoke emitted 24 sealed prediction rows and two interaction summaries for one matched
  12-profile replication. Post-container evaluation verified the prediction seal and balanced
  treatment coverage. It remains explicitly labeled `scientific_result: false`.
- The infrastructure doctor still reports `existing_llm_execution_location: host` and
  `existing_full_swarm_isolation: false`. The Docker path is therefore ready for sealed
  provider-free validation, but the hosted-model runner is not yet executed inside that boundary.
- The container emits a non-blocking Matplotlib cache warning because its home directory is
  read-only; setting `MPLCONFIGDIR` to the existing writable `/tmp` mount would remove the warning.

### 2026-10-04 19:21–21:12 EDT — Ohio Docker run and bounded live smoke completed

- The new Docker path completed `anes2012-ohio-20261004` with network disabled, a read-only root,
  non-root execution, all capabilities dropped, `no-new-privileges`, bounded resources, read-only
  sealed profiles, and a separate writable output mount. `MPLCONFIGDIR=/tmp/matplotlib` removes the
  earlier read-only cache warning.
- The structural run selected 226 Ohio profiles, of which 164 had valid two-party targets. Thirty
  matched replications emitted 13,560 provider-free prediction rows. Weighted Brier scores were
  `0.105333` for independent and `0.116824` for society; these are descriptive mock-engine values,
  not evidence about live-model performance or a treatment effect. National ANES weights are not
  calibrated to the Ohio subset.
- The first live Ohio attempt selected a retired Claude model and stopped on HTTP 404. The second
  completed 30 of 36 logical calls before a Llama worker repeatedly returned an invalid final
  ballot; neither attempt was scored as complete.
- `anes2012-ohio-live-20261004-v3` then completed with GPT-4.1 mini, GPT-4o mini, Claude Haiku 4.5,
  and Gemini 2.5 Flash-Lite. It recorded 24 completed logical-call checkpoints, 16 deliberation
  rows, eight sealed final ballots, and balanced four-profile coverage in both arms. One JSON retry
  produced 25 provider reservations, all reconciled in this run.
- Only three profiles had valid two-party targets. Both arms had 100% weighted agreement; weighted
  Brier was `0.06547967` for independent and `0.08896300` for society. With one replication and
  three scorable observations, these values are non-powered pipeline evidence and must not be
  described as a treatment estimate or scientific result.
- Across the three Oct. 4 live attempts, 72 provider reservations reported `$0.00880242` total
  usage. One reservation in the first attempt remains unreconciled. Provider calls ran on the host,
  without tools or an evidence pack; model weights were not temporally isolated to the 2012 cutoff.
- Repository verification passed: 256 tests with paid models disabled, Ruff, both JavaScript syntax
  checks, `git diff --check`, Docker Compose configuration validation, and image-ID verification.
- Review found four scale-up blockers: the area script persists target-inclusive
  `private-area-source.csv` beside shareable run outputs; the successful live run depends on
  ignored run-local scripts/catalog data; the live evaluation is rewritten outside the core
  evaluator and is not cryptographically sealed to the prediction seal and evaluator version; and
  the Docker base image/dependencies are not digest/lock pinned. These do not invalidate the smoke,
  but they should be resolved before a larger paid or publication-facing study.

### 2026-10-04 21:49–23:55 EDT — protocol bug corrected; sealed live dialogue pilot completed

- Review of the earlier live attempts found that `complete_turn` forwarded the experiment system
  instruction to Anthropic but not to OpenRouter or other OpenAI-compatible routes. The intended
  cutoff/date and role instruction was therefore absent from those requests. The earlier v3 smoke
  remains valid as pipeline evidence but is not a protocol-faithful replication.
- The runner now forwards the system message without mutating caller history. OpenRouter JSON mode
  is opt-in through the model configuration, and the live contract binds the system-prompt hash,
  worker model names, temperature, token limit, and JSON-mode setting. Tests cover both forwarding
  and provider JSON parameters.
- The core evaluator now derives its engine label from the verified prediction seal, rejects
  mismatched prediction provenance, and emits an evaluation seal binding the prediction-seal file,
  predictions, targets, evaluator source, and report. The comparison artifact is separately sealed
  to the evaluation seal and analysis source. This closes two of the prior quality findings.
- Two preceding dialogue attempts were preserved but excluded: one stopped after 98 completed
  logical calls when Gemini repeatedly returned invalid ballot JSON, and the next failed on its
  first provider call. Neither was scored as a completed panel.
- Corrected run `anes2012-ohio-live-dialogue-corrected-20261004` used GPT-4.1 mini, GPT-4o mini,
  and Gemini 2.5 Flash-Lite, with four workers per model, two matched replications, 12 profiles per
  replication, two rounds, and eight strict pre-election fields. The draws happened to contain 24
  unique respondents; 22 had valid two-party targets.
- The run completed 144 logical/provider calls: 48 private reflections, 48 public messages, and 48
  private ballots. It recorded no format retry, failed checkpoint, or unreconciled reservation.
  Provider-reported cost was `$0.01765025`.
- Weighted mean agreement was `0.825762` independent versus `0.665297` society. Weighted mean Brier
  was `0.11673581` independent versus `0.14847838` society. The two replication-level Brier changes
  disagreed in sign (`-0.00211416` and `+0.06559930`); four of 24 binary predictions changed, and
  mean absolute probability change was `0.0729167`. These are descriptive pilot values, not a
  powered treatment estimate.
- Full offline verification passed: 260 collected tests, Ruff, both JavaScript syntax checks,
  `git diff --check`, and independent regeneration/verification of the comparison seals.
- Remaining operational gaps: the Docker base and Python dependency set are still not pinned; the
  live provider calls remain host-side rather than inside the container boundary; target-inclusive
  `private-area-source.csv` remains mode `0644` beside run output; and the new runner, config,
  analyzer, and ANES implementation/tests are still untracked working-tree files. A clean checkout
  cannot reproduce the pilot until the owner records them in version control or an equivalent
  immutable bundle. Provider catalog and worker snapshots are also ignored artifacts rather than a
  committed, sealed dependency input.

### 2026-10-11 04:38–08:02 EDT — respondent-context factorial and limited-network pilot

- The new preparation path created 5,914 label-decoded profiles from 20 audited pre-election
  fields. Vote, health-law, and gun-policy targets are absent from the runtime allowlist and stored
  separately in a mode-`0600` file under a mode-`0700` evaluation vault. Runtime profiles,
  checkpoints, cohort files, and the run directory also have restrictive permissions. This closes
  the target-inclusive staging issue for the new experiment, though the older Ohio structural run
  still retains its `0644` private staging CSV.
- The live cohort contained 24 Ohio respondents not found in earlier call checkpoints and whose
  recorded pre-election baseline date followed the two dated evidence documents. The historical
  pack is explicitly a narrow economy-focused supplied-context treatment, not evidence of personal
  exposure or a balanced campaign archive. The Fed source bytes are retained; the BLS excerpt has
  official provenance text but no retained source snapshot.
- A matched 2×2 comparison crossed sparse/rich profiles with no evidence/fixed evidence, using the
  same respondent-model assignment and two stochastic repeats. All 192 independent calls completed
  without missing predictions. Vote scoring covered 18 unique respondents; the two held-out
  pre-election policy items covered all 24.
- Half-scaled multiclass Brier scores for vote were `0.106901` sparse/no-evidence, `0.134875`
  sparse/evidence, `0.089928` rich/no-evidence, and `0.103553` rich/evidence. Richer profiles without
  supplied evidence improved vote Brier by `0.016973` on this cohort, but health-law Brier worsened
  by `0.010042`. The evidence pack worsened vote Brier in both profile conditions. These are
  exploratory development contrasts with multiple comparisons, national survey weights on a state
  subset, and no complex-survey inference.
- A predefined first-12 subset then compared a synthetic directed three-neighbor network with an
  equal-activity, equal-call private-reflection control. Twelve public messages and twelve private
  reflections preceded 24 final predictions. Social versus private Brier was `0.108627` versus
  `0.090723` for vote, `0.254590` versus `0.291924` for health law, and `0.365767` versus `0.419940`
  for gun policy. Gun-policy agreement nevertheless declined, so probability loss and modal
  accuracy must not be conflated; no general swarm improvement is supported.
- The complete experiment used 240 provider calls at `$0.04662035` reported cost, with no retries,
  invalid responses, or unreconciled reservations. Modern model weights remain historically
  unisolated and provider execution remains host-side with tools disabled.
- Integrity improved materially: the contract binds profiles, field audit, cohort, prior-ID
  exclusions, evidence pack, exact workers, catalog/pricing snapshot, provider/model runner, and
  experiment sources. Prediction seals bind checkpoint snapshots; the interaction seal also binds
  the network plan and transcripts. Evaluation and summary seals verified independently.
- Verification passed: 271 collected tests, Ruff, JavaScript syntax checks, `git diff --check`,
  result-summary regeneration, restrictive-permission checks, held-out-field inspection, and all
  contract/prediction/evaluation/summary seals.
- Remaining production blockers: every new decision-context source/config/protocol/test file is
  still untracked, so a clean checkout cannot reproduce the work; the live process is not inside
  the Docker isolation boundary; the base image and Python dependencies are not durably pinned; and
  test coverage does not yet exercise end-to-end Stata preparation or pre-contract recovery from a
  tampered partial preparation. The latter is fail-closed at scoring, but could waste paid calls.

### 2026-10-12 21:10–2026-10-13 00:10 EDT — reserved-cohort validation started

- Run `anes2012-ohio-reserved-validation-20261012` freezes 120 previously unprompted Ohio
  respondents for the current development validation and records 50 additional respondent IDs as a
  reserve. The reserve is not mounted into either Docker stage and is not sent to model providers.
- The design compares sparse and rich profiles without the earlier historical pack, with two
  stochastic repetitions and fixed balanced assignments across GPT-4.1 mini, GPT-4o mini, and
  Gemini 2.5 Flash-Lite. The planned panel is 480 logical calls; the retry-aware ceiling is 960
  requests and `$5`, while preflight estimated a conservative maximum of `$1.876992`.
- The local validation image is recorded as
  `sha256:2847425865f4b0b93449e98a72b62d642be548704b8c8f14db23b181eea4f25d`.
  Offline prompt planning passed the saved checks for non-root execution, no active non-loopback
  interface, no provider credential, no forbidden target/vault/socket path, read-only root and
  input mounts, and `NoNewPrivs`. The container does not perform remote inference: a trusted host
  broker sends only the frozen prompts, and a second offline Docker stage is planned to reconstruct
  the jobs and validate matched response coverage before the target vault is opened.
- Provider readiness authenticated. The saved account values imply approximately `$864.366869`
  available (`66489` total credits less `65624.633131408` usage); the key endpoint reported
  approximately `$49.91555003` remaining. No credential text is recorded here.
- At the 00:10 EDT checkpoint, the active process had 131 reconciled provider reservations and
  three in-flight or otherwise unreconciled reservations, with `$0.02027805` provider-reported
  cost. Durable checkpoint counts were 89 Gemini, 38 GPT-4.1 mini, and four GPT-4o mini. This
  substantial worker skew is being coordinated with the execution owner as a possible provider
  stall; it is not an outcome and must not be used for interim scoring.
- Focused read-only verification passed 17 decision-context/reserved-validation tests, Ruff on the
  new runner and test, and `git diff --check`. No contract-bound source, image, prompt, cohort, or
  active run artifact was modified by the review. The new runner, protocol, test, and validation
  Dockerfile remain untracked, dependencies remain range-specified, and the contract contains
  absolute checkout paths; clean-checkout and portable reproducibility therefore remain blocked.

### 2026-10-13 03:45 EDT — reserved-cohort validation completed and independently checked

- All 480 frozen logical calls completed with valid first-format predictions: 160 durable
  checkpoints for each of GPT-4.1 mini, GPT-4o mini, and Gemini 2.5 Flash-Lite. The initial broker
  process ended after provider read timeouts; same-contract resume reused 202 completed responses
  without changing prompts, assignments, arms, or targets.
- The final ledger contains 482 request reservations: 480 reconciled provider responses and two
  unresolved usage records from the timeout path. Confirmed provider-reported cost is `$0.0836825`;
  that value excludes any eventual charge for the two unresolved requests and is not an exact final
  bill.
- Scorable respondent counts were 84 for vote, 116 for health law, and 120 for gun policy. Weighted
  half-multiclass Brier changed from `0.147859` to `0.145513` for vote, `0.276586` to `0.282043`
  for health law, and `0.279448` to `0.288865` for gun policy. The equal-task rich-minus-sparse
  change was `+0.004176`; its exploratory respondent-bootstrap interval was
  `[-0.009541, +0.017883]`.
- The predeclared gate failed: the rich profile did not improve average Brier by at least `0.005`,
  and its interval did not exclude zero in the improving direction. The result provides no evidence
  of a general benefit from this twenty-field bundle, but the interval also does not establish
  general harm. Agreement fell on every target; policy repeat stability improved, and gun-policy
  aggregate distribution distance improved despite worse individual scoring. These metrics answer
  different fidelity questions and must not be collapsed into one success label.
- The separate 50-ID reserve had zero overlap with prompt jobs or predictions. It remains a limited
  future confirmation resource and should not be opened repeatedly while optimizing on the current
  120 development cases.
- The offline validation container reconstructed the frozen prompts, verified the complete matched
  panel, and sealed predictions before host evaluation opened targets. Independent review verified
  the contract; six canonical seals; every completion and source-archive binding; both Docker
  inspections (`network=none`, read-only root, `cap-drop=ALL`, `no-new-privileges`, exactly two
  mounts); and zero reserve overlap.
- Independent verification passed all 278 offline tests with paid models disabled, full Ruff,
  JavaScript syntax checks, and `git diff --check`. No experiment or product source was edited by
  the quality review; only this status log was updated.
- Remaining blockers are operational rather than a reason to reinterpret the result: all new
  validation source/protocol/test/Docker artifacts remain untracked; the contract uses absolute
  paths; dependencies are range-specified; remote inference still uses a trusted host broker; two
  usage records are unresolved; and worker exceptions surface only after other submitted workers
  finish. The current evaluator also hard-codes `% 3` for model subgroup mapping and should use the
  actual worker count before any roster change.

### 2026-10-20 14:57 EDT — individual development comparison completed and independently checked

- Run `anes2012-ohio-individual-development-20261020` compared four individual-agent conditions
  for 24 previously inspected Ohio development respondents, two repeats, and one GPT-4.1-mini
  model: sparse direct, rich direct, focused direct, and focused with a private evidence review.
  Simple baselines were fit on a disjoint set of 96 development respondents; the 50-person reserve
  had zero overlap with evaluation, training, prompts, or predictions.
- All 240 planned logical calls completed on their first valid format attempt: 192 final forecasts
  and 48 private reviews. Provider-reported cost was `$0.0929464`, with zero unresolved usage
  records. Six reviews exceeded the requested 80-word preference, with a maximum of 86 words, so
  the reviewed condition must not be described as strictly length-matched cognition.
- Equal-task weighted half-multiclass Brier was `0.27166` for rich direct, `0.25996` for focused
  direct, and `0.26601` for focused plus review. Focused-minus-rich was `-0.01170`, but its paired
  respondent-bootstrap interval was `[-0.04104, +0.01600]`; the predeclared development signal
  gate therefore failed. The party-smoothed baseline scored `0.25009`, best overall. Private review
  did not improve the focused condition.
- The apparent focused gain came mainly from gun-policy prediction. Vote and health-law scores
  slightly regressed, gun-policy response distributions remained badly mismatched, and focused gun
  forecasts were overconfident relative to their accuracy. These diagnostics support ablation and
  calibration work on development data, not a claim of a validated individual-agent improvement.
- Independent review recomputed all 285 completion bindings with zero missing or mismatched files,
  counted 240 durable JSON checkpoints, found no credential-pattern hit in the bound run files,
  and confirmed that no reserve respondent was used. Full verification passed 296 tests with paid
  models disabled, Ruff, Python compilation, and `git diff --check`.
- Each prompt worker ran in a fresh network-disabled, no-mount, non-root, read-only container with
  dropped capabilities and `no-new-privileges`; remote inference and the trusted host broker remain
  outside that image. Clean-checkout reproduction is still blocked because the worker Dockerfile,
  protocol, runner, audit/plot scripts, and tests remain untracked. The evaluated cohort was already
  inspected, only one model and two repeats were used, and national weights are applied within a
  small Ohio subset. The reserve should remain closed while profile ablations and calibration are
  developed.

### 2026-10-20 20:59 EDT — full development-cohort profile ablation completed and checked

- Run `anes2012-ohio-profile-ablation-development-v1` completed 960 forecasts for the 120
  previously inspected Ohio development respondents across original sparse, original rich,
  reduced existing, and reduced-plus-observed profiles, with two repeats and one model. The
  separate 50-person reserve had zero overlap with preparation, fitting, prompts, predictions, or
  evaluation and was not opened.
- Direct equal-task weighted half-multiclass Brier was `0.23786` for original sparse, `0.23778`
  for original rich, `0.23871` for reduced existing, and `0.23184` for reduced plus observed. The
  reduced-plus-observed point estimate improved on reduced existing by `0.00686`, but its paired
  interval was `[-0.01867, +0.00350]`. Removing rich-profile fields changed Brier by `+0.00092`,
  with interval `[-0.00944, +0.01127]`. Both intervals cross zero; no improvement or equivalence
  is established.
- Five-outer/four-inner-fold hybrid calibration excluded each evaluated person's outcomes from
  fitting and parameter selection. The best hybrid point estimate was `0.22235` for original rich,
  while the party baseline remained best at `0.22087`. Hybrid-versus-party intervals crossed zero
  in every arm. The conditional intervals hold fitted calibration fixed and are exploratory, so
  they do not support promotion.
- Provider accounting reconciles all 960 requests at `$0.6672136`, with no unresolved usage. Two
  Docker startup timeouts occurred before provider calls at 154 and 880 saved forecasts; same-
  contract resume completed without duplicate paid requests. Each prompt was generated in a fresh
  network-disabled, no-mount, non-root, read-only Docker worker with dropped capabilities and
  `no-new-privileges`; the trusted host broker and remote inference remain outside that boundary.
- Independent review recomputed all 988 completion bindings with zero missing or mismatched files,
  counted 960 checkpoints, found no credential-pattern hit in 984 scanned run files, confirmed
  zero reserve overlap, and verified that all direct scores matched independent recomputation.
  The full 309-test suite passed with paid models disabled, together with Ruff, Python compilation,
  JavaScript syntax, `git diff --check`, a wheel build, and a successful aggregate-only API smoke
  check exposing 48 metric rows and no respondent-level data.
- No critical correctness or security defect was found, and no source repair was needed. The main
  production blocker remains durability: the new Dockerfile, runner, worker, tests, audit and
  diagnostics scripts, dashboard endpoint, result documents, and this status report are untracked,
  while frozen contracts and seals contain absolute checkout paths. Clean-checkout reproduction is
  therefore not established. The cohort is development data previously inspected by researchers;
  national weights within an Ohio subset, one model, two repeats, and exploratory multiple
  comparisons limit interpretation. The reserve should remain closed pending an immutable revision
  and clean-checkout Docker verification.

## Evidence register

Hashes below were independently recomputed from the named files at the report timestamp unless a
note says otherwise.

| Evidence | SHA-256 | Notes |
| --- | --- | --- |
| `data/runs/anes2012-society-official-structural/anes-society/runtime/manifest.json` | `8225d79d914c0183c36e9b1353838ca5c9df85b05c0a527a49dca67ec22d7f0c` | Declares 5,914 profiles, official weighting, cutoff, timing, and profile fields. |
| `data/runs/anes2012-society-official-structural/anes-society/runtime/profiles.jsonl` | `0fd722cc19af1b04770d11266b6828424de6719f02c59facf76ff79bc5d2e577` | 5,914 lines; matches the runtime manifest and split seal. |
| `data/evaluation-vault/anes2012-society-official-structural/targets.csv` | `e158ddc1be3bb9843058cc90f3d4cc14663fdc2254fd45a11fe4e68970ffa803` | 5,914 data rows plus header; matches the split seal. |
| `data/runs/anes2012-society-official-structural/anes-society/split-seal.json` | `52e6584be38a44ff396e9335258345bd31c21af8dc77c8b305011d543d4d8925` | File hash. Its internal canonical `seal_sha256` is `902d65ffd255dc6ca8f6e9d385858c659ce4387803f34cdf42a3064631d25ac6`. |
| `data/runs/anes2012-society-official-structural/anes-society/container-output/predictions.jsonl` | `1e38b6f50210371a52de99180120969a558621ca87893c1c99c7650b8df69411` | 1,200 lines; matches the prediction seal. |
| `data/runs/anes2012-society-official-structural/anes-society/container-output/interaction_summaries.jsonl` | `af789ffb28d3b423c13566c9acb430485f104bd49a7532da3d1a9c7e842c6957` | 150 lines; matches the prediction seal. |
| `data/runs/anes2012-society-official-structural/anes-society/container-output/prediction-seal.json` | `6132fc83cfbc1a29c00ad0d63e6d2b8e782f536ab563bd6c03b656da9a3918f6` | File hash. Its internal canonical `seal_sha256` is `24c7399577f0087ac489606571c7cc52349918e654e373a277b35e834ee20e0b`. |
| `data/runs/anes2012-society-official-structural/anes-society/container-output/evaluation.json` | `ee82c6a58d268912bf399af4220cfdf42307515e6b1e52d2df98268fba07b413` | Explicitly records `scientific_result: false`. |
| `data/runs/anes2012-live-vote-smoke-6/spend_ledger.json` | `541cf73f223fcce1f90c879ad95ee9ca5ec63111f9326dcc6b1240d62128d3f7` | One unreconciled local reservation; `reported_usage: null`. |
| `src/psbx/experiments/anes_society.py` | `73c465b35bb34d5ae84e6b92e26ffcd55067b394ea80c2148c8982ea8ff3e3b5` | Hardened live runner at the 01:21 EDT checkpoint. |
| `tests/test_anes_society.py` | `a87beebe685470d6646fea7406c3557c8956fa9f00cdcf1eefe717cf67cdc70e` | Focused hardening and resume tests at the checkpoint. |
| `config/anes2012-live-smoke-swarm.yaml` | `60d2d41d9899f5cb4d4f157b6ade83dbf5beda84f6167bfa974f3d0f3828b6f8` | Six-species smoke roster; no credential material. |
| `config/anes2012-paper-faithful.yaml` | `b41edd81668ba059d187d6f4f52a19338972e5420f7781397287974bc0ba0fc6` | Ten-field retrospective/paper-comparison policy; includes two post-election fields by design. |
| `config/anes2012-strict-pre-election.yaml` | `8ebcbe9f1251e708b9198b182b50048639c182907602ac8d43626bf85d56abee` | Eight-field strict live-treatment policy. |
| `data/runs/anes2012-paper-faithful/anes-society/conditioning-field-timing-audit.json` | `f8191cf9e0dec6ce3f805eb53185daa5f340c9cd7f71ce354552574f2e4bc652` | Marks `discuss_disc` and `patriot_flag` as post-election. |
| `data/runs/anes2012-paper-faithful/anes-society/runtime/profiles.jsonl` | `60719961dd3ead6474172f06387ab4fddb20da2d2b526682bc966327660bae09` | 5,914-row paper-faithful profile set; canonical split seal `634089e82c8842879ac00e28f3c4df4b8d639f99eb388bb331ec282a13cfd7b4`. |
| `data/runs/anes2012-strict-pre-election/anes-society/conditioning-field-timing-audit.json` | `5c949f259f412aed7adb30f312d0de04790cb5d7e7951cfdf6ca70d14a1e162f` | Eight audited fields, no post-election fields. |
| `data/runs/anes2012-strict-pre-election/anes-society/runtime/profiles.jsonl` | `4a96e41283c05a5099a515d64854bad41b9bc292db618b1d4f97d197a2f48778` | 5,914-row strict profile set; canonical split seal `210ee53ab74ec6c40db8daccddb52ea1d1deb723f858bf21ccc51498b98aabe7`. |
| `data/runs/anes2012-strict-pre-election/anes-society/statistical-baselines.json` | `c2a0568359bfd30cb9c8482d7e448af54ade85a5674a7c5f814a03be6d0a6101` | Six retrospective comparators for 4,188 valid two-party respondents. |
| `data/runs/anes2012-strict-pre-election/anes-society/statistical-baseline-predictions.jsonl` | `78dce506d196e7e4f1f8b02e00fe295b1771ca71d470fa04e145c58ee4137204` | 25,128 prediction rows without observed targets. |
| `src/psbx/experiments/anes_baselines.py` | `63d2328931dd18c3ed6765d4bafe072bf02f96d405a1e2c61afc8c17adc2d832` | Retrospective baseline implementation at the review checkpoint. |
| `tests/test_anes_baselines.py` | `9ac296be01f401c5a6c39e8542e0eea2dbae76a54d7866312bd34249c2d7f706` | Current focused baseline test; cryptographic input rejection is not yet covered. |
| `Dockerfile` | `1f7d285811735ef3f67b9f0eeae420735dbf6e32163b317f31f052a3045bf770` | Hardened Ohio area container; base image and dependencies remain unpinned. |
| `compose.yaml` | `c6a8ebffe15ded5f4bdb4e330934ea67850edf740e50190413c84d8ad2efee7f` | Network-disabled, non-root, read-only-root structural service. |
| `README.Docker.md` | `262748761bfa177fb14b403eed4d67e5802737bb9caddc6b86984123329a6161` | Correctly distinguishes structural mock validation from live-model inference. |
| `scripts/run_anes_area.py` | `01f0d38499d1acecc171c1a9ef8fb6595ac1944839f4a1197e11206976bb9ea9` | Area-run orchestrator; target-inclusive staging placement needs hardening. |
| `experiments/anes-2012-silicon-society/logs/CHECKPOINTS.md` | `f824c039cf88dc3efce393ed3a710d12b9fbd4651b26683d6669903055c5f4d9` | Contemporaneous structural and live-run log through Oct. 11. |
| `data/runs/anes2012-ohio-20261004/run-manifest.json` | `ce2c79d3a184534b78af216172475fe9fa21c56f7d61a5c22acb051d998ccfe2` | Ohio provider-free Docker run manifest. |
| `data/runs/anes2012-ohio-20261004/evaluation.json` | `8f31b81b970273009472ba48424e07c311a9a6e3022089dd768cdc896a811ee4` | Thirty-replication structural evaluation; `scientific_result: false`. |
| `data/runs/anes2012-ohio-live-20261004-v3/anes-society/run-contract.json` | `40aa8b30e2c5755f0679014ddd27148a01334326373ec7bd51ca3a143197c38b` | Completed four-model matched live-smoke contract. |
| `data/runs/anes2012-ohio-live-20261004-v3/anes-society/prediction-seal.json` | `5fe81937e0c662fb98be8bdfe120895b2523e762124b8a97cb08283bd9a4d096` | File hash; its recorded artifact hashes and canonical seal verify. |
| `data/runs/anes2012-ohio-live-20261004-v3/evaluation.json` | `f151f711999e21c60ad41e59795e166c2fdc9b39ccdbc1c0dbbd92dfc8afa3d7` | Three-scorable-profile live-smoke evaluation; not a powered result. |
| `data/runs/anes2012-ohio-live-20261004-v3/spend-summary.json` | `c5e81fa6f62186afd932fef44201256271d1e06a2898295aa03b427da7b19285` | 25 reconciled provider reservations for the completed v3 run. |
| `config/anes2012-ohio-live-dialogue-json.yaml` | `ec31f10ca10c4bc34eebc426c3a5219c7e73a3504cfdc266f620817e95d3ffc9` | Corrected two-replication JSON-mode pilot config; currently untracked. |
| `scripts/run_anes_live_dialogue.py` | `9e434f2379bd0f834563637a06e4c09f5d9afc3be28a69e3a2377856698c692a` | Live readiness, catalog resolution, contract, run, and evaluation entry point; currently untracked. |
| `scripts/summarize_anes_dialogue.py` | `a068bc09e7b754b1adfce095e5fa62fcdc444b7262edee83c16ca23b7dd859e8` | Seal-verifying paired comparison generator; currently untracked. |
| `src/psbx/agents/runner.py` | `a69df301f13bc1a28a55faad504761119b4678f8bca792ee2fdf3eb77dd53cb4` | Forwards system instructions to OpenAI-compatible routes. |
| `src/psbx/openrouter.py` | `8f96e02dd909e9796a912ba1625755bbab319cd0b93109380be19d5a2e4188fa` | Supports provider-enforced JSON-object output. |
| `src/psbx/experiments/anes_society.py` | `e319d1b06f93aedffd8ddd722a3772a9aac8ab99bbc626cf7eb8bfe038d55076` | Live contract, matched arms, provenance validation, and evaluation sealing; currently untracked. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/anes-society/run-contract.json` | `5bc50d9c1cf38e7c4b7d8f9d68582dd3d5b67372ed5dab2971c498c24fb3cec4` | Seals the corrected prompt and worker/runtime settings. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/anes-society/prediction-seal.json` | `6c57861c851d3296ef12081b3c02a38c87fb93c3f0a21c2b77a934e8d9115da4` | Verified artifact hashes, engine, contract, balanced coverage, and spend reconciliation. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/evaluation.json` | `3ca9432b3f8a3288df7d428e078383f6ba5c5d810d70619553f7744b710df063` | Corrected 22-scorable-profile evaluation; `scientific_result: false`. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/evaluation.seal.json` | `4e370f02dfcb6771bfb6aba406e9e15e73a817930093d7063583b5e3b004de21` | Binds evaluator source, targets, predictions, prediction seal, and report. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/comparison.json` | `9b0ce2e724f285eb35a15755e0ed9f7c27d09929e73ee7baa9ba6ec86bab7986` | Descriptive paired metrics and provider accounting. |
| `data/runs/anes2012-ohio-live-dialogue-corrected-20261004/comparison.seal.json` | `4e3a86e29d45a7c48ef889ca961ad95221b447bdc3a9589006368692fdf69ed9` | Binds comparison output to the evaluation seal and analyzer source. |
| `docs/ANES_DECISION_CONTEXT_PROTOCOL.md` | `f324165c31fb17a16bf84bdfc9ed3efc1df657b49f88f91ac116e63d3a7c1afe` | Development protocol and interpretation boundaries; currently untracked. |
| `config/anes2012-decision-context.yaml` | `5a206a8b2944e3711f3c21297a0875e695e5e7da295d2c1f946216cd3aa1314f` | Factorial and limited-network design; currently untracked. |
| `config/anes2012-historical-pack.json` | `a2fd36c2ef24634116043b48cccee2410ec175694b37657100b20299f1d7cbb8` | Two-document economy-focused historical pack; currently untracked. |
| `src/psbx/experiments/decision_profiles.py` | `86aeb819f6d7d1a4729fc41b2253c774b13331e0fc252d42add66538dadf36e5` | Audited profile/vault builder; currently untracked. |
| `src/psbx/experiments/decision_experiment.py` | `a123d9d7c89899e26c0a4e663d9e559dde3c3d6e633d514b2074922e7f21db37` | Factorial, interaction, checkpoint, seal, and scoring runner; currently untracked. |
| `tests/test_decision_context.py` | `2fd7f400aa277bd8146a5fa473f9f56d1cada6312a2401c7afe50b3cd8348d72` | Eleven focused decision-context tests; currently untracked. |
| `scripts/summarize_decision_context.py` | `9ed9623641aaa27b8fe83e19da635579eb576f6cccb4e95d829d31a992298277` | Verifies sealed evaluations and emits stability/accounting summary; currently untracked. |
| `data/runs/anes2012-decision-context-20261011/contract.json` | `211f6bf972c206cd1f284db8e569435c9ab6b0b0e365da31c81b1b2f9065b68c` | Binds all design inputs, exact workers/catalog, and runtime sources. |
| `data/runs/anes2012-decision-context-20261011/profile-seal.json` | `a6af02329a4a2632f8d6e6ddc5ed8a261db6406a611d4985452dd05ca6c20b24` | Seals 5,914 profiles, field audit, private targets, source, and pack. |
| `data/runs/anes2012-decision-context-20261011/independent-prediction-seal.json` | `0c2fa80f784df04bb2cafbac0bedae575d98158cea3e88045c4a6d69063641fa` | Seals 192 factorial predictions and checkpoint snapshot. |
| `data/runs/anes2012-decision-context-20261011/independent-evaluation.json` | `c9fde410c09e1170dabdb56d86cb7745dbd65bf6c750015e11ddb60f2582a3ac` | Independent factorial metrics and exploratory contrasts. |
| `data/runs/anes2012-decision-context-20261011/interactions-prediction-seal.json` | `ba4199459d0e88923a061949ba8e43a421dd5a48674b02a6abd6b7fbbc948bf0` | Seals 24 interaction predictions, cumulative checkpoints, network, and transcripts. |
| `data/runs/anes2012-decision-context-20261011/interactions-evaluation.json` | `48ca82b151649ccae144a03180432a43d4a47297ebf4dc2760cf8e74d971c225` | Limited-network versus private-matched descriptive metrics. |
| `data/runs/anes2012-decision-context-20261011/summary.json` | `0d77d5ae4326ea9a684230bec36c339fef7f62ed17eb1fad7b0a460346d48bc0` | Combined sealed metrics, repeat stability, dialogue counts, and spend reconciliation. |
| `data/runs/anes2012-decision-context-20261011/summary-seal.json` | `64d037b8fcbf76209829a81afe3e949b0b474e6107434bc5475147b4a6ee3625` | Binds both evaluation seals, transcripts, spend ledger, summary, and analyzer source. |
| `Dockerfile.validation` | `66d02bedb9b5f9299cfd6e6d55dd6c058ebc57b5a148d4e0fdb233c263f66a2c` | Thin validation image layer over the locally retained dependency image; currently untracked. |
| `docs/ANES_RESERVED_VALIDATION_PROTOCOL.md` | `f63778dafeb7fad4fb03c8009e3403622b221e9c73eb86295cf392f527876688` | Pre-call design and Docker/trusted-host boundary description; currently untracked. |
| `src/psbx/experiments/reserved_validation.py` | `2cc401b05b01bbb33be3f3b4c7afa1422fc9d098fd14582a727bb7675ee3b611` | Frozen planner, host broker, offline validator, and evaluator source for the active run; currently untracked. |
| `tests/test_reserved_validation.py` | `e1eae6bf83ecacdc5feb4ae8070dc5b391be802b352029a0cd0934af1f1a6d18` | Focused determinism, panel-corruption, metric, and bootstrap tests; currently untracked. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/contract.json` | `70e8e908d2aec42217e4c414c4b122dd0abe5e0e195f126c26aacb8545bc2eb7` | Seals the cohort, reserve IDs, prompts, workers/catalog, image ID, upstream profiles, Dockerfiles, and runtime sources. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/output/jobs.json` | `5b3147e8d2ca5fba173c9b0f8f18a8fda7b02dad3678c9406016e938e07c6e5e` | Frozen 480-job panel emitted by the offline Docker planner. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/output/plan-isolation.json` | `104da04902dcb8fd041d78aed1ede21fb0779d5c1045506ea6da5094e1b232db` | Saved isolation-probe result for the planning stage. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/output/prediction-seal.json` | `697502381a33bf796b8f5776bfd1ef505df2b137c775fd010103c8f0b12dfd1d` | Seals the complete 480-row prediction panel and frozen jobs after offline Docker validation. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/prediction-boundary-seal.json` | `491872366e59cbb9eb6a6a25791b738fb9497e7b94ff71b4e31ae4e34ced8874` | Binds the contract, prediction seal, and three checkpoint logs before target access. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/evaluation.json` | `56f7c27b1d9d11459d3eca1037dab53d12085df292595ca787f55dac328a1f72` | Primary metrics, paired contrast, failed development gate, baselines, stability, accounting, and limitations. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/evaluation-seal.json` | `a930f08e14e38e2677993078ad50a6ec516a23069c1e08188832b94e0346d357` | Binds evaluation to predictions, targets, boundary seal, and frozen evaluator source. |
| `scripts/diagnose_reserved_validation.py` | `c1a4cd3f6766ff57176f762ba4f0568ed7b66d700c7c8ed022bee3198eb42a16` | Post-primary exploratory calibration and missing-field diagnostics; currently untracked. |
| `tests/test_reserved_diagnostics.py` | `fa0da34226ca44af2a186678d2e37ce3de8cbd55a4c76a4d83feff2bceaef5f8` | Focused weighted-calibration-bin test; currently untracked. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/diagnostics.json` | `bf5f797e5f095c15451f96e09f226086f697f4ed38f68dc602a3af1866417aa9` | Explicitly exploratory calibration, entropy, and profile-missingness diagnostics. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/source-archive-seal.json` | `14cb3ecb7c4ac8de1690efecdc5767a0246eb8b12d528508eee72853d9c7d0ed` | Binds retained snapshots of eight contract-bound source and Docker files; does not make absolute-path contracts portable. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/image-environment.json` | `62fc47ba0611e044031fb33ea8781f96c5d27226b1c91642dfc2f909b635a638` | Records the immutable image ID, 52 installed package versions, and matching in-image runner hash. |
| `data/runs/anes2012-ohio-reserved-validation-20261012/completion-seal.json` | `42be4cc385bb61c0405bfd55947fbf12ea9aab52f5539d1bcd16a165fa7a0590` | Binds the final evaluation, diagnostics, run logs, spend ledger, Docker evidence, source archive, and 278-test log. |
| `docs/ANES_INDIVIDUAL_DEVELOPMENT_PROTOCOL.md` | `109728db4c097c07deb5fc6d21744f244a25ccb45689b4bc55fc9926e9bc2147` | Pre-call individual-agent development design and interpretation boundary; currently untracked. |
| `src/psbx/experiments/individual_validation.py` | `9cbd638c557ef90ab4bca6a3fb92533b7db13888817a9049704fb92642c4c22b` | Frozen planning, broker, validation, baseline, bootstrap, and evaluation implementation; currently untracked. |
| `src/psbx/experiments/individual_worker.py` | `42af83d4b91c395ffa75a5c96a7a38f33cc2bc4e91e176aa057a206fbb0ece14` | Prompt worker with explicit per-condition field allowlists and review-memory boundary; currently untracked. |
| `tests/test_individual_validation.py` | `b85437a6cd91bf3100a3063fa6423df93959468e890f015b5e3f520ef643b7d9` | Focused cohort, field-boundary, review, panel, resume, and provider-failure tests; currently untracked. |
| `data/runs/anes2012-ohio-individual-development-20261020/contract.json` | `75cf5136237463c4fb280cf1bf3e00a10033fafbd49104b9ee9cfd470c952ec7` | Seals the development cohorts, four conditions, prompts, worker, model, upstream inputs, and runtime sources. |
| `data/runs/anes2012-ohio-individual-development-20261020/prediction-seal.json` | `3439162c42b811f493ce97e09a22ba3b739b2a1286c597685c8d92070a043d39` | Binds the complete 192-forecast panel, 48 private reviews, checkpoints, contract, and validation evidence. |
| `data/runs/anes2012-ohio-individual-development-20261020/evaluation.json` | `5eb8971367bc3f6a3dc60ba9e822add8a914fa2702dd0704621a98f4a823164a` | Primary weighted scores, paired contrasts, failed development gate, baselines, stability, accounting, and limitations. |
| `data/runs/anes2012-ohio-individual-development-20261020/evaluation-seal.json` | `e38dd99360750937387ec81489a472af048ca36252fa9279022fd74b5772d539` | Binds evaluation to targets, sealed predictions, contract, source, and environment evidence. |
| `data/runs/anes2012-ohio-individual-development-20261020/audit.json` | `007b6a910b6365cc2b7ab240b8429866144c5761c181ec062f6f878a731dc43c` | Independently reconstructs inputs/review pairing and recomputes agent and baseline scores. |
| `data/runs/anes2012-ohio-individual-development-20261020/completion-seal.json` | `4d7ca6f5608845802598fa84cb560d0bf6d50fcfd0ca681780e8beae4ea3dc01` | Binds 285 final artifacts, including 240 checkpoints, Docker evidence, source snapshots, image archive, spend ledger, and 296-test log. |
| `Dockerfile.profile-ablation` | `f8f1aaa67f9e139b856f49688d26e681b2324915df09577daa4fc8a5b68b8d2e` | Isolated standard-library prompt-worker image; currently untracked. |
| `docs/ANES_PROFILE_ABLATION_RESULTS.md` | `bcc1660812dc0881469752dbcd41ab6845a4fd3118f91aafdbebf5c36056e5ed` | Development-only results, diagnostics, execution boundary, and interpretation limits; currently untracked. |
| `src/psbx/experiments/profile_ablation.py` | `091acd86a848a4c148af0c925ec7ad33f5da38a301812ffb7c9de0f2a950ca28` | Frozen preparation, broker, nested calibration, sealing, and evaluation implementation; currently untracked. |
| `src/psbx/experiments/profile_ablation_worker.py` | `78ecdebcd9802b36ad15c45a182832ec2c316ca1f2796e7e82edea152590c601` | Strict four-arm field and provenance boundary for the isolated worker; currently untracked. |
| `tests/test_profile_ablation_audit.py` | `c6a7c3b971506d13a90643cd7b8132e3261d3d90e1430b6b27656d2cfc579884` | Independent profile-difference, fold-stability, and held-out-label leakage tests; currently untracked. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/contract.json` | `3460165e2156c2c93dfa046beab5fd3849cc2c7e7680800e9b4dd7c0bb6e2784` | Seals cohort, reserve boundary, profile arms, prompts, worker/model, Dockerfile, upstream inputs, and runtime sources. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/prediction-seal.json` | `66326ee874ae4cce309c19feb9491cf7d80acc82ac4c146ce1c10edf81ac76dc` | Binds the complete 960-forecast panel, checkpoints, contract, and immutable image identity. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/evaluation.json` | `2cc6b3b3e55a479b935cc23f785f691e5630944ba64b8a88f4fcd0b57c3f1705` | Direct, nested hybrid, party, prevalence, contrast, fitting-audit, and limitation outputs. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/independent-audit.json` | `0807dc8eb9a6e7fdd8ee3b6a01c51e6a82f5c10a1ab9b325145b0288d68ffd52` | Verifies payloads, isolation, full panel, reserve exclusion, fitting boundaries, and direct-score recomputation. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/additional-diagnostics.json` | `cb64465634c6c66ab1a51325547c8c9512a610c9767e6b66014752f2c88ca80e` | Exploratory marginal-share, modal-pair, association, and hybrid-contrast diagnostics. |
| `data/runs/anes2012-ohio-profile-ablation-development-v1/completion-seal.json` | `4bfcd8fc2d1b05626c882eae481e90e7600d907c7c52afd481b48baba372f0b9` | Binds 988 final artifacts, including 960 checkpoints, source snapshot, audit, diagnostics, spend ledger, Docker evidence, and result report. |

The split seal records the official source artifact SHA-256 as
`c68701295e31a9f18e6d33180724909275c9666a558a73fb13d795f51d289923`. The source
artifact itself is intentionally not linked from this report.

## Readiness decision

**Structural validation, runner hardening, the timing split, retrospective baselines, hardened
provider-free Docker execution, corrected live dialogue, a broader respondent-context experiment,
the 120-person reserved-cohort development validation, the 24-person individual profile study, and
the full 120-person development-cohort profile ablation are complete. Neither profile experiment
established a general agent improvement; private review did not earn its extra step, and nested
hybrids did not establish superiority over the party baseline. The workflow closes target staging
and catalog/worker binding gaps and demonstrates sealed multi-outcome comparison, limited-network
execution, isolated individual-worker execution, and leakage-tested out-of-fold calibration. It
does not establish population-level human fidelity, a validated individual-agent improvement, or a
beneficial swarm effect.**

Before scaling paid execution or making publication-facing claims, record all currently untracked
experiment/config/protocol/test files in an immutable revision, run live provider calls within the
intended isolation boundary, pin the container base and Python dependencies, retain independently
verifiable source bytes for every historical evidence excerpt, and add end-to-end preparation and
partial-recovery tests. The older structural staging CSV should be removed from any shareable bundle
or migrated to the new private-vault pattern. The retrospective baseline boundary also still needs
cryptographic input verification and fold-local preprocessing. A powered, preregistered design with
reserved respondents, enough independent network clusters, frozen model artifacts, multiplicity
control, and predeclared analysis remains required for a scientific result.
