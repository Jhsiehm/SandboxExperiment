# Prediction Sandbox

A sealed 2012 newsroom for language models.

Clone: `git@github.com:Jhsiehm/SandboxExperiment.git`

Agents are dropped into a frozen historical epoch. They may only search a
reconstructed contemporaneous corpus (`published_at` on or before the cutoff),
then they are scored on real later outcomes. They are not trained on that
corpus. Weights stay as the vendor shipped them.

**This repo is not Shortlist, not a voter-info product, and not a live
forecast leaderboard.** ForecastBench, MIRAI, FutureX, Halawi et al., and
OracleProto already cover live or near-term questions. The contribution here:

1. Deep-history epochs those benchmarks do not test.
2. Legislative and policy outcome questions.
3. A training-area **society swarm** of cheap models with explicit simulation
   personas (`config/swarm.yaml` + `config/perspectives.yaml`).

Epoch **e2012**: cutoff `2012-06-30`, resolution window through `2013-06-30`.
Fifty binary questions (20 economic, 20 legislative, 10 geopolitical). Scoring
matches ForecastBench Brier `(f − o)²` and Brier Index `(1 − √Brier) × 100`,
plus Harrell C-index (pairwise ranking of yes vs no).

Agent-loop layout follows [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety)
(`custom/envs`, `custom/agents`, `examples/e2012_forecast`). Cite Piao et al.
(arXiv:2607.11895). Do not copy their urban simulator into this repo.

## Two complementary tracks (Phase 1)

They share the frozen corpus, cutoff, sequential OpenRouter swarm, and
Brier/C-index scoring. Neither is PolicySim.

**Track A — media stimulus.** Time-locked headlines / news / media
(`published_at` ≤ cutoff) are the prompt. The swarm predicts public or
political response. We score that against **later observed history** (e2012
`ground_truth`) and against contemporaneous human/analyst thinking
(`prior_signal`). This is the “how close to historical human response”
test using media as the stimulus.

**Track B — demographic society swarm.** The same pack also contains
**surveys, ad metadata, and academic studies** as conditioners. Twelve
explicit constituency personas (`config/perspectives.yaml`: region,
urban/rural, party ID, age band, education, media diet) should react
differently to the **same headline**. Personas are labeled simulation
roles, never inferred from names or zips, and are not a scoring feature
that guesses protected class.

Roadmap (conservative): **baseline eval → yearly epoch advance → event /
response prediction → PolicySim (later).** Year-step is a hook
(`psbx epoch propose`); it does not ingest future documents. PolicySim
(constituents drafting bills that are statistically likely to pass) is
explicitly out of Phase 1.

## Status

Working today (aligned 1 September 2026):

- e2012 freeze: cutoff `2012-06-30`, resolution through `2013-06-30`, 50 binary
  questions. Brier **and** Harrell C-index.
- Dashboard at `:8765` (Minecraft enchant workshop HUD overlay). Three HUD
  buttons: **Run practice** (`config/run.yaml`, `phase1-e2012-smoke`),
  **Run live mix** (`config/run-openrouter.yaml`, six species × 1 question,
  `phase2-e2012-openrouter`), **Run swarm** (`config/run-swarm.yaml`, 12 votes
  median, `phase2-e2012-swarm-probe-container`).
- `OPENROUTER_API_KEY` is enough for live mix **and** swarm. Anthropic + OpenAI
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
- `local-*` Llama 3.1 8B / Qwen2.5 7B stay vLLM-only (`VLLM_BASE_URL`). They
  are never auto-routed onto `OPENROUTER_API_KEY`.
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

Not working yet:

- Native Claude + GPT still needs **both** `ANTHROPIC_API_KEY` and
  `OPENAI_API_KEY` (`config/run-phase2.yaml`). That path is optional; OpenRouter
  covers live mix and swarm.
- Sequential / time-to-event questions (C-index is binary ranking now; the same
  pairwise definition will cover ordered events when those items exist).
- A contamination curve that **crosses** 2024/2025 training cutoffs on this
  epoch. Every e2012 outcome is 2012–2013, so frontier configs already sit
  inside the training window. The curve code runs; this set cannot show a
  before/after split. That is still worth scoring: Brier asks whether
  percentages are honest; C-index asks whether true events rank above false
  ones. A leaked model can look excellent on ranking and mediocre on Brier.
