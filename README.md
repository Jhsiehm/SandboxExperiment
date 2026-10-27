# Prediction Sandbox

An auditable, local-first research laboratory for historical forecasting,
human-response prediction, and synthetic agent populations.

Clone: `git@github.com:Jhsiehm/SandboxExperiment.git`

Prediction Sandbox tests whether language models, richer profiles, local
training, or agent discussion improve predictions of observed human outcomes.
Each comparison retains statistical controls, saved predictions, source
provenance, costs, and an explicit boundary between development and evaluation.
Recent work spans ANES survey responses, DEBATE opinion changes, local MLX
adapter training, and a reconstructed Oregon Medicaid enrollment benchmark.

The original forecasting environment remains epoch **e2012**: cutoff `2012-06-30`, resolution
window through `2013-06-30`, and 50 binary economic, legislative, and
geopolitical questions. Scoring includes Brier probability error, a derived
forecast score, calibration views, and Harrell C-index ranking.

That forecasting track freezes the searchable evidence and clock around the
model. Behavioral studies use their own cohort, information, and evaluation
contracts; they do not inherit the e2012 cutoff. Local training experiments
explicitly change adapter weights and compare them with the base model.

## Research update · 27 October 2026

**The tested training and discussion additions have not established a useful
improvement over their controls.** Direct prediction had the lowest RPS point
estimate in the larger DEBATE comparison, but discussion performed worse.
Learning discussion language did not establish better belief prediction.

The latest saved behavioral experiments are from **23 October**. The October 27
update compiled and verified the research record without new paid runs.

- **DEBATE discussion comparison:** 116 people in 29 groups. Direct prediction
  scored RPS **0.11512**, transition control **0.13029**, and generated discussion
  **0.14671**. Discussion incorrectly changed the modal answer for 28 of 58 people
  whose actual answers stayed stable. These are now-inspected development
  results, with a documented source-integrity recovery.
  [Comparison and limitations](reports/social-comparison-audit-20261022/FINDINGS.md).
- **Local message training:** a four-bit Llama 3.1 8B adapter completed 13
  optimizer updates on a 24 GB M5 MacBook Air. Validation message loss improved
  **3.6280 → 3.2011 nats/token** across 133 messages in four groups, but the
  adapter failed its first direct-belief output. Belief accuracy was not scored
  and interaction testing stopped.
  [Matched comparison](docs/LOCAL_MATCHED_COMPARISON_2026-10-23.md).
- **Categorical prediction and calibration:** a fresh classifier produced valid
  probabilities but scored RPS **0.21605**, worse than the base model's **0.18457**
  and transition control's **0.12472** on 24 internal-evaluation participants.
  It overpredicted opinion change. A separate five-fold diagnostic on 92 fitting
  participants found no useful gain from adding frozen-model logits to calibrated
  transition probabilities. Both progression gates failed.
  [Classifier](docs/CLASSIFIER_PILOT_RESULTS_2026-10-23.md) ·
  [Calibration](docs/RESIDUAL_CALIBRATION_RESULTS_2026-10-23.md).
- **ANES profiles:** the 120-person profile ablation did not beat the party-based
  statistical baseline. Its half-multiclass Brier was **0.22087**, versus **0.23184**
  for the best direct-model profile and **0.22235** for the best hybrid.
  The separate 50-person reserve remained excluded.
  [Profile ablation](docs/ANES_PROFILE_ABLATION_RESULTS.md).
- **Oregon Medicaid:** reconstructed two published enrollment results using
  **74,922 people in 66,385 households**, passing all six rounding checks.
  Household-separated statistical prediction improved Brier **0.167696 → 0.164220**.
  Agent performance on this benchmark remains untested.
  [Reproduction and baseline](reports/behavior-feasibility-20261022/baseline/README.md).

Lower scores indicate less error, but RPS, message loss, and the different Brier
scales are not interchangeable. These retrospective development studies do not
establish prospective forecasting performance or a validated policy simulator.

Start with the [October research summary](docs/RESEARCH_LOG_2026-10-27.md).
The [complete research log](docs/RESEARCH_LOG.md) indexes **31 studies**, including
earlier Ohio work, costs, stopped runs, limitations, and next steps. Its
[machine-readable register](reports/research-register-20261027/experiment-ledger.json)
is backed by an [84-source inventory](reports/research-register-20261027/source-inventory.json).
Some underlying artifacts remain local or in parallel checkouts; the register
records their locations and does not imply that a clone contains every dataset.

## What comes next

