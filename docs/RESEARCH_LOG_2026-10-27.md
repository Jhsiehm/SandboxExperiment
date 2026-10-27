# Research log · 27 October 2026

**The latest experiments did not establish a useful improvement over their statistical controls.** Local training learned discussion language, but that did not translate into better belief predictions. A recurring error is predicting change when people remain stable. Oregon supplied a successfully reconstructed behavioral benchmark; agent performance on it remains untested.

**Scope:** new research since `28f1664` (22 October) in the research-preview checkout, plus earlier findings needed to interpret it. The latest saved behavioral experiments are dated 23 October; the 27 October run was offline maintenance. This compilation adds no experiments or API spending. These retrospective development comparisons do not establish prospective forecasting performance.

RPS and Brier scores are better when lower. Compare scores only within the same outcome and cohort. ANES reports half-multiclass Brier; Ohio reports full multiclass Brier. Dollar amounts below are recorded provider charges, not a complete account billing reconciliation.

## New since the research commit

**Hosted diagnostic · 23 October — useful for debugging, too small for a method ranking.**

One already-inspected four-person DEBATE training group; 60 GPT-4.1-mini requests, **$0.0192684** recorded. Private reflection scored RPS **0.10293**, transition control **0.14632**, persistence **0.20000**, direct prediction **0.20477**, discussion swarm **0.23925**. The transition control used the other 28 admitted training groups. All outputs passed formatting. This tiny development result does not overturn the larger comparison below. [Run record](../experiments/debate-sft-replication/README.md) · [Evaluation](../data/runs/debate-development-comparison-20261023/evaluation.json)

**Local message training — feasible on this machine, unsuccessful as a belief predictor.**

A four-bit Llama 3.1 8B adapter completed 52 microsteps / 13 optimizer updates in **224 seconds** on the 24 GB M5 MacBook Air. Training used 831 messages from 29 groups; validation used 133 messages from four other development groups. Validation token loss fell **3.6280 → 3.2011 nats**, improving in all four groups. However, the base model returned 16/16 valid belief distributions; the adapter failed its first response and stopped. Its belief accuracy was therefore **not scored**, and interaction testing did not begin. A subsequent 16-generation training-only format diagnostic produced **0/8 valid adapter distributions**, including failures with a supplied JSON prefix. No paid calls. Some validation material had already been exposed during the hardware pilot; these are development results, not fresh confirmation. [Matched comparison](LOCAL_MATCHED_COMPARISON_2026-10-23.md) · [Format diagnostic](LOCAL_FORMAT_SMOKE_RESULTS_2026-10-23.md)

**Six-category classifier — valid probabilities, worse predictions.**

A fresh categorical adapter used 92 fitting participants in 23 groups and 24 internal-evaluation participants in six separate groups. All 48 base/candidate predictions were finite and complete. RPS: transition **0.12472**, persistence **0.13333**, base **0.18457**, candidate **0.21605**. Candidate deterioration of **+0.03148** exceeded the allowed +0.02: **progression stopped**.

The post-hoc diagnosis: 14/24 people did not change, accounting for **88.6% of the candidate's excess RPS over the transition control**. It assigned an average **80.24% probability of change**, versus **41.67% observed**. Predictions concentrated around categories 3–4 with little variation across people. The training audit reconstructed only 52 unique examples encountered; a transition control restricted to those examples still scored **0.1347**. Limited exposure does not explain away that ranking; longer training remains untested. The reconstruction depends on RNG assumptions because sample IDs were not logged. [Results](CLASSIFIER_PILOT_RESULTS_2026-10-23.md) · [Error analysis](CLASSIFIER_ERROR_ANALYSIS.md) · [Training audit](CLASSIFIER_TRAINING_AUDIT.md)

**Frozen-model calibration — no useful added signal in this test.**

Ninety-two local forwards across 23 groups fed five training-only folds. RPS was **0.141336** for raw transition probabilities, **0.140186** for their calibrated control, and **0.140233** after adding frozen-model logits. The extension missed the required 0.01 gain over raw transition and slightly worsened the calibrated control. Four of five fitted logit weights were near zero. **No refit, internal readout, or outer evaluation followed.** An independent saved-result audit reproduced the probabilities and metrics. No neural training or paid calls. This small difference is neither an equivalence finding nor evidence that models can never add information. [Results](RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md) · [Audit](RESIDUAL_CALIBRATION_RESULT_AUDIT.md)

**Next dataset — design prepared, ingestion blocked.**

The proposed ANES panel study predicts seven-category party identification: 2016→2020 for development, then 2020→2024 for later evaluation. The saved 23 October readiness report still has five blockers: 2024 question construction differs; original official-document bytes are missing after HTTP 403 responses; archive schema/member identity is unverified; release and errata dates need reconciliation; and raw linkage, wave availability, and missing-value encodings remain unchecked. **No raw panel ingestion, training, or later-cohort evaluation is recorded.** The benchmark must also distinguish continuing panel members from the full 2024 electorate. [Design](DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md) · [Readiness](ANES_PANEL_METADATA_READINESS.md)

## Earlier findings that still govern the next step

