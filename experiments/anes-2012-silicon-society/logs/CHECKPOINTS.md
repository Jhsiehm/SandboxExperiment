# Checkpoint log

This log records evidence, not aspirations. A working-tree file does not close a gate until its
commit, command, and outcome are recorded.

## 2026-09-23 — Documentation scaffold and local structural artifacts

- Milestones affected: M0–M4
- Repository commit at inspection: `cce0e0621eb49dd6d011742d9c0a070d8a54a68b`
- Working tree: dirty; related implementation was not yet part of the inspected commit
- Protocol state: draft
- Observed local question inventory: 998 total, 486 pre, 512 post, 765 generically eligible, 233
  excluded
- Observed structural split: 5,914 pseudonymous profiles
- Weighting state: `uniform_unweighted_validation_only`
- Observed structural replications: five independent and five society
- Scientific interpretation: none; evaluation declares `scientific_result: false`
- Open evidence: stable implementation commit, parser audit, targeted/full tests, container execution,
  paper-baseline seal, official weight, frozen evidence corpus, and all live arms

This checkpoint intentionally records counts rather than respondent-level data or local artifact
paths that could invite accidental publication. Artifact hashes must be added in the first stable
run record after the implementation is committed.

## Entry template

### YYYY-MM-DD — Checkpoint title

- Milestones affected:
- Git commit SHA:
- Git state clean: yes/no
- Protocol version and amendments:
- Commands executed:
- Test results:
- Input/config/prompt/evidence hashes:
- Prediction/evaluation hashes:
- Aggregate counts only:
- Deviations and failures:
- Supported interpretation:
- Open gates:
- Reviewer:

## 2026-10-04 — Ohio structural experiment and Docker initialization

Executed `docker init`, then adapted its Dockerfile and Compose scaffolding for the
existing pyproject package and sealed batch runner. Restored existing data exclusions
and added `.env.*`, reports, and third-party exclusions. Added
`scripts/run_anes_area.py` and `README.Docker.md` for reproducible state selection,
split verification, container execution, and post-seal evaluation.

Run `anes2012-ohio-20261004` selected all 226 Ohio respondents (FIPS 39), without
outcome filtering. Eight strict pre-election fields were used. Thirty paired
replications, groups of 12, and three rounds yielded 13,560 prediction rows;
164 respondents had valid two-party targets for scoring. The container ran without
network access, with a read-only root, non-root user, dropped capabilities,
no-new-privileges, resource bounds, and only profile/output mounts.

Weighted means: independent Brier 0.105333, agreement 0.864047, Republican share
0.485885; society Brier 0.116824, agreement 0.855999, Republican share 0.474220.
Observed weighted Republican share in the ANES Ohio two-party subset was 0.477793.
These are descriptive state-subset estimates using national survey weights.
The interaction heuristic improves aggregate share proximity but worsens individual
prediction scores in this run. This is not evidence about live LLMs or human social
influence. Repeated seeds reuse the same respondents, not independent survey samples.

Image ID: `sha256:f6d88417b4cb9be9c9ec18377c1343a81ac2595955e2c72f63a8f6272f4df1ac`.
Runtime profiles SHA-256:
`cf40e91d8112dcd64bf432c59db53bb11c3be1bf8097aad3ee17a0a84b494b90`.
Evaluation SHA-256:
`8f31b81b970273009472ba48424e07c311a9a6e3022089dd768cdc896a811ee4`.
Durable evidence: ignored `data/runs/anes2012-ohio-20261004/` contains the manifest,
resolved Compose config, container log, split, sealed predictions, evaluation, and
paired comparison. Runtime/prediction hashes and balanced coverage were verified.
All 21 society/baseline tests passed; the new runner passed Ruff.

Read-only provider checks returned HTTP 401 for both authentication and credits;
no model generation call was made. Evidence is in
`data/runs/anes2012-area-20261004/provider-readiness.json`. Live scientific execution
remains blocked on working provider authentication and subsequent credit validation.


