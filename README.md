# Prediction Sandbox

A sealed 2012 newsroom for language models.

Agents are dropped into a frozen historical epoch. They may only search a
reconstructed contemporaneous corpus (`published_at` on or before the cutoff),
then they are scored on real later outcomes. They are not trained on that
corpus. Weights stay as the vendor shipped them.

**This repo is not Shortlist, not a voter-info product, and not a live
forecast leaderboard.** ForecastBench, MIRAI, FutureX, Halawi et al., and
OracleProto already cover live or near-term questions. The contribution here:

1. Deep-history epochs those benchmarks do not test.
2. Legislative and policy outcome questions.
3. Later: single-agent vs swarm (`config/swarm.yaml`: 8 mini + 4 Haiku, sequential median).

Epoch **e2012**: cutoff `2012-06-30`, resolution window through `2013-06-30`.
Fifty binary questions (20 economic, 20 legislative, 10 geopolitical). Scoring
matches ForecastBench Brier `(f − o)²` and Brier Index `(1 − √Brier) × 100`,
plus Harrell C-index (pairwise ranking of yes vs no).

Agent-loop layout follows [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety)
(`custom/envs`, `custom/agents`, `examples/e2012_forecast`). Cite Piao et al.
(arXiv:2607.11895). Do not copy their urban simulator into this repo.

## Status

Working today:

- Question set, seed corpus, cutoff-filtered search, Brier + C-index scoring, dashboard.
- Mock pipeline (retrieval heuristic, no API keys).
- Docker search sidecar: clock frozen at 2012-06-30, outbound traffic dropped.
- Optional Internet Archive ingest at **index-build** time only.
- Cheap live OpenRouter probe (`config/run-openrouter.yaml`) when `OPENROUTER_API_KEY` is set.
  Swarm mix is `config/swarm.yaml` (8 × `openai/gpt-4.1-mini` + 4 × `anthropic/claude-3.5-haiku`).
- Sequential swarm (`psbx run --config config/run-swarm.yaml --limit 1`): one shared
  search pack, 12 serialized OpenRouter votes, median probability (`swarm-median`).
  Individual votes are written to `swarm_votes.jsonl`. A full 12×50 pass is hours
  at 2s/req — keep `--limit` small. Dashboard **Run live AI** does not fire this.

Not working yet:

- Native Claude + GPT live scores still need both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.
- Sequential / time-to-event questions (C-index is wired for binary ranking now;
  the same pairwise definition will cover ordered events when those items exist).

Frontier models on e2012 already *could* know the answers from pretraining
(cutoffs 2024–2025, outcomes 2012–2013). That is still worth running. Brier
asks whether probabilities are calibrated. C-index asks whether the model
*ranks* true events above false ones. A leaked model can look excellent on
ranking and mediocre on Brier.

Built indices and run folders are gitignored. After clone, rebuild the index
before you run.

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

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). With no API keys, `psbx run`
uses the retrieval heuristic so the loop is exercisable.

Copy `.env.example` to `.env` when you want live models. Do not commit `.env`.

## Mock vs live

| | Mock | Live (native) | Live (OpenRouter) |
|---|---|---|---|
| Config | `config/run.yaml` | `config/run-phase2.yaml` | `config/run-openrouter.yaml` |
| Run id | `phase1-e2012-smoke` | `phase2-e2012-real` | `phase2-e2012-openrouter` |
| Needs | Nothing | Anthropic + OpenAI keys | `OPENROUTER_API_KEY` |
| What it measures | Pipeline + heuristic | Claude + GPT forecasts | Cheap `openai/gpt-4.1-mini` probe (not the 12-agent swarm) |

Live will not fall back to the heuristic. If keys are missing it fails loud.

OpenRouter is rate-limited in-process: 1 request / 2s, max 20/min, concurrency 1
(`OPENROUTER_MIN_INTERVAL_SEC`, `OPENROUTER_MAX_PER_MINUTE`, `OPENROUTER_MAX_CONCURRENCY`).
Completions cap at 256 tokens unless `OPENROUTER_MAX_TOKENS` is raised. On HTTP 429 the
client waits 15s then 30s and retries at most twice.

Cheap OpenRouter probe (one question; do not omit `--limit` on bigger configs).
Dashboard live click uses this. It does **not** expand the 12-agent mix:

```bash
psbx run --config config/run-openrouter.yaml --limit 1
```

Real swarm (12 sequential votes, shared retrieval, median `p`). Default is one
question. A full 12×50 pass at `OPENROUTER_MIN_INTERVAL_SEC=2` is hours:

```bash
psbx run --config config/run-swarm.yaml --limit 1
```

Needs `OPENROUTER_API_KEY`. Local Llama/Qwen are not in this mix and are never
auto-routed onto that key. Scorer reads `swarm-median`; per-agent votes are
`data/runs/phase2-e2012-swarm-probe/swarm_votes.jsonl`.

Native live (edit `config/run-phase2.yaml` to `models: [frontier-b]` first):

```bash
psbx run --config config/run-phase2.yaml --limit 5
```

Search does not use those keys. Keys are only for the model APIs. Vendor calls
stay on the host; they are never put inside the isolated search container.

## Frozen search (Docker)

[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) is
required for the isolated sidecar. Search publishes `http://127.0.0.1:8766`.
libfaketime ([wolfcw/libfaketime](https://github.com/wolfcw/libfaketime.git),
distro package inside the image) freezes the clock. iptables drops outbound
packets. Docker Desktop on Mac cannot bind-mount a Unix socket or publish
ports on `--network none`, so this is the working equivalent.

```bash
psbx sandbox up --epoch e2012
psbx sandbox clock          # today should be 2012-06-30
PSBX_MOCK_LLM=1 psbx run --config config/run-sandbox.yaml
psbx sandbox down
```

Viewer stays on **8765**. Search sidecar is **8766**. Without Docker, search
stays in-process (`sandbox_mode: host`). The prompt still injects the cutoff;
the index still hard-filters.

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
`data/corpus-cache/wayback/`. Frozen search also exposes `GET /archive?url=`
on the sidecar/viewer: 200 only if that URL is in the index with
`published_at <= cutoff`; 404 otherwise. No live origin fetch at query time.

Optional local WARCs (or a converted ARC slice) can be dropped in
`data/corpus-cache/commoncrawl/` and dated wiki JSONL in
`data/corpus-cache/wikipedia/` — ingested offline. Do not ingest CC-MAIN-2013-20
into e2012.

The fixture seed (~33 documents) is enough to exercise the 50-question smoke.

## Design constraints

1. **No future leakage through search.** Index contains only
   `published_at <= cutoff`. Checked at build and again at query time.
2. **No future leakage through the clock.** Prompt injects the frozen date;
   the sidecar also fakes wall-clock time.
3. **No live web for the agent.** Search is the local index, not the 2026
   internet.
4. **Contamination is measured.** Every model declares a pretraining cutoff.
5. **Citations required.** Uncited or non-supporting spans are flagged.
6. **Reproducible.** Questions, source snapshots, and scoring are in-repo.

## Layout

```
config/          epochs, models, swarm roster, run profiles
src/psbx/        CLI, index, agent loop, scoring, Docker sidecar
leaderboard/     dashboard (port 8765)
custom/          AgentSociety-shaped env + forecaster
data/questions/  e2012 question set
data/sources/    ALFRED / Congress / GDELT / Gallup snapshots
data/corpus/     built index (gitignored)
data/runs/       predictions and scores (gitignored)
tests/
```

## Tests

```bash
pytest
```

## License

MIT (see `pyproject.toml`).
