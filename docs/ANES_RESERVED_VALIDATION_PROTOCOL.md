# Independent Ohio validation and Docker boundary

Run: `anes2012-ohio-reserved-validation-20261012`.

The October 11 experiment favored richer profiles without its small economic
context pack on vote Brier, but effects differed by task. This follow-up changes
sample size while retaining the profile definitions, task wording, temperature,
and model roster. It does not select another historical pack after seeing results.

## Design fixed before calls

- 170 eligible previously unprompted Ohio respondents, excluding the 55 people
  appearing in earlier call checkpoints; recorded pre-election completion dates.
- Seed 20261012 splits 120 validation cases and 50 reserved respondent IDs.
- The reserved cases are not mounted into containers or sent to model providers.
  They are not guaranteed untouched by every earlier retrospective dataset analysis.
- Sparse eight-field versus rich twenty-field profiles, without external context.
- Two repetitions per respondent and condition: 480 planned calls. Fixed, balanced
  respondent/model assignments across three models; condition order randomized.
- Maximum 960 requests (one format repair per call), maximum $5; actual costs
  separately reconciled. Three concurrent provider workers, one for each model.
- Primary contrast: equal-task mean of weighted half-multiclass Brier differences
  (rich minus sparse), evaluated over vote, health law, and gun policy.
- Development gate: mean improvement at least .005, no task worsens by more than
  .01, and conditional respondent-bootstrap 95% interval for mean change below 0.
  These are engineering thresholds, not a power calculation or a registered trial.
- Resample respondents jointly across tasks; repetitions are not independent people.
  Missing target answers remain unscored. An invalid prediction excludes that
  respondent from all paired comparisons rather than selectively dropping arms.
- Secondary metrics: agreement, log loss, response-distribution total variation,
  weighted/unweighted Brier, repeat stability, per-model summaries, effective sample
  size. Report outcome-specific counts and effective respondent n.
- Simple reference predictors use only previously prompted respondents: weighted
  outcome prevalence (add-one category counts) and party-specific estimates shrunk
  toward prevalence with five pseudocounts. These are deliberately simple
  references, not optimized machine-learning competitors. No new cohort labels
  influence their rules or fitting.

## Executed boundary

The existing Dockerfile installs application code without source data or secrets.
The new workflow builds `psbx-anes-validation:local` and records its immutable local
image ID. Planning and response validation run by that ID, with:

- no network (`none`), read-only root and input bind mount;
- non-root UID, all capabilities dropped, no-new-privileges;
- 1 GiB memory, two CPUs, 128 PIDs, 64 MiB noexec/nosuid temporary filesystem;
- exactly two mounts: selected runtime inputs, and a writable output directory;
- no ANES source, evaluation vault, reserved profiles, credentials, or Docker socket.

In-container probes check non-root execution, loopback-only networking, absence of
provider key and forbidden paths, denied writes to root/input, and NoNewPrivs.
Resolved Docker inspection is saved for both stages. The container emits frozen
prompt jobs, and later reconstructs those jobs and validates complete matched
response coverage. Predictions seal before the separate host evaluator reads labels.

A trusted host broker makes the external API requests; inference takes place at
remote providers. This is not an air-gapped LLM, a hostile-host security guarantee,
or temporal decontamination of model weights. The broker runs with host privileges
and can technically access host files, although its execution path reads only
contract-bound prompts, worker settings, checkpoints, and credentials.
Hash seals detect changes relative to saved hashes; they are not independent digital
signatures or proof against a host administrator rewriting both data and seals.

Dependencies remain range-specified. Retain the image for exact environment reuse;
rebuilding from the Dockerfile alone is not guaranteed bit-for-bit reproducible.
Live stochastic provider outputs also need not reproduce exactly.

## Commands

```sh
docker build -t psbx-anes-validation-deps:20261012 .
docker build -f Dockerfile.validation -t psbx-anes-validation:local .
.venv/bin/python -m psbx.experiments.reserved_validation prepare
.venv/bin/python -m psbx.experiments.reserved_validation run
.venv/bin/python -m psbx.experiments.reserved_validation evaluate
```

Do not modify bound source after preparation or reuse the run ID for a different
experiment. Resume uses saved requests and rejects changed prompt fingerprints.
Old October 11 source modules and seals are preserved.

## What to test next

First use the validation result to decide whether the broad profile package merits
promotion. If effects remain mixed, work on the now-used development cohort with
feature-block ablations, matched-length formatting controls, and shuffled-extra-field
negative controls before spending the 50-case reserve. Once a design is frozen,
use the reserve once, report every outcome, and seek a new geography/year for
external validation. Do not keep reusing it until performance improves.

