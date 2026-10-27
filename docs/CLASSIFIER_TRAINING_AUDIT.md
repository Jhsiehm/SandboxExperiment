# Classifier training audit — 23 October 2026

## Finding

The saved artifacts and inspected implementation do **not** show a target-order, loss-position, gradient-accumulation, adapter-loading, or probability-extraction bug that explains the failed internal gate. The classifier received a very small optimization budget, but **this audit does not establish that more training would improve its predictions**.

There is a concrete exposure imbalance: the transition baseline fitted all 92 available training people. Replaying the frozen sampler reconstructs 52 distinct gradient examples, covering 21 of 23 training groups, for the classifier. Forty people were not encountered. This qualifies an algorithm-comparison interpretation; it does not erase the recorded failure or establish its cause.

The frozen internal result remains candidate RPS **0.216049**, base **0.184574**, transition **0.124716**, persistence **0.133333**. Candidate minus base is **+0.031475**, above the predeclared +0.02 entry guard. Three groups improve and three worsen. Outer validation and interaction remain unopened.

## Scope and evidence

This audit read saved fit tokens, training metrics, adapter files, already-saved internal predictions/evaluation, and local implementation code. It did not load a language model, run inference, train any model, read outer-validation payloads, or access reserve data. It did not read internal outcome files; those outcomes had already been scored by the separate evaluator.

Reproducible artifact calculations are in `scripts/audit_classifier_training.py`; its output is `reports/classifier-training-audit-20261023.json`. The audited run is `data/local-mlx-pilot/outcome-classifier-v1-20261023/`.

The frozen contract hash is `d337a209357e71e07a0aa4b7460ce23f57b82685a08cae65c69e8362e1dffbbc`. The current classifier source matches its bound hash. Every candidate-seal binding verifies. The adapter hash is `1c56804c7d758b421337bdfdff1ab1f3383444ba1e9c724bb6ae9afe0f400698`.

## Training execution and exposure

The metrics contain exactly 52 reports, with contiguous iterations 1–52, finite losses, and cumulative supervised-example count 52. The reported `trained_tokens` field counts **one categorical supervision event per example** in this custom loss; it is not the number of prompt tokens processed.

The public MLX trainer calls the optimizer only when `iteration % grad_accumulation_steps == 0`, averages accumulated gradients by four, and resets the accumulator after each update. With batch size one and accumulation four, the executed path therefore entails **13 optimizer updates**. This is supported by source plus the complete callback sequence; the optimizer state/counter itself was not saved. The logged learning rate is consistently approximately `5e-5`. The runner supplies `val_dataset=None`; there is no validation loss monitoring or checkpoint selection.

The installed batch iterator first stably sorts example indices by token length, then applies a NumPy permutation. Replaying that algorithm with seed 20261023 yields:

- 52 distinct examples out of 92: **56.5% coverage**, with no repeat in this first partial epoch.
- 21 of 23 groups represented.
- Selected final-category counts for categories 1–6: **11, 5, 8, 7, 8, 13**.
- Available counts across all 92 people: **16, 8, 20, 10, 15, 23**.
- Unseen counts: **5, 3, 12, 3, 7, 10**.

All 52 reconstructed sequences and offsets were checked against the installed public `iterate_batches` function using these saved token arrays, without a model. The reconstruction and its optimizer blocks are in the JSON report.

**Important limit:** sampled row IDs and the NumPy state immediately before batching were not logged during the real run. The reconstruction assumes no intervening NumPy random-state consumption after the runner's seed. No other `np.random`/`numpy.random` use was found in the inspected MLX model loader, tokenizer loader, or LoRA conversion path. That supports the reconstruction but does not turn it into an observed sample-ID trace. The separate error analysis can use these rows for a clearly labeled post hoc exposure-matched baseline, without modifying the original baseline.

## What the loss trace does and does not establish

Across 52 examples, mean loss is **2.7983**, median **2.2043**, minimum **0.2995**, and maximum **7.6488**. Mean loss over the first 26 examples is **3.2151**, versus **2.3816** over the last 26. The first/last 13-example means are **3.4767 / 2.2954**.

