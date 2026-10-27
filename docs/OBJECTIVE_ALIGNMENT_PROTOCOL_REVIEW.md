# Independent review: objective-aligned local adaptation

2026-10-23. Status: **training and internal-prediction implementation review passed; coordinator must freeze artifacts, supervise stage deadlines and independently admit the evaluator before outcome access**. Reviewer work is metadata/code review only: no training, model inference, paid calls, reserve inspection, or held-out outcome access.

## What the target actually means

One recorded final six-category answer is one observation of a person's response. A one-hot vector encoding that answer is an admissible supervised categorical label; it is not a measured six-way subjective distribution for that individual. Repeated observations or a separately identified measurement model would be required to make stronger claims about personal uncertainty.

Training a model to emit a one-hot JSON string uses next-token cross-entropy over serialized text. This can teach output shape and association between input and observed category. It does not directly minimize six-category Brier/RPS or establish calibrated probability estimates. It may favor extreme reported probabilities because every training answer is extreme. Better JSON compliance or lower text loss alone must never pass the behavioral gate.

A more directly aligned alternative is a six-choice categorical classifier: train a fixed verified single-token category, score all six allowed tokens under the same prefix, and normalize those six logits. This minimizes categorical negative log likelihood of observed labels and provides a defined probability extraction rule. Those conditional probabilities still need empirical calibration/accuracy evaluation. It is a different method from free-form probability JSON and must be chosen before training, not substituted after results.

The initial one-hot JSON proposal came from the coordinator, not a user requirement. Before freezing or reading new results, the coordinator selected the restricted six-class objective on review advice. A JSON imitation pilot would have been a different, limited objective. Do not manufacture soft targets from the model, label smoothing, or a hand-tuned persistence coefficient and describe them as observed human distributions. Any smoothing/mixture is a separately fixed modeling assumption.

## Split and initialization requirements

A new holdout carved from the previous 29 training groups was already exposed to the existing message adapter. Use a fresh base model and newly initialized adapter for this new split. Keeping that old adapter would invalidate a claim of unseen-by-adapter cases.

Split connected components of group/topic/participant membership, not individual rows or a fixed number of groups followed by ignoring shared topics. The data agent identified that an initial five-group proposal shares a topic across the split; its topic closure may produce six holdout and 23 training groups. Verify the actual closure and participant overlap before freezing counts. All outcomes, message examples and derived records belonging to a split component inherit its role. A split that cannot separate people/topics must be revised before looking at model results.

Even with fresh model initialization, this is researcher-exposed development data. It is not fresh external confirmation, and pretrained-model contamination remains a separate question. Original development-validation groups and the protected reserve stay outside this training action unless separately admitted under a new contract.

Training preparation may extract final labels from admitted training groups because that is the authorized supervised target. Holdout targets must remain evaluator-only; initial-only holdout cases can be supplied for prediction. Do not permit target-derived profile enrichment, final-state summaries, later dialogue or target values in the prompt. The direct task should keep the same initial-only information boundary at training and inference.

## Fixed candidate and budget

The proposed starting point is fresh base plus a new LoRA candidate, one fixed seed, rank 8 over 16 layers, learning rate 5e-5, batch size 1, 52 microsteps with accumulation 4 (13 optimizer updates), no checkpoint selection from holdout performance. These are provisional until the coordinator freezes the contract. With approximately 92 training people, 52 batch-one examples are less than one pass through the people; report this as a bounded feasibility pilot rather than adequate convergence.

Freeze all trainable layers, adapter initialization, target rendering, sequence cap, masking, optimizer and scheduler, exact update count, checkpoint rule, data ordering/seed, and model/tokenizer/package/source hashes. Audit completion masks and retain the full initial state and supervised completion; never silently truncate. No mixed message objective is required to establish feasibility. If added, freeze its ratio, sampling schedule and data roles before calls; it expands interpretation and must not leak holdout messages into adaptation.

The coordinator declared new budgets: 1800 seconds for training and 600 seconds for the matched internal prediction pair, with 14 GiB MLX peak, 18 GiB process RSS and 2 GiB swap-growth limits per stage. These are distinct from the earlier format-experiment cap. No paid inference is necessary. Existing zero-paid-call constraints remain compatible with native MLX; a paid/cloud fallback is outside this review. The coordinator must resolve any broader session spending limit before executing dependent work.

## Evaluation and format gates

1. Predeclare one training-only format smoke cohort before tuning. Record every call and every invalid output. Format-gate success is compatibility, not belief accuracy.
2. Freeze the new candidate and then predict all initial-only held-out cases for both unchanged base and new candidate, with identical model bytes except the adapter, prompt/tokenizer/prefix, decoding limits, seeds and probability parser. Seal predictions before evaluator outcomes are opened.
3. For JSON generation, preserve a strict six-finite-number parser with exact schema, sum tolerance, duplicate-key rejection, no extraction, normalization, retry or repair. Any declared prefix is supplied input, with exact continuation assembly. Report full coverage; failures cannot disappear through complete-case scoring.
4. Predeclare categorical probability scoring, change/no-change diagnostics and persistence/statistical baselines. If zeros can occur, explicitly define log-loss handling before evaluation; do not choose clipping after seeing scores. Brier/RPS remain finite for one-hot forecasts.
5. Report paired group effects and coverage. A handful of group/topic components is not enough for an equivalence or general-superiority conclusion. Separate predictive gain from format validity and training text loss.
6. No holdout-driven reruns, prompt changes, label-smoothing searches, checkpoint substitution, or objective mixing in the same version. Preserve a failed candidate and create a separately justified development version if further work is warranted.