1. **Resolve ANES panel provenance and measurement.** The proposed design develops
   seven-category party-identification transitions on 2016→2020, then evaluates
   2020→2024. Five source and construction blockers remain; raw panel ingestion,
   training, and later-cohort evaluation have not started.
   [Readiness report](docs/ANES_PANEL_METADATA_READINESS.md).
2. **Freeze the next comparison before inspecting another cohort.** Retain
   persistence and transition controls, measure change/no-change calibration,
   and require a defined predictive gain before expanding training or discussion.
   [Data and design plan](docs/DATA_AND_DESIGN_NEXT_STEPS_2026-10-23.md).
3. **Define the Oregon agent comparison.** Resolve the pre-event feature set and
   lottery-batch cutoffs before testing agents against the statistical reference.
   Reproducing enrollment effects alone does not validate simulated behavior.

The immediate research priority is predicting stability and establishing
comparable data and baselines before scaling the agent population.

## What this repository is now

The research workbench includes local adapter training and evaluation scripts,
participant admission audits, calibration protocols, a study register, and a
viewer for aggregate experiment progress and saved discussion recordings.
The underlying forecasting platform has six cooperating systems:

| System | What it does today |
|---|---|
| Frozen evidence world | Builds cutoff-checked combined and source-specific corpora from registered fixtures, dated archives, and optional bounded ingest. Agents cannot browse the live web during a run. |
| Forecast engines | Runs an offline practice heuristic, direct provider models, fixed benchmark personas, or a sequential multi-model swarm whose individual ballots and aggregate forecast are retained. |
| Population laboratory | Builds deterministic weighted synthetic populations, validates their marginals, compresses them into representative cells, and measures agent-count convergence separately from behavioral validity. |
| Election and demographic comparison | Catalogs and imports election results and Census comparison layers outside model runtime, with explicit vintage, geography, checksum, and access-state metadata. |
| Scoring and safeguards | Scores comparable question sets against later truth, verifies citation document IDs and literal quotations, reports descriptive declared-cutoff gaps, fingerprints resumable runs, and enforces paid-model request, token, origin, and dollar limits. |
| Local research console | Serves a tactical U.S. World Model, run controls, agent traces, results, population evidence, and an Arena leaderboard for agents, swarms, model families, and corporations. |

The evidence chain is the product: source date → frozen index → run manifest →
agent ballot → swarm aggregate → later ground truth → score. Missing,
source-only, synthetic, validated, comparison-only, and runtime-accessible states
remain separate throughout that chain.

## Current vision

Near term, Prediction Sandbox is testing whether evidence, profile construction,
local training, calibration, and interaction improve individual predictions over
strong statistical controls. Historical forecasting and population construction
remain supporting tracks. The goal
is not merely to produce a winning percentage; it is to expose why a result was
possible, what information the agent could access, how much evidence supports
the ranking, and where uncertainty enters the system.

The longer-term direction is a carefully validated policy-simulation research
environment, but only after multi-epoch forecasting, population fidelity,
aggregate behavior validation, and convergence tests are credible. PolicySim is
therefore a later phase rather than a claim of the current codebase.

**This is not a voter-information product, a live election predictor, a
microtargeting system, or a model of identifiable people.** Synthetic people
are statistical constructions, benchmark personas are explicit simulation
roles, and election/Census layers are evaluation or display inputs unless a run
contract explicitly and safely says otherwise. See
[`PRODUCT.md`](PRODUCT.md), [`docs/USE_CASES_AND_BOUNDARIES.md`](docs/USE_CASES_AND_BOUNDARIES.md),
and [`docs/DATA_GOVERNANCE.md`](docs/DATA_GOVERNANCE.md).

Agent-loop layout follows [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety)
(`custom/envs`, `custom/agents`, `examples/e2012_forecast`). Cite Piao et al.
(arXiv:2607.11895). The sibling platform remains external; its urban simulator
is not vendored into this repository.

## Historical forecasting tracks (original Phase 1)

They share the frozen corpus, cutoff, sequential OpenRouter swarm, and
Brier/C-index scoring. Neither is PolicySim.

**Track A — media stimulus.** Time-locked headlines / news / media
(`published_at` ≤ cutoff) are the prompt. The swarm predicts public or
political response. We score that against **later observed history** (e2012
`ground_truth`) and against contemporaneous human/analyst thinking
(`prior_signal`). This is the “how close to historical human response”
test using media as the stimulus.