## 2026-10-04 — live Ohio smoke completed after roster failures

User authorized a live test and supplied a replacement credential, stored only in
ignored `.env`. Authentication and credit endpoints returned HTTP 200. No secret
is included in run artifacts or this record.

The original run stopped at retired Claude 3 Haiku (HTTP 404). A separately sealed
six-model run replaced it with catalog-verified Haiku 4.5 and refreshed provider
price ceilings. That run completed 30 logical calls, then repeatedly failed the
Llama final-ballot JSON contract; its checkpoints remain preserved and it was not
scored as a complete treatment panel.

A fresh four-model run, `anes2012-ohio-live-20261004-v3`, used GPT-4.1 mini,
GPT-4o mini, Haiku 4.5, and Gemini 2.5 Flash-Lite. It completed 24 logical calls
(25 request reservations, including one format retry), 16 deliberation rows, and
eight sealed private ballots. Each arm had the same four Ohio profiles, two rounds,
and matched model assignments. Three profiles had valid two-party targets.
Weighted agreement was 100% in both arms; Brier was 0.06547967 independent and
0.08896300 society. These are descriptive scores on three observations, not a
population inference or conclusive interaction effect. No outcomes were used to
select the four-model sample. The run used host provider calls, tools disabled,
no external evidence pack, and supplied-context cutoff 2012-11-05. It was not a
network-isolated Docker run and cannot remove later knowledge from model weights.

All input/target/prediction/conversation/checkpoint seals and balanced coverage
were verified before reporting. The run-local `evaluate.py` corrects the existing
evaluator's hard-coded mock warning for this verified live artifact, while retaining
`scientific_result: false`. Evaluation SHA-256: `f151f711999e21c60ad41e59795e166c2fdc9b39ccdbc1c0dbbd92dfc8afa3d7`.

Across all three attempts: 72 request reservations; provider-reported cost
$0.00880242; one unreconciled reservation from the retired-model error. These are
reported costs, not a reconciled final invoice. Evidence and scripts are in the
ignored run directories; `v3/spend-summary.json` records all attempts. The successful
smoke establishes that live authentication, model calls, paired interaction,
sealing, and scoring work. A powered scientific study remains unrun.


## 2026-10-04 — corrected Ohio live dialogue comparison completed

User requested a fresh state ANES comparison with interacting agents. The first
three-replication attempt stopped after 98 completed logical calls because Gemini
repeatedly returned prose instead of ballot JSON. A subsequent JSON-mode attempt
failed its first provider call. Diagnosis found that `complete_turn` forwarded its
system instruction only to Anthropic, not OpenRouter or other OpenAI-compatible
routes. Earlier live ANES runs therefore did not enforce the intended system/date
instruction on those routes. Their outputs must not be treated as protocol-faithful
replications. All failed attempts were retained and excluded from the corrected
comparison.

Fixes now forward the system message, support opt-in provider JSON output, bind
system-prompt and worker sampling/output settings in the live contract, preserve raw
parse failures in private run artifacts, derive evaluator engine labels from checked
prediction seals, and seal evaluation outputs against the targets, predictions,
prediction seal, and evaluator source. Regression tests cover system forwarding,
JSON-mode requests, provenance mismatch, and evaluation seals. The full offline
suite passed (260 test markers), as did focused Ruff and `git diff --check`.

Completed run: `anes2012-ohio-live-dialogue-corrected-20261004`.
Tracked config: `config/anes2012-ohio-live-dialogue-json.yaml`.
Tracked runner/analyzer: `scripts/run_anes_live_dialogue.py` and
`scripts/summarize_anes_dialogue.py`. The provider catalog selection and exact worker
settings are frozen in ignored run artifacts. Runtime sampling did not inspect
outcomes. All 226 Ohio runtime profiles were eligible; two draws of 12 yielded 24
unique sampled respondents, of whom 22 had valid two-party evaluation targets.

