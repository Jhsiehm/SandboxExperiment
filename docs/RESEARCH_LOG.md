# Research log — compiled 27 October 2026

The latest substantive research artifacts found are from **22–23 October**. The 27 October run was offline maintenance, not a new Oregon or model experiment. This log consolidates the available records across the research, Ohio and automation checkouts; the source reports and frozen results remain authoritative.

## Current conclusion

- **Keep the statistical reference and improve the data/design before more training.** The outcome classifier and frozen-logit calibration both failed their declared advancement gates.
- **Independent prediction is worth retaining.** In the larger DEBATE comparison, direct agents had the lowest RPS (0.115118 versus statistical 0.130286). Generated discussion was worse (0.146711). This is a specific point-estimate result, not proof that agents outperform statistics generally.
- **Richer profiles sometimes helped.** They improved several Ohio outcomes, but the statistical model remained the stronger broad reference. Calibration and peer effects varied by outcome; negative results are retained alongside the positives.
- **The laptop is adequate for bounded local experiments.** Small 8B quantized LoRA and inference runs completed. Better message likelihood did not translate into valid belief outputs or better outcome prediction.
- **Oregon is a useful verified reference.** We reproduced two published enrollment rows and measured a modest statistical predictive improvement. No agent advantage or health-effect prediction has been shown.
- **The next linked-panel study is preparation-only.** Five source/harmonization blockers remain; no panel respondent data or later-wave outcomes were ingested.

## Oregon Medicaid: what we actually learned

This is the **Oregon Health Insurance Experiment**, involving a lottery for access to Medicaid. It is not Medicare or an evaluation of Oregon's current healthcare system. The [original first-year study](https://www.nber.org/papers/w17190) supplies the historical reference.

Our saved October 22 analysis used **74,922 people in 66,385 households**. The adjusted effect of lottery assignment on ever-enrollment was **+25.59 percentage points**; on enrollment at the September 30, 2009 endpoint, **+14.81 points**. All six published-rounding checks passed for the two rows. These are assignment effects on enrollment, not individual treatment effects or estimates of health improvement.

Fivefold household-separated prediction reduced Brier error from **0.167696 to 0.164220**, about **2.07% relative**, using fixed-L2 logistic regression. This is a small development gain without a reported difference interval; age was omitted, so the model is not the strongest possible statistical reference. The full public-use sample has already been inspected, and cannot now be described as a pristine holdout.

The next Oregon task is to fix the same-information, pre-event feature set and per-lottery-batch cutoffs, then review a source-specific adapter. Matched control draw is analyst design information, not a notification the person received. Only a frozen matched comparison could test whether agents add predictive value. Enrollment, healthcare use and health outcomes must remain separate targets.

Evidence: [aggregate results](../reports/behavior-feasibility-20261022/baseline/oregon-results.json), [methods and limits](../reports/behavior-feasibility-20261022/baseline/README.md), [source review](../reports/behavior-feasibility-20261022/oregon-data/BASELINE_SOURCE_REVIEW.md).

## Reading the record correctly

Lower Brier, ranked probability score (RPS), log loss and NLL mean lower error, but **do not compare their values across different scales, cohorts or targets**. The separate Ohio attitude report uses full multiclass Brier (0–2); later ANES work uses half-multiclass Brier (0–1); DEBATE uses normalized ordinal RPS. Message NLL measures text prediction, not human-outcome accuracy. Repeated generations on the same people are not independent human replications.

Costs below are provider-reported usage, not necessarily final bills. Reservations are ceilings, not charges. No grand total is calculated because early attempts overlap and some calls have unresolved usage. Software test counts are historical, branch- and stage-specific; they must not be added together. This compilation ran a documentation/artifact verification, not new scientific evaluations.

## Study register

Each entry gives the scope, main result, decision and source. Exact fields, source identifiers and selected metrics are also in the [machine-readable ledger](../reports/research-register-20261027/experiment-ledger.json).

### 01. 2026-09-23/2026-10-04 · Timing, provider failures and mock validation

