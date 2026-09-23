# Milestones and gates

Status vocabulary:

- **Not started** — no reviewable implementation or artifact.
- **In progress** — work exists, but one or more required gates remain open.
- **Structurally validated** — mechanics passed with mock, heuristic, or provider-free execution;
  this is not a scientific result.
- **Complete** — every exit gate is evidenced by a stable commit and checkpoint record.

| ID | Milestone | Current state | Exit gate |
|---|---|---|---|
| M0 | Protocol and repository scaffold | In progress | Protocol version frozen; scope, estimands, exclusions, matrix, claims, and amendment policy approved. |
| M1 | Data governance and temporal split | In progress | Sources registered; licenses and hashes recorded; runtime/vault separation and leakage checks pass. |
| M2 | Questionnaire inventory | In progress | Full pre/post inventory generated; exclusions explained; stratified manual audit recorded; artifact sealed. |
| M3 | Paper-style baseline | In progress | Study-specific variables and target matched; weighted metrics sealed; deviations from the paper enumerated. |
| M4 | Provider-free society pilot | Structurally validated | Independent/society arms, pairing, sealing, evaluation ordering, and no-network container run pass. |
| M5 | Election-eve live experiment | Not started | Frozen evidence authenticated; live matrix completed under budgets; failures and protocol deviations retained. |
| M6 | Analysis and robustness | Not started | Uncertainty, subgroup, ablation, missingness, and sensitivity analyses complete from sealed artifacts. |
| M7 | Reviewable release | Not started | Reproduction instructions pass on a clean checkout; disclosure review and claims audit complete. |

## Gate details

### M0 — Protocol and repository scaffold

- Assign a protocol version and freeze date.
- State primary and secondary estimands before live execution.
- Distinguish paper replication, forward prediction, and society treatment.
- Declare the amendment process and label all post-freeze changes.
- Commit this documentation directory and the protocol on a stable SHA.

### M1 — Data governance and temporal split

- Record origin, release date, collection timing, access terms, and SHA-256 for each source.
- Keep raw microdata and evaluation targets outside Git.
- Prove that held-out fields cannot appear anywhere in nested runtime payloads.
- Verify pseudonymous identifiers and minimum necessary runtime fields.
- Confirm workspace export cannot package secrets, nested repositories, raw microdata, or vault data.

### M2 — Questionnaire inventory

- Inventory every named specification from both official questionnaires.
- Preserve phase, page, section, variable, wording, options, mode, and source hash.
- Explain every automated exclusion; do not silently drop rows.
- Manually audit a stratified sample across phase, mode, response type, inclusion, and exclusion.
- Seal the inventory and record its counts and hash.

### M3 — Paper-style baseline

- Match the published Study 2 profile fields and presidential vote target.
- Reproduce supported correspondence metrics and document any unavailable metric.
- Use the official ANES weight for representative estimates; otherwise label output unweighted.
- Keep Study 3 leave-one-question-out replication separate from any full-question extension.
- Seal predictions before evaluation and record deviations from the published design.

### M4 — Provider-free society pilot

- Pair profiles, questions, seeds, and call budgets across treatments.
- Save private final answers separately from public interaction messages.
- Seal predictions before opening the vault.
- Run the structural engine in a no-network, read-only, capability-dropped container.
- Demonstrate deterministic replay for the same code, config, seed, and input hash.

### M5 — Election-eve live experiment

- Freeze and authenticate the 2012-11-05 evidence world.
- Pin model identifiers, provider settings, prompts, tool contract, seeds, and budgets.
- Run independent, society, shuffled-profile, shuffled-evidence, and no-evidence arms.
- Retain all failures, retries, usage, costs, and protocol deviations.
- Do not evaluate against held-out targets until prediction artifacts are sealed.

### M6 — Analysis and robustness

- Report weighted aggregate error, individual correspondence, missingness, and completion.
- Report between-replication variance and cluster-aware uncertainty.
- Run subgroup analyses only where cell size and disclosure rules permit.
- Compare treatment effects with the prespecified ablations and model-cutoff sensitivity.
- Clearly separate confirmatory, exploratory, and structural-pilot findings.

### M7 — Reviewable release

- Reproduce tracked mechanics from a clean checkout.
- Verify all committed aggregate results against sealed artifact hashes.
- Run privacy, licensing, security, and supported-claims reviews.
- Publish limitations beside results, not only in an appendix.
- Tag the release and retain the exact environment and dependency inventory.
