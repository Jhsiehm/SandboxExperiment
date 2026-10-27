# Independent review: versioned training-only format diagnostic

Reviewer date: 2026-10-23. Status: **review passed for the bounded format-only diagnostic, subject to the coordinator enforcing the shared 900-second deadline and verifying the frozen artifacts before the first call**.

Scope: output-format feasibility only, using already-admitted training profiles. No model calls, participant target files, reserve contents, credentials, or raw failed predictions were read for this review. The stopped development comparison remains a distinct immutable experiment. Its observed format failure motivates this new diagnostic; it does not permit calling the old validation cases an untouched test.

## Findings from the preceding implementation

The preceding direct runner validates file bindings, loads a fixed local base model and optional adapter, uses greedy decoding with a fixed 256-token limit, writes every attempted response, and stops at a format failure. Its probability parser rejects extra fields, wrong vector length, booleans, nonfinite/out-of-range numbers, and sums outside tolerance. It does not repair responses. These are useful controls to retain.

Two items need attention in the new version:

- Standard `json.loads` silently accepts duplicate keys. The new parser should reject repeated `probabilities` keys, even if the final occurrence is a valid vector. Keep fenced text, trailing commentary, NaN/Infinity, strings and booleans invalid. Leading/trailing whitespace is ordinary JSON syntax, not repair.
- `scripts/debate_local_cases.py` is validation-specific and invokes a parser that extracts final labels. Do not reuse it to claim a no-outcome training-only preparation. Extract only initial-profile fields from sealed training inputs or initial-opinion rows, verify training membership, and never invoke the outcome parser.

## Admission checklist for the new version

1. **Distinct version and directory:** new immutable experiment ID; no overwriting the stopped comparison, its predictions, or old source snapshots. Record that design followed its format failure.
2. **Training-only provenance:** an auditable deterministic selection rule, exact case IDs/hashes and ordering, training-partition membership, and explicit rejection of validation/reserve cases. Do not derive selected cases from which earlier outputs failed.
3. **Minimal model input:** initial topic, score and explanation only as declared; exclude later messages, assistant training completions, final beliefs, post-survey outcomes and any evaluator artifacts. Record allowlisted fields.
4. **Fixed intervention:** predeclared original versus fixed assistant-prefix conditions, with no additional prompt search. Exact prompt bytes and token sequences must match between base and adapter. If using a prefix, disclose that continuation parsing includes that prefix; do not present continuation-only text as independently generated JSON.
5. **Fixed comparisons and resource budget:** case count/order, base and adapter identities, quantization, adapter hash, template/tokenizer/package hashes, greedy settings, seed, output/context limits, generation count, wall/RSS/MLX/swap caps, and stopping rules frozen in advance.
6. **Strict parsing:** six finite probabilities in [0,1], sum tolerance declared, exact object schema, duplicate-key rejection, and no coercion, extraction, normalization, retry, repair, or selective case replacement. Record invalid attempts as failures.
7. **Source sealing:** verify contract bindings before execution and run the bound code bytes. Include all locally imported helper sources and prompt code, not just the launcher. Preflight all cases and both arm configurations before the first call where feasible.
8. **Complete accounting:** preserve raw attempted responses locally, prompt hashes, per-case validity, completed/planned counts, failures, watchdog exit, and artifact hashes. A stopped arm is not full coverage. Do not report validation accuracy or scientific superiority from training format success.
9. **Promotion boundary:** success can justify a separately frozen new development comparison. It cannot resurrect the old frozen comparison, certify belief fidelity, or make already inspected validation outcomes fresh.

## Proposed design received from coordinator

The coordinator fixed one first admitted training group in manifest order and all four initial profiles: two models × two conditions (original and fixed assistant prefix `{"probabilities":[`) = 16 generations. Keep 256 generated tokens, 4096 total context, greedy decoding and matched per-condition prompts across model arms. Continue after format failures to measure all predeclared cells; resource/integrity failure still stops execution. The declared success criterion is four of four valid prefixed outputs for **both** models. Report original-condition coverage too, without selecting another prompt after results.

