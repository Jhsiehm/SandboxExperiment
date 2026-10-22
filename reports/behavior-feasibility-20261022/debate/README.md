# DEBATE feasibility audit — 22 October 2026

Decision: metadata supports a new group/topic validation study, but the proposed 30-group full-condition confirmation does not fit the existing 1,000-request ceiling. Neither data admission nor a paid run is complete. A larger sample is available in principle; a conclusive interaction advantage is not established.

## Evidence and scope

This audit reads the existing eight-group development pilot and source directory metadata. It does not fetch new session CSVs, read new final outcomes or conversations, access the ANES reserve, or call a paid inference provider. Existing frozen files are unchanged. New artifacts live only in this directory. No AGENTS.md was found in the searched ChatGPT workspace.

Primary dataset source: [pinned repository tree](https://huggingface.co/datasets/seantw/DEBATE_LLM/tree/5e699a5458ec6ed776ab54e925ad33bb241fd831). The public API tree was retrieved recursively, including pagination, for revision `5e699a5458ec6ed776ab54e925ad33bb241fd831`; saved as `source-tree.json`. Entries preserve Git object IDs, paths and sizes. API metadata Git object IDs are not SHA-256 file checksums. The inventory script records SHA-256 of the saved metadata.

Local sources: `docs/DEBATE_ISOLATED_PILOT_PROTOCOL.md`, `docs/DEBATE_ISOLATED_PILOT_RESULTS.md`, `data/corpus-cache/debate-20261014/{README.md,LICENSE,revision.txt,*.source.json}`, and `data/runs/debate-isolated-social-pilot-20261014/evaluation.json`. Source paper: [Chuang et al., DEBATE v6](https://arxiv.org/html/2510.25110v6). Its main text describes 697 cleaned groups, while Appendix F's complete-session/golden mask lists 213 training plus 51 test groups. The pinned golden directory has 264 sessions, matching that latter count. Do not present 697 as our available complete-session sample or silently equate the two filters.

## Inventory and inspection provenance

| Source partition | Session CSV files | Topics | Nominal four-person slots |
|---|---:|---:|---:|
| raw/breadth | 565 | 100 | 2,260 |
| raw/depth | 143 | 7 | 572 |
| golden/breadth | 225 | 100 | 900 |
| golden/depth | 39 | 7 | 156 |
| golden total | 264 | 107 | 1,056 |

Raw and golden files are overlapping representations, not additive populations. Nominal slots are not verified unique people. Golden selection already conditions on completion and content quality; conclusions concern that selected discussion population, not all enrolled participants or society. The source README defines four-person completion and per-round message criteria; scale validation must retain 1–6, as the pilot established.

Eight known inspected golden sessions, 32 participants and four topics are bound by the prior `*.source.json` manifests and pilot outcomes. Those groups remain development-only. The remaining 256 golden sessions have no use identified in those manifests. This audit has not opened their contents; that does **not** prove nobody previously inspected them. Cross-session repeated participants and exact official train/test memberships remain unverified. Global held-out claims require an inspection ledger and participant-component audit.

## Deterministic provisional split

`split-proposal.json` names each of the 264 source paths, source object IDs, group identifiers, topic, assignment and inspection status. Selection depends only on topic/path metadata using SHA-256 ranking with seed `polisim-debate-feasibility-20261022-v1`:

- Keep eight inspected groups as development.
- Reserve 30 hash-ranked topics excluding the four known pilot topics. Select one hash-ranked group per topic for a **30-group topic-generalization candidate panel**. Reserve the other 30 sessions on these topics as a buffer, never training data.
- Allocate 40 additional development candidates from other topics by deterministic topic-balanced round-robin ranking.
- Leave 156 groups unallocated.

This is a proposed project split, not the authors' official split, and not executable admission. Before freezing, compare participant IDs (without message text/outcome values) across candidates. Keep connected participant/group components in one split; regenerate the entire manifest deterministically if overlap requires it. Apply predeclared eligibility criteria through a masked evaluator. A reserve replacement order must be fixed before any outcomes are scored. Do not discard difficult-looking groups after seeing results.

One group per topic lets this confirmation test new topics without treating correlated same-topic groups as independent. A future same-topic new-group test is a different generalization question and should be reported separately. Do not claim this single panel tests both questions independently.

## Development fitting and controlled conditions

Primary metric: normalized six-category ranked probability score (RPS), with five cumulative thresholds, lower better. Primary proposed contrast: generated conversation minus the strongest admissible development-fitted independent baseline, selected and frozen before confirmation. Include persistence and a regularized probabilistic ordinal transition baseline; choose the strongest comparator on development folds rather than final outcomes.

Fit a shrinkage transition distribution `P(final rating | initial rating)` using development groups only. Tune diagonal/persistence shrinkage or ordinal-distance smoothing in nested whole-group folds. Prefer this modest baseline over a high-dimensional model trained on only 32 people. Additional 40 development groups can support fitting after their admission and allocation are frozen. If using explanation features, specify a fixed extraction method, avoid post-discussion demographics, and fit extraction/calibration choices only in development. Topic-specific parameters cannot use held-out-topic labels. Preserve predictions for all six categories and score unchanged as well as changing people.

Conditions using identical admissible personal inputs:

1. Persistence: 0 calls.
2. Fitted ordinal transition: 0 inference-provider calls.
3. Direct independent forecast: 1 call/person.
4. Private reflection: six private updates plus final forecast, 7 calls/person.
5. Generated interaction: three recorded dyadic rounds, two synchronous passes each, then private forecast, 7 calls/person.
6. Actual incoming human-message replay: 1 final call/person; a conditional diagnostic using post-start information, not a time-zero forecast or causal control.

The recorded schedule is admissible as an experimental design input only if known at the forecast cutoff; otherwise model/freeze it without using subsequent message behavior. Read initial rating/explanation only for profile construction. Keep true future messages out of forecast conditions and final outcomes out of every prompt. Replay requires its own exposure designation. Use recorded initial-time measurements for biography; exit-survey demographics remain excluded.

Match reflection and interaction call/output allowances, and report their input-token differences. Improve turn-taking using development-observed message-length and participation distributions before freezing; do not tune those distributions on confirmation messages. Optional shuffled-message control is a later diagnostic, not a substitute for a strong independent baseline. Preserve full input/prediction/evaluation separation and per-call fresh Docker isolation. Host broker and remote inference remain outside Docker.

## Sample size and budget

Using only the eight existing group-level RPS contrasts:

| Existing development contrast | Group difference SD | Approximate 80% power detectable effect at 30 groups | Groups for 0.02 effect |
|---|---:|---:|---:|
| Swarm minus reflection | .05515 | .02821 | 60 |
| Swarm minus persistence | .10722 | .05484 | 226 |

These are illustrative two-sided alpha=.05 normal approximations, `(1.96+.8416)*SD/sqrt(n)`, not a guarantee or an empirical power analysis for the new primary comparison. Eight convenience clusters give unstable variance estimates. New topics, baseline fitting, model changes and multiplicity can increase uncertainty. The transition baseline has not been fitted, so its relevant paired variance is unknown. A 30-group feasibility target cannot yet be described as adequately powered. Report group-resampled intervals and refit development-fitted models in an appropriate nested resampling analysis; where omitted, label uncertainty conditional on fitted models. Repeated model samples are not new human participants.

Full model conditions cost 16 calls/person. Thus:

| Design | Planned calls before retries |
|---|---:|
| 30 groups × 4 people × full conditions × 1 model × 1 repeat | 1,920 |
| Same, 2 models × 2 repeats | 7,680 |
| 15 groups × full conditions × 1 model × 1 repeat | 960 |
| 30 groups × direct + generated interaction only × 1 model × 1 repeat | 960 |

A 960-call design leaves only 40 requests for retries under the existing ceiling and no separate development allowance. Dollar affordability does not override the request cap. The old 480-call pilot cost $0.1506896; doubling its cost is not a valid quote for stronger models, changed prompts, or different context lengths. Price current model IDs and worst-case token allowances before execution.

Recommendation: perform offline split/data admission and ordinal-baseline development first; use already-inspected groups for cheap design debugging. Then either obtain a separately specified confirmation budget or explicitly narrow the experiment's question. Do not reduce necessary statistical sample size solely to fit 1,000 calls and then call it confirmation. The existing runner hardcodes arms, scheduling and preflight counts: do not run it against this manifest unchanged.

## Required implementation before paid calls

1. Masked importer that emits IDs/topics/initial-time inputs separately from final labels and replay messages; register provenance and eligibility reasons, and verify scale and reciprocal schedules.
2. Participant-component split audit and inspection-history reconciliation; freeze admitted manifests and replacement rule.
3. Development-only probabilistic transition fitting with nested group validation; tests prove held-out labels cannot change fitted predictions or hyperparameter selection.
4. Configurable runner supporting direct control, repetitions, all planned arms and an exact call calculator; preserve Docker checks and frozen-artifact behavior.
5. Predeclared meaningful RPS improvement and calibration/false-movement/answer-share/dispersion guardrails. Expected-rating variance is not a joint group distribution; label that diagnostic honestly.
6. Freeze model/version, prompts, schedule, token limits, sources/image hashes, request and dollar caps, retry policy and prediction seal before confirmation.
7. Score once, report negative/inconclusive findings, and retain untouched-topic buffers for a later independent study rather than iterative tuning.

## License

The local pinned LICENSE permits research, including qualifying industry research, and does not grant commercial-use rights. Its definition covers derivative data/models/code/outputs; attribution and redistribution conditions apply. A copy is included here. This benchmark is therefore a research track, not blanket permission to embed its artifacts in a revenue-generating policy simulator. No new licensing claim is made beyond the recorded source terms.

## Reproduction

From the repository root run `.venv/bin/python reports/behavior-feasibility-20261022/debate/build_inventory.py`. It uses the saved tree and existing development evaluation, writes only this directory, and asserts nonoverlap and counts. It never opens new raw sessions. Output: `split-proposal.json` and `planning-diagnostics.json`.