These are different people encountered under changing weights, not repeated evaluations of the same fixed set. Their decrease cannot establish convergence, generalization, or even a controlled reduction in fit-set risk. No frozen pre/post fit-set score was recorded. Comparison with `log(6)` would likewise mix changing cases and parameters rather than diagnose the learned candidate on a fixed dataset.

“Undertraining” is therefore a **hypothesis**, supported only in the narrow sense of limited exposure and few updates. More exposure could improve, worsen, or leave held-out RPS unchanged. Learning-rate/adapter-scale effects, small-sample variation, topic transfer, and the difference between categorical cross-entropy and ordinal RPS remain distinguishable possibilities rather than established explanations.

## Loss, target, and prompt consistency

The class mapping is **A–F → scores 1–6**, with tokenizer IDs **32–37** in that order. Preparation verifies single-token encoding, distinct IDs, and decode round-trips. Fit records validate integer targets 1–6 and append the corresponding one class token after the initial-only assistant-generation prompt.

For prompt length `offset`, the custom loss uses the logits at `offset - 1`, which predict the first assistant token. It selects only the six declared columns and computes float32 cross-entropy against the observed class. It does not include an EOS target or full-vocabulary loss. Although padding and the appended target token are present later in the batch, the selected position is before that target, under the causal attention mask.

The six focused tests pass. Analytic tests verify uniform restricted loss `log(6)`, correct prediction position, zero loss-gradient outside the six columns and selected position, and unchanged restricted loss when an unrelated vocabulary logit is increased by 10,000. They also verify token mapping and prompt-field whitelisting.

Both saved inference arms use identical prompt hashes for all 24 cases and the same ordered class IDs. Recomputing restricted softmax from all 48 saved six-logit vectors agrees with saved probabilities within **6.34e-8** maximum absolute error. No class-order or output-normalization inconsistency was found. The reported full-vocabulary class mass is a separate diagnostic, not a multiplier or filter used in scoring.

## Adapter persistence and reload

The saved candidate contains exactly **224 float32 tensors / 10,485,760 parameters**. Their names and shapes match all seven linear projections in each of layers 16–31, with rank eight. This is the actual scope of the installed helper's default module selection; it is not only attention query/value adaptation.

All saved adapter elements are finite. All 112 `lora_b` matrices contain nonzero values; their combined L2 norm is **2.6680**. The inspected initializer sets these matrices to zero, so the saved artifact is not an unmodified initialization. The A-matrix norm is **17.4266**, but no initial A snapshot was saved, so that norm alone does not quantify its change.

The step-52 checkpoint and final adapter are byte-identical. Reload configuration preserves 16 layers, rank eight, dropout zero, and MLX scale 20. The installed loader reconstructs LoRA modules, checks tensor names/shapes, and loads the adapter weights. Both inference processes completed successfully after candidate-seal and training-watchdog checks; all 24 candidate probability vectors differ from base.

These observations support successful persistence and use of a nontrivial adapter. **Exact before-save versus after-reload prediction equivalence was not measured:** no live pre-save outputs were retained, and this audit did not run inference to create them. The installed loader uses `strict=False`, but the saved artifact's full expected 224-key/shape set was independently verified, so there is no evidence of silently omitted adapter tensors here.

MLX's `scale=20` is a direct multiplier in its LoRA forward expression. It is not automatically interchangeable with another framework's `alpha=20` divided by rank. The frozen implementation consistently uses the MLX meaning at training and inference; this is not a discovered mismatch within this run.

## What can be concluded about the baseline advantage

The baseline won the recorded internal comparison. The current audit finds no implementation defect that invalidates that result. It identifies unequal actual training exposure, an unlogged sampler trace, no fixed fit-set learning curve, and no direct save/reload equivalence check as limits on explaining it.

The separately computed 52-example transition refit obtains **RPS 0.134724**, versus 0.216049 for the classifier. This is a **post hoc diagnostic** using reconstructed exposure, not a replacement for the frozen 92-example baseline. Its continued advantage means the exposure difference alone does not explain the ranking. It still does not establish what additional classifier updates would do.

Future comparisons can directly falsify explanations by logging exact sampled IDs, evaluating fixed pre/post fit-set scores, and checking a deterministic pre-save/reloaded output. Those checks must belong to a new frozen experiment; no extra training, tuning, or outer-validation opening was performed for this audit.