This is an appropriate bounded format diagnostic provided the implementation enforces those rules. The prefix is part of the supplied prompt and reconstructed response, not independently generated text. This review does not yet certify implementation or grant a behavioral-success claim.

## Verification still required

Read the new protocol, case-preparation implementation, inference runner and tests when available. Require synthetic tests that fail on forbidden fields/partitions, altered bindings, prompt mismatch, duplicates and malformed probabilities, output-directory reuse, and invalid-response accounting. Model-free tests must not silently load a model or access an evaluator file. Report any deviations to the coordinator before execution.

## First implementation pass

Inspected `format_smoke_v1.py`, `format-smoke-v1.protocol.json`, `test_format_smoke_v1.py`, and the imported prompt worker. Ten initial model-free tests passed. The runner prepares eight shared tokenized prompts once, uses them for both model arms, concatenates only the declared prefix with the exact continuation, records each invalid response without retry, and preserves resource/integrity stop behavior. The parser now rejects duplicate JSON keys.

Three blockers were sent to the author before execution:

- The report initially caught `ValueError` from its own validity-consistency assertion inside the parsing exception block. This could classify valid assembled JSON marked invalid as acceptable accounting. Parsing errors and record-consistency checks need separate control flow.
- Runtime `contract.policy` was initially independent of the hash-bound protocol file. Require equality and verify actual model/adapter paths are bound candidates, so changing active settings cannot preserve a superficially passing binding check.
- `total_wall_seconds=900` was used independently by each arm. Declare whether this is per arm or experiment-wide, and align watchdog calls and total experiment budget.

These findings are code-integrity requirements, not evidence that a model or an actual artifact was altered. Final disposition follows after fixes and focused regression tests.

## Final implementation disposition

The three identified blockers are resolved in the reviewed revision. `load_contract` verifies the active policy against the hash-bound protocol and requires the active model/adapter files to be bound. Preparation verifies the exact model/adapter bytes against the preceding contract metadata without opening its validation payloads. Report parsing now separates parse exceptions from record-consistency assertions, and rejects forged validity, prompt hashes, prefix, model and group identity. The protocol explicitly assigns the shared 900-second deadline to the coordinator; summed supervisor time is a secondary report check, not proof that inter-arm gaps are counted.

All **17 model-free tests** passed in an independent reviewer invocation. They include deterministic initial-only training selection, checksum enforcement, malformed/duplicate JSON rejection, exact prefix reconstruction, policy divergence, forged record rejection, and complete condition reporting. A separate provenance reviewer reported that inaccessible validation/rejected/later input files were never selected and later-state fields were excluded.

No remaining blocking source finding for this narrowly scoped diagnostic. Before model calls, the coordinator must freeze and verify the contract/case/prompt hashes and retain the exact shared deadline across both arms. Do not modify reviewed code after freeze. Format success remains evidence of compatibility on four training people only; neither belief accuracy nor validation performance is evaluated.

Reviewed source SHA-256:

- `format_smoke_v1.py`: `e88f31b216c2f3e81ac10e9ccba56301bd42dd631f7a371864f5f749407c54bb`
- `format-smoke-v1.protocol.json`: `f34fce99d9a8da5539a3199fc6020dbee3d444c7d2a0a5c5a3cbc171298272c7`
- `test_format_smoke_v1.py`: `ac830b74adbd34475deb55428cffc2c709aacfb65693b08a47618dcab0d18fa8`

## Coordinator final review and admission

The independent reviewer completed preliminary review but reached the workspace spend cap before its final pass. The coordinator reviewed the resulting source and 17 passing model-free tests, including the report try/else fix, protocol equality gate, candidate-byte checks, exact paired prompt bindings, and explicit token-count/termination records. The separate provenance review confirmed first-admitted-TRAIN selection with initial-only field extraction. The coordinator admits this bounded format diagnostic; this is not represented as a completed independent final review.

The frozen contract SHA256 is `7012a60a86630e0566c9eed87e696e590267c93288c3d4667fede3435cce717a`. All bindings matched before execution. Cases/prompts/contract are read-only and source snapshots retained. A parent supervisor enforces the remaining portion of a 900-second whole-experiment budget for the second arm, including elapsed time between arms. No behavioral targets are scored.
