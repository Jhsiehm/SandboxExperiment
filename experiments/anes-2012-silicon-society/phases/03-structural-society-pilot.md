# Phase 3 — provider-free structural society pilot

## Objective

Validate orchestration, pairing, treatment separation, artifact sealing, and evaluation order without
making a model-performance claim.

## Procedure

1. Run matched independent and society arms with the deterministic provider-free engine.
2. Verify that public interaction summaries do not overwrite private final answers.
3. Seal prediction output before the evaluation vault is opened.
4. Repeat inside the no-network container with read-only inputs and a constrained output mount.
5. Replay with the same inputs and seed and compare hashes; change a seed and verify identity changes.

## Exit evidence

- Run record with input, config, code, prediction, and evaluation hashes.
- Pairing and deterministic-replay evidence.
- No-network container command and successful completion record.
- Explicit `scientific_result: false` in structural evaluation.
- Completed M4 milestone review.

## Current state

Structurally validated on the host for 5,914 profiles across five independent and five society
replications. Container execution and checkpointing on a stable commit remain open.
