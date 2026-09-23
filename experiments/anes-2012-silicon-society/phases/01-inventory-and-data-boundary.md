# Phase 1 — questionnaire inventory and data boundary

## Objective

Produce an auditable question universe and prove that runtime profiles cannot expose held-out
answers or outcomes.

## Procedure

1. Generate the named-item inventory from the official pre/post questionnaires.
2. Review every automated exclusion category and manually audit a stratified sample.
3. Split respondent data into minimum-necessary runtime profiles and an evaluation vault.
4. Hash and seal the source, inventory, runtime manifest, split manifest, and vault target artifact.
5. Run leakage tests against nested payloads and verify the vault is absent from container mounts.

## Exit evidence

- Question-bank counts, hash, source hashes, and audit table.
- Runtime manifest and split seal.
- Passing leakage, pseudonymization, and container-plan tests.
- Completed M1 and M2 milestone reviews.

## Current state

In progress. A local inventory and structural split exist. The parser audit, full source registration,
and stable-commit test evidence remain open.