**Track B — demographic society swarm.** The same pack also contains
**surveys, ad metadata, and academic studies** as conditioners. The twelve
explicit constituency personas (`config/perspectives.yaml`: region,
urban/rural, party ID, age band, education, media diet) remain fixed golden
benchmarks; they are not presented as a statistically sampled township. A
separate offline population pipeline can construct and validate weighted
synthetic people and representative cells before any behavior simulation.
Personas are labeled simulation roles, never inferred from names or zips, and
are not a scoring feature that guesses protected class.

Roadmap (conservative): **baseline eval → yearly epoch advance → event /
response prediction → PolicySim (later).** Year-step is a hook
(`psbx epoch propose`); it does not ingest future documents. PolicySim
(constituents drafting bills that are statistically likely to pass) is
explicitly out of Phase 1.

## Forecasting platform capabilities

The original e2012 platform provides the following capabilities. The research
update above reports the newer behavioral experiments separately.

- e2012 freeze: cutoff `2012-06-30`, resolution through `2013-06-30`, 50 binary
  questions. Brier **and** Harrell C-index.
- Dashboard at `:8765` (tactical U.S. World Model and experiment console). Three
  buttons: **Run practice** (`config/run.yaml`, `phase1-e2012-smoke`),
  **Run live mix** (`config/run-openrouter.yaml`, six species × 1 question,
  `phase2-e2012-openrouter`), **Run swarm** (`config/run-swarm.yaml`, 12 votes
  median, `phase2-e2012-swarm-probe-container`).
- Arena leaderboard with evidence-backed views for individual agents, scored
  swarm runs, model families, and corporations. Rankings retain Brier error,
  hit rate, forecast count, per-run winners, and links to saved result logs;
  sample size remains visible beside the game-like presentation.
- `OPENROUTER_API_KEY` plus the deliberate `PSBX_ENABLE_PAID_MODELS=1` switch
  enables live mix **and** swarm. Anthropic + OpenAI
  are only for optional native Claude+GPT (`config/run-phase2.yaml`). If
  OpenRouter is set, HUD live stays on the cheap probe even when native keys
  exist. HUD live uses native only when OpenRouter is unset and both vendor
  keys are present.
- Sequential swarm is **real**. `src/psbx/agents/swarm.py` has no
  `NotImplementedError`. Shared retrieval, 12 sequential OpenRouter votes
  (2 × each of `openai/gpt-4.1-mini`, `openai/gpt-4o-mini`,
  `anthropic/claude-3-haiku`, `google/gemini-2.5-flash-lite`,
  `meta-llama/llama-3.1-8b-instruct`, `qwen/qwen-2.5-7b-instruct`), median
  `swarm-median`, votes in `swarm_votes.jsonl`. Rate limit 1 req / 2s, 20/min,
  concurrency 1, `max_tokens` 256. A full 12×50 pass is hours — keep `--limit 1`.
- In the forecasting runner, `local-*` Llama 3.1 8B / Qwen2.5 7B use vLLM (`VLLM_BASE_URL`). They
  are never auto-routed onto `OPENROUTER_API_KEY`.
  The separate DEBATE training scripts use native MLX on Apple Silicon.
- Seaborn charts on Results: vote swarm vs later truth / median / 2012 prior,
  Brier bars by species, signed-error lollipops. Practice (≥8 questions) also
  gets a per-question Brier violin. `psbx score` writes the same PNGs next to
  the run.
- Mock pipeline (retrieval heuristic, no API keys). Docker search sidecar:
  clock frozen at 2012-06-30, outbound traffic dropped. Viewer search is the
  same index (`GET /archive?url=` returns 200 only if that URL is already in
  the frozen index).
- Wayback ingest at **index-build** time only (`to=20120630`). Not the
  CC-MAIN-2012 HTML dump (legacy ARC) and not CC-MAIN-2013-20 (after cutoff).
  No live origin fetch at query time.
- Society Track A (media stimulus) + Track B (personas + survey/ad/academic
  fixtures), `psbx eval baseline`, `psbx epoch propose` (no future ingest),
  `psbx society export` to an AgentSociety 2 sibling clone (`../AgentSociety`).
  PolicySim is later.
- Offline Track B population foundation: cutoff-aware source registry,
  deterministic synthesis, exact integerization, marginal validation, weighted
  representative-cell compression, separate reasoning budgets, and held-out
  aggregate behavior evaluation. The bundled fixture is synthetic and does not
  select or claim to represent a real place.
