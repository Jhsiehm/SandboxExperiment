# Phase 4 — election-eve live matched experiment

## Objective

Estimate the effect of bounded peer conversation under a frozen election-eve evidence world while
separating evidence dependence, profile dependence, and model-prior knowledge.

## Preconditions

- M0–M4 are complete.
- The 2012-11-05 evidence corpus is authenticated, cutoff checked, and sealed.
- The protocol, prompts, model roster, sampling settings, assignments, budgets, and stopping rules are
  frozen.
- Paid execution has explicit approval and enforced request, token, and dollar ceilings.

## Procedure

1. Run a small live smoke test that cannot consume the confirmatory assignments.
2. Execute paired independent and society arms.
3. Execute shuffled-profile, shuffled-evidence, and no-evidence ablations.
4. Persist every attempt, failure, retry, provider usage record, and protocol deviation.
5. Seal all predictions before any held-out evaluation is opened.

## Exit evidence

- Complete run matrix and assignment manifest.
- Model, prompt, tool, evidence, and budget fingerprints.
- Sealed prediction artifacts and failure ledger.
- Cost and completion report.
- Completed M5 milestone review.

## Current state

Not started. No live scientific result is claimed.
