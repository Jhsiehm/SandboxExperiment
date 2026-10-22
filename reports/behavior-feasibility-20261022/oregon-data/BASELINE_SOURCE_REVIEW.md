# Independent source-to-code review — 2026-10-22

Scope: read-only review of `baseline/oregon_reference.py`, `reference-targets.json`, and `oregon-results.json` against the acquired QJE source programs and Table III. No new fit or experiment was run during this review.

**Result: no discrepancy found in the two reproduced Table III reference rows.**

- Paper target is full-sample columns (1) and (2), not credit-record or survey subsamples. N=74,922 matches the public-use source sample.
- `prepare_data.do` renames `ohp_all_ever_matchn_30sep2009` to `ohp_all_ever_admin` and `ohp_all_end_30sep2009` to `ohp_all_end_admin`. The adapter uses these exact originals. “Ever” spans matched notification through September 30, 2009; endpoint is September 30 only. It does not substitute the first-notification survey outcome.
- Original master program uses `sample_hdd`, created as 1 for every public-use row, `noweight=1`, and controls `lll* nnn*`. These are additive lottery-draw and listed-household-member indicators. The adapter's dummy design is equivalent; category reference choice does not change the treatment coefficient.
- `tables_firststage.do` regresses outcome on assignment and controls with `cluster(household_id)`. The adapter sums residual score vectors by household and applies the usual CR1 multiplier G/(G−1) × (N−1)/(N−K). With constant unit weights and a full-rank dummy matrix this matches the stated reference calculation.
- The source reports unadjusted control means separately from adjusted assignment coefficients. The adapter preserves this distinction; the difference of raw assignment-arm shares is not substituted for the adjusted ITT.
- All six published-rounding checks pass: means/effects within .0005 and SEs within .00005. The saved target and adapter hashes match the reported result. This verifies source correspondence and reported rounding; it is not an independent numeric reimplementation of clustered regression.

Reported ever-enrollment reference: control mean 0.1409687722, adjusted assignment coefficient 0.2558657885, household SE 0.0035091501. Endpoint reference: 0.1057709368, 0.1481392362, 0.0031115199.

## Nonblocking scope caveats

The predictive logistic section uses a selected set of observed features and omits released birth year. It should not be described as the strongest available statistical baseline. A future same-information agent comparison must freeze the same inputs on both sides, or add prespecified age preprocessing to both. `draw_lottery` for controls is matched design metadata, not personally experienced notification. The predictor is correctly labeled historical development; these fits do not establish prospective event forecasting or untouched validation. Neither coefficient estimates a person's individual counterfactual outcome.
