# ANES 2012 profile ablation development results

Run: `anes2012-ohio-profile-ablation-development-v1`.

Completed 960 forecasts for 120 previously inspected development respondents across four profile arms and 2 repeats. This is development evidence, not fresh external validation. No automatic promotion was performed. The 50-person reserve remained excluded.

## Individual prediction

Lower weighted half-multiclass Brier is better. Macro scores equally average the three tasks. Direct predictions average the two probability vectors before scoring; this differs from the previous experiment's mean of repetition-level losses.

| Profile | Direct | Hybrid | Party baseline | Prevalence baseline |
|---|---:|---:|---:|---:|
| original_sparse | 0.23786 | 0.22821 | 0.22087 | 0.29875 |
| original_rich | 0.23778 | 0.22235 | 0.22087 | 0.29875 |
| reduced_existing | 0.23871 | 0.22590 | 0.22087 | 0.29875 |
| reduced_plus_observed | 0.23184 | 0.22483 | 0.22087 | 0.29875 |

Party and hybrid predictions use five outer respondent folds and four inner folds. Each scored respondent's outcomes were excluded from their model fitting and parameter selection. The party baseline is repeated by profile for comparison; it uses the same party observations in every arm.

## Profile contrasts

Negative differences favor the second arm. These paired respondent bootstrap intervals condition on this development sample and model setup.

| Before → after | Macro Brier difference | 95% interval |
|---|---:|---:|
| original_rich → reduced_existing | +0.00092 | [-0.00944, +0.01127] |
| reduced_existing → reduced_plus_observed | -0.00686 | [-0.01867, +0.00350] |

The rich-to-reduced contrast tests removal of existing fields; the reduced-to-augmented contrast tests addition of four measured fields. The sparse original profile provides an additional reference.

## Calibrated comparisons

Negative differences favor the hybrid. Intervals resample people while holding the already fitted out-of-fold predictions fixed. They do not include calibration-refitting uncertainty and are exploratory multiple comparisons.

| Profile | Reference | Hybrid minus reference | Conditional 95% interval |
|---|---|---:|---:|
| original_sparse | party | +0.00735 | [-0.00299, +0.01780] |
| original_sparse | direct | -0.00964 | [-0.02349, +0.00480] |
| original_rich | party | +0.00148 | [-0.00939, +0.01128] |
| original_rich | direct | -0.01544 | [-0.03222, +0.00268] |
| reduced_existing | party | +0.00504 | [-0.00524, +0.01514] |
| reduced_existing | direct | -0.01280 | [-0.02910, +0.00449] |
| reduced_plus_observed | party | +0.00396 | [-0.00680, +0.01448] |
| reduced_plus_observed | direct | -0.00701 | [-0.02128, +0.00854] |

## Population and cross-attitude diagnostics

Share MAE is the mean absolute difference between predicted and observed category shares, equally averaged across tasks. Modal-pair TV compares observed response-pair frequencies with pairs of predicted most-likely answers, equally averaged across task pairs. The latter is a descriptive assignment proxy, **not a joint predictive distribution**.

| Profile | Variant | Share MAE (percentage points) | Modal-pair TV |
|---|---|---:|---:|
| original_sparse | direct | 5.979 | 0.31672 |
| original_sparse | hybrid | 2.666 | 0.25597 |
| original_sparse | party | 0.782 | 0.26148 |
| original_sparse | prevalence | 0.601 | 0.51663 |
| original_rich | direct | 5.815 | 0.31437 |
| original_rich | hybrid | 2.551 | 0.30850 |
| original_rich | party | 0.782 | 0.26148 |
| original_rich | prevalence | 0.601 | 0.51663 |
| reduced_existing | direct | 5.724 | 0.31809 |
| reduced_existing | hybrid | 2.467 | 0.25170 |
| reduced_existing | party | 0.782 | 0.26148 |
| reduced_existing | prevalence | 0.601 | 0.51663 |
| reduced_plus_observed | direct | 6.116 | 0.35898 |
| reduced_plus_observed | hybrid | 3.148 | 0.29755 |
| reduced_plus_observed | party | 0.782 | 0.26148 |
| reduced_plus_observed | prevalence | 0.601 | 0.51663 |

The machine-readable diagnostics also include observed and predicted Cramér’s V, full pair tables and unweighted counterparts. Undefined association for constant modal predictions is retained as missing. Modal ties use first-index argmax. The base evaluation includes task scores, log loss, repeat agreement, effective sample sizes and descriptive party subgroup results.

## Execution and audit

Provider requests reserved: 960. Provider-reported cost: $0.667214. Unresolved usage records: 0. Hard run ceiling: $10; request ceiling: 1000.

Each prompt was built in a fresh non-root Docker worker with no network or credentials, read-only filesystem, dropped capabilities and no new privileges. The host broker and remote model inference remain outside that container boundary.

The independent audit verified exact payloads, worker isolation, complete unique forecast panel, reserve exclusion, outer-fold boundaries and independently recomputed direct Brier scores. Statistical/hybrid behavior was additionally tested by adversarial held-out-label changes; it was not reimplemented independently.

Independent audit seal: `919f708811714e28a692f5e4c4677569852762fa72c4faad69d3da557664a68c`.

## Interpretation limits

These are previously inspected Ohio development respondents, one model and two repeats. Survey weights within a state subset and small subgroups limit representativeness. Policy items reconstruct contemporaneous answers; they do not establish causal policy reception or longitudinal change. Interview completion is a provenance date, not an exact item timestamp; available information is not assumed to be personal exposure. There was no historical pack, private reflection or conversation in this comparison. A favorable development estimate requires frozen, larger external validation before generalization; statistical nonsignificance is not evidence of equivalence.

No additional fine-tuning or AgentSociety installation was part of this run. Interaction value remains a separate comparison after individual fidelity is validated.
