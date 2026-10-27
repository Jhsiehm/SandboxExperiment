# Method review: the transition baseline and the local classifier

2026-10-23. This is a post-result development investigation, not a revised evaluation contract. It uses the frozen protocol, evaluator source, fitted baseline, already-scored internal aggregates and sealed prediction vectors. No outer-validation/reserve records, new model calls or training were used. Original results and the failed progression gate remain unchanged.

## Finding

The transition baseline currently predicts these 24 development people better than either language-model arm. Its mean normalized RPS is 0.124716, versus persistence 0.133333, base 0.184574 and candidate 0.216049. The candidate-minus-base difference is +0.031475, so the predeclared +0.02 non-worsening gate failed. Stopping outer validation and interactions was appropriate.

This establishes failure of this candidate and protocol on this cohort. It does not establish that language models cannot add useful information, that longer training would fix the problem, or that the baseline predicts human social mechanisms correctly.

## Is the baseline comparison fair?

**Target and evaluation match.** Every arm predicts the same final six-category observed answer for the same initial-only cases. The evaluator applies the same normalized RPS, equal weighting of people within groups, and equal weighting of six groups. Persistence uses the observed initial category. The transition baseline estimates final-category frequencies conditional on initial category, with one pseudocount per cell. Its 6×6 counts are fitted exclusively on the 23 fitting groups/92 people and sealed before internal outcomes are opened. There is no evidence in the reviewed implementation that it uses internal outcomes or later messages.

**Information access favors the language model, not the baseline.** The classifier also sees the topic and recorded initial explanation, whereas the transition table uses only initial category. The baseline is therefore a deliberately smaller information subset. Its success is a meaningful minimum-performance benchmark; it does not isolate the marginal value of text because architecture, estimation and regularization also differ.

**Eligible data match; actual optimization exposure does not.** The baseline consumes all 92 fitting labels directly. The adapter takes only 52 batch-one microsteps, accumulated into 13 optimizer updates, and therefore has not made a full pass over 92 people. This was a feasibility candidate, not a convergence-matched contest. Its loss is categorical cross-entropy; the baseline is a smoothed frequency estimator, with no neural optimization. Equal eligible data and identical prediction prompts are appropriate controls for candidate usefulness, but cannot support a claim that the two algorithms received equal learning opportunity. The independent sampler reconstruction identifies 52 distinct cases (56.5% of 92) spanning 21 of 23 fitting groups, with no repeated case in the first epoch. The exact row order was not logged during training, so this reconstruction remains conditional on the frozen RNG/iterator assumptions. Its class counts are [11, 5, 8, 7, 8, 13], versus [16, 8, 20, 10, 15, 23] in all 92 fitting people.

A post hoc Laplace-one transition table fitted to those reconstructed 52 cases scores 0.134724 RPS; the full-92 table scores 0.124716. The extra 40 cases improve this control by about 0.010008, roughly 11% of the original candidate-versus-baseline gap. The candidate still trails the 52-case control by about 0.081325. Thus extra baseline data do not explain the observed ranking; this does not rule out neural undertraining or optimization sensitivity. This descriptive control never replaces the frozen full-92 baseline.

The baseline also supplies a strong structural assumption: initial category predicts final category, and distributions pool over people. LoRA must learn to use that same anchor from a short prompt while updating a much larger parameterization. This difference is the intended strength of a statistical control, not cheating. It does mean that failure is not evidence against all possible language-based features.

## What the diagnostics support

The candidate changes the dominant answer more than it differentiates people. Base argmax is category 5 for 22/24 people; candidate argmax is category 4 for 23/24. Mean candidate probability mass on categories 3+4 is about 80.8%. The independent error decomposition reports candidate expected categories in approximately 3.837–3.919, versus a wider base range of 4.234–5.322. These descriptive patterns support weak use of person-specific information under this candidate; they do not identify a unique cause.

A generic “became more confident” explanation is not supported: mean maximum probability falls from 0.479 to 0.425, while mean six-class entropy is nearly unchanged (1.222 to 1.219 nats). The important issue is where probability moved, especially its failure to preserve high initial categories, rather than a simple scalar confidence increase.

Unchanged cases account for most of the candidate's deficit against the transition baseline in the independent decomposition. Seven people starting at category 6 all remain at 6; their candidate RPS is approximately 0.322, versus base 0.084 and transition 0.086. This cohort also has more final category-6 answers proportionally than the 92-case fitting set. That supports investigating retention and distribution shift together, without using these inspected answers to retune the candidate.

**Six-choice conditioning is explicit, and its limitation is measurable.** Median total full-vocabulary mass on A–F falls from 0.983 in the base to 0.655 in the candidate (ranges 0.975–0.997 and 0.617–0.682). Reported probabilities renormalize within A–F by design. The restricted objective does not train the probability of emitting an allowed token against the rest of the vocabulary. The lower mass is therefore not itself proof that the six-class softmax is calculated incorrectly or the reason RPS worsened. It does prevent describing this classifier as a reliable unconstrained answer generator. Raw vocabulary mass and conditional classification performance must stay separate.

**Ordinal loss alignment remains a hypothesis.** Restricted cross-entropy is a proper categorical training loss and can learn the correct distribution in principle. It does not explicitly exploit that confusing adjacent categories is less severe under RPS than moving across the entire scale. RPS is also a proper score; different small-sample fitted models can rank differently under the two objectives. The present result does not demonstrate that changing to RPS training will solve weak conditioning. Training-loss decline is not evidence of ordinal generalization or calibration.