Design: four bodies each for GPT-4.1 mini, GPT-4o mini, and Gemini 2.5 Flash-Lite;
two matched replications; two rounds in groups of 12; temperature 0.8; 256 output
tokens; eight strict pre-election fields; no external evidence pack. Independent
agents reflect privately for the same number of calls; society agents receive prior
round messages before contributing and the complete group discussion before their
private ballot. Execution was on the host with tools disabled, not in a sealed
Docker container. Modern model weights are not restricted to 2012.

The corrected run completed 144 logical/provider calls, without format retries,
failed checkpoints, or unreconciled requests: 48 public messages, 48 private
reflections, and 48 final ballots. Hash seals and exact matched coverage verified.
Mean weighted agreement: independent 82.5762%, society 66.5297%.
Mean weighted Brier: independent 0.11673581, society 0.14847838.
Mean absolute per-replication vote-share error: independent 1.90735 percentage
points, society 1.20171 points. Brier changed by -0.00211416 in replication one and
+0.06559930 in replication two. Four of 24 binary predictions changed after the
interaction treatment; mean absolute probability difference was 7.29167 points.
These are descriptive comparisons, not a powered causal finding: only two groups
and 22 scorable respondents, with no separate model-sampling-noise ablation.

Reported provider cost for the completed run: $0.01765025. Earlier attempts in this
turn reported $0.01137695, plus one unreconciled rejected request. No credentials
are included in these artifacts.

Comparison SHA-256: `9b0ce2e724f285eb35a15755e0ed9f7c27d09929e73ee7baa9ba6ec86bab7986`.
Evaluation SHA-256: `3ca9432b3f8a3288df7d428e078383f6ba5c5d810d70619553f7744b710df063`.
Prediction seal SHA-256: `6c57861c851d3296ef12081b3c02a38c87fb93c3f0a21c2b77a934e8d9115da4`.
The final `comparison.json`, `comparison.seal.json`, `evaluation.json`,
`evaluation.seal.json`, and complete conversations are under the run directory.


## 2026-10-11 — respondent-context factorial and limited-network pilot

User authorized richer evidence-based profiles, with/without historical context, independent comparisons before conversation, less artificial interactions, and broader survey fidelity.

Built 20-field, label-decoded profiles for all 5,914 respondents. Field timing and categories are audited against the official source and existing timing audit. Held-out presidential vote, health-law opinion, and gun-policy opinion are excluded from runtime fields. Actual media exposure, recall, trust, social ties, and susceptibility remain unknown. Targets are separate 0600 files in a 0700 evaluation-vault directory; no target-inclusive staging CSV is created.

The Ohio cohort has 24 previously unprompted respondents, excluding 31 earlier prompted IDs and requiring dated pre-election interviews. This is a development cohort, not a claim that outcomes were never used in earlier retrospective analyses. Four matched conditions cross eight/twenty fields with no pack/a small fixed economy-focused historical pack. Two stochastic repeats, balanced fixed model assignments, and randomized condition order produced 192 calls. Models: GPT-4.1 mini, GPT-4o mini, Gemini 2.5 Flash-Lite; temperature 0.4; JSON mode; 256 output tokens.

Historical context comprises the original August 3 BLS July employment release and August 1 FOMC statement. Source dates/excerpts were verified through official pages; Fed HTML bytes are retained. BLS direct local download was blocked, so only its tool-verified excerpt/provenance is retained. No independent contemporaneous capture or personal exposure is claimed. All pack dates precede eligible interviews. The pack is not a balanced campaign archive and contains no dedicated health/gun-policy evidence.

Unique scorable cases: 18 for vote, 24 for each attitude. Health/gun outcomes are held-out pre-election item imputation; they are not observed human post-conversation changes. Half-scaled multiclass Brier, weighted agreement, log loss, distributional total variation, repeated-answer stability, and exploratory paired respondent-bootstrap contrasts are recorded. Multiple comparisons and small samples preclude general causal claims.

