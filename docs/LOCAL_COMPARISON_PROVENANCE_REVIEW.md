# Local comparison provenance review

Reviewed 2026-10-23 while the base message-loss process was running. Scope: `data/local-mlx-pilot/matched-comparison-20261023`, its bound metadata, runner source, and memory-probe evidence. No evaluator target file or reserve payload was opened. No frozen artifact or runner was modified.

## Verified

- All 21 runtime-contract file bindings matched their current bytes, including model weights, tokenizer/configuration, selected adapter, package lock, cases, participant audit, message data, row-group mapping, and runners. The protocol copy matches `protocol_sha256`.
- Four `frozen-source` snapshots byte-match the bound working sources. The observed process command executes the working scorer and watchdog; this is consistent with the verified source bytes, though it does not execute the snapshots directly.
- The 133 row-group entries exactly match validation manifest order and admitted per-group counts: 30, 32, 33, and 38. This establishes mapping consistency with preparation metadata, not independent re-extraction of each message from raw exports.
- Cases contain only `group_id` and an explicitly whitelisted initial profile. The prompt worker additionally validates that profile and renders initial rating/explanation/topic with an empty history for direct inference. It does not render partner IDs. No evaluator targets are loaded by either model runner. Message scoring intentionally consumes completion targets for teacher-forced NLL; this is distinct from blind belief prediction.
- The baseline uses 29 admitted training groups and 116 people. Its probability rows sum to one. Its builder enforces source hashes and the admission-bound participant audit and does not open validation CSVs or belief labels.
- Participant audit shows zero supplied-ID, group, or topic overlap between admitted training and validation data. Canonical admitted-group IDs/hash are bound and checked by preparation. Different supplied IDs do not establish unique real-world people.

## Defects and limits requiring explicit handling

1. **The fitted baseline is not in the runtime contract's bindings.** Its current SHA-256 is `61605c5978812f7881ecffebeb3940ec6583d07848aac36f1d9d58082d0ee24b`. A subsequent independent rebuild reproduced the baseline byte-for-byte, and `baseline-provenance-seal.json` now binds the baseline, builder, input manifest, preparation/participant audits, and 29 training CSVs (34 bindings). Seal SHA-256: `bde956117d9f89aa8d26e4657c4980e9ff847276521bb3f0cfaaf6da4166622d`. It was created exclusively and marked read-only; owner-level permissions are not tamper-proof. The final outcome seal must bind this provenance seal together with predictions and evaluator implementation before scoring. The frozen runtime contract was not rewritten.
2. **The current memory-probe helper does not match the second probe's recorded source hash.** The second probe has eight training callback records and two explicitly labelled warmup records, so callback execution is evidenced. The coordinator identifies the subsequent change as addition of a finite-loss gate. Its exact historical implementation still cannot be independently established from the current helper alone; no byte-matching historical snapshot was available during this review.
3. **The first memory probe is not evidence of live callback enforcement.** It reports completion and a final peak but has no metrics journal. The second probe records about 7.006 GB allocated peak (about 6.525 GiB), 71.4 seconds elapsed, and zero sampled swap growth. That short eight-microstep probe does not establish sustained-training capacity or prove a deliberately triggered memory-stop path.
4. **Execution is native-host isolation by convention, not a filesystem/network sandbox.** Offline environment flags and key removal prevent normal provider use; accessible host files remain accessible to the process. Prompt construction provides the audited label boundary. Permission modes on evaluator files do not isolate processes sharing the same user account.
5. **Provenance is checked at process startup, not continuously.** Bound working files must remain unchanged during each arm. The current watchdog samples resource use every two seconds rather than imposing a hard allocation limit; system swap changes can include other processes. The direct runner relies on that external watchdog for wall-time enforcement.
6. **These are development results.** Four validation groups were already used during the adapter pilot. The selected adapter has only 52 microsteps / 13 optimizer updates. Neither split cleanliness nor a favorable comparison would establish fresh-holdout performance or general human fidelity.

## Focused validation

- Main project environment: 21 tests passed covering participant admission/overlap, case-label separation, training-only baseline, and watchdog behavior.
- MLX environment: 10 tests passed covering completion-only shifted loss and strict probability parsing.
- No GPU model load or further training was launched for this review. The comparison was still running when this review was written; this document makes no completion or outcome claim.