- ANES 2012 silicon-society protocol: full 998-specification pre/post questionnaire inventory,
  target-vault split, independent-versus-conversation treatment, sealed provider-free pilot, and
  an explicit audit showing that the older Docker mode isolates retrieval rather than the host-side
  model process. See [`docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md`](docs/ANES_2012_SILICON_SOCIETY_PROTOCOL.md).
- The official FEC 2012 legacy workbook now normalizes 2,033 candidate rows across 524
  presidential, U.S. Senate, and U.S. House general-election contests. State-legislative and local
  election coverage still requires jurisdiction-specific adapters and is not claimed complete.

Remaining forecasting limitations and setup requirements:

- Native Claude + GPT still needs **both** `ANTHROPIC_API_KEY` and
  `OPENAI_API_KEY` (`config/run-phase2.yaml`). That path is optional; OpenRouter
  covers live mix and swarm.
- Sequential / time-to-event questions (C-index is binary ranking now; the same
  pairwise definition will cover ordered events when those items exist).
- A causal contamination claim from declared model cutoff dates. The cutoff-gap
  chart is descriptive metadata analysis only; it cannot establish training
  membership, leakage, retrieval use, or causality. Use the paired evidence
  experiment for bounded no-evidence, authenticated-evidence, and shuffled-pack
  contrasts.
- PolicySim (constituents drafting bills) is later. Fuller conditioner coverage
  (more pre-cutoff Gallup/Pew vintages, FEC independent-expenditure metadata
  through 2012-06-30) is still fixture work, not a live scrape.

`data/corpus` and `data/runs` are gitignored. After clone, rebuild the index
before you run. Do not commit `.env`. To continue with the same downloaded
sources, generated populations, and experiment history on another machine, use
the checksum-verified workflow in
[`docs/WORKSPACE_MIGRATION.md`](docs/WORKSPACE_MIGRATION.md).

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

psbx practice status --epoch e2012
psbx practice prepare --epoch e2012
psbx sandbox up --epoch e2012
PSBX_MOCK_LLM=1 psbx run --config config/run.yaml
psbx score --run phase1-e2012-smoke
psbx viewer --host 127.0.0.1 --port 8765

# Provider-free ANES experiment plumbing (requires local public source files).
psbx experiment anes-pilot \
  --config config/anes2012-society.yaml \
  --input data/survey-microdata/anes/2012/source/full_results_2012_2.csv \
  --paper-baseline-input \
    data/survey-microdata/anes/2012/source/full_results_2012_2.csv
psbx experiment anes-doctor
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The page is a local tactical
workbench with a 3D U.S. geography model and evidence inspector. With no API
keys, plain `psbx run` uses the retrieval heuristic. The dashboard keeps **Run
practice** disabled until the generated corpus exists and the sidecar reports
the selected epoch, scope, frozen clock, and isolation controls. `psbx practice
prepare` builds deterministic local assets and makes zero provider calls.

The viewer is intentionally local-only and rejects wildcard or remote bind
addresses because it has no user-account layer. Put an authenticated reverse
proxy in front of a separate deployment before adding remote access. Browser
state changes also require a same-origin, non-simple request header.

Copy `.env.example` to `.env` when you want live models. A provider key alone
cannot send paid traffic: set `PSBX_ENABLE_PAID_MODELS=1` only for an intentional
live session. Do not commit `.env`.

## Practice / live mix / swarm / native

| | Practice | Live mix | Swarm | Native Claude+GPT |
|---|---|---|---|---|
| HUD | **Run practice** | **Run live mix** | **Run swarm** | CLI (HUD live uses this only if OpenRouter is unset) |
| Config | `config/run.yaml` | `config/run-openrouter.yaml` | `config/run-swarm.yaml` | `config/run-phase2.yaml` |
| Run id | `phase1-e2012-smoke` | `phase2-e2012-openrouter` | `phase2-e2012-swarm-probe-container` | `phase2-e2012-real` |
| Needs | Prepared corpus + sealed sidecar | Authenticated corpus + sealed sidecar + OpenRouter key + paid switch | Authenticated corpus + sealed sidecar + OpenRouter key + paid switch | Authenticated corpus + sealed sidecar + Anthropic + OpenAI keys + paid switch |
| What it measures | Keyword heuristic | Six species × 1 question | 12 votes, median `p` | Claude + GPT forecasts |

Live will not fall back to the heuristic. If keys are missing it fails loud.
If `OPENROUTER_API_KEY` is set, HUD live stays on the six-species probe even
when native vendor keys exist. Native Claude+GPT is
`psbx run --config config/run-phase2.yaml`.

The causal evidence comparison is a separate paired protocol:

