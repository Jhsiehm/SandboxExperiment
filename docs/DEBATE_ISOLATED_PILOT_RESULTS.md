# Social-emulation pilot: results and decision

Completed 2026-10-14. Run `debate-isolated-social-pilot-20261014`.

**Decision: continue controlled development, with a promising interaction signal; do not promote this swarm as a validated human simulator.** Generated conversation improved probabilistic prediction over repeated private reflection on this small sample. It did not establish superiority to persistence across metrics, and important human-fidelity problems remain.

## What ran

32 real research participants in eight four-person groups across four topics: government responsibility, income equality, competition, and democracy. One model (GPT-4.1 mini), one repetition, 480 live calls. Profiles contained the person's recorded initial rating and explanation. Three conditions used private reflection, generated dyadic conversations, or actual incoming human messages. Persistence predicted the initial rating exactly without model calls.

The private and swarm conditions each used seven calls per person; input-token counts differed. Generated conversations used two messages per person per round across three rounds, shorter than the original human protocol and without its tweet phase. Replay is a conditional diagnostic, not a causal or compute-matched control. See the [frozen protocol](DEBATE_ISOLATED_PILOT_PROTOCOL.md).

## Main results

RPS is ranked probability score for the six-category ordinal response, lower being better. Absolute error uses the predicted expected rating on the 1–6 scale. Direction accuracy uses the modal category's change relative to the initial rating.

| Condition | RPS ↓ | Expected-rating absolute error ↓ | Change-direction accuracy ↑ | Exact modal-rating accuracy ↑ |
|---|---:|---:|---:|---:|
| Keep initial opinion | .16250 | .81250 | 56.25% | 56.25% |
| Private reflection | .15808 | 1.10500 | 50.00% | 43.75% |
| Generated conversation | .12166 | .95813 | 62.50% | 50.00% |
| Real incoming messages | .11116 | .85437 | 68.75% | 56.25% |

The predeclared primary contrast, swarm minus private RPS, was **−.03642**, a 23.0% relative reduction. The exploratory paired group-bootstrap 95% interval was **[−.07418, −.00178]**. Six of eight groups improved. This is an encouraging within-pilot result, with an interval only narrowly excluding zero and just eight selected clusters.

Swarm minus persistence RPS was −.04084, interval **[−.11170, +.02350]**. A reliable advantage over persistence is not established. Persistence also had the lowest expected-rating absolute error. Real incoming messages minus private RPS was −.04692, interval [−.07226, −.02133]. The replay point estimate was better than the swarm's, but this comparison does not isolate a causal benefit of authentic wording or prove that message generation is the only remaining problem.

![Pilot scores and paired group differences](../data/runs/debate-isolated-social-pilot-20261014/results.png)

## Failures that matter for human fidelity

**Unnecessary movement remains.** Fourteen people changed their rating; eighteen did not. Private reflection incorrectly moved the modal prediction for 7/18 unchanged people, generated conversation for 4/18, and real-message replay for 3/18. Conversation improved this diagnostic but did not solve it.

**Change probability was too high on average.** Actual change occurred in 43.75% of people. Mean predicted change probability was 55.53% for private reflection, 59.63% for the swarm, and 55.94% for replay. This is an exploratory calibration warning from a small sample, not a precise population calibration estimate. Binary change Brier improved from .26159 (private) to .25258 (swarm) and .22578 (replay), illustrating that better overall prediction can coexist with average overprediction.

**Group disagreement is not yet reproduced.** Mean within-group variance was 1.22656 initially and 1.25781 in final human ratings. Variance of predicted expected ratings was .55398 for private reflection, .23889 for the swarm, and .28225 for replay. Swarm absolute dispersion error was 1.04775 versus .93642 for private reflection. These are warnings about compressed predicted means; probability vectors do not specify a joint group distribution, and uncertainty can compress expected ratings. This diagnostic alone is not proof that sampled agent societies would converge excessively.

**Conversation remains stylistically artificial.** Median generated message length was 45 words versus 16 for observed incoming human messages; means were 44.85 versus 19.97. There were 192 generated public messages versus 254 nonempty observed incoming messages. No generated message was empty despite silence being allowed. Human empty messages were filtered in preprocessing, so a comparative silence rate cannot be inferred. Length is only a descriptive indicator, but the mismatch argues for improving turn-taking and exposure realism before simply making conversations longer.

## What to improve next

1. Preserve these eight groups as inspected development evidence. Reserve new groups and whole topics before tuning; repeat across seeds and models only after a candidate is frozen.
2. Add an initial-profile-only direct-answer control. Repeated private reflection is not necessarily the strongest independent baseline.
3. Fit a simple probabilistic transition baseline on development data. Exact persistence is a useful lower-complexity comparison, but a calibrated model of stability and response noise is stronger.
4. Compare observed-length turn-taking, bounded attention, and realistic exposure against the current fixed two-pass design, one factor at a time. Add a predefined shuffled-message control to separate informative exposure from added context length.
5. Improve personal profiles using observed issue salience, trust, knowledge, and circumstances where available. Never infer missing biography as fact. Keep the unused ANES reserve sealed while diagnosing development failures.
6. Require gains on proper prediction scores plus calibration and heterogeneity guardrails before promoting an interaction model. Investigate policy reception later with held-out human intervention data.

This run justifies a larger, better-controlled confirmation. It does not justify scaling agent counts as the main research investment, attributing the benefit uniquely to a human-like mechanism, or promising reliable policy forecasts.

## Execution, isolation, and reproducibility

- 480/480 live calls completed; 96 final forecasts and 384 generated reflection/public messages.
- All calls valid on the first format attempt; zero recorded provider failures and zero unresolved usage records.
- Provider-reported cost: **USD .1506896**. This is recorded provider usage, not an independently reconciled invoice.
- **288 offline tests passed**, with two existing dependency deprecation warnings. Focused lint and diff checks passed.
- Independent audit verified all 480 checkpoints, private-state boundaries, exact message-history reconstruction, frozen bindings, and independently recomputed RPS.
- Every prompt-worker job passed isolation probes. Separate Docker inspection confirmed no mounts/network/credentials, non-root execution, read-only root, dropped capabilities, no-new-privileges, and resource limits.
- Exact Linux/arm64 worker image exported and all 12 content-addressed blobs verified. The model itself runs remotely; the host broker is trusted. No claim of erased pretrained knowledge or full clean-checkout portability.
- Prior ANES completion bindings remain valid. The separate 50-ID ANES reserve was not used.

Artifacts are in `data/runs/debate-isolated-social-pilot-20261014/`: `evaluation.json`, `audit.json`, seals, checkpoints, plot, image export, and logs. Source modules and the research/protocol documents are retained locally. Dataset use and derivatives remain subject to the DEBATE research-only license; this is not permission to integrate them into a commercial product.

Attribution: Yun-Shiuan Chuang and collaborators, [DEBATE: A Large-Scale Benchmark for Evaluating Opinion Dynamics in Role-Playing LLM Agents, v6](https://arxiv.org/abs/2510.25110v6). Our selection, shortened protocol, and diagnostics are project-specific modifications.
