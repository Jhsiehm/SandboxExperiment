# Decision and amendment log

Record decisions that affect interpretation, comparability, privacy, or supported claims. Never
rewrite an old entry; add a superseding entry.

## D-001 — Separate three experiment families

- Date: 2026-09-23
- Status: accepted
- Decision: Keep paper replication, election-eve forward prediction, and society treatment as
  separate designs and result sets.
- Reason: They answer different questions and have different temporal and causal interpretations.
- Consequence: A successful structural or paper-style run cannot be reported as evidence for the
  live society treatment.

## D-002 — Treat hosted-model knowledge as uncontrolled

- Date: 2026-09-23
- Status: accepted
- Decision: Do not claim that a modern hosted model "knows only 2012." Control supplied evidence,
  tool access, and external retrieval, then measure model-prior dependence with ablations.
- Reason: Model weights may encode post-cutoff information and cannot be inspected or erased by this
  harness.
- Consequence: Result language must describe a cutoff-controlled context, not a cutoff-controlled
  model.

## D-003 — Keep provider-free output non-scientific

- Date: 2026-09-23
- Status: accepted
- Decision: Provider-free heuristic output validates structure only and must carry
  `scientific_result: false`.
- Reason: Its behavior is engineered for deterministic testing, not respondent simulation.
- Consequence: Structural summary metrics may be used for QA but not as substantive findings.

## D-004 — Commit documentation, not protected artifacts

- Date: 2026-09-23
- Status: accepted
- Decision: Keep this operating record in Git while raw microdata, questionnaires subject to source
  terms, respondent-level profiles, vault targets, and run outputs remain ignored.
- Reason: The experiment needs durable review history without publishing data or leaking outcomes.
- Consequence: Committed summaries must be aggregate, disclosure-reviewed, and linked to sealed
  artifacts by hashes.

## Entry template

### D-NNN — Short title

- Date: YYYY-MM-DD
- Status: proposed | accepted | superseded
- Protocol version/amendment:
- Decision:
- Alternatives considered:
- Reason:
- Consequence:
- Affected files/runs:
- Approval:
