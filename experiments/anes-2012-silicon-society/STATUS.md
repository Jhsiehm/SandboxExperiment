# Status

- Last updated: 2026-09-23
- Active phase: Phase 0–3 implementation and structural validation
- Overall status: **in progress; no scientific result yet**

## Verified locally

- Official pre- and post-election questionnaire PDFs and a public replication CSV are present in
  the ignored ANES source directory.
- A question-bank artifact was generated with 998 named specifications: 486 pre-election, 512
  post-election, 765 generically eligible, and 233 excluded. These counts require manual sampling
  QA before the inventory milestone closes.
- A provider-free structural pilot produced 5,914 pseudonymous runtime profiles and kept the held-
  out vote target in the evaluation vault.
- Five independent and five society replications completed in the structural pilot. Its evaluation
  explicitly records `scientific_result: false`.
- The current public replication CSV has no survey weight in the configured run, so the structural
  pilot is marked `uniform_unweighted_validation_only`.

## Not yet established

- The draft protocol has not been frozen as a preregistration.
- The question parser has not completed a documented manual sample audit against both instruments.
- A paper-style replication report has not been sealed and checkpointed.
- The official weighted respondent file and its access/license record have not been registered for
  representative aggregate claims.
- The election-eve evidence corpus has not been authenticated and frozen for the live matrix.
- No matched live-model independent-versus-society experiment has run.
- No live result, causal treatment effect, or behavioral-fidelity claim is supported.
- Hosted-model weights cannot be made temporally ignorant; only supplied context and tool access can
  be cutoff controlled.

## Immediate next gate

Close M0 and M1 in `MILESTONES.md`:

1. review and freeze the protocol version;
2. record source licenses, checksums, and timing classifications without committing source data;
3. run the targeted tests and the full repository test suite on a stable commit;
4. execute and record the no-network container validation; and
5. add the resulting commit SHA, commands, and artifact hashes to `logs/CHECKPOINTS.md`.

## Working-tree caution

At the time of this checkpoint, related implementation exists in the working tree. Its presence is
not evidence of completion. Reviewers should use `git status`, the checkpointed commit SHA, and the
recorded test commands before treating any capability as reproducible.