| Condition | Vote Brier | Health-law Brier | Gun-policy Brier |
|---|---:|---:|---:|

| sparse_no_evidence | 0.106901 | 0.246143 | 0.349783 |

| sparse_evidence | 0.134875 | 0.255654 | 0.325233 |

| rich_no_evidence | 0.089928 | 0.256184 | 0.316412 |

| rich_evidence | 0.103553 | 0.255109 | 0.337712 |


Richer profiles without supplied evidence improved vote Brier by 0.0170 in this development sample, but health-law Brier worsened by 0.0100. Evidence worsened vote Brier in both profile conditions. Do not equate richer information or supplied historical context with universal improvement.

The separate predefined first-12 social pilot used rich profiles plus evidence, not a post-hoc winning arm. A synthetic directed ideology-homophilous network limits each agent to three contacts; interest-linked activity probabilities and abstention are permitted. These rules are assumptions, not observed ANES relationships. Private reflection shares exactly the same activity schedule and call counts. Two rounds produced 12 private reflections, 12 nonempty public messages (four message turns received prior contact messages), and 24 final multivariate predictions. Vote had ten scorable respondents; policy outcomes had twelve.

Social versus private Brier: vote 0.1086 vs 0.0907; health law 0.2546 vs 0.2919; gun policy 0.3658 vs 0.4199. Gun modal-answer agreement nevertheless fell from 26.1% to 17.7%; probability loss and classification accuracy must not be conflated. No default swarm improvement is established.

All 240 live calls completed without retries or invalid responses; reported provider cost $0.04662035, no unreconciled entries. 271 offline tests passed, including eleven new decision-context tests. Ruff and diff checks passed.

Contract binds profiles, field audit, cohort, exclusion list, evidence, complete worker settings, pricing/catalog snapshot, and runtime source. Phase seals bind predictions and checkpoint snapshots; the social seal also binds network/transcripts. Evaluation seals bind targets, prediction seal, report, and evaluator. All were verified after execution. Live calls remain host-side with tools disabled; modern weights are not historically isolated.

Summary SHA-256: `0d77d5ae4326ea9a684230bec36c339fef7f62ed17eb1fad7b0a460346d48bc0`. Contract SHA-256: `211f6bf972c206cd1f284db8e569435c9ab6b0b0e365da31c81b1b2f9065b68c`.

Implementation: `src/psbx/experiments/decision_profiles.py`, `decision_experiment.py`, `config/anes2012-decision-context.yaml`, `config/anes2012-historical-pack.json`, `scripts/summarize_decision_context.py`, `tests/test_decision_context.py`. Protocol: `docs/ANES_DECISION_CONTEXT_PROTOCOL.md`. All detailed artifacts are in ignored `data/runs/anes2012-decision-context-20261011/`.

### 2026-10-13 — larger independent validation completed; benefit did not replicate broadly

Run `anes2012-ohio-reserved-validation-20261012` completed with 120 previously
unprompted Ohio respondents, two repetitions, sparse/rich observed profiles,
no historical pack and no conversation: 480 valid logical responses, all first
format attempts. Fifty additional eligible IDs were reserved and never prompted.
Three fixed/balanced model assignments were held constant across arms. The run
contract, prompt jobs, source hashes and improvement rule froze before paid calls.

Scorable unique people: vote 84, health law 116, gun policy 120. Weighted effective
respondent sizes were 49.6, 69.4 and 72.6, respectively. Weighted half-multiclass
Brier sparse→rich: vote .147859→.145513; health .276586→.282043;
gun .279448→.288865. Equal-task average .234631→.238807. Paired average change
+.004176, conditional respondent-bootstrap 95% interval [-.009541,+.017883].
The predeclared development gate failed. No evidence of a general improvement;
intervals also do not establish that rich profiles are generally harmful.
Weighted agreement fell on all three tasks: .8610→.8327, .5614→.5314,
.5552→.5214. Policy repeat stability improved despite worse individual scores.
Gun aggregate distribution TV improved .0995→.0786 while individual fidelity
worsened, illustrating the distinction between population fit and personal fit.

