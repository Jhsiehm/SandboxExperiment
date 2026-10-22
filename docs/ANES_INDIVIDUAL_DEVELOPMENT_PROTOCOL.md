# Individual-agent development comparison — 2026-10-20

Run `anes2012-ohio-individual-development-20261020`. This narrative describes the configuration and executable contract frozen before paid calls. Contract seal: `435f7e745689714377519f0c5eb27fd4d8edbd0db5e35db421126a1d0430d322`.

## Question

Can selecting measured personal evidence improve independent response reconstruction, and does a brief private evidence review help beyond a direct answer? No interaction or historical evidence pack is used.

## Sample and information boundaries

Select 24 people by seed 20261020 from the previously inspected 120-person Ohio development cohort. The other 96 supply statistical baseline training data. The separate 50-person reserve is excluded from both sets. These 24 people are not a fresh holdout; previous analyses have already exposed their outcomes. Predictions are sealed before this run's evaluator opens targets, but that execution boundary cannot undo prior researcher exposure.

Only the source columns caseid, health_self, owngun_owngun, interest_attention, and trust_social are read during additional-covariate preparation. Their official Stata labels identify PRE measurements. Negative/missing codes remain explicitly unknown; no imputation or invented biography is performed. These fields are not target aliases. The health-law and gun-policy targets are contemporaneous item reconstruction, so PRE labels do not imply each input precedes each target within the interview. Gun ownership may reveal genuine relevant information, but not the held-out gun-policy answer itself.

## Conditions

| Arm | Observations | Calls per person per repeat |
|---|---|---:|
| sparse_direct | Existing eight observed profile fields | 1 |
| rich_direct | Existing 20 observed fields | 1 |
| focused_direct | Existing eight, personal-finance change, insurance, economic retrospective perception; plus measured health, gun ownership, political attention, social trust:15 total | 1 |
| focused_review | Same focused 15; short review of relevant observations and missing information before final prediction | 2 |

The focused condition changes both feature selection and four additional measured covariates. It cannot identify the contribution of any individual field. Later ablations are required. The private review is prompted to stay within 80 words, summarize evidence/unknowns, and avoid predicting answers or inventing motives. It is not an attempt to elicit hidden chain-of-thought. The parser enforces a 4,000-character ceiling; actual word compliance is audited.

All arms predict vote, health-law opinion and gun-policy opinion as three probability vectors. Vote is scored only for reported eligible vote categories; missing targets are excluded per task. Arm order is randomized within each person and repetition. Two stochastic repeats use the same model, temperature and output allowance. They are not independent human observations. Each provider call is stateless except for the explicitly supplied same-person review in its designated arm.

## Statistical baselines

After predictions seal, fit weighted outcome prevalence and a party-conditioned smoothed distribution on the other 96 development people only. Use task-valid cases, weights normalized to mean 1, add-one marginal smoothing, and party counts shrunk with five prior pseudo-observations. An unseen party category falls back to the training prior; missing party is its own category when present in training. No evaluation-person outcomes enter baseline fitting, and no reserve outcomes are used. These are simple comparators, not an exhaustive search for the strongest statistical model.

## Execution and isolation

GPT-4.1-mini via OpenRouter, temperature .4, maximum 256 output tokens, JSON mode. Planned 240 logical calls,500 request cap,USD 2 cap. Existing provider rate/concurrency limits remain unchanged. At most one format repair per logical call. Persistent invalid output stops execution. Provider exceptions are recorded by type and surfaced immediately; resumption verifies payload/model fingerprints.

Every turn starts a new non-root Docker prompt worker with network none, read-only root, no mounts, no credentials, all capabilities dropped, no-new-privileges, and resource limits. The input includes only that person's allowed observations, interview date, condition/stage, and permitted review. The host checks exact agreement with its own prompt construction. Runtime probes verify the isolation settings. Remote model inference remains outside Docker, and the host broker is trusted.

Source, selected data, training/reserve IDs, model settings, price catalog, and imageID are bound by a frozen contract. All prediction checkpoints are sealed before evaluation. No previous experiment source is modified.

## Metrics and decision rule

Primary: focused_direct minus rich_direct, equal-task mean of survey-weighted half-multiclass Brier loss. Average each person's two repeat losses, not their probabilities, before computing paired contrasts. Lower is better. A 4,000-draw paired respondent bootstrap resamples people jointly across tasks/conditions; survey weights are retained. This is conditional uncertainty in a small selected Ohio development subset, not full ANES survey-design inference.

The development signal gate requires macro improvement at least .005, upper 95%bootstrap endpoint below 0, and no task regression exceeding .01. It is not a promotion gate or confirmation on fresh people.

Secondary: focused_review versus focused_direct; rich versus sparse; focused versus party baseline; per-task accuracy, mean top-category confidence, and repeated modal-choice agreement. Secondary contrasts are exploratory without multiplicity correction. There is no automatic change to profiles or prompts based on results.

A favorable result motivates fixed candidate testing on new respondents. An unfavorable result motivates development ablations, not repeated tuning on the unused reserve. Policy reception under interventions remains a separate future benchmark.

## Reproduction

From SandboxExperiment:

```sh
docker build -f Dockerfile.individual-worker -t psbx-individual-worker:local .
.venv/bin/python -m psbx.experiments.individual_validation prepare
.venv/bin/python -m psbx.experiments.individual_validation run
.venv/bin/python -m psbx.experiments.individual_validation evaluate
```

A frozen run requires its original bound files and image ID; rebuilding a tag does not replace those requirements. Full clean-checkout portability is not claimed. Runtime artifacts stay in `data/runs/anes2012-ohio-individual-development-20261020/`.