## Current blockers and review handoff

- Objective chosen before freeze: restricted six-class cross-entropy, fixed A–F single-token categories; review executable loss and extraction mapping.
- Data preparation must freeze participant/topic/group closure and demonstrate no model-visible holdout outcomes.
- Fresh candidate initialization and fixed optimizer-update budget must be enforced by executable code, not only prose.
- Matched evaluation, strict-format handling and resource budgets must be versioned alongside training.
- Final independent source and synthetic-test review remains pending; this document is not a claim that training or evaluation has run.

## Coordinator decision before freeze

The final proposed method uses restricted six-class cross-entropy through the trainer's public loss hook. Targets are the single observed final class, mapped in order to A–F. Start from the unchanged base and fresh adapter; use 52 microsteps/13 optimizer updates. Inference extracts the same six logits at the same assistant next-token position for both base and candidate and applies a six-class softmax. Valid probabilities follow from the method; they do **not** demonstrate learned JSON format or calibration.

Internal progression is a predeclared development engineering guard: candidate-minus-base RPS <= 0.02 before considering a separately frozen four-group development-validation protocol. It is non-worsening tolerance, not superiority or equivalence. Evaluation targets remain isolated until both sets of predictions are sealed.

The loss audit must verify: target token cannot enter the logits used to predict itself; A–F each encode as exactly one distinct token in the actual response context; category ordering is identical in data, loss, inference and scoring; only the six selected logits enter cross-entropy; masks/padding cannot change the chosen position; fresh-base and new-adapter prompts are byte/token-identical. Stop on nonfinite logits/loss/probabilities, unknown labels, malformed context, target leakage or budget violations.

## Initial executable review

The proposed `classifier_v1.py` correctly selects causal logits at `prompt_offset - 1`, restricts the vocabulary to the ordered six class IDs, and uses the observed categorical target in mean cross-entropy. Inference uses the last initial-only prompt position and the same six logits. It additionally logs total full-vocabulary probability mass assigned to those six tokens; this helps distinguish a conditional choice distribution from unconditional generation behavior. Native training uses a fresh base, freezes it before LoRA insertion, passes `val_dataset=None`, seeds NumPy and MLX, and uses the public trainer loss callback rather than monkeypatching a module global.

The prepared split has 23 fit groups/92 people and six internal groups/24 people, with topic closure and supplied-ID separation. The reviewer independently ran the initial five preparation tests; the author subsequently added a sixth chronology regression and stated that the actual payload bytes remained unchanged. The selected final target rule is the last numeric Post Opinion, required to follow the person's finite initial-event order; this is an observed final category, not a subjective distribution.

First-pass runtime integrity findings were sent to the implementation author: active model/protocol paths must be verified as bound candidates (not only arbitrary bound files), and preparation should assert actual topic disjointness plus declared zero supplied-ID overlap. The reviewer is awaiting those changes and focused tests of the restricted loss and causal response position before final disposition.

## Final training and prediction disposition

The current implementation resolves the identified path-binding and split assertions. It verifies the active protocol against bound bytes, pins active base paths/weights to prior candidate metadata, enforces A–F ordering, and checks disjoint groups, topics and rendered identities plus zero supplied-ID overlap declared in the sealed preparation manifest. Training verifies only fit bindings; prediction verifies only initial-only prediction bindings. Neither runtime reads evaluator targets or recursively follows raw-source target bindings. The contract also binds the training-only statistical baseline and evaluator source before predictions.

Independent reviewer execution: **12 tests passed** across the six classifier tests and six data-preparation tests. Restricted-loss tests verify analytic log(6) at uniform logits, correct causal response position, gradients only on the six selected logits at that position, and invariance to large unrelated-vocabulary logits. Additional tests distinguish conditional six-class probabilities from total vocabulary mass, reject nonfinite values, verify token mapping, enforce profile allowlists, and reject changed artifacts. These tests use synthetic arrays; no model weights were loaded and no training/inference jobs were run by this reviewer.

No remaining blocking finding in the reviewed training/internal-prediction implementation. This admission is conditional on the declared coordinator watchdog deadlines (1800 seconds training, 600 seconds across the prediction pair), exact final-candidate sealing, and evaluator review before heldout outcome access. The evaluator itself is owned by the coordinator and is not certified by this source review. This is a small observed-category development classifier; neither calibration nor general behavioral fidelity is established by implementation correctness.

Reviewed file SHA-256:

- `experiments/debate-sft-replication/classifier_v1.py`: `b2fb9152fa73bc8c0f91ce5a73070783df69dd5c09650a15dbf944e95d8d1f6c`
- `experiments/debate-sft-replication/classifier-v1.protocol.json`: `b96125d7bf7b1ac6c13a425b3e1f4c2443d553620c7ba5ba1a1fbedf118dff36`
- `experiments/debate-sft-replication/test_classifier_v1.py`: `bf79eaad0f02ace29c018257d23fa9c2742236fb5e4e53dfd67d53900bdfe299`
- `scripts/prepare_debate_outcome_sft.py`: `3dc94354e68d42af7fb17b09ee797560e45c8ac62636037fc8f01cea2fd0d55b`
- `tests/test_debate_outcome_sft.py`: `cbec3524a7695c5aed9ed2583e0bba23632c46803564f0d7c46edc1f789f31f9`
