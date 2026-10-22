# Masked participant and structure admission audit

Completed 22 October 2026. This audit advances the earlier metadata-only inventory; the earlier README describes the state before raw-byte admission. No paid calls or predictions were made.

The proposed metadata split was copied unchanged to `split-proposal.frozen-before-admission.json` **before** new source downloads. SHA-256: `bb321073386031ce76a38977be089351c2e17f13b4fe2c7c68bd86834539cd60`. Source revision remains `5e699a5458ec6ed776ab54e925ad33bb241fd831`.

## Scope and outcome exposure

The importer processed all 108 allocated candidate sessions: eight previously inspected development groups, 40 additional development candidates, 30 confirmation groups, and 30 same-topic reserve buffers. Eight came from the old cache; 100 new CSVs were downloaded from the pinned source to ignored `raw-cache/`, with directory mode0700 and files0600. A local `.gitignore` excludes raw inputs. Every source Git blob ID matched the tree; each CSV's SHA-256 is recorded in `participant-admission.json`.

**Automated processing read raw CSV bytes**, including outcome-bearing columns, only to extract pseudonymous ID hashes and boolean presence/validity flags. No new outcome values, initial/final statements, or conversation texts were printed or provided to the reviewing model. There was no fitting, outcome-based ranking, calibration or scoring. This is masked automated admission, not a claim that source outcome bytes have never been accessed. Existing eight pilot groups had already been inspected in the earlier experiment.

The importer follows the existing pilot schema: `worker_id` from Initial Opinion rows, `sender_id`/`recipient_id` for reciprocal schedules, `sliderValue` solely for integer1–6 validity flags, and `text` solely for nonempty/equality flags. It never emits text, numeric ratings, or raw participant identifiers. Source pseudonyms are hashed consistently for equality checking, without attempted reidentification.

## Results

- 108/108 source files retrieved and hash-verified.
- **432 distinct source participant pseudonyms across 432 slots.** No repeated pseudonyms and no connected components bridging sessions or development/reserve partitions.
- **104/108 sessions pass the current strict pilot structural rules.**

| Assignment | Pass | Fail |
|---|---:|---:|
| Known development | 8 | 0 |
| Additional development candidates | 39 | 1 |
| Confirmation topic candidates | 29 | 1 |
| Topic reserve buffer | 28 | 2 |

One development candidate has five initial events for four source IDs; one confirmation candidate has six for four IDs. A buffer candidate has five for four IDs and incomplete initial data. These duplicate initial records are not all identical. Another buffer group fails the three-distinct-reciprocal-partner schedule criterion. Final-rating validity/presence flags pass for all groups, but no values were emitted.

**Do not silently deduplicate, replace, or relax the parser to restore 30 confirmation groups.** First establish a principled initial-submission and schedule rule using development records only, freeze it, and re-audit masked candidates. If ambiguity cannot be resolved, retain the exclusion and apply an explicitly frozen replacement rule without inspecting final outcomes. No split regeneration was necessary for participant overlap, and the proposal remains unchanged.

## Limits and next requirements

This verifies equality-disjointness of **source pseudonymous IDs**, not independently verified unique humans. The accessed schema describes worker IDs but does not establish stable identity across separate sessions; if identifiers are regenerated per session, equality checks would miss repeated humans. Verify ID stability with the source documentation/authors before claiming person-level independence. No attempt to infer or recover real identities is appropriate.

The other156 unallocated golden groups were **not audited**. Any future addition requires checking its IDs against all allocated groups and re-evaluating component membership. Prior inspection outside recorded local manifests remains unknown. Historical model pretraining exposure is not addressed by this audit.

Thus the current result is **29/30 structurally admissible confirmation candidates under the unchanged pilot parser**, not a paid-ready30-group confirmation study. Budget, sample-size, source-identity, parser, historical-inspection and preregistration requirements in README still apply.

Re-run `.venv/bin/python reports/behavior-feasibility-20261022/debate/audit_participants.py` from repository root. It refuses a changed split proposal, reuses cached source bytes, validates source hashes, and writes only masked metadata. Dataset and derivative-use restrictions in the accompanying LICENSE remain applicable.