## How much can six groups establish?

Three groups improve and three worsen against base, with unequal magnitudes. Removing one group at a time moves candidate-minus-base mean RPS from −0.010596 to +0.066032. This does not alter the frozen failed gate; it shows that a general adaptation-effect claim is unstable.

The baseline advantage is more consistent within this particular cohort: leave-one-group-out base-minus-transition remains positive, approximately 0.034354–0.084030, and candidate-minus-transition remains approximately 0.068756–0.116190. These are sensitivity calculations, not significance tests. Groups share topic structure, so six groups need not be six fully independent shocks. Neither seed repetitions nor 24 individual rows resolve that uncertainty.

The internal cohort is now explicitly exposed development evidence. A calibration fit on these 24 people followed by reporting their improved score would be resubstitution, not a new validation result. Outer validation remains uninspected in this investigation and must not become a prompt-search resource.

## Competing explanations to retain

- **Too little or unrepresentative optimization exposure:** 13 updates may primarily shift label priors; reconstructed sample/order and training gradients can diagnose exposure, but do not prove a longer run would help.
- **Weak use of the initial anchor:** a simple transition table has the useful structure explicitly; the candidate's narrow expected-category range is consistent with failing to use it.
- **Useful text signal with poor probability mapping:** base logits vary across people but are dominated by category 5. A low-dimensional correction might recover signal; it might also expose that little incremental signal exists.
- **Finite-sample topic/label shift:** fitting and internal category composition differ, and a few groups dominate the aggregate effect.
- **Objective/regularization mismatch:** categorical CE, short LoRA adaptation and evaluation by ordinal RPS may favor different fitted solutions. This remains distinct from implementation correctness.

## One next experiment: does frozen-base information add to the transition prior?

Before another LoRA budget increase, run **one versioned, training-only cross-fitted residual-calibration experiment**, then one fixed readout on the already-inspected internal set. This directly tests whether the existing base representation contributes predictive information after the strong initial-state baseline. A positive result would not isolate a causal effect of explanation text: the representation contains initial category, topic and explanation together; a subsequent separately designed ablation would be needed for that attribution. It is a calibration diagnostic, not another claim of untouched confirmation.

Use the same frozen base checkpoint and initial-only classifier prompt to obtain A–F logits for the 92 fitting cases; retain the existing sealed base logits for the internal 24. This requires exactly 92 new local forward evaluations, zero generated completions and zero paid calls; the 24 internal base predictions already exist. Freeze a 900-second total forward-evaluation deadline, batch size 1, 18 GiB RSS, 14 GiB MLX peak and 2 GiB swap-growth stops. No candidate-adapter logits or target-derived prompt enrichment. Freeze all settings before new calls. Group the fitting cases into five deterministic folds at the connected topic/person-component level, balancing counts using metadata only.

Within each fitting fold, rebuild the Laplace-one transition table using the other folds. Fit two paired low-dimensional models on those same other folds:

- Control: `softmax(log T(initial) + b)`.
- Text/logit extension: `softmax(log T(initial) + b + alpha * z)`, where `z` is the frozen base six-logit vector centered within person, `sum(b)=0`, and `alpha` is constrained to [0,1].

Use the same equal-group mean RPS objective and fixed regularization in both models; one concrete predeclared penalty is `0.01 * mean(b²)`, plus `0.01 * alpha²` in the extension, with `b` bounded to [−2,2]. These are engineering choices to freeze, not estimated scientific constants. Use one deterministic SLSQP optimization from zero biases/alpha, at most 500 iterations and tolerance 1e-9; failed convergence is a failed fit, not permission for another solver or initialization. No hyperparameter grid or internal-label tuning. Score held-out fitting folds with tables and coefficients that never saw their labels. Report the original unadjusted transition baseline alongside both models. Refit each method once on all 92 fitting cases, seal its internal probabilities, then evaluate the already-exposed internal 24 once.

Predeclare before execution: complete finite six-class coverage; the exact frozen base prompt/tokenization rule for every case, with case-specific prompt hashes; no outcome fields in inference; unchanged data boundaries; fixed local call/wall/memory budget; no repairs or retries. For progression, require the extension to improve out-of-fold mean RPS over **both** its calibrated control and the unadjusted transition baseline by at least 0.01, with no held-out topic component worsening by more than 0.05. Require the exposed internal readout to retain the direction of improvement over both controls, and report every component. These thresholds are conservative engineering gates, not significance or power guarantees.

If the gate fails, keep the statistical baseline as the working predictor and do not expand interactions. If it passes, the only next entitlement is consideration of a separately frozen external/outer validation protocol. It does not certify a human simulation. This experiment changes neither the original candidate result nor the status of inspected internal labels.

## Evidence locations

- Frozen run: `data/local-mlx-pilot/outcome-classifier-v1-20261023/` (protocol, baseline, training summary, internal evaluation, sealed prediction vectors).
- Evaluation implementation: `scripts/evaluate_outcome_classifier.py`.
- Exposure reconstruction: `reports/classifier-training-audit-20261023.json`; post hoc exposure-matched control: the run's `error-analysis-sampled-control-v1/` artifacts.
- Independent error decomposition: `scripts/analyze_classifier_errors.py` and the run's `error-analysis-v2/aggregate.json`.
- Reviewer-derived entropy, maximum probability and vocabulary-mass summaries used only the two sealed internal prediction files; no target values were needed for those calculations.