```bash
PSBX_MOCK_LLM=1 psbx experiment evidence \
  --config config/evidence-experiment.yaml --limit 2
```

Each model/question/replication unit receives the same call, token, and
temperature budget under no factual evidence, matched authenticated evidence,
and a shuffled eligible pack. Assignments, pack hashes, observations, and
question-cluster bootstrap intervals are persisted under the experiment run ID.
The manifest also fingerprints the rendered prompts, tool protocol, and execution
source; a resume refuses protocol drift. Failed attempts are retained in
`failures.jsonl` and reported separately from completed paired observations.
The configured random seed controls condition assignment and cluster bootstrap,
not provider sampling determinism.
The mock form validates mechanics only; research conclusions require declared
live models and authenticated corpus material.

OpenRouter is rate-limited in-process: 1 request / 2s, max 20/min, concurrency 1
(`OPENROUTER_MIN_INTERVAL_SEC`, `OPENROUTER_MAX_PER_MINUTE`, `OPENROUTER_MAX_CONCURRENCY`).
Completions cap at 256 tokens unless `OPENROUTER_MAX_TOKENS` is raised. On HTTP 429 the
client waits 15s then 30s and retries at most twice.

Rate limits are paired with independent spending controls. Every live run is
preflighted, every paid request reserves a conservative maximum cost before
network I/O, and `data/runs/<run-id>/spend_ledger.json` records estimates and
provider-reported usage without prompts or credentials. Defaults are 100 paid
requests, $0.10/request, $1/run, and 16,000 conservative input tokens/request
(`PSBX_MAX_PAID_REQUESTS`, `PSBX_MAX_REQUEST_USD`, `PSBX_MAX_RUN_USD`,
`PSBX_MAX_INPUT_TOKENS`). Invalid settings fail closed. OpenRouter requests also
send a provider price ceiling, require supported parameters, prefer the cheapest
eligible route, and reject data-collection routes. Configure a separate hard
limit on the provider API key and disable automatic top-ups; the local dollar
guard uses checked-in price metadata and is intentionally an estimate.
See `docs/COST_AND_SECURITY_GUARDRAILS.md` for per-run request/token projections, enforced
boundaries, and residual risks.

Paid credentials are pinned to official HTTPS origins. Custom paid-provider
proxies are refused unless `PSBX_ALLOW_CUSTOM_PROVIDER_BASE_URL=1`; local vLLM
remains loopback-only. Model-generated search queries, result counts, and fetch
IDs are bounded before they reach the frozen index.

Cheap OpenRouter probe (one question across the planned low-end mix; do not omit
`--limit` on bigger configs). Dashboard **Run live mix** uses this. It does
**not** expand the 12-agent mix:

```bash
psbx run --config config/run-openrouter.yaml --limit 1
```

Real swarm (12 sequential votes, shared retrieval, median `p`). Default is one
question. A full 12×50 pass at `OPENROUTER_MIN_INTERVAL_SEC=2` is hours:

```bash
psbx run --config config/run-swarm.yaml --limit 1
```

Needs `OPENROUTER_API_KEY` and `PSBX_ENABLE_PAID_MODELS=1`. `local-*` Llama/Qwen are not in this mix and are
never auto-routed onto that key. Scorer reads `swarm-median`; per-agent votes
are `data/runs/phase2-e2012-swarm-probe-container/swarm_votes.jsonl`.

## Training-area society swarm (Phase 1)

Rebuild the index so survey/ad/academic fixtures are searchable, then run the
12-persona swarm (mock first). Headlines are the stimulus; conditioners are
in the same cutoff-locked pack.

```bash
psbx corpus build --epoch e2012
PSBX_MOCK_LLM=1 psbx society run --config config/run-society-swarm-mock.yaml --limit 1
psbx eval baseline --run phase1-e2012-society-swarm-mock-container
psbx epoch propose --from e2012 --years 1
```

Live (serialized OpenRouter, `allow_mock: false`):

```bash
psbx society run --config config/run-society-swarm.yaml --limit 1
psbx eval baseline --run phase2-e2012-society-swarm-container
```

Personas: `config/perspectives.yaml` (add a persona to expand the catalog;
slots 0–11 zip onto the 12 bodies). Eval config: `config/eval-baseline.yaml`.
Year-step: `config/epoch-advance.yaml` — **does not** load 2013+ documents.

Still needed for a fuller conditioner set (fixtures, not live scrape): more
pre-cutoff Gallup/Pew vintages, FEC independent-expenditure metadata through
2012-06-30, and attributed academic summaries. Do not ingest respondent
microdata, ad creative, or full papers. PolicySim is later.

