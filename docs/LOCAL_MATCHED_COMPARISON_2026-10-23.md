# Local matched comparison — 2026-10-23

The fixed pilot adapter improved observed-history message prediction, but failed the direct-belief output-format gate. Interaction testing was therefore not started. This is development evidence, not confirmation or evidence of better human-belief prediction.

## Completed message test

Both arms scored all 133 messages across four validation groups, with 3,415 supervised tokens. Token-weighted negative log likelihood fell from 3.627999 to 3.201114 nats/token (adapter minus base −0.426885). Equal-group mean message loss fell from 3.970071 to 3.304992. All four group differences favored the adapter. The existing adapter had only 13 optimizer updates, and eight validation batches had already been exposed during its hardware pilot.

Both watchdogs exited successfully. Base scoring took 232.8 seconds and adapter scoring 283.1 seconds. Peak MLX allocation was approximately 5.17 GiB and 5.38 GiB respectively. These are native-host allocation measurements, not total laptop memory or Docker-isolation claims; system swap is shared with other applications.

## Behavioral gate

The base produced 16/16 valid direct predictions. The adapter's first response was not valid JSON (822 characters), so execution stopped at 1/16 attempted, 0 valid. No repair, retry, normalization or selectively scored comparison was performed. The guarded evaluator rejected this incomplete stage before outcome target access. No B2 private/swarm runs were launched. Belief accuracy remains unevaluated.

## Provenance and checks

All 21 frozen execution bindings and four source snapshots matched. Participant auditing found no supplied-ID, group or topic overlap between admitted training and validation; supplied IDs do not prove unique real-world identities. The training-only baseline was reproduced byte-for-byte and sealed with 34 provenance bindings. Reserve payloads were not accessed. This comparison made no paid calls.

The final combined evaluator, research viewer, recording navigation, participant audit, case-boundary and baseline suite passed 33 tests. Separate MLX loss/parser/watchdog tests passed earlier. The memory-probe source-hash limitation is documented in LOCAL_COMPARISON_PROVENANCE_REVIEW.md.

## Preview

The research page now defaults to an available DEBATE recording (51 actions), enables playback, explains absent recordings, and displays local message-scoring progress separately from social action playback. Browser cache versions were advanced and the backend restarted. The legacy study evidence card still describes its named historic report; recording availability is a separate status.

## Decision

Keep this run frozen, including its failure. Any future output-format intervention needs a new versioned protocol and a separate development evaluation; do not retry these prompts and present the result as this same experiment. The current evidence supports the message-task signal only, and does not warrant interaction expansion.

Artifacts: data/local-mlx-pilot/matched-comparison-20261023/{contract.json,message-evaluation.json,baseline-provenance-seal.json,stage-decision.json}, arm predictions and watchdog summaries. Raw inference artifacts remain local and are not exposed in the dashboard.
