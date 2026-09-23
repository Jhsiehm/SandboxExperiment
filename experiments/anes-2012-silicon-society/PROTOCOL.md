# Protocol overview

- Protocol status: draft
- Protocol version: 0.1
- Information cutoff for forward prediction: 2012-11-05
- Election date: 2012-11-06

## Research questions

1. Can the published paper-style silicon-sample comparison be reproduced with the declared ANES
   fields and scoring rules?
2. How accurately do modern models predict held-out individual and aggregate ANES responses when
   supplied context and tool access are restricted to an election-eve information world?
3. Holding profiles, questions, evidence, model roster, budgets, and seeds fixed, does bounded peer
   conversation change final private response fidelity relative to independent answering?

## Experimental units and outcomes

The unit is a pseudonymous respondent-question-replication assignment. The treatment contrast is
society interaction versus independent answering. Public interaction messages are intermediate
treatment artifacts; only private final answers enter the primary outcome.

Primary outcomes for the vote target are weighted aggregate vote-share error and individual
correspondence. Brier score is used when calibrated probabilities are collected. Agreement and
Cohen's kappa may be reported as descriptive correspondence metrics. Uncertainty must reflect
replication and respondent/question clustering appropriate to the estimand.

## Required arms

| Arm | Profiles | Evidence | Interaction | Role |
|---|---|---|---|---|
| Paper-style independent | Published profile fields | None | No | Replication baseline |
| Forward independent | Pre-election only | Matched frozen pack | No | Society control |
| Forward society | Same as control | Same matched pack | Bounded rounds | Treatment |
| Shuffled profile | Shuffled | Matched | Match parent arm | Profile ablation |
| Shuffled evidence | Same | Shuffled eligible pack | Match parent arm | Evidence ablation |
| No evidence | Same | None | Match parent arm | Model-prior ablation |

Assignments, prompt order, evidence packs, model allocation, sampling settings, and budgets must be
paired across the independent and society contrast.

## Temporal and leakage boundary

Post-election answers and certified outcomes are evaluation-only. Pre-election ANES responses are
private contemporaneous covariates, not public evidence, and are permitted only when their timing is
verified. Raw respondent data and the evaluation vault are never mounted in a runtime container.

A modern hosted model may contain later knowledge in its weights. The supported description is:
"modern model, no browsing or external tools, supplied context restricted to authenticated material
dated on or before 2012-11-05." Model-prior and evidence effects therefore require separate
ablations.

## Question inclusion

The inventory includes every named questionnaire specification. Automated experimental prompts
exclude restricted or identifying fields, interviewer or routing items, display-only items,
free-text answers, unbounded numeric fields without answer sets, and items with no extracted
wording. Vote prediction also excludes post-election measures and pre-election fields that directly
reveal an already-cast vote.

All exclusions remain in the inventory with reasons. A manual stratified audit is required before
the eligible subset is frozen.

## Stopping and failure policy

- A budget or safety ceiling stops new paid calls; completed and failed attempts remain recorded.
- Missing responses are retained and reported rather than silently regenerated until success.
- A protocol or input fingerprint mismatch must refuse resume.
- Prediction artifacts are append-only and sealed before evaluation.
- Structural-pilot output must carry `scientific_result: false`.
- Any change to an estimand, arm, eligibility rule, prompt contract, model roster, sampling setting,
  or evaluation method after protocol freeze is an amendment recorded in `logs/DECISIONS.md`.

## Responsible-use boundary

The experiment evaluates aggregate response fidelity under declared treatments. It must not infer
how a named person voted, support political targeting or persuasion, or describe synthetic agents
as literal people. Protected traits are covariates in a controlled research design, not deterministic
political labels.

The more detailed implementation-facing protocol is maintained at
[`docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md`](../../docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md).
If the two documents conflict, the frozen version named in the latest checkpoint governs and the
conflict must be logged before another run.