Simple party-smoothed prior-cohort baseline Brier: vote .147425, health .300606,
gun .270241. Thus language-model superiority is outcome-dependent. Secondary
calibration diagnostics were explicitly exploratory, added without changing the
frozen experiment or gate. Twenty candidate/blocked fields were audited by official
Stata labels; none were added to this run. POST discussion/MIP and target-derived
health-law aliases remain excluded from proposed pre-election profile enrichment.

Both Docker planner and validator executed with network none, read-only root/input,
non-root UID, dropped capabilities, no-new-privileges, resource limits, and exactly
selected-input/output mounts. No credentials, raw data, labels, reserved profiles
or Docker socket were mounted. Docker Desktop's dormant tunnel interfaces were
handled by checking for active non-loopback interfaces before the contract froze.
Remote inference was through a trusted host broker, not inside an air-gapped LLM.
Image ID, 52 package versions, matching host/image runner hash, eight source
snapshots, resolved container inspections and integrity seals were retained.

Initial execution ended with a confirmed provider read timeout after other workers
continued. Same-contract resume reused 202 saved responses. Final ledger contains
482 reservations: 480 reconciled valid responses and two unresolved usage records.
Confirmed provider-reported cost $0.0836825 excludes unresolved usage; do not claim
an exact final bill. Existing provider limits were not weakened. Worker exception
visibility needs improvement in a future runner version, not a mid-run source edit.

Full offline suite: 278 passed (two pre-existing dependency deprecation warnings).
Focused Ruff, git diff --check, all frozen bindings/seals, both mount inspections,
all planned assignments and zero reserved-ID overlap verified. Completion seal:
`data/runs/anes2012-ohio-reserved-validation-20261012/completion-seal.json`.
Protocol: `docs/ANES_RESERVED_VALIDATION_PROTOCOL.md`. Results and exploratory
calibration: `evaluation.json` and `diagnostics.json` in the run directory.
Local artifacts are uncommitted; absolute paths and range-specified dependencies
mean clean-checkout portable reproducibility is not established. Retain the image.

## 2026-10-14 — empirical interaction benchmark and per-turn Docker isolation

Reviewed primary research on individual emulation, generative societies, opinion
dynamics, and experimental-effect forecasting. Added a separate DEBATE pilot to
test actual initial-to-final human opinion prediction; ANES's 50-ID reserve remains
unused and all 17 prior completion bindings still verify.

Run `debate-isolated-social-pilot-20261014`: 32 people, eight convenience-selected
four-person groups, four topics, one GPT-4.1-mini model/repetition. Profiles use
only initial private ratings/explanations, with no exit-survey demographics or
final-answer leakage. Private reflection and generated interaction use seven
calls/person; actual incoming-human-message replay uses one. Persistence requires
no model. Generated interactions use the recorded dyadic partner schedule but only
two message passes/round and omit the original tweet phase; not a full replication.

All 480 paid calls completed on first format attempt, producing 96 final forecasts
and 384 generated messages. No provider failures or unresolved usage. Recorded
provider cost USD0.1506896. Existing concurrency/rate limits unchanged. Final
predictions/checkpoints were sealed before evaluation targets were opened.

