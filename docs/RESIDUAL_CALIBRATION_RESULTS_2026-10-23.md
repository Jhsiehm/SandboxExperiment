# Frozen-base residual calibration — 2026-10-23

The experiment completed, but did not pass its predeclared progression gate. Adding frozen language-model scores did not improve the calibrated initial-state baseline on the development cross-validation folds. Keep the statistical baseline as the working reference; this result does not support advancing this candidate or launching more training on its behalf.

## Result

All 92 fitting profiles received exactly one local base-model forward evaluation. Five folds kept connected topic/participant components together: 23 groups, 21 components, fold sizes 20/20/20/16/16. Every profile was scored out of fold exactly once. Each fold fitted its transition table and two small calibrators using only the other folds.

Equal-group mean normalized ranked probability score (RPS; lower is better):

- Unadjusted transition baseline: **0.141335935**.
- Calibrated transition control: **0.140185794**.
- Same control plus frozen base logits: **0.140233300**.

The model extension improved over the raw transition baseline by 0.001102635, below the required 0.01. It was worse than the calibrated control by 0.000047505. The component-harm bound passed, but both improvement requirements failed. This is a failed research gate, not an execution error.

All ten single-attempt SLSQP fits converged within 21–27 iterations and satisfied their parameter constraints. The fitted logit coefficient was effectively zero in four folds and 0.021114 in the remaining fold. This supports a narrow conclusion: the fixed bounded correction extracted no useful incremental predictive performance under this design. It does not prove that language models lack predictive information or that another dataset or representation could not work. Solver convergence does not establish a global optimum.

## Boundaries and laptop measurements

The workflow stopped immediately after the out-of-fold gate. It did not refit on all 92, produce new internal-cohort predictions, reopen the 24 internal outcomes, or access outer-validation/reserve outcomes. Earlier experiments and their results remain unchanged. There were no paid API calls, generated completions, or new neural training steps.

The native MLX forward pass took 32.56 seconds; the supervisor completed in 36.43 seconds. Peak MLX allocation was 4,932,223,088 bytes (4.59 GiB). The supervisor observed no system swap growth from its starting 5,975.81 MiB, and no time or memory stop. System swap is shared by all applications; sampled process RSS and MLX allocation measure different things. These measurements establish feasibility of this particular inference run on the laptop, not a general training capacity claim.

## Reproduction and audit

Run artifacts are under `data/local-mlx-pilot/residual-calibration-v1-20261023/`: frozen `contract.json`, label-free `prompts.json`, `base-fit/` predictions/summary, `watchdog-base-fit/` telemetry, `oof-predictions.json`, `oof-evaluation.json`, and `decision.json`. The decision is `oof_gate_failed`. Outputs are exclusive-create and the frozen source must not be edited or reused to overwrite this run.

Contract SHA-256: `6df0158c65d784b20b12e2331dcf00c4216842c179fd20e6d74bf21c1df93841`. Base predictions SHA-256: `45d3dfedf6b65ab6a51987b28d349206a72a35e4083880d7ee2a52e8a3333207`. The contract binds model/tokenizer bytes, original prompt source, fold manifest, runner, solver, supervisor and analysis versions. Runtime verifies Python, NumPy 2.5.3 and SciPy 1.18.1 against the frozen environment before loading analysis inputs.

The 21 focused pre-execution tests passed, covering fold separation, analytic gradients, optimizer failure, model-arm admission, both progression criteria, and runtime drift stopping before data access. Independent protocol review is recorded in `RESIDUAL_CALIBRATION_PROTOCOL_REVIEW.md`; independent numerical result verification is recorded in `RESIDUAL_CALIBRATION_RESULT_AUDIT.md`.

The independent result auditor reconstructed all out-of-fold probabilities exactly and reproduced metrics and objective components within 1e-12, without rerunning the optimizer or accessing internal outcomes. The dashboard exposes whitelisted aggregates, with 16 viewer tests plus JavaScript syntax/rendering checks passing. The local server was restarted and the browser preview verified the failed gate, all 92 completed evaluations, distinct six-decimal scores and the stopped internal stage.

The next research decision should concern data and experimental design, using the statistical baseline as the reference. Do not tune this candidate repeatedly against the exposed development cohorts or present this negative diagnostic as confirmation evidence.
