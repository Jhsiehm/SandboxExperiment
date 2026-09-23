# Artifact and data map

## Tracked in Git

| Artifact class | Location | Purpose |
|---|---|---|
| Protocol and operating record | `experiments/anes-2012-silicon-society/` | Review, milestones, decisions, checkpoints, templates |
| Configuration | `config/anes2012-society.yaml`, `config/epochs.yaml` | Declared structural-pilot and epoch settings |
| Implementation | `src/psbx/experiments/anes_society.py`, `src/psbx/cli.py` | Inventory, split, execution, sealing, evaluation |
| Isolation definition | `Dockerfile.anes-society` | Provider-free no-network runtime image |
| Tests | `tests/test_anes_society.py` | Automated boundary and mechanics checks |

Tracked files must contain no raw respondent rows, evaluation targets, credentials, provider
payloads, or licensed source documents.

## Ignored local inputs and outputs

| Zone | Expected location | Runtime access |
|---|---|---|
| Official/source material | `data/survey-microdata/anes/2012/source/` | No direct mount; transformed minimum fields only |
| Derived question inventory | `data/survey-microdata/anes/2012/derived/` | Eligible prompt fields only |
| Runtime profiles | `data/runs/<run-id>/anes-society/runtime/` | Yes, read-only |
| Sealed runtime output | `data/runs/<run-id>/anes-society/sealed-runtime-output/` | Written by runtime; evaluated after seal |
| Evaluation vault | `data/evaluation-vault/<run-id>/` | Never available to runtime |
| Aggregate evaluation | `data/runs/<run-id>/anes-society/evaluation.json` | Created only after prediction seal verification |

## Required run identity

Every material run record must capture:

- Git commit SHA and clean/dirty status;
- protocol version and amendment IDs;
- config path plus canonical config hash;
- input identifiers, licenses, release/collection dates, and SHA-256 hashes;
- question-bank and evidence-pack hashes;
- model/provider identifiers and settings;
- prompt/tool-protocol fingerprint;
- seed, assignment fingerprint, budgets, and environment details;
- prediction seal and evaluation artifact hashes;
- failure, retry, missingness, usage, and cost counts.

## Promotion rule

Generated artifacts stay ignored by default. A result may be promoted into Git only when it is:

1. aggregate and disclosure-reviewed;
2. reproducibly linked to a sealed run by hashes;
3. labeled structural, exploratory, or confirmatory;
4. accompanied by limitations and protocol deviations; and
5. approved in a completed milestone review.

Never use `git add -f` to publish raw or row-level artifacts. Create a purpose-built aggregate
summary instead.