**development only.** 5,914-profile timing preparation; later Ohio mock: 226 profiles, 164 valid targets, 30 repetitions. Strict pre-cutoff and paper-faithful profiles were separated. A retrospective two-field baseline scored 0.076340 Brier. The mock produced 13,560 predictions; its 0.105333 individual and 0.116824 society Brier scores measure mechanics only. Credit, authentication and retired-model failures are retained in the status log.

Keep retrospective conditioning and mock checks separate from live human-response evidence. The retrospective baseline conditions on information after the strict cutoff. Failed requests do not establish completed experiments; no combined bill is inferred. Sources: [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 02. 2026-10-04 · Early live smoke excluded from protocol evidence

**protocol invalid.** Completed smoke: four profiles, three scorable, 24 logical calls; earlier attempts incomplete. Brier 0.06547967 individual versus 0.088963 society was observed, but the OpenRouter path omitted the system instruction. Across three attempts: 72 request reservations, $0.00880242 reported, one unresolved reservation.

Retain receipts; exclude these scores from claims about the corrected protocol. Reservations, logical calls and provider attempts differ. Usage total covers overlapping attempts, not an additional independent run. Sources: [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 03. 2026-10-04 · Corrected individual versus society run

**completed development.** 24 unique people, 22 scorable, two repetitions; 48 reflections, 48 public messages, 48 ballots. Individual Brier 0.11673581; society 0.14847838. Replication differences had opposite signs. Earlier corrected attempts stopped after 98 logical completions and after a first-call format failure; they remain incomplete.

No reliable interaction advantage. Provider calls/completions: 144. Reported usage: $0.01765025. Sources: [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 04. 2026-10-11 · Profile and evidence factorial

**completed development.** 24 new Ohio people, four individual conditions; 12-person social subset. Vote Brier: sparse 0.106901, sparse + evidence 0.134875, rich 0.089928, rich + evidence 0.103553. Social versus private: vote 0.108627/0.090723, healthcare 0.254590/0.291924, gun 0.365767/0.419940.

Mixed outcome-specific effects; do not promote context or interaction as generally beneficial. Narrow economic context is available evidence, not verified individual exposure; only 18 vote targets scorable. Provider calls/completions: 240. Reported usage: $0.04662035. Sources: [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 05. 2026-10-12/2026-10-13 · 120-person profile comparison

**gate failed.** 120 inspected development people; three models; a separate 50-person reserve excluded. Sparse → rich Brier: vote 0.147859 → 0.145513, healthcare 0.276586 → 0.282043, gun 0.279448 → 0.288865. Macro change +0.004176, interval [-0.009541, 0.017883].

No progression. The folder name “reserved-validation” does not make these now-inspected people untouched. 482 reservations included two unresolved read timeouts; reported cost is incomplete billing. Target counts 84/116/120 differ. Provider calls/completions: 480. Reported usage: $0.08368250. Sources: [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 06. 2026-10-14 · Vote pilot and synthetic-population check

**completed development.** 16-person LLM pilot; 135 eligible statistical-evaluation records; separate 1,000-person synthetic population. Rich LLM Brier 0.13609 versus basic 0.30290; rich naive Bayes 0.01925 on the same 16 and 0.09927 on 135. Peer conditions did not beat rich individual prediction. Synthetic Democratic two-party share 51.8014% versus official 51.5146%, but predicted turnout exceeded the official count by about 1.39 million.

Close aggregate vote share is insufficient behavioral validation; preserve the turnout correction. Effective pilot sample about 10.8; self-reported turnout is not validated turnout. Statistical samples must be distinguished. Provider calls/completions: 96. Reported usage: $0.01369720. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 07. 2026-10-14 · Expanded three-outcome attitude comparison

**completed development.** 226 Ohio people; valid targets healthcare 221, gun 226, environment 225. Full multiclass Brier, basic/rich/logistic: healthcare 0.66999/0.55004/0.50910; gun 0.58653/0.56180/0.47719; environment 0.67847/0.61459/0.54280. Rich profiles improved point estimates; logistic remained best on all three. Rich-minus-basic intervals excluded zero for healthcare and environment, not gun policy.

Keep rich profiles as a development finding; retain logistic as the benchmark. Brier scale 0–2; bootstrap intervals are descriptive and conditional, not full complex-survey uncertainty. Provider calls/completions: 452. Reported usage: $0.16262160. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 08. 2026-10-14 · Separate calibration and transfer

**completed development.** 240 people outside Ohio/New Jersey: 160 fit, 80 validation; then frozen Ohio transfer. Validation raw → calibrated Brier: healthcare 0.52873 → 0.49867, gun 0.60027 → 0.53570, environment 0.72427 → 0.63460. Ohio: 0.55004 → 0.58293, 0.56180 → 0.52402, 0.61459 → 0.55935. Logistic still beat calibrated LLM forecasts on all three Ohio outcomes.

Calibration is outcome- and sample-dependent; it did not generally repair prediction. Only the validation environment interval excluded zero. The $0.3208856 reserved amount is not billed cost. Reported usage: $0.08781000. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 09. 2026-10-14 · Initial isolated interaction pilot

**promising small pilot.** 32 people, eight groups, four topics; 14 changed and 18 unchanged answers. RPS: persistence 0.16250, private 0.15808, generated discussion 0.12166, real-message replay 0.11116. Discussion-minus-private -0.03642, interval [-0.07418, -0.00178]; versus persistence interval [-0.11170, 0.02350] crossed zero.

Motivated the larger comparison; not confirmation of society simulation. Small selected pilot. Real-message replay is a diagnostic with observed discussion information. Provider calls/completions: 480. Reported usage: $0.15068960. Sources: [DEBATE_ISOLATED_PILOT_RESULTS.md](<../docs/DEBATE_ISOLATED_PILOT_RESULTS.md>).

### 10. 2026-10-14 · Isolation and ANES software checks

**mechanics verified.** Separate Ohio checkout and Docker development checks. Recorded suite: 253 passed plus 39 targeted tests; later fixes reached 290 then 294. Real 2012 ANES data were correctly rejected under the June 2012 cutoff because fieldwork/release occurred later. A 48-vote mock exercised two questions.

Use an explicit retrospective contract; passing tests do not establish human fidelity. Counts are stage-specific and overlapping; do not add them or describe them as a new full-suite run. Provider calls/completions: 0. Sources: [ANES_EXPERIMENT_TEST_REPORT_2026-10-14.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/ANES_EXPERIMENT_TEST_REPORT_2026-10-14.md>), [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 11. 2026-10-15 · Controlled peer follow-up

**completed development.** 40 profiles, three repetitions; 38 valid healthcare targets. Mean full Brier, reconsideration/grouped peer: healthcare 0.569933/0.536531, gun 0.546849/0.499083, environment 0.614939/0.659114. Grouped arithmetic beat grouped agents on healthcare and environment. Same-cohort logistic: 0.468742, 0.509153, 0.461641; peer agents had the lower gun-policy point estimate only.

Retain the narrow positive gun result and the negative outcomes together. 362 reservations; two HTTP 502 requests have unknown charges. Recovery preserved completed predictions. No significance claim or independent human replications; $0.6278636 is conservative reservation. Provider calls/completions: 360. Reported usage: $0.18838400. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 12. 2026-10-15 · Observed media and historical availability audit

**completed development.** 226 Ohio people; eight observed categorical media predictors; archive/source review. Rich → rich + measured-media logistic Brier: healthcare 0.509103 → 0.508760, gun 0.477193 → 0.495882, environment 0.542803 → 0.549810. The October 20 archived debate transcript was available before only 64 of 226 interview starts. Fifty-eight broadcast metadata records are not 58 independent stories.

No overall feature gain. Preserve interview cutoffs and reject heuristic outlet weights as measured audience evidence. Publication date is not proof of contemporaneous archival availability or personal exposure. POST discussion fields excluded; this is not causal media analysis. Provider calls/completions: 0. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 13. 2026-10-15 · Reserve evaluator and cross-year candidates

**preparation only.** New Jersey evaluator/access audit and cross-year questionnaire readiness. Existing reports document reserve controls and candidate item/mode comparisons. They do not establish an authorized new reserve readout or successful longitudinal transfer.

Keep later outcomes outside development. Use source-backed crosswalks before execution. This compilation did not open New Jersey targets, respondent exports or reserved evaluator outcomes. Provider calls/completions: 0. Sources: [OHIO_2012_PILOT_REPORT.md](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>).

### 14. 2026-10-20 · Focused profiles and private review

**gate failed.** 24 previously inspected people, two repetitions, four arms; 96 other development people fit baselines; 50-person reserve excluded. Macro weighted half-multiclass Brier: prevalence 0.29645, party 0.25009, sparse 0.26736, rich 0.27166, focused 0.25996, focused + review 0.26601. Focused-minus-rich -0.01170, interval [-0.04104, 0.01600].

No demonstrated advantage over the party baseline or progression criterion. 192 final forecasts and 48 reviews; Brier uses half-multiclass normalization, unlike the separate Ohio report. Provider calls/completions: 240. Reported usage: $0.09294640. Sources: [ANES_INDIVIDUAL_DEVELOPMENT_RESULTS.md](<../docs/ANES_INDIVIDUAL_DEVELOPMENT_RESULTS.md>), [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 15. 2026-10-20 · Profile ablation and statistical hybrids

**gate failed.** 120 inspected people, four arms, two repetitions; nested 5-outer/4-inner development folds. Direct macro Brier: sparse 0.23786, rich 0.23778, reduced 0.23871, reduced + observed 0.23184; party baseline 0.22087. Hybrid scores 0.22821/0.22235/0.22590/0.22483. Added observed information change -0.00686, interval [-0.01867, 0.00350].

No candidate promoted; keep the separate 50-person reserve untouched. Conditional intervals omit baseline refit uncertainty; this is development reuse, not fresh confirmation. Provider calls/completions: 960. Reported usage: $0.66721360. Sources: [ANES_PROFILE_ABLATION_RESULTS.md](<../docs/ANES_PROFILE_ABLATION_RESULTS.md>), [ANES_2012_EXPERIMENT_STATUS.md](<../docs/ANES_2012_EXPERIMENT_STATUS.md>).

### 16. 2026-10-22 · Published enrollment estimates reproduced

**historical reproduction.** 74,922 people, 66,385 households; two full-sample Table III enrollment rows. Lottery assignment increased ever-enrollment by 25.5866 percentage points (household-clustered SE 0.3509 points), and endpoint enrollment on September 30, 2009 by 14.8139 points (SE 0.3112). All six published-rounding checks passed. This reproduces enrollment findings, not the entire paper.

Retain as a verified historical statistical reference; no agent or health-outcome claim. Medicaid, not Medicare. Unit-weight OLS with lottery-draw and listed-household-size indicators; household CR1 standard errors. Raw control means and adjusted assignment coefficients are different estimands. Full-sample inspection leaves no pristine holdout inside this sample. Provider calls/completions: 0. Reported usage: $0.00000000. Sources: [oregon-results.json](<../reports/behavior-feasibility-20261022/baseline/oregon-results.json>), [README.md](<../reports/behavior-feasibility-20261022/baseline/README.md>), [BASELINE_SOURCE_REVIEW.md](<../reports/behavior-feasibility-20261022/oregon-data/BASELINE_SOURCE_REVIEW.md>).

### 17. 2026-10-22 · Household out-of-fold enrollment prediction

**development only.** Five household-separated folds; assignment and selected administrative/list features. Brier 0.16769607 assignment-only → 0.16421990 fixed-L2 logistic, an absolute reduction of 0.00347618 (2.07% relative). Log loss 0.51126394 → 0.50097743. No LLM calls.

Resolve the pre-event feature/cutoff contract before a matched agent comparison; keep the statistical model. No difference interval; age omitted, so not the strongest available statistical baseline. Matched lottery draw is analyst alignment, not personal information. No individual causal, health, current-system or prospective forecast validation. Provider calls/completions: 0. Reported usage: $0.00000000. Sources: [oregon-results.json](<../reports/behavior-feasibility-20261022/baseline/oregon-results.json>), [source-contract.unresolved.json](<../reports/behavior-feasibility-20261022/baseline/source-contract.unresolved.json>), [FEASIBILITY.md](<../reports/behavior-feasibility-20261022/oregon-data/FEASIBILITY.md>).

### 18. 2026-10-22 · Larger six-arm comparison

**primary gate failed.** 116 people, 29 evaluation groups/topics; 47 other groups and 188 people fit development baseline. RPS: direct 0.115118, transition 0.130286, real replay 0.131949, generated discussion 0.146711, reflection 0.149433, persistence 0.163793. Discussion-minus-baseline +0.01643, interval [-0.01698, 0.05190]; discussion-minus-direct +0.03159, interval [0.00791, 0.05933]. False modal changes: discussion 28/58 unchanged people, direct 17/58.

Retain direct prediction as a useful reference; do not expand interaction. These 29 groups are now exposed. One model/generation; direct-baseline lead is a point estimate without a prespecified contrast interval. Source drift in three files caused the original final check to fail; frozen-source recovery reconstructed saved calls without new provider jobs. Not a clean original integrity pass. Original raw run folder not materialized in this worktree. Provider calls/completions: 1,856. Reported usage: $0.58634280. Sources: [FINDINGS.md](<../reports/social-comparison-audit-20261022/FINDINGS.md>).

### 19. 2026-10-23 · Participant admission and message dataset

**development preparation.** 47 downloaded development groups; 33 admitted: 29 training and four validation. Fourteen groups excluded by receipt matching; 831 training and 133 validation messages prepared. Ninety-six unused candidate groups remain metadata-only, not admitted fresh evaluation.

Preserve participant/source overlap checks and separate admitted from merely discovered data. Documentation-level admission does not imply independently verified unique humans across all sessions. Provider calls/completions: 0. Sources: [README.md](<../experiments/debate-sft-replication/README.md>), [PARTICIPANT_ADMISSION.md](<../reports/behavior-feasibility-20261022/debate/PARTICIPANT_ADMISSION.md>).

### 20. 2026-10-23 · OpenRouter format smoke

**completed with format failures.** 12 responses; 10 valid. Two outputs failed formatting. This was not a scientific evaluation.

Keep invalid-response costs and failures in the record. Provider calls/completions: 12. Reported usage: $0.00009274. Sources: [summary.json](<../data/runs/debate-openrouter-development-smoke-20261023/summary.json>).

### 21. 2026-10-23 · Single-group hosted development diagnostic

**development only.** Four already-inspected people in one group. RPS: private 0.102925, transition 0.146322, persistence 0.200000, direct 0.204770, discussion 0.239250.

Do not use one group to overturn the larger comparison or rank models generally. No independent evaluation or intervals; baseline participant overlap was not audited for this diagnostic. Not a base-versus-SFT comparison. Provider calls/completions: 60. Reported usage: $0.01926840. Sources: [evaluation.json](<../data/runs/debate-development-comparison-20261023/evaluation.json>).

### 22. 2026-10-23 · Laptop pilot and memory probes

**feasibility only.** Recorded laptop: MacBook Air M5, 24 GB memory, 10-core GPU; quantized Llama 3.1 8B. LoRA pilot: 52 microsteps/13 updates, batch 1 with accumulation 4, rank 8 over 16 layers; 223.99 seconds, about 40 MiB adapter. Eight-batch validation loss 5.024 → 3.457 was diagnostic. System swap rose about 2.8 → 6.3 GiB. Both subsequent memory probes completed (~70–71 seconds; about 6.52 GiB peak MLX allocation).

Small supervised runs fit the laptop, but resource feasibility does not establish predictive utility. System swap is shared by all applications. Hardware measurements describe these saved runs, not an unrestricted training capacity. Provider calls/completions: 0. Sources: [result.json](<../data/local-mlx-pilot/pilot-20261023-030458/result.json>), [result.json](<../data/local-mlx-pilot/memory-probe-20261023-033958/result.json>), [result.json](<../data/local-mlx-pilot/memory-probe-20261023-034222/result.json>), [README.md](<../experiments/debate-sft-replication/README.md>).

### 23. 2026-10-23 · Matched base/adapter comparison

**outcome comparison blocked.** 133 messages, four groups, 3,415 supervised tokens; matched prompt/source bindings. Token-weighted NLL 3.627999 → 3.201114; equal-group NLL 3.970071 → 3.304992. All four groups improved message likelihood. Direct belief format: base 16/16 valid; adapter first output invalid (822 non-JSON characters), so stopped after 1/16.

Message imitation improved, but belief-outcome superiority was not evaluated. Validation had already supplied eight training-time diagnostic batches; it is not untouched confirmation. No outcome scoring after format failure. Provider calls/completions: 0. Sources: [LOCAL_MATCHED_COMPARISON_2026-10-23.md](<../docs/LOCAL_MATCHED_COMPARISON_2026-10-23.md>), [message-evaluation.json](<../data/local-mlx-pilot/matched-comparison-20261023/message-evaluation.json>).

### 24. 2026-10-23 · Bounded format diagnosis

**candidate format failed.** Four training people × two models × two prompt styles = 16 generations. Base original 4/4 valid; base prefix 3/4 (one vector summed to 0.99). Adapter 0/4 for both styles; all prefixed vectors were zero. Run completed in 50.79 seconds.

A prompt prefix did not rescue the adapter; avoid a larger outcome run. No outcome evaluation. Independent reviewer hit a spending cap; final root review must not be labeled independent. Provider calls/completions: 0. Sources: [LOCAL_FORMAT_SMOKE_RESULTS_2026-10-23.md](<../docs/LOCAL_FORMAT_SMOKE_RESULTS_2026-10-23.md>), [format-evaluation.json](<../data/local-mlx-pilot/format-smoke-v1-20261023/format-evaluation.json>).

### 25. 2026-10-23 · Task-aligned classifier pilot

**internal nonworsening gate failed.** 92 fit people/23 groups; 24 internal people/six groups; 52 microsteps/13 updates. RPS base 0.184574, candidate 0.216049, persistence 0.133333, transition 0.124716. Candidate-minus-base +0.031475 exceeded the +0.02 nonworsening limit. Change-event Brier improved 0.397598 → 0.379312, but expected-category MAE worsened 1.332604 → 1.511860.

Stop this candidate; secondary improvement does not override the primary failed gate. Native offline training 43.78 seconds, peak 5.10 GiB. Six-label probability mass fell 0.984780 → 0.654332; this is not a calibration score. Provider calls/completions: 0. Sources: [CLASSIFIER_PILOT_RESULTS_2026-10-23.md](<../docs/CLASSIFIER_PILOT_RESULTS_2026-10-23.md>), [internal-evaluation.json](<../data/local-mlx-pilot/outcome-classifier-v1-20261023/internal-evaluation.json>).

### 26. 2026-10-23 · Training, error and method audit

**diagnosis only.** Saved classifier outputs and admitted fit cohort; no new training. No implementation bug identified. The candidate chose category 4 for 23/24 people; 14 unchanged people accounted for 88.6% of the gap to the transition baseline. Reconstructed training exposure covered 52/92 people and 21/23 groups. A 52-case statistical control scored 0.134724 versus 0.124716 for all 92, still far better than candidate 0.216049.

Investigate target/data design; the evidence does not justify asserting that more training will fix the failure. Exposure was reconstructed, not observed in a training log. Leave-one-group sensitivity is descriptive, not a new independent test. Provider calls/completions: 0. Sources: [CLASSIFIER_INVESTIGATION_2026-10-23.md](<../docs/CLASSIFIER_INVESTIGATION_2026-10-23.md>), [CLASSIFIER_ERROR_ANALYSIS.md](<../docs/CLASSIFIER_ERROR_ANALYSIS.md>), [CLASSIFIER_TRAINING_AUDIT.md](<../docs/CLASSIFIER_TRAINING_AUDIT.md>), [CLASSIFIER_METHOD_REVIEW.md](<../docs/CLASSIFIER_METHOD_REVIEW.md>).

### 27. 2026-10-23 · Frozen-model residual calibration

**oof gate failed.** 92 fit people, 23 groups, 21 topic/person components; five folds of 20/20/20/16/16. Equal-group normalized RPS: raw transition 0.141335935, calibrated control 0.140185794, control + frozen logits 0.140233300. Gain over raw 0.001102635 was below 0.01; extension was worse than control by 0.000047505. Ten bounded fits converged; model coefficient effectively zero in four folds.

Keep the statistical baseline; stop before refit/internal/outer stages. Independent audit reproduced probabilities exactly and metrics within 1e-12. Ninety-two base forwards took 32.56 seconds, peak 4.59 GiB, no observed swap growth. No new neural training or internal/outer outcome read. Provider calls/completions: 0. Sources: [RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md](<../docs/RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md>), [RESIDUAL_CALIBRATION_RESULT_AUDIT.md](<../docs/RESIDUAL_CALIBRATION_RESULT_AUDIT.md>), [decision.json](<../data/local-mlx-pilot/residual-calibration-v1-20261023/decision.json>), [oof-evaluation.json](<../data/local-mlx-pilot/residual-calibration-v1-20261023/oof-evaluation.json>).

### 28. 2026-10-23 · Statistical reference frozen and data audited

**reference preserved.** 92 admitted people, 23 groups, 21 topics; 48 unchanged, 44 changed. Required fields were present and valid; initial-category counts ranged from 10 to 22. The exact six-category Laplace-one transition table was retained, not replaced by a calibrated variant. SHA-256 ffc4ecc705c209841dfe51bcab5b40f68159c91cb914ef4e362c4abdda46b245.

Improve data and design before further model training. Completeness of the admitted export does not establish selection representativeness or adequate sample size. Provider calls/completions: 0. Sources: [DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md](<../docs/DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md>), [manifest.json](<../reports/statistical-reference-20261023/manifest.json>), [data-quality.json](<../reports/statistical-reference-20261023/data-quality.json>).

### 29. 2026-10-23 · Linked-panel source and design readiness

**ingestion blocked.** Proposed seven-category party ID: 2016 → 2020 development; separately frozen 2020 → 2024 later evaluation. Development auditor, reference functions and readiness gates implemented; 52 relevant tests reported. Five source blockers remain: 2024 summary construction, unavailable original documentation bytes, unverified repeated-variable archive, release/errata alignment, and unverified merged schema/linkage/missing codes. No respondent dataset ingested.

Archive source documentation, resolve equivalence and freeze a development-only projection before ingestion; then fit a new seven-category baseline. Derived paraphrase hash is not an original-source hash. One early transition cannot test a matched long-history ablation. Candidate, practical margin and design-aware uncertainty remain unresolved; later evaluation and model training disabled. Provider calls/completions: 0. Sources: [ANES_PANEL_METADATA_READINESS.md](<../docs/ANES_PANEL_METADATA_READINESS.md>), [PANEL_EXPERIMENT_DESIGN_REVIEW.md](<../docs/PANEL_EXPERIMENT_DESIGN_REVIEW.md>), [DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md](<../docs/DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md>), [readiness.json](<../reports/anes-panel-readiness-20261023/readiness.json>).

### 30. 2026-10-23 · Research playback and aggregate display

**recorded playback verified.** Available DEBATE recording selected; 51 recorded actions reported in the prior preview check. Playback operates on a materialized recording. “No actions” on an unavailable ANES run did not imply that a live job was running. Dashboard checks subsequently covered failed classifier/calibration gates and panel readiness as separate states.

Display recording availability, experiment status and live execution separately. The 51-action browser check is prior-session evidence, not a fresh October 27 browser check. Current server liveness was not tested in this compilation. Provider calls/completions: 0. Sources: [LOCAL_MATCHED_COMPARISON_2026-10-23.md](<../docs/LOCAL_MATCHED_COMPARISON_2026-10-23.md>), [RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md](<../docs/RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md>), [DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md](<../docs/DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md>).

### 31. 2026-10-23/2026-10-27 · Mock-mode provenance and routine offline verification

**mechanics verified.** Separate automation/daily-swarm checkout; October 23 provenance fix and October 27 verification. Mock/live mode now participates in resumable-run provenance. Seven regression cases were added; 313 tests passed on October 23 and again October 27 with two existing warnings. Bounded mocks ran two questions × 12 votes, Brier 0.25.

Keep maintenance evidence separate from scientific outcomes; these checks do not refresh research-branch results. Research branch remained unmerged. Mock scores show mechanics, not model performance; October 27 checks did not test Docker isolation. Provider calls/completions: 0. Reported usage: $0.00000000. Sources: [DAILY_SWARM.md](</Users/joshua/Documents/Codex/2026-09-20/git-github-com-jhsiehm-sandboxexperiment-git/work/SandboxExperiment/docs/automation/DAILY_SWARM.md>).

## Decisions and next work

1. Preserve the exact six-category DEBATE statistical reference and the failed candidate outputs. No more training is justified by the current classifier/calibration results.
2. Resolve the five ANES panel metadata blockers: original documentation bytes/checksums; 2024 summary construction; repeated-variable archive; release alignment; merged schema/linkage/missing codes. Freeze a projection that exports only authorized 2016/2020 development fields.
3. Audit development sample selection, missingness, mode, attrition and category support. Fit a new seven-category panel reference; the six-category DEBATE table cannot be reused.
4. Choose one bounded candidate and matched feature set, justify a practical improvement margin and uncertainty method, and freeze the evaluator before later-wave evaluation. Do not inherit a convenient 0.01 margin without a panel-specific rationale.
5. For Oregon, complete the source-specific temporal/feature contract and strengthen the matched statistical reference before any agent comparison. No new Oregon run was found after October 22.
6. Reintroduce social interaction only after an independent predictor has earned its place, with matched private-computation budgets and explicit change/no-change diagnostics.

## Integrity exceptions and limits

- Early October 4 live smoke omitted a system instruction; its results are not evidence for the corrected protocol. Interrupted and invalid-format attempts remain logged.
- The October 22 larger DEBATE run failed its original final source-integrity check. Frozen-source recovery reused completed checkpoints with new provider work disabled. Preserve this exception; do not relabel it a clean initial pass.
- Exposed development or evaluation people do not become untouched again. The 120-person “reserved-validation” label, one-group diagnostic and four message-validation groups each need their stated exposure limits.
- Source reports for older runs exist here, but their original run directories are not all materialized in this checkout. Those entries are report-backed, not newly reconstructed from raw predictions.
- The inventory includes additional protocols, source reviews, historical Word reports and maintenance records. Inventorying a file does not mean every result inside it was independently replicated. Cross-checkout links require the original local checkout to remain available.
- No respondent-level or reserved outcome files were opened for this compilation. No new training, provider requests, baseline refit, commit, push or deployment was performed.

## Evidence and verification

The [source inventory](../reports/research-register-20261027/source-inventory.json) records paths, checkout revisions, sizes and SHA-256 digests. It is a reproducibility snapshot, not a backup of unavailable raw runs. The [verification receipt](../reports/research-register-20261027/verification.json) records source existence/hash checks, ledger coverage, selected metric reconciliation, baseline preservation and generated-document checks. Re-run with `python3 scripts/verify_research_log.py` from this research checkout.

The original [October 22 research plan](</Users/joshua/Downloads/PoliSim_Research_Game_Plan_2026-10-22.md>) is indexed as context. Proposed work in it is not automatically recorded as completed work. Detailed experiment reports retain the full methods and historical test commands.