- PolicySim (constituents drafting bills) is later. Fuller conditioner coverage
  (more pre-cutoff Gallup/Pew vintages, FEC independent-expenditure metadata
  through 2012-06-30) is still fixture work, not a live scrape.

`data/corpus` and `data/runs` are gitignored. After clone, rebuild the index
before you run. Do not commit `.env`.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

psbx corpus build --epoch e2012
PSBX_MOCK_LLM=1 psbx run --config config/run.yaml
psbx score --run phase1-e2012-smoke
psbx viewer --host 127.0.0.1 --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The page is a Minecraft
enchant workshop with a HUD overlay. With no API keys, **Run practice** (and
plain `psbx run`) uses the retrieval heuristic so the loop is exercisable.

Copy `.env.example` to `.env` when you want live models. `OPENROUTER_API_KEY`
unlocks HUD **Run live mix** and **Run swarm**. Do not commit `.env`.

## Practice / live mix / swarm / native

| | Practice | Live mix | Swarm | Native Claude+GPT |
|---|---|---|---|---|
| HUD | **Run practice** | **Run live mix** | **Run swarm** | CLI (HUD live uses this only if OpenRouter is unset) |
| Config | `config/run.yaml` | `config/run-openrouter.yaml` | `config/run-swarm.yaml` | `config/run-phase2.yaml` |
| Run id | `phase1-e2012-smoke` | `phase2-e2012-openrouter` | `phase2-e2012-swarm-probe-container` | `phase2-e2012-real` |
| Needs | Nothing | `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | Anthropic **and** OpenAI keys |
| What it measures | Keyword heuristic | Six species × 1 question | 12 votes, median `p` | Claude + GPT forecasts |

Live will not fall back to the heuristic. If keys are missing it fails loud.
If `OPENROUTER_API_KEY` is set, HUD live stays on the six-species probe even
when native vendor keys exist. Native Claude+GPT is
`psbx run --config config/run-phase2.yaml`.

OpenRouter is rate-limited in-process: 1 request / 2s, max 20/min, concurrency 1
(`OPENROUTER_MIN_INTERVAL_SEC`, `OPENROUTER_MAX_PER_MINUTE`, `OPENROUTER_MAX_CONCURRENCY`).
Completions cap at 256 tokens unless `OPENROUTER_MAX_TOKENS` is raised. On HTTP 429 the
client waits 15s then 30s and retries at most twice.

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

Needs `OPENROUTER_API_KEY`. `local-*` Llama/Qwen are not in this mix and are
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
stay on the host; they are never put inside the isolated search container.

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
different epoch.

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
exact release/version date, access mode, retrieval method, and an internal
content marker. Public, dated artifacts are checksum-pinned in
`data/corpus-cache/survey-sources/<epoch>/`; raw Pew, CSES, WVS, and ISSP data
that require an account or agreement are listed but never downloaded
automatically. This prevents a survey fielded in 2012 but released or corrected
in 2015–2019 from leaking into the e2012 environment.

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
config/          epochs, models, swarm roster, perspectives, eval tracks, run profiles
src/psbx/        CLI, index, agent loop, scoring, Docker sidecar, eval tracks
src/psbx/agents/swarm.py   sequential 12-vote median (not a stub)
src/psbx/scoring/plots.py  seaborn vote swarm / Brier bars / signed-error / violin
leaderboard/     HUD overlay on a Minecraft enchant workshop (port 8765)
leaderboard/jobs.py        Run practice / live mix / swarm button wiring
custom/          AgentSociety-shaped env + forecaster
examples/        e2012 AgentSociety 2 InitConfig + questionnaire steps
../AgentSociety  sibling clone (gh repo clone tsinghua-fib-lab/AgentSociety)
data/questions/  e2012 question set (also Track A media-stimulus items)
data/sources/    ALFRED / Congress / GDELT / Gallup / survey / ad / academic snapshots
data/corpus/     built index (gitignored)
data/runs/       predictions and scores (gitignored)
tests/
```

## Tests

```bash
pytest
```

Covers cutoff lock, 50-question e2012 set, Brier + C-index, swarm roster
(no `NotImplementedError`, local models stay vLLM-only), OpenRouter HUD
routing (`live_config_path` prefers the cheap probe), seaborn plots, Docker
clock / archive-index-only, society Track A/B, and the year-step hook.

## License

MIT (see `pyproject.toml`).
