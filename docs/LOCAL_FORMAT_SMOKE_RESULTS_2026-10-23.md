# Training-only format diagnostic — 2026-10-23

The fixed JSON assistant prefix did not restore usable probability output from the existing message-trained adapter. The predeclared progression gate failed; no new validation or interaction runs were started.

## Design and results

One deterministic first admitted training group supplied four initial profiles. Each model received both the original prompt and a fixed assistant prefix, giving 16 total generations. Model/tokenizer/adapter bytes matched the earlier frozen comparison. Eight prompts were sealed before inference, with identical token sequences across models within each condition. Greedy decoding used a 256-token continuation cap and no repair, extraction, normalization, retry or post-result prompt search.

Base: original 4/4 valid; prefix 3/4 valid. The failed prefixed response was syntactically valid JSON but its six values summed to 0.99.

Adapter: original 0/4 valid; prefix 0/4 valid. Original responses were non-JSON prose; one ended at the output-token limit. Every prefixed adapter response was syntactically valid JSON containing six zeros, hence not a probability distribution. None of those prefixed responses hit the token cap. All 16 scheduled responses were retained and both supervisors exited successfully, with combined supervised elapsed time 50.79 seconds.

This is stronger evidence of a task/output mismatch than the first failed validation case alone, but it still does not identify the causal training mechanism. Passing JSON syntax alone is inadequate. Repetition statistics on structured numeric JSON are not directly comparable to prose and should not be interpreted as a behavioral-quality metric.

## Boundaries and review

Only initial profile fields from one admitted TRAIN source were admitted into prompts; preparation did not extract post-opinion labels. The raw source checksum necessarily covers the whole training CSV. No validation profiles, evaluator targets or reserve payloads were opened by this experiment. The selected training group had appeared in an earlier hosted-model diagnostic; it is not a fresh test. No paid calls, new downloads or training steps occurred.

The provenance agent independently verified deterministic selection and initial-only field extraction. The implementation agent produced the runner and tests. The independent runner reviewer identified issues that were fixed, but reached the workspace spending cap before its final pass; the coordinator completed the final source review. Do not describe that final pass as independent. Seventeen model-free runner tests passed; dashboard checks separately verify aggregate-only exposure.

Frozen artifacts: data/local-mlx-pilot/format-smoke-v1-20261023/contract.json, prompts.json, cases.json, frozen-source/, model arm predictions, watchdog summaries and format-evaluation.json. Contract SHA256: 7012a60a86630e0566c9eed87e696e590267c93288c3d4667fede3435cce717a.

## Decision and next work

Preserve both experiments. The original matched comparison remains stopped, and the new format gate is failed. Belief accuracy remains unscored. Do not normalize all-zero responses or quietly fall back to base outputs.

Before another validation comparison, define a new training-only intervention with an instruction-following objective and a bounded update budget, or explicitly redesign the architecture to separate message generation from belief estimation. Either changes the candidate/method and requires a new frozen protocol with matched controls. More training on the same message-only objective is not justified by these results alone. Do not select a new prompt on these outputs and present it as the same test.