A later historical-context trial should distinguish no context, balanced topic
context known to have been available, and explicitly assumed media-channel exposure.
Actual personal exposure may be asserted only where directly observed. Retrieval
must use profile/topic/date, never held-out answers. Topic-pack length, wording,
source balance, question wording, and model assignment should be controlled.
A media-use answer does not establish reading, remembering, believing, or trusting
any particular article. A richer factual briefing can make an agent more informed
than the person it is meant to emulate.

Local Stata label inspection identifies pre-election political attention,
trust, gun ownership, health status, and political-knowledge candidates. They are
candidates for a separate provenance and leakage audit, not fields added in this run.
Health-law strength/summary aliases must be withheld with the health-law target.
The main most-important-problem and political-discussion items are labeled POST:
loading them into a pre-election profile would cross the intended time boundary.

ANES provides redacted open-ended auxiliary data, but individual items still need
timing, identity-linkage, consent/access, missingness, and target-leakage checks.
The 2012 vote-validation supplement concerns turnout and registration; it does not
supply verified secret-ballot candidate choices.

Sources:
- https://electionstudies.org/data-center/2012-time-series-study/
- https://arxiv.org/abs/2411.10109v3
- https://docs.docker.com/engine/containers/run/

## Operational findings during execution

The initial broker process encountered provider read timeouts. Saved responses were
retained, the original log was kept, and the same contract was resumed; no arm,
prompt, model, sample, or outcome definition was changed. Unreturned usage records
remain unreconciled rather than being treated as free requests. Existing provider
limits permit only one in-flight call despite three application workers. Future
runner versions should surface each worker failure immediately, instead of waiting
for all submitted workers to finish before exposing the first exception. That
control-flow change is deliberately not made to the contract-bound runner mid-run.

Docker Desktop exposed dormant tunnel interfaces in network mode `none`. The
initial overly strict probe rejected their names. Before the contract was frozen
or any live calls were made, the probe was corrected to reject active non-loopback
interfaces; resolved Docker network mode is also retained. Read-only, non-root,
no-secret, and no-new-privileges probes all remained required.

`image-environment.json` records 52 package versions and a matching host/container
runner hash. `frozen-source/` retains eight bound source files with a separate
archive seal. This preserves exact code without claiming that the original
absolute-path contract is portable.

The added `scripts/diagnose_reserved_validation.py` reads only sealed evaluation
artifacts and produces exploratory top-label calibration bins and entropy. These
are secondary diagnostics created during the run, not part of the frozen primary
gate. Calibration bins contain repeated rows and have no inferential intervals.

## Interpretation limits for human emulation

A rich profile is a bundle of observed answers, not a recovered person. Keep four
layers separate: recorded self-report; latent/unknown characteristics; externally
supplied experimental information; and held-out evaluation answers. Generated
explanations must not be promoted into evidence about the real respondent.

The current three-choice targets exclude don't-know/refusal responses. The vote
summary also combines some nonvoting and nonreporting cases in its negative code;
that code cannot be treated as a clean turnout measure. Thus this benchmark does
not yet measure realistic abstention, refusal, or nonresponse. The PREPOST vote
summary may include already-reported early votes, so not every case is a forecast
of a future choice from the interview baseline.

Marginal answer agreement does not establish calibration, realistic cross-issue
associations, a human decision process, or plausible social influence. Conversely,
repeat consistency alone is insufficient: a consistently wrong caricature is
stable. The three probability vectors do not define a joint distribution over
all three issues. Future cross-issue tests must make their joint-response sampling
assumptions explicit.

Recommended later diagnostics on development cases, before opening the reserve:

1. Add observed feature blocks separately: education/finances; economic beliefs;
   insurance/health; media use; audited political attention/knowledge/trust.
2. Test factual tables versus faithful summaries of exactly the same observed
   content; control information content and prompt length where feasible.
3. Shuffle extra features between respondents within coarse baseline strata,
   clearly treating these as negative controls rather than real people. A similar
   benefit under shuffling would weaken an individual-information explanation.
4. Compare against tuned, held-out statistical predictors as well as the simple
   previous-cohort baselines, with all tuning confined to development data.
5. Test confidence, minority-category shares, measured don't-know/refusal behavior,
   and subgroup/mode errors with adequate cell counts and uncertainty.
6. Only then assess interactions, with equal computation/private reflection,
   limited contacts, measured or explicitly assumed ties, optional participation,
   no forced consensus, and comparison to real longitudinal or experimental change.

The 50-person reserve is a small future confirmation set, not an inexhaustible
optimization resource. More generations of the same 120 people cannot substitute
for more independent people or external validation in another setting.