**DEBATE · 22 October — the larger study did not support discussion gains.**

116 participants in 29 held-out discussion groups; 1,856 paid requests, **$0.5863428**. Direct prediction had the best RPS point estimate: **0.11512**, versus transition **0.13029**, human-discussion replay **0.13195**, swarm **0.14671**, private reflection **0.14943**, persistence **0.16379**. Swarm minus direct was **+0.03159**, exploratory group-bootstrap 95% interval **[+0.00791, +0.05933]**. Of 58 unchanged humans, the swarm incorrectly changed the modal answer for 28; direct prediction did so for 17. The statistical control best matched population answer shares; persistence best predicted expected ratings. There was no universal winner across metrics.

The earlier 32-person pilot favored swarm over private reflection, but not conclusively over persistence. The larger comparison therefore weakens that initial interaction claim. Its first integrity check failed after telemetry modified source files; recovery used frozen source and existing checkpoints, with no paid replay. This documented exception and subsequent inspection make it development evidence. [Larger comparison](../reports/social-comparison-audit-20261022/FINDINGS.md) · [Initial pilot](DEBATE_ISOLATED_PILOT_RESULTS.md)

**ANES · 20 October — richer profiles did not beat the strong baseline.**

The 120-person, four-profile, two-repeat ablation produced 960 forecasts for **$0.6672136**. Party baseline half-Brier **0.22087** beat every direct and hybrid point estimate; best direct was **0.23184**, best hybrid **0.22235**. Adding four observed fields improved the reduced profile by **−0.00686**, but its 95% interval **[−0.01867, +0.00350]** included zero. A separate 24-person, two-repeat development study also failed its focused-profile gate; private review showed no demonstrated benefit. These cohorts had been inspected; the separate 50-person reserve remained excluded. [Profile ablation](ANES_PROFILE_ABLATION_RESULTS.md) · [Individual study](ANES_INDIVIDUAL_DEVELOPMENT_RESULTS.md)

**Ohio 2012 · parallel checkout — close aggregate shares concealed wrong behavior.**

A 1,000-person synthetic population came within **0.2868 percentage points** of the two-party vote share while implying **1.39 million too many voters**. This was a statistical population simulation, not 1,000 API respondents. In the 226-person, 452-request live study (**$0.1626216**), richer profiles improved health, gun, and environmental response scores, yet logistic controls remained better on all three. Calibration transferred unevenly: Ohio health predictions worsened. The subsequent 40-profile, three-repeat peer experiment produced 360 responses; peers improved health/guns relative to reconsideration and worsened environment. Its **$0.188384** known charge excludes two unresolved reservations. Media/outlet weights were identified as unvalidated heuristics, not measured exposure probabilities. [Ohio report](</Users/joshua/Documents/ChatGPT/Policy Sim/docs/OHIO_2012_PILOT_REPORT.md>)

**Oregon Medicaid · 22 October — a reproduced benchmark, no agent result yet.**

Two published enrollment rows were reproduced using **74,922 people / 66,385 households**; all six checks of rounded means, effects, and standard errors passed. Lottery assignment raised ever-enrollment through September 2009 by **25.5866 percentage points** (household-clustered SE **0.3509 pp**) and enrollment at that date by **14.8139 pp** (SE **0.3112 pp**). Household-grouped, five-fold statistical prediction improved Brier **0.167696 → 0.164220** over the assignment-only control. **Zero provider calls; no agent comparison.** This reproduces two rows, not the entire study, and the inspected full sample cannot now serve as an untouched confirmation set. [Replication and baseline](../reports/behavior-feasibility-20261022/baseline/README.md)

## What the evidence changes

- **Predict stability before adding discussion.** Both the classifier and larger swarm study overpredicted change. Initial belief and simple transition controls must stay in every comparison.
- **Separate capabilities.** Better message likelihood, valid probability output, individual prediction, aggregate matching, and causal-effect replication are different achievements. None substitutes for another.
- **Require a defined gain before expanding.** Direct prediction sometimes beat statistical controls on RPS; the tested training and interaction additions did not establish further benefit. Keep negative results and freeze the next comparison before opening another cohort.
- **Resolve panel provenance first.** The next useful step is a verified, consistent outcome and a frozen statistical baseline—not a larger swarm.

## Engineering status · separate automation branch

The 27 October automation run passed **313 offline tests** plus lint, compilation, JavaScript syntax, and whitespace checks; two existing dependency warnings remained. Its bounded mock run scored two questions with 12 votes each (Brier **0.25**): pipeline verification only, with no forecasting interpretation or paid traffic.

The 23 October automation fix records effective mock mode and rejects resumes with changed or unknown mode; earlier safeguards hash implicit roster/persona inputs and provide an identical-prompt control. These changes live on `automation/daily-swarm`; they are **not evidence that the research worktree contains the same fixes or passes that test suite**. No push or merge was performed. [Automation log](</Users/joshua/Documents/Codex/2026-09-20/git-github-com-jhsiehm-sandboxexperiment-git/work/SandboxExperiment/docs/automation/DAILY_SWARM.md>)