## Track B population foundation

Run the deterministic offline fixture before configuring any real geography or
live model work:

```bash
psbx population plan --config config/track_b_fixture.yaml
psbx population build --config config/track_b_fixture.yaml
psbx population validate \
  --config config/track_b_fixture.yaml \
  --population data/population/e2012/fixture-township-e2012/synthetic_people.csv
```

The build writes a checksum-pinned manifest, source decisions, synthetic-person
records, representative cells, raking history, and a validation report under
`data/population/`. That directory is ignored because these are generated
artifacts. See `docs/TRACK_B_ARCHITECTURE.md`, `docs/DATA_GOVERNANCE.md`, and
`docs/USE_CASES_AND_BOUNDARIES.md` before replacing fixtures with controlled
data. Real source artifacts require verified release dates and local checksums;
post-cutoff evaluation targets stay outside population-building and runtime
zones. This phase does not make live LLM population calls.

Plan the cutoff-safe state, D.C., and national Census input pack, then explicitly
execute the resumable download:

```bash
psbx population sync-census
psbx population sync-census --execute --workers 4
psbx population verify-census
```

The sync uses official Census bulk files rather than the modern API, so it does
not require or persist an API key. It downloads selected ACS summary sequences,
2010 demographic profiles, CVAP, and state-level person and housing PUMS files.
The national PUMS donor pool is the exact union of the state and D.C. files,
avoiding a redundant national download.

## Election and electoral-demography layers

Election/Census comparison layers are cataloged separately from the frozen agent runtime. They
can be selected in a run manifest for display and evaluation, but the server marks them
`runtime_access: false` and never inserts them into model prompts or retrieval.

```bash
psbx elections plan --start-year 1982 --through-year 2026 --as-of 2026-09-14
psbx elections sync-federal --years 2022 --execute
psbx elections import-fec \
  --workbook data/elections/raw/federal/2022/federalelections2022.xlsx \
  --year 2022 --source-release-date 2026-09-14 --cutoff 2026-09-14 \
  --dataset-id fec-federal-2022 \
  --label "Official FEC federal general results · 2022"
psbx elections sync-census --year 2024 --states all --levels all
```

These commands make no model calls. Federal source download and modern Census electoral-
geography execution are opt-in; the latter requires `CENSUS_API_KEY` and defaults to a 350-
request hard limit. See `docs/ELECTION_DATA_PIPELINE.md` for source coverage, canonical result
fields, district-vintage requirements, and the state/local adapter roadmap.

## AgentSociety 2 (sibling clone)

This repo already uses the AgentSociety 2 **module layout** (`custom/envs`,
`custom/agents`). The full platform is cloned beside this project, not copied in:

```bash
# already present as ../AgentSociety after `gh repo clone tsinghua-fib-lab/AgentSociety`
export PSBX_AGENTSOCIETY_ROOT="$(cd ../AgentSociety && pwd)"
psbx society export --config config/run-society-swarm.yaml --limit 1
```

That writes 12 `agent_0001`…`agent_0012` workspaces, `init_config.json`, and a
questionnaire `steps.yaml` under `data/runs/phase2-e2012-society-swarm-container/society/`.
Search still goes through `FrozenEpochEnv`. Votes still use serialized OpenRouter
(`config/swarm.yaml`: 2× mini, 4o-mini, Haiku, Flash-Lite, Llama 3.1 8B, Qwen 2.5 7B).
We do not vendor their city simulator.

Non-swarm society scaffolding (heuristic models, not the 12-vote median):

```bash
PSBX_MOCK_LLM=1 psbx society run --config config/run-society.yaml --limit 1
```

Optional live AgentSociety CLI (Python 3.11–3.13, Ray, `AGENTSOCIETY_LLM_API_KEY`).
Commented on purpose — do not dump AgentSociety source here:

```bash
pip install -e "../AgentSociety/packages/agentsociety2"
export WORKSPACE_PATH="$(pwd)"
export AGENTSOCIETY_LLM_API_KEY="$OPENROUTER_API_KEY"
export AGENTSOCIETY_LLM_API_BASE=https://openrouter.ai/api/v1
export AGENTSOCIETY_LLM_MODEL=openai/gpt-4.1-mini
# python -m agentsociety2.society.cli \
#   --config examples/e2012_forecast/init_config.json \
#   --steps examples/e2012_forecast/steps.yaml \
#   --run-dir data/runs/phase2-e2012-society-swarm-container/society
```

