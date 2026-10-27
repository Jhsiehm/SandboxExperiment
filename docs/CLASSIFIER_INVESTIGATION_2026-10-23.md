# Coordinated classifier investigation — 2026-10-23

The statistical baseline wins mainly because it preserves useful dependence on the initial category, while the tested adapter produces nearly the same distribution for different people. No concrete implementation bug has been identified. The cause of that weak conditioning remains unresolved; this investigation does not show that more training would fix it.

## Evidence

The candidate's most probable category is 4 for 23 of 24 people. Its expected category ranges only from 3.8366 to 3.9188. In contrast, the transition baseline changes its distribution explicitly with initial category. Fourteen people stayed in their initial category; they account for about 88.6% of the candidate's RPS disadvantage against the transition baseline. Seven people started and stayed at category 6, where the candidate's shift toward the middle is particularly costly.

The fitting and internal cohorts differ: 25.0% of fitting outcomes are category 6, versus 45.8% internally. This is a small, topic-separated development cohort, not evidence of a general population shift. Candidate confidence did not simply increase: mean maximum probability declined and entropy was nearly unchanged. The important observation is misplaced, weakly differentiated probability.

The neural pilot also consumed less data than its statistical comparator. The source/RNG reconstruction selects 52 unique records from 21 of the 23 fitting groups, leaving 40 of 92 records without a gradient exposure in this run. Sample IDs were not logged, so this is a conditional reconstruction, not direct telemetry. A post-hoc transition table fitted to those same reconstructed 52 records scores 0.134724 RPS, versus 0.124716 using all 92. Both remain well ahead of the candidate's 0.216049. Extra baseline examples account for about 11% of the original gap in this diagnostic; they do not explain the ranking. This does not rule out neural undertraining or optimization sensitivity.

The original gate remains failed. Candidate-minus-base RPS is +0.031475, but leaving out one group changes that difference across −0.010596 to +0.066032. The adaptation effect is therefore unstable across these six groups. The transition baseline's observed advantage over both language-model arms stays positive under each leave-one-group-out calculation. These ranges are sensitivity checks, not confidence intervals or significance tests.

## Audit scope and limitations

The agents reviewed data/metric decomposition, training implementation and artifacts, and comparison methodology independently, with the coordinator integrating results. Source/analytic checks support correct class ordering, causal prediction position, restricted six-class loss, paired prompts and outcome separation. The training artifacts record 52 contiguous microsteps; the public optimizer schedule implies 13 updates. Saved weights are finite and the final checkpoint matches the step-52 checkpoint. Neither exact sample IDs nor optimizer state was serialized, and no new model inference was performed to test save/reload equivalence. These are evidence limits, not a discovered failure.

All analyses used previously scored internal outcomes, fitting data and saved artifacts. No outer-validation or reserve files were accessed. No new language-model calls or neural training occurred. The original frozen protocols, models, predictions and baseline remain unchanged; the 52-example statistical control and other analyses are stored separately. Dashboard aggregate filtering and rendering checks passed ten tests plus JS syntax validation.

## One next experiment

Test whether the frozen base model adds useful information beyond initial state before spending more on LoRA. Obtain its six logits on the 92 fitting profiles under the unchanged prompt. Using five deterministic topic/person-separated fitting folds, compare a calibrated initial-state transition control with the same control plus a bounded contribution from the frozen base logits. Fit only on each fold's training portion, with fixed regularization, optimizer and budgets; no hyperparameter search on the internal 24 people.

The method review specifies a concrete version: 92 local forward evaluations, no generated conversations or paid calls; at most 900 seconds, 14 GiB MLX allocation, 18 GiB process RSS and 2 GiB system swap growth. Fit two small paired RPS calibrators using fixed bounds and regularization. Require the extension to beat both its calibrated control and the unadjusted transition baseline by at least 0.01 out of fold, with no held-out topic component worsening by more than 0.05. Only afterward permit one sealed readout on the already-exposed internal cohort, explicitly labeled development. A passed gate would justify considering separate outer validation; a failed gate leaves the statistical baseline as the working reference.

This is a proposed experiment, not an executed result. Exact fitting, fold and convergence rules are documented in CLASSIFIER_METHOD_REVIEW.md. It tests incremental predictive information in base scores; it would not establish a causal effect of text or validate human social simulation.

## Reproducible evidence

- CLASSIFIER_ERROR_ANALYSIS.md and scripts/analyze_classifier_errors.py: group, initial-category and change-status decomposition; reproduces all four frozen RPS values to numerical tolerance.
- CLASSIFIER_TRAINING_AUDIT.md and reports/classifier-training-audit-20261023.json: source/artifact review and conditional sampling reconstruction.
- CLASSIFIER_METHOD_REVIEW.md: fairness, competing explanations and the proposed controlled experiment.
- Run artifacts under data/local-mlx-pilot/outcome-classifier-v1-20261023/: error-analysis-v2/, error-analysis-sampled-control-v1/, investigation/group-sensitivity.json and investigation-summary.json.
