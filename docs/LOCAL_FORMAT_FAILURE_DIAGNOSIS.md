# Local direct-format failure diagnosis

Scope: frozen comparison `matched-comparison-20261023`. Reviewed recorded prompts, raw model predictions, training preparation/objective and training-only message targets. No evaluator outcomes or reserve payloads were opened. No inference, training, retries, or frozen-file edits were performed for this diagnosis. Raw participant statements and generated response text are intentionally omitted here.

## Evidence

- Base direct inference produced 16 valid probability vectors from 16 attempts. Adapter direct inference stopped on its first response: zero valid vectors from one attempt. Therefore adapter-wide failure prevalence and relative belief accuracy remain unknown.
- The failed adapter and corresponding base case have the same participant identity, exactly equal system/user prompts, and equal recorded prompt lengths of 269 tokens. Both use the frozen deterministic decoding policy and 256-token output cap.
- The base response is valid JSON and re-encodes to 22 tokens. The adapter response re-encodes to **exactly 256 tokens** with the pinned local tokenizer (`241a666dad6cb93c8ff213d39a7f34a36bf26db4`, special tokens disabled). Only tokenizer/configuration files were loaded; no model weights were loaded.
- The adapter output contains no opening JSON brace. It repeats one short sentence **34 times** and ends midphrase. The strict JSON parser fails at the first character. This is not a valid probability object surrounded by commentary, nor merely a probability object cut off before its closing bracket.
- Exact re-encoded length and the unfinished ending strongly support exhaustion of the output cap. The runner did not persist generated token IDs or an explicit finish reason, so re-encoding is corroborating evidence rather than a direct recorded termination code.
- Training preparation explicitly requests a participant's next private chat message and plain message text. All 831 prepared training examples use one system instruction; no assistant target contains the `"probabilities"` field. None contains the exact sentence repeated in the failed output. This establishes task/output-format mismatch; it does not establish the cause of the repetition.

## Interpretation and limits

The observed failure is a free-text instruction-following failure with repetition, followed by apparent cap truncation. Raising the token cap would not address the absence of a probability distribution from the start. JSON extraction would have nothing valid to recover.

The changed adapter is the experimental difference in this matched case, but the evidence does not isolate a mechanism. Narrow message-only adaptation, decoding dynamics, optimizer/update effects, or other adaptation behavior could contribute. Do not describe this as proven catastrophic forgetting, a proven training bug, or a general inability of the adapter to follow instructions. The hardware pilot contained only 13 optimizer updates. Improved teacher-forced message likelihood does not guarantee stable free generation or belief-format transfer.

The original frozen behavioral stage correctly remains stopped and unscored. Any subsequent format experiment is a new development diagnostic, not repair of this result.

## Minimal next intervention

Freeze a small **training-only** format smoke using identical cases and settings for both models. Test a deterministic assistant JSON prefix as a mechanical format intervention, record prefix and generated continuation separately, and strictly validate their concatenation without extraction, normalization, retry, or label-dependent changes. Select cases from training metadata before inference and do not use belief outcomes for selection or prompt changes.

This is smaller than retraining or adding a new structured-output library, but it may still fail to produce a normalized six-value distribution. A failed smoke is useful evidence; do not enlarge the cap to conceal the repetitive failure. Record actual generated-token count and finish reason in the new runner. A successful format smoke would establish only format compatibility, not belief accuracy, and would not retroactively alter the frozen comparison.
