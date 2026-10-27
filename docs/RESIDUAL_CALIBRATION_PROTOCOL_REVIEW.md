# Independent review: residual calibration diagnostic

2026-10-23. Status: **source review passed; admitted for the single frozen diagnostic, subject to unchanged source hashes and runtime gates**. The reviewer performs source, metadata and synthetic-numerical checks only. No model calls, new internal outcome reads, outer validation or reserve access.

## Frozen design being reviewed

The authorized diagnostic uses 92 fitting cases, five folds defined by connected topic/person components, frozen-base six-choice logits, and initial-category transition probabilities. Within each fold, both the transition table and calibrators must be fitted exclusively on the other folds. The paired models are a bias-adjusted transition control and the same model with a single nonnegative scalar multiplying centered base logits. Both fit equal-group mean RPS with fixed penalties, bounds and one deterministic SLSQP initialization.

Declared optimizer: at most 500 iterations, `ftol=1e-9`, zero biases and zero alpha at initialization, biases in [−2,2] with sum zero, alpha in [0,1], penalty `0.01*mean(b²)` and extension penalty `0.01*alpha²`. No solver restarts, grid search, alternate candidate, outcome-based case exclusions or internal-label calibration.

Declared gate: out-of-fold RPS improvement of at least 0.01 over both the calibrated control and raw transition baseline, and no held-out topic/person component worsening by more than 0.05 against either comparator. Overall OOF scores must aggregate all held-out people/groups once, rather than averaging unequal-sized fold means. Internal outcomes may be read only after this gate passes, both calibrators are refitted once on all 92 fitting cases, and all resulting internal predictions are sealed.

## Review checks

- Fold components include transitive links through topics and supplied participant IDs; each component stays whole. Deterministic balancing must use only metadata, not label frequencies or observed errors. All fitting cases appear in exactly one held-out fold, with nonempty fit/test partitions.
- Each OOF transition table uses only fold-training labels and fixed Laplace-one smoothing. The control and extension share that exact table, cases, weighting, solver settings and bias regularization. The extension alone adds alpha and its fixed penalty.
- Base logits must use the exact original base weights, class ordering, prompt/template/tokenizer and initial-only token sequences. Never append training class tokens during inference. Bind/check record identities, order and prompt hashes against prepared prompts.
- The logits feature is centered within each person's six classes, independent of labels; unrestricted vocabulary mass is diagnostic, not silently renormalized into another feature.
- Require finite logits, features, losses, gradients when used, predictions and optimizer outputs. Solver failure, exhausted iteration budget without success, violated constraints, or unexpected coverage stops the experiment rather than triggering another initialization.
- Verify constraints numerically after optimization: bias sum, parameter bounds, exactly six finite probabilities summing to one, and all expected rows. Record success flag, status/message, iteration count, initial/final objective, parameters and objective components. A solver success flag is numerical termination, not proof of a global optimum.
- Preserve the complete original OOF predictions and per-component comparisons even when the gate fails. Failure must prevent internal target access and any automatic external validation.
- Bind source, optimizer package version, fold manifest, fitting-data hashes, base model and prompt hashes, and original internal base feature hashes. Do not recursively verify outcome-bearing target files during preflight or model inference.
- Native local inference remains under the separately frozen call/wall/memory budget; fitting is local numerical optimization with no model generation. Do not call passing six-class probabilities a learned output-format success.

## Interpretation boundary

All results remain development evidence. The 24 internal cases were previously inspected and cannot regain confirmation status through new seals. Positive incremental performance would show usefulness of this frozen base representation beyond these controls, not a causal contribution of text alone or a validated society model. A negative result cannot distinguish absent signal from insufficient data, the chosen restricted correction, fold variability or local numerical optimization limits.

## Final source review and verification

Independent review confirmed fit-fold-only priors, identical control/extension fit cases and weights, analytic RPS derivatives, one-attempt optimization, finite objective/gradient checks and post-optimization feasibility checks. The predictor imports the frozen classifier prompt helper, binds model/tokenizer bytes and ordered class IDs, and evaluates the final prompt position without appending a target token. It does not load fitting outcomes. Workflow admission verifies base arm, identity/order, prompt digest and probability/logit consistency. Source preparation assigns connected components using metadata alone; runtime independently rejects topic or supplied-ID overlap. The supplied-ID separation is supported by the inherited raw-participant audit and is not a claim about unobserved real-world identities.

The orchestrator computes all out-of-fold group scores once, checks both comparator gains and both component-harm bounds, and returns on failure before calling the internal readout. On success it refits once, writes and seals internal predictions, then accesses the internal target file. Original internal predictions are verified against their earlier seal. All fitting targets are validated as integer categories before conversion. No outer validation stage is invoked.

All **20 focused tests passed** using `/Users/joshua/Documents/ChatGPT/Policy Sim/.venv/bin/python`: fold preparation, solver, workflow and inference-contract suites. Coverage includes metadata-only label/rating invariance, finite-difference gradient agreement, failed-optimizer rejection without restart, fold exclusion, actual topic leakage, both-comparator gates and base-arm admission. The MLX environment lacks SciPy, so analysis must use the recorded separate analysis interpreter; inference continues in the existing MLX environment. These are synthetic/source checks, not model executions or claims about eventual results.

Reviewed fold manifest: `folds-v3.json`, SHA-256 `8aa85b5282ecf80f83001ad8ca16583b330019f4a87aeb5288bd8e92827d14ba`; 92 rows, 23 groups, 21 connected components and fold sizes 20/20/20/16/16. No additional target files were inspected for this review.

Reviewed source digests (SHA-256):

- `scripts/prepare_residual_calibration_folds.py`: `9779c5d9cf1cb5f03d924207c251c7d9891fbc42a5c8575e05c3d52e650bd7aa`
- `scripts/residual_calibration_solver.py`: `3b100b042eef7a29a501a480edee063590abb4985641b9e9c41dc5b1fabd94b1`
- `scripts/run_residual_calibration.py`: `b1414edc1151babc5a0e791f00802dfe1a426bddee7e66a2cfc7f5afc5f46f9a`
- `experiments/debate-sft-replication/residual_calibration_v1.py`: `5fd7631d3042efca9aaa15ccac74a743e6a3742b5383778bcac2093de5697e26`
- `experiments/debate-sft-replication/residual-calibration-v1.protocol.json`: `35b5cda06f81a2b0f248fa4adce96c17b286c14f5f293385c48d74fae7b0936a`

Final runtime guard reviewed: immediately after contract/source binding verification and before profile/target loading or any optimization, the runner requires exact equality of Python version, NumPy version and SciPy version with the frozen `analysis_environment`. A mismatch raises rather than adapting or retrying. All 20 focused tests passed again after this change. Version equality is a reproducibility guard, not a guarantee of bitwise equivalence across hardware.
