# ANES 2012 silicon-sample and society experiment

This directory is the durable, reviewable record for the ANES 2012 experiment. It stays in Git
while licensed or sensitive source data, runtime profiles, evaluation targets, and generated run
artifacts remain in ignored data directories.

The program contains three separate scientific claims:

1. reproduce the published paper-style silicon-sample comparison;
2. measure election-eve prediction under a declared 2012-11-05 information cutoff; and
3. compare independent answers with bounded peer conversation as a matched treatment.

These claims must never be collapsed into one result. The provider-free structural pilot only
checks plumbing, sealing, treatment assignment, and evaluation. It is not an LLM result and it is
not a replication finding.

## Review path

Read these files in order:

1. [STATUS.md](STATUS.md) — current checkpoint, blockers, and next action.
2. [MILESTONES.md](MILESTONES.md) — gates required before each phase can be called complete.
3. [PROTOCOL.md](PROTOCOL.md) — estimands, experiment matrix, temporal boundary, and claims.
4. [ARTIFACTS.md](ARTIFACTS.md) — what is tracked, ignored, sealed, and publishable.
5. [phases/](phases/) — step-by-step setup, execution, analysis, and release procedures.
6. [logs/DECISIONS.md](logs/DECISIONS.md) — decisions that change interpretation or scope.
7. [logs/CHECKPOINTS.md](logs/CHECKPOINTS.md) — dated evidence for milestone transitions.

Use [templates/RUN_RECORD.md](templates/RUN_RECORD.md) for every material run and
[templates/MILESTONE_REVIEW.md](templates/MILESTONE_REVIEW.md) before changing a milestone to
complete.

## Repository integration

The implementation remains in the normal project locations rather than being duplicated here:

| Concern | Source of truth |
|---|---|
| Experiment configuration | [`config/anes2012-society.yaml`](../../config/anes2012-society.yaml) |
| Election-eve epoch | [`config/epochs.yaml`](../../config/epochs.yaml) |
| Experiment implementation | [`src/psbx/experiments/anes_society.py`](../../src/psbx/experiments/anes_society.py) |
| CLI commands | [`src/psbx/cli.py`](../../src/psbx/cli.py) |
| Structural isolation image | [`Dockerfile.anes-society`](../../Dockerfile.anes-society) |
| Automated checks | [`tests/test_anes_society.py`](../../tests/test_anes_society.py) |
| Detailed implementation protocol | [`docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md`](../../docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md) |

Links can temporarily point to uncommitted implementation work during a milestone. A milestone is
not complete until its referenced implementation and tests are committed together or identified by
an immutable commit SHA in `logs/CHECKPOINTS.md`.

## Documentation rule

Every experiment-changing commit must update at least one of:

- `STATUS.md` when the active phase, blocker, or next action changes;
- `logs/CHECKPOINTS.md` when evidence is produced or a gate changes state;
- `logs/DECISIONS.md` when a design choice changes the estimand, data flow, model roster, prompt,
  sampling, exclusion rule, evaluation, or supported claim.

Generated metrics belong in an ignored run directory first. Only aggregate, disclosure-reviewed
results may be copied into Git, and the committed record must include hashes or a manifest that
links the summary to the sealed run.
