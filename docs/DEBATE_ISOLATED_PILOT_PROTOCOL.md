# Isolated social-emulation pilot, 2026-10-14

Run: `debate-isolated-social-pilot-20261014`. Frozen before paid calls. This is an exploratory research pilot, not a population estimate, causal experiment on humans, or complete DEBATE replication.

## Question and selection

Does generated interaction improve prediction of recorded final human opinions over private reflection with the same number of model calls? Does receiving actual incoming human messages improve prediction, suggesting a possible gap in generated interaction?

Source: Chuang et al., [DEBATE v6](https://arxiv.org/abs/2510.25110v6), [dataset](https://huggingface.co/datasets/seantw/DEBATE_LLM), pinned revision `5e699a5458ec6ed776ab54e925ad33bb241fd831`.

Eight four-person groups (32 people) selected as the first two lexicographic golden/breadth files for each of four predetermined topics: government responsibility, income equality, competition, and democracy. This is a convenience selection, not a random sample or the author's official test split. Selection did not use final answer values. Topic labels use the source statement text in prompts.

## Inputs and targets

The only personal inputs are each respondent's initial private 1–6 rating and initial explanation. Exit-survey demographics are excluded because they were collected after discussion. Unknown biography stays unknown. Initial and final scale values are validated as integers from 1 to 6; the source README's simplified description is not used to truncate valid 6s.

Targets are the last valid numeric Post Opinion event by event_order. Duplicate numeric final submissions are handled with this deterministic rule. Final ratings and final explanations never enter prompts. Targets reside in a separate evaluator vault with a pre-run hash. Scoring waits for a complete sealed prediction panel. The trusted preprocessing host can access raw source data; isolation is at agent input level, not an adversarially blinded research institution.

The actual reciprocal partner schedule is reconstructed from message_sent rows, requiring one partner per round and three distinct partners overall. message_received rows are not added again. Replay sees incoming chat messages only, not the respondent's own later human statements, tweets, final explanations, or ratings.

## Conditions

| Condition | Experience | Calls per person |
|---|---|---:|
| Persistence | Predict the initial rating exactly; no fitting | 0 |
| Private | Six short private reflections, then final probability vector | 7 |
| Swarm | Three recorded dyadic rounds, two synchronous message passes per round, then private final probabilities | 7 |
| Replay | Actual incoming human chat messages, then private final probabilities | 1 |

All generated messages in a pass are collected before delivery, so sequential API order does not provide an agent extra information. Each agent sees only its own initial information, own generated history, and messages from its assigned partners in permitted rounds. No group-wide transcript or peer private profile is provided.

Private and swarm conditions match call count and maximum output allowance, not input-token count: interaction adds peer messages to context. This contrast does not isolate social information from all possible effects of additional context length. A future negative control can provide length-matched irrelevant or shuffled messages on development groups, without changing this frozen test.

Messages are prompted to be at most 60 words, with silence allowed. The parser enforces a 4,000-character safety bound rather than a 60-word hard bound; actual lengths should be audited. The human dataset used timed conversations and a tweet phase; this pilot compresses conversation to two messages per person per round and omits tweets. It does not identify effects of matching the full human interaction protocol.

Replay is a conditional diagnostic with more authentic incoming content, not a randomized causal control or a compute-matched arm. Human messages themselves were produced in response to real people. It cannot establish that replacing synthetic messages alone causes any performance difference.

## Frozen execution

One model: OpenRouter GPT-4.1 mini, temperature .4, max output 256 tokens, JSON mode. One repetition, seed 20261014 controls group arm ordering. The seed does not guarantee deterministic provider inference. 480 planned logical calls; hard request limit 1,000 and USD5 cap. Existing provider concurrency/rate settings are retained. A response-format repair is allowed once; invalid outputs are not repeatedly sampled until a desired answer appears.

Each call starts a fresh container from a frozen image ID with network none, read-only root, user10001, dropped capabilities, no-new-privileges, 32-PID/64MiB/1CPU limits, and an 8MiB noexec/nosuid temporary filesystem. No host mounts, evaluation data, API key, or Docker socket enter it. Host and container prompt construction must match. Runtime probes check identity, interfaces, write restriction, capabilities, privileges, and forbidden inputs. The host broker remains trusted and conducts remote model inference outside Docker.

Checkpoints bind permitted payload, constructed prompt, response, attempt metadata, and isolation checks. Provider errors are recorded immediately and surfaced; resumption reuses validated checkpoints. Source and dataset bindings are checked before and after execution. Predictions, transcripts, and checkpoint hashes are sealed before evaluation.

Frozen contract seal: `38fc92580b447626a227baedcca5bb8174224512f2dd7d2effae8585a1ae4535`.

## Evaluation

Primary metric: ranked probability score (RPS), the mean squared error between predicted and observed cumulative probabilities across the five thresholds of the six-category scale. Lower is better. Primary contrast: swarm minus private mean RPS.

Probabilities are elicited JSON forecasts, not measurements of an agent's internal beliefs or token likelihoods. Their usefulness is judged against human outcomes; verbal certainty is not treated as calibration evidence.

Secondary diagnostics: expected-score absolute error, signed and absolute movement, direction accuracy using the modal category, movement among actually unchanged humans, and group dispersion. Compare also to persistence. Probability-vector uncertainty and across-person heterogeneity are distinct; variance of expected scores is not a full joint-group distribution.

Use 4,000 paired bootstrap resamples of groups. Only eight groups spanning four selected topics remain a weak basis for uncertainty estimation and generalization. No person-level independence assumption is used for the primary interval, but group resampling does not account fully for topic selection. No automatic promotion is allowed from this pilot.

Interpretation rules: better swarm performance would motivate confirmation on new groups and topics, not prove universal social fidelity. Worse swarm performance rejects this particular implementation on this pilot, not every possible interaction model. Replay improvement can motivate exposure/interaction diagnostics, but does not by itself identify a causal mechanism.

## Artifacts and licensing

Implementation: `src/psbx/experiments/social_benchmark.py`, `social_worker.py`, `Dockerfile.social-worker`, `tests/test_social_benchmark.py`.

Run artifacts: `data/runs/debate-isolated-social-pilot-20261014/`. Targets: separate `data/evaluation-vault/` subtree. Original data are cached locally, not copied into source control or agent containers.

DEBATE Research-Only License (Non-Commercial v1.0) applies to the data and derivatives. Research use is permitted under its terms; commercial-product reuse is not established. Preserve attribution and license. This pilot never consumes the 50 reserved ANES IDs.

Run the phases from the project environment:

```sh
docker build -f Dockerfile.social-worker -t psbx-social-worker:local .
.venv/bin/python -m psbx.experiments.social_benchmark prepare
.venv/bin/python -m psbx.experiments.social_benchmark run
.venv/bin/python -m psbx.experiments.social_benchmark evaluate
```

Existing frozen runs require their bound image/source/input hashes, not a newly rebuilt replacement image. A clean-checkout portable replication has not been demonstrated.

The exact Linux/arm64 prompt-worker image is exported as `social-worker-image.tar.gz` in the run directory (43,086,445 bytes). Its export hash and scope are recorded in `image-export.json`; the archive OCI index matches the frozen image ID and every content-addressed blob was hash-verified. It can be restored with `docker image load -i <archive>`. This preserves the prompt-worker image, not the remote model weights or the entire host environment.
