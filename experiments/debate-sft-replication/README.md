# DEBATE SFT replication preparation

Original preparation status: data preparation completed and tested in Docker; no trained model or new predictions existed at preparation time. The paper reports an 80 GB H100 and approximately 2–4 GPU-hours for one SFT run; smaller-memory adaptations are separate experiments. The current laptop was verified on 2026-10-23 as an Apple M5 MacBook Air with 24 GB unified memory and a 10-core GPU; the previous 16 GiB statement referred to an outdated hardware assumption.

## Local MLX hardware pilot

An adapted 4-bit QLoRA feasibility pilot uses `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` at revision `241a666dad6cb93c8ff213d39a7f34a36bf26db4`. It is not the authors' DEBATE checkpoint or full-weight SFT replication. Both future base and adapted comparison arms must use this same quantized base and tokenizer.

`local_mlx_preflight.py` reconstructs only the manifest-listed development examples, checks their original sealed hashes, and verifies every completion-only prompt mask against the actual tokenizer. All 831 training and 133 validation examples fit the configured 2,304-token limit (maximum observed 2,149). No truncation or evaluation-reserve access is needed.

`local-mlx-pilot.yaml` specifies 52 microsteps, batch size 1, accumulation 4 (13 optimizer updates), rank 8 on 16 layers, gradient checkpointing, and eight validation batches. This measures hardware feasibility; the partial validation loss is not a human-fidelity evaluation. `run_local_mlx_pilot.py` enforces a 30-minute wall-time cap and writes a hashed contract, training log, adapters, and completion status beneath gitignored `data/local-mlx-pilot/`.

Use the separate `.venv-mlx` environment. Once the pinned model and checksum-verified development sources are available, run from the repository root:

```sh
.venv-mlx/bin/python experiments/debate-sft-replication/local_mlx_preflight.py
.venv-mlx/bin/python experiments/debate-sft-replication/run_local_mlx_pilot.py
```

MLX runs natively on macOS. Offline Hugging Face flags prevent automatic hub access during training, but are not an operating-system network sandbox. This pilot does not claim Docker isolation, make paid provider calls, consume confirmation groups, or release a production model. Local dependency versions, hardware metadata, model revision, and data audits are retained with the pilot artifacts.

