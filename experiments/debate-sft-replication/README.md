# DEBATE SFT replication preparation

Status: data preparation completed and tested in Docker. No model has been trained, no new predictions exist, and no API requests were made. Launch is blocked by absence of a verified DEBATE checkpoint or a GPU training backend. The local machine has 16 GiB memory. The paper reports an 80 GB H100 and approximately 2–4 GPU-hours for one SFT run; smaller-memory adaptations would be separate experiments.

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

Use the same base architecture before and after SFT in both independent and interacting conditions. This 2×2 design separates training gains from interaction gains. Retain persistence and a development-fitted transition baseline. Profile enrichment remains a separate experiment. Primary scoring is individual probability error; add change/no-change calibration, population answer shares, change magnitude, group stance spread and repeated-generation variability. Fit calibration only on development data.

The provisional 20-group/80-person comparison requires 1,280 calls for one repetition under the previous compressed schedule. A faithful full-protocol simulation will need a new count. The prior authorized experiment used 1,856 of 2,000 calls ($0.5863428 provider-reported usage). No new budget has been assumed and no existing cap or ledger changed.

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
