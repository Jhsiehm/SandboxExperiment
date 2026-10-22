# ANES respondent-context development experiment

This is a descriptive extension of the ANES silicon-sampling work, not an exact
paper replication or a powered causal study. It tests independent emulation first.

## Frozen independent comparison

`config/anes2012-decision-context.yaml` fixes the cohort size, models, repetitions,
budget, and later interaction assumptions. Profiles are generated for all 5,914
available respondents. The live cohort is 24 Ohio respondents without earlier
model-call checkpoints and with a recorded pre-election baseline date before
Election Day. These are previously unprompted development cases, not a claim that
their outcomes have never appeared in any earlier retrospective analysis.

Each respondent/model assignment appears in four conditions, twice:

| Condition | Measured profile | Historical context |
|---|---|---|
| sparse_no_evidence | Eight existing fields | None |
| sparse_evidence | Eight existing fields | Fixed pack |
| rich_no_evidence | Twenty fields | None |
| rich_evidence | Twenty fields | Fixed pack |

Within each respondent/repetition, arm order is randomized. All arms use identical
question wording, temperature, token ceiling, and JSON response mode. Outcomes are
probability distributions over reported presidential vote, health-law opinion, and
gun-policy opinion. Their observed values and direct summary aliases are absent
from the feature allowlist. Health/gun tasks are retrospective pre-election item
imputation; vote is retrospective forecast validation. This is not a claim to have
observed changing human opinions after treatment.

The richer profile adds education, personal financial circumstances, insurance,
economic perceptions, and media-use answers. Official Stata variable and value
labels provide the audit. Missing answers remain unknown. Unknown exposure,
memories, trust, relationships, and susceptibility are never asserted as facts.
Web interviews had multiple parts; the baseline is the latest recorded pre-election
interview completion. The historical pack predates all eligible interviews.

## Historical context

`config/anes2012-historical-pack.json` contains two short summaries of official
August 2012 economic releases. Dates and supporting excerpts were checked against
the official sources, and the accessible Fed source bytes are retained and hashed.
The BLS excerpt was verified through the web retrieval tool; direct local download
was blocked. No independent contemporaneous archival-capture claim is made.
This is a narrow economy-focused supplied-context treatment. It is not a balanced
campaign archive, a health/gun evidence pack, or a reconstruction of what each
respondent read. Actual personal exposure and trust remain unknown. Modern models
can still contain post-2012 information in their weights.

## Separate interaction pilot

After independent evaluation, a predefined first-12 subset receives rich profiles
and the same pack. A synthetic directed network exposes each agent to at most
three contacts, favoring similar reported ideology with randomized variation.
Interest-linked participation probabilities and a missing-interest fallback are
fixed in config. Contacts and influence parameters are illustrative assumptions,
not measured ANES relationships. Inactive participants can still receive contact
messages before their final answer. Agents can abstain or retain their views.

The private-reflection control has the identical activity schedule, model
assignments, and number of message/final calls. Public agents see only prior-round
messages during discussion, and selected-contact history before private final
answers. Neither the network nor the selected rich/evidence condition is chosen
by inspecting which independent arm wins. The pilot tests this assumed interaction
mechanism; it does not validate the underlying social network.

## Evaluation and integrity

Scoring opens the separate 0600 evaluation vault only after prediction sealing.
Runtime profiles and cohort files also use 0600 permissions; the run directory is
0700. No target-inclusive staging CSV is created. Source, profiles, field audit,
cohort, exclusion list, model settings, catalog pricing selection, evidence, and
runner sources are hash-bound in a frozen contract. Phase prediction seals bind
checkpoint snapshots, and the social seal also binds network/transcript artifacts.
Evaluation seals bind target bytes, prediction seals, report bytes, and evaluator.

Metrics include half-scaled multiclass Brier, log loss, agreement, and total
variation between predicted and observed response distributions. Multiclass Brier
here is half the summed squared category errors; it should not be confused with an
unscaled multiclass score. Repeated observations are clustered by respondent in
exploratory paired bootstrap intervals. These intervals do not implement ANES
complex-survey uncertainty or network-cluster inference. Multiple contrasts are
exploratory; no automatic winner or claim of significant improvement is made.

Invalid JSON gets one format retry, then remains missing. It is not repeatedly
regenerated until a preferred answer appears. All conditions must retain the
planned cohort and model assignments; scoring compares complete matched panels
and reports missingness. Resume reuses completed or failed checkpoints and rejects
changed prompts/settings. Provider failures stop the process; checkpoints survive.

## Commands

From SandboxExperiment, with the existing ignored ANES source and local environment:

```sh
.venv/bin/python -m psbx.experiments.decision_experiment prepare
.venv/bin/python -m psbx.experiments.decision_experiment independent
.venv/bin/python -m psbx.experiments.decision_experiment interactions
```

The paid phases are explicitly enabled by this authorized live-run entry point and
bounded by the configured request and dollar ceilings. Execution is host-side with
tools disabled; this is not the no-network Docker workflow. Never mount the raw
source or evaluation vault into a model runtime. The config/run ID must be changed
for a genuinely new study, while the same ID resumes an identical contract.
