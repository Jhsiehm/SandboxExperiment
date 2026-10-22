# Completed DEBATE comparison — 22 October 2026

The current swarm does not justify increased complexity. Direct independent prediction achieved the lowest probability error; generated interaction did not outperform the development-fitted statistical baseline. This is progress in identifying a failure mode, not validation of a society simulator.

## Design and expenditure

116 people in 29 held-out discussion groups and 29 topics; 47 other groups (188 people) supplied development data for a transition baseline. One GPT-4.1-mini configuration and one generation per condition. The six arms were frozen before evaluation. All 1,856 requests completed, with $0.5863428 provider-reported usage, no unresolved usage, and no repair attempts. Limits were 2,000 requests and $30. The conservative reservation ledger was $3.2731328; this is not actual billed usage.

| Method | Ranked probability score (lower better) | Expected-score MAE | Answer-share MAE |
|---|---:|---:|---:|
| Direct independent agent | 0.115118 | 0.9185 | 0.062960 |
| Development-fitted transition baseline | 0.130286 | 1.0005 | 0.030074 |
| Real human-message replay | 0.131949 | 1.0250 | 0.071020 |
| Generated conversation | 0.146711 | 1.0966 | 0.068807 |
| Private reflection | 0.149433 | 1.0664 | 0.041839 |
| Preserve initial answer | 0.163793 | 0.8190 | 0.063218 |

## Interpretation

- The primary contrast, swarm minus statistical-baseline RPS, was +0.01643 (exploratory group-bootstrap 95% interval −0.01698 to +0.05190). The preregistered exploratory improvement criterion was not met.
- Swarm minus direct-agent RPS was +0.03159 (interval +0.00791 to +0.05933): worse in this comparison. Swarm versus private reflection was inconclusive, −0.00272 (−0.02939 to +0.02229).
- Replay also failed to improve on direct prediction: +0.01683 (+0.00024 to +0.03300). It conditions on actual human messages, so it is a diagnostic, not a time-zero forecast or causal control.
- Half the humans did not change their answers. The swarm's modal prediction nevertheless changed for 28 of these 58 people (48.3%); direct prediction did so for 17 (29.3%). This points to overreaction and insufficient preservation of existing beliefs.
- The statistical baseline had the best population answer-share error. Persistence had the lowest expected-score MAE. The direct agent's RPS lead therefore does not imply superiority on every aspect of human fidelity; its lead over the baseline is a point estimate without a prespecified contrast interval in this report.
- Dispersion of expected scores is not the same as the spread of sampled human outcomes. Do not interpret that diagnostic alone as proof of lost social diversity.

## Docker and audit

Each of the 1,856 provider attempts used a fresh prompt worker with UID 10001, network disabled, a read-only root, dropped capabilities, no-new-privileges, resource limits, and no API key, host data mount, or Docker socket. The host API broker and remote model inference remained outside Docker. This isolates local workers; it does not isolate the hosted model or remove its pretrained knowledge.

Exact permitted histories were reconstructed for every checkpoint, including synchronous message-delivery boundaries. An independent cumulative-probability calculation reproduced all six aggregate RPS values. The frozen worker image was exported with content verification.

The original final integrity check FAILED because concurrent telemetry edits changed three bound workspace source files. The run stopped before sealing, after all paid calls had completed. Recovery imported the frozen source, checked original hashes against that snapshot for exactly those three files, required every other binding to match, and reconstructed outputs from completed checkpoints with provider calls and fresh worker jobs explicitly disabled. The contract was not rewritten and concurrent edits were not reverted. The source drift, diffs, recovery code, and verification exception are saved beside this report. This is a documented recovery, not a clean pass of the original live-workspace integrity check. Of 2,178 preservation-snapshot files, 2,177 remained unchanged; the exception was the shared social benchmark source, not historical results or held-out labels.

## Next frozen experiment

1. Keep individual prediction as the reference. On development people, separately test profile selection, additional observed evidence, and probability calibration; preserve untouched evaluation people.
2. Diagnose false opinion change by initial conviction, topic, and information exposure. Test a learned change/no-change probability before predicting the destination answer, using development data only.
3. Compare cheap and stronger models on the same held-out people, prompt conditions, and repeated seeds. This experiment did not compare model tiers; more expensive reasoning is not established as the remedy.
4. Compare targeted context separately from profile improvements. Distinguish information available historically from information plausibly encountered by the individual.
5. Reintroduce interaction only after freezing the improved independent model, with matched private-reflection budgets and observed human change/no-change outcomes. Do not tune on these 29 groups and describe them as fresh confirmation again.
6. Launch future host runners from immutable source snapshots or immutable runner containers as well as isolated prompt workers, preventing concurrent dashboard edits from invalidating source bindings.

These results concern one compressed discussion protocol, one model, and one generation on 29 groups. Bootstrap intervals condition on the fitted baseline and that generation; they do not incorporate model-repeat or baseline-fitting uncertainty. Historical/pretraining contamination is not excluded. Topic-separated groups do not establish independently verified unique humans across sessions. The data are research-only. This is not a representative policy-reception forecast, causal effect estimate, or validation of an entire simulated society.