Primary RPS: persistence .16250, private .15808, swarm .12166, replay .1111575.
Swarm-private delta -.03642, group-bootstrap95% [-.0741794,-.0017786]; six/eight
groups improved. Swarm-persistence interval [-.1116978,+.0235032] crosses zero.
Expected-rating absolute error: persistence .81250, private1.10500, swarm .958125,
replay .854375. Change-direction accuracy:56.25%,50%,62.5%,68.75%, respectively.
Human unchanged18/32; false modal movement private7/18,swarm4/18,replay3/18.
Swarm group dispersion error worsened versus private. Variance of expected scores
is not a joint predictive group variance and can reflect uncertainty. Generated
public messages median45words versus human16, showing a remaining style mismatch.

Promising exploratory interaction signal; no automatic promotion, population
claim, causal human-treatment claim, or declaration that swarms generally work.
Replay is a conditional diagnostic and differs in input and compute. New groups,
topics, direct-answer and empirical-transition controls are needed for confirmation.

Fresh no-mount Docker worker per call: network none, read-only root, user10001,
dropped capabilities/no-new-privileges/resource limits. Host broker retains API
access; remote model inference is outside Docker. Runtime probes passed on all480
calls. Independent audit reconstructed exact histories and recalculated RPS.
Exact Linux/arm64 image exported with verified OCI index and12hashed blobs.
288 offline tests passed; focused lint/diff checks passed. New modules preserved
earlier frozen experiment sources; the sequential runner surfaces failures promptly.

Docs: `docs/SOCIAL_EMULATION_RESEARCH.md`, `docs/DEBATE_ISOLATED_PILOT_PROTOCOL.md`,
`docs/DEBATE_ISOLATED_PILOT_RESULTS.md`. New scripts audit and plot the sealed run.
DEBATE data and derivatives are research-only licensed, with creator attribution;
do not assume commercial-product rights. Raw data and artifacts remain local.

## 2026-10-20 — individual-agent development comparison

Completed `anes2012-ohio-individual-development-20261020`:24 previously inspected
Ohio people, two repeats, GPT-4.1-mini, four independent-agent conditions. Sparse 8,
rich 20, focused 15 direct, focused 15 with private evidence review. Focused adds measured
health, gun ownership, political attention, social trust while reducing other fields.
All four new fields observed for all 24. No conversation or historical pack.
Statistical baselines fit on the other 96 development people;50 reserve excluded.

Weighted equal-task half-Brier: prevalence .29645;party .25009;sparse .26736;
rich .27166;focused .25996;reviewed .26601. Primary focused-rich delta-.01170,
95%paired-person bootstrap[-.04104,+.01600]. Development gate FAILED, no promotion.
Review-focused +.00605[-.02596,+.03189]. Focused-party+.00987[-.03380,+.05426].
20 scorable vote cases and 24 each policy;effective weighted n 12.18 and 14.62.
Focused gains mainly in gun policy, but allagent variants underpredict keeping
rules the same.19/24 actually chose that category;88.45%weighted versus 41.97%
focused predicted share. Source target codes/values independently verified after
sealing. Unweighted sensitivity changes small agent rankings; no robust winner.

240 calls valid on first attempt,192 final forecasts,48 private reviews;zero recorded
provider failures/unresolved usage. Provider-reported cost USD.0929464.296 tests
passed;focused lint/diff checks passed. Independent audit confirms scores,
training/evaluation/reserve separation, correct own-profile inputs and same-repeat
review pairing. Sixreviews exceeded soft 80-word prompt preference(max 86), retained.

Fresh Docker prompt worker perturn, no mounts/network/credentials, non-root,
read-only, droppedcaps/no-new-privileges/resource limits. Exact image archived and
OCI index/13 blobs verified. Hostbroker/remote inference remain outsideDocker.
Frozen contract435f7e745689714377519f0c5eb27fd4d8edbd0db5e35db421126a1d0430d322.
Docs:ANES_INDIVIDUAL_DEVELOPMENT_PROTOCOL.md and ANES_INDIVIDUAL_DEVELOPMENT_RESULTS.md.
Next:development field ablations and calibration/baselines;no reserve tuning or
swarm expansion warranted by this pilot. Previous frozen source modules unchanged.