Measured result (`pilot-20261023-030458`): all 52 microsteps completed in 223.99 seconds, exit code 0, saving a roughly 40 MiB adapter. Reported eight-batch validation loss was 5.024 initially and 3.457 at the final validation checkpoint (the trainer evaluates before that iteration's update). This is a small runtime diagnostic, not a complete validation-set comparison or evidence of improved human prediction. System swap was about 2.8 GiB before loading and reached about 6.3 GiB in training samples; these are system-wide readings, not isolated model allocation measurements. The run fits operationally, but memory headroom is not yet comfortable. Do not infer a reliable full-run duration or launch confirmation from this pilot alone.

## What is ready

- 831 next-chat-message training examples from 29 previously admitted development groups.
- 133 validation examples from 4 other development groups, with no shared topics between training and validation.
- 14 of the 47 development groups excluded because a receipt could not be matched to an earlier send; no replacements. This is a stricter requirement than predicting only the final answer.
- Every example carries group and event provenance. Inputs contain the speaker's measured initial opinion and earlier observed messages, not another person's initial profile or future outcomes. Only VALID target messages supply supervision; invalid historical messages remain context if observed.
- Explicitly addressed tweets are included as context. Unknown recipients are not guessed or broadcast. Four tests check unseen-message rejection, missing receipts, invalid supervision and future-label exclusion. All pass in Docker.
- Metadata identifies 96 candidate groups across 36 topics absent from the earlier admitted development and confirmation panels. They are not an admitted evaluation cohort. Their outcomes were not opened for this preparation. Participant overlap and event-level eligibility still need auditing before freezing a cohort.
- Docker execution uses a non-root user, network disabled, read-only root, dropped capabilities, no-new-privileges, and CPU/memory/process limits. Source and permitted development inputs are baked into the image. No credential or reserve-data mount is used. The image digest and file hashes are in `preparation-seal.json`.

The published study trains against human next messages. This initial corpus uses private chat targets only and is explicitly an adaptation, not an exact reproduction of the paper's public/private outputs or full discussion protocol. An exact replication requires the original prompt pipeline, train/test identifiers, checkpoint or complete training recipe, and validation of target coverage. A generic Llama checkpoint must never be labelled DEBATE-trained.

## Controlled comparison

### Hosted development diagnostic (2026-10-23)

`scripts/run_debate_development_test.py` exercises a smaller hosted-model comparison before any new reserve admission. It uses the first manifest-listed admitted training group (four already-inspected people), GPT-4.1 mini through OpenRouter, and direct/private-reflection/generated-discussion arms. Reflection and discussion each use three recorded dyadic rounds and two synchronous passes per round. This is 60 planned calls, capped at 72 attempts including format repairs and $0.50 total. Provider-internal retries are disabled; execution is serialized.

The comparator is persistence plus a fixed Laplace-one transition model fit on the other 28 admitted training groups, excluding the selected group and topic. Repeated-person overlap is not audited, so this is development diagnosis only. Agent prompts contain initial profiles and generated histories, never real subsequent messages or final human ratings. The trusted preparation process places targets in a separate evaluator directory; each prompt worker runs without network, credentials, or data mounts. Predictions and checkpoints are sealed before evaluation. Native host broker and remote provider remain outside Docker.

Run `prepare`, `run --credentials /absolute/path/to/.env`, then `evaluate` as separate invocations of the script with the project Python and `PYTHONPATH=.:src`. Immutable inputs, per-attempt checkpoints, spending ledger, predictions and evaluation live under `data/runs/debate-development-comparison-20261023/`. No automatic promotion, significance claim, local-adapter comparison, or confirmation-cohort use follows from this single-group test.

Completed result: 60 provider requests, zero format repairs, $0.0192684 provider-reported cost. Mean RPS (lower is better): private reflection 0.102925; fixed transition 0.146322; persistence 0.200000; direct forecasting 0.204770; generated discussion 0.239250. Private reflection was best on this one development group; interaction did not improve the result. This is not a general model ranking or evidence about the locally trained adapter. All 12 final forecasts and 48 generated messages were sealed before scoring; the run did not consume a protected evaluation cohort. The new runner's synchronous/private-history test and 32 existing social/OpenRouter tests passed.

### Planned base-versus-adapted comparison

Use the same base architecture before and after SFT in both independent and interacting conditions. This 2×2 design separates training gains from interaction gains. Retain persistence and a development-fitted transition baseline. Profile enrichment remains a separate experiment. Primary scoring is individual probability error; add change/no-change calibration, population answer shares, change magnitude, group stance spread and repeated-generation variability. Fit calibration only on development data.

The provisional 20-group/80-person comparison requires 1,280 calls for one repetition under the previous compressed schedule. A faithful full-protocol simulation will need a new count. The prior authorized experiment used 1,856 of 2,000 calls ($0.5863428 provider-reported usage). No new budget has been assumed and no existing cap or ledger changed.

### Frozen-base residual calibration (2026-10-23)

The follow-up diagnostic completed all 92 local base-model forwards and ten fixed calibrator fits across five topic/person-separated folds. Equal-group out-of-fold RPS was 0.141336 for raw transition, 0.140186 for its calibrated control, and 0.140233 with base logits added. The required 0.01 gain against both comparators was not met. The workflow stopped before full-data refits or any internal readout; no outer/reserve outcomes were accessed. This is a negative development result, not an execution failure. See [the results](../../docs/RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md) and [independent audit](../../docs/RESIDUAL_CALIBRATION_RESULT_AUDIT.md). The existing statistical baseline remains the working reference.

The subsequent [data and design preparation](../../docs/DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md) preserves that exact reference and audits the 92 fitting records. It prepares a separate ANES panel study and tested development-export tools; real panel ingestion remains gated on official source archives, release alignment and cross-wave question construction. No additional neural training or reserve evaluation was launched.

## Remaining launch requirements

1. Obtain a checkpoint with documented training groups/topics, or provision a GPU backend and accessible base-model weights. No public DEBATE checkpoint was located in the author's model listing, dataset repository, paper links or benchmark site on 2026-10-22. This is a search result, not proof that none exists.
2. Finalize exact versus adapted replication; resolve remaining training settings and model license. Avoid changing architecture or quantization only in the trained arm.
3. Audit and freeze a new evaluation cohort before inspecting outcomes. Treat the earlier 29-group result as exposed development evidence from now on.
4. Smoke-test format, loss masking, data separation, runtime isolation and spending controls on development data. Freeze immutable runner source so concurrent UI edits cannot invalidate another run.
5. Reconcile a training/inference budget and execute only after the real model and backend are available. Do not substitute prompt examples for SFT and claim the same intervention.

## Sources and attribution

Chuang et al., DEBATE: A Large-Scale Benchmark for Evaluating Opinion Dynamics in Role-Playing LLM Agents, arXiv:2510.25110v7 (2026-10-19), https://arxiv.org/html/2510.25110v7, especially appendices A, J and L.
Dataset: https://huggingface.co/datasets/seantw/DEBATE_LLM
Benchmark: https://debate-benchmark.vercel.app/

This is an unofficial filtered and reformatted derivative for noncommercial research. The complete DEBATE Dataset Research-Only License is retained in `inputs/LICENSE`; it governs the inputs and resulting research models. No commercial deployment rights are assumed.