Search does not use those keys. Keys are only for the model APIs. Vendor calls
stay on the host; provider keys are excluded from both the Docker search
container and the less-isolated host-side fallback. Dashboard model jobs receive
only an explicit allowlist of supported provider settings, not the full parent
environment. For shared deployments, supply those settings through an OS or
deployment secret manager rather than a plaintext `.env` file.

## Frozen search (Docker)

[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) is
required for the isolated sidecar. Search publishes `http://127.0.0.1:8766`.
libfaketime ([wolfcw/libfaketime](https://github.com/wolfcw/libfaketime.git),
distro package inside the image) freezes the clock at the epoch cutoff.
iptables drops outbound packets. The runtime root filesystem is read-only;
the corpus and config mounts are read-only; and the search service runs as an
unprivileged user with no effective capabilities and `no-new-privileges`.
Docker Desktop on Mac cannot bind-mount a Unix socket or publish ports on
`--network none`, so the sidecar exposes only the loopback port and installs
the egress firewall before dropping privileges.

```bash
psbx sandbox up --epoch e2012
psbx sandbox clock          # today should be 2012-06-30
PSBX_MOCK_LLM=1 psbx run --config config/run-sandbox.yaml
psbx sandbox down
```

Every build also writes one index per source type under
`data/corpus/<epoch>/silos/<source-type>`. Select a cell explicitly when an
experiment should see only one kind of evidence:

```bash
psbx corpus silos --epoch e2012
psbx sandbox up --epoch e2012 --source-type survey
curl http://127.0.0.1:8766/health
```

The Docker container bind-mounts only that exact cell at the configured epoch
path; sibling source types and other epoch indexes are not mounted. Add the
same selection to the run YAML so the harness can fail closed if the sidecar
does not match:

```yaml
epoch: e2012
source_type: survey
sandbox_mode: container
```

Omit `source_type` (and `--source-type`) for the combined index. A run pointed
at `e2012/survey` will refuse to start against `e2012/news`, `e2012/all`, or a
different epoch or cutoff. Resumable runs also record `provenance.json`, which
fingerprints the run config, question set, model and persona inputs, corpus,
and embeddings. Existing isolated outputs are reused only when that fingerprint
still matches.

Viewer / HUD stays on **8765**. Search sidecar is **8766**. Without Docker,
search stays in-process (`sandbox_mode: host`). The prompt still injects the
cutoff; the index still hard-filters. `GET /archive?url=` is the frozen index
only — 200 if that URL is already indexed with `published_at <= cutoff`, 404
otherwise. No live web at query time.

## Corpus

The e2012 library is **Wayback Machine snapshots with `to=20120630`**, plus in-repo
seeds, dated Wikipedia fixtures, and optional GDELT. It is **not** the
[CC-MAIN-2012 HTML dump](https://data.commoncrawl.org/crawl-data/CC-MAIN-2012/index.html)
(legacy ARC, “check back later”) and **not** CC-MAIN-2013-20 (captures May–June 2013).

```bash
psbx corpus build --epoch e2012
# Grow the 2012 library this week (Wayback only; paced; bounded):
# export PSBX_IA_USER_AGENT_SUFFIX="your-project"
psbx corpus build --epoch e2012 --live --max-docs 400
```

`--live` uses User-Agent `PredictionSandbox/0.1.0 (psbx; corpus-builder)`,
5s pacing, and 429 / Retry-After. Default `--max-docs` is 400 (hundreds, not
unbounded). Re-run the same command to resume: snapshots cache under
`data/corpus-cache/wayback/`. Wayback ingest is **index-build only**.

Optional local WARCs (or a converted ARC slice) can be dropped in
`data/corpus-cache/commoncrawl/` and dated wiki JSONL in
`data/corpus-cache/wikipedia/` — ingested offline. Do not ingest CC-MAIN-2013-20
into e2012.

The fixture seed (news/gov plus survey/ad/academic snapshots) is enough to
exercise the 50-question smoke and the training-area conditioner tools.

The directory structure is a two-dimensional isolation grid:

```text
data/corpus/
  e2012/
    documents.jsonl             # combined index
    silos/
      news/                     # e2012 + news only
      survey/                   # e2012 + survey only
      academic/                 # e2012 + academic only
      ...
  e2013/                        # created after e2013 is configured and built
```

Each entry in `config/epochs.yaml` supplies the epoch cutoff and its own corpus
path. Only `e2012` is populated today; adding a later epoch requires its dated
source material and question set before `psbx corpus build --epoch <id>`.

List the configured years, preview the survey download plan, or sync every
configured year:

```bash
psbx epoch list
psbx corpus sync-surveys --epoch e2012 --provider all --plan
psbx corpus sync-surveys --all-epochs --provider all --rebuild
```

The survey registry is `config/survey_sources.yaml`. It records fieldwork range,
exact release/version date, access mode, retrieval method, an internal content
marker, and a release checksum. Direct public artifacts must match that
checked-in SHA-256 before they are cached or indexed. Public, dated artifacts
are cached in `data/corpus-cache/survey-sources/<epoch>/`; raw Pew, CSES, WVS,
and ISSP data that require an account or agreement are listed but never
downloaded automatically. This prevents a survey fielded in 2012 but released
or corrected in 2015–2019 from leaking into the e2012 environment.

## Design constraints

1. **No future leakage through search.** Index contains only
   `published_at <= cutoff`. Checked at build and again at query time.
2. **No future leakage through the clock.** Prompt injects the frozen date;
   the sidecar also fakes wall-clock time.
3. **No live web for the agent.** Search is the local index, not the 2026
   internet. `GET /archive?url=` does not fetch origin.
4. **Contamination is measured, but e2012 cannot split on 2024/2025 cutoffs.**
   Every model declares a pretraining cutoff; the curve code runs. Every
   outcome here is 2012–2013, so frontier models already sit inside the
   training window.
5. **Citations required.** Uncited or non-supporting spans are flagged.
6. **Reproducible.** Questions, source snapshots, and scoring are in-repo.
   Built indices and run folders stay gitignored.

## Layout

```
config/          epochs, sources, models, swarms, population/election registries, run profiles
src/psbx/        CLI, corpus, agents, scoring, population, elections, society, security
src/psbx/agents/swarm.py   sequential 12-vote median (not a stub)
src/psbx/scoring/plots.py  seaborn vote swarm / Brier bars / signed-error / violin
leaderboard/     tactical World Model, Arena leaderboard, experiment console, local APIs
leaderboard/jobs.py        Run practice / live mix / swarm button wiring
experiments/debate-sft-replication/  local MLX training, protocols, and focused tests
scripts/         participant audits, development evaluation, calibration, register verification
reports/         saved aggregate findings, provenance, readiness, and study register
custom/          AgentSociety-shaped env + forecaster
examples/        e2012 AgentSociety 2 InitConfig + questionnaire steps
../AgentSociety  sibling clone (gh repo clone tsinghua-fib-lab/AgentSociety)
data/questions/  e2012 question set (also Track A media-stimulus items)
data/sources/    ALFRED / Congress / GDELT / Gallup / survey / ad / academic snapshots
docs/            architecture, governance, dashboard, election, security, and use boundaries
data/corpus/     built index (gitignored)
data/population/ generated population artifacts (gitignored)
data/elections/  downloaded/imported election artifacts (gitignored)
data/runs/       predictions and scores (gitignored)
data/local-mlx-pilot/  local training and inference artifacts (gitignored)
tests/
```

## Tests

```bash
ruff check .
pytest -q
python -m compileall -q src leaderboard
node --check leaderboard/static/app.js
node --check leaderboard/static/geography-map.js
node --check leaderboard/static/research.js
node --check leaderboard/static/research-live.js
```

The offline suite covers the cutoff lock, 50-question e2012 set, Brier and
C-index scoring, per-run leaderboard attribution, swarm routing, population
synthesis/validation/convergence, Census and election adapters, spending and
security boundaries, plots, Docker clock and archive-only search, society
tracks, the year-step hook, and wheel contents including dashboard static
assets. GitHub Actions runs Ruff, the complete test suite, and whitespace checks
without provider credentials or paid-model access.

Behavioral research checks also cover participant admission, local comparison
boundaries, outcome-classifier evaluation, residual calibration, panel readiness,
and research-viewer navigation. MLX-dependent tests under
`experiments/debate-sft-replication/` require the separate Apple Silicon MLX
environment and are outside the default `tests/` collection.

Before the October 27 research commit, 475 offline tests and 16 additional
MLX-dependent tests passed. The research register passed 417 checks across 31
studies and 84 indexed sources. These counts describe that checkout and test
selection; they are software and record-consistency checks, not new experiments.
To verify the register in a workspace containing its recorded local artifacts:

```bash
python scripts/verify_research_log.py
```

That verifier needs the source paths and saved outputs recorded in the inventory;
it is not a fresh-clone check and does not call a model provider.

## License

MIT (see `pyproject.toml`).
