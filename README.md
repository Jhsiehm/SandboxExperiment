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
3. Later: single-agent vs swarm (swarm is still a stub).

Epoch **e2012**: cutoff `2012-06-30`, resolution window through `2013-06-30`.
Fifty binary questions (20 economic, 20 legislative, 10 geopolitical). Scoring
matches ForecastBench: Brier `(f − o)²`, plus Brier Index `(1 − √Brier) × 100`.

Agent-loop layout follows [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety)
(`custom/envs`, `custom/agents`, `examples/e2012_forecast`). Cite Piao et al.
(arXiv:2607.11895). Do not copy their urban simulator into this repo.

## Status

Working today:

- Question set, seed corpus, cutoff-filtered search, Brier scoring, dashboard.
- Mock pipeline (retrieval heuristic, no API keys).
- Docker search sidecar: clock frozen at 2012-06-30, outbound traffic dropped.
- Optional Internet Archive ingest at **index-build** time only.

Not working yet:

- Live Claude / GPT scores — needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `.env`.
- Swarm (`src/psbx/agents/swarm.py` raises `NotImplementedError`).
- A contamination curve that crosses model training cutoffs. Every e2012
  question resolves in 2012–2013; the frontier configs declare 2024/2025
  cutoffs, so they already *could* know the answers from pretraining.

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

| | Mock | Live |
|---|---|---|
| Config | `config/run.yaml` | `config/run-phase2.yaml` |
| Run id | `phase1-e2012-smoke` | `phase2-e2012-real` |
| Needs | Nothing | Anthropic + OpenAI keys |
| What it measures | Pipeline + heuristic | Actual model forecasts |

Live will not fall back to the heuristic. If keys are missing it fails loud.

Cheaper live probe (edit `config/run-phase2.yaml` to `models: [frontier-b]` first):

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

```bash
psbx corpus build --epoch e2012
# optional: Wayback at index-build only (not agent search)
# export PSBX_IA_USER_AGENT_SUFFIX="your-project"
psbx corpus build --epoch e2012 --live
```

`--live` uses User-Agent `PredictionSandbox/0.1.0 (psbx; corpus-builder)`,
5s pacing, and 429 / Retry-After. Drop Common Crawl WARCs in
`data/corpus-cache/commoncrawl/` and dated wiki JSONL in
`data/corpus-cache/wikipedia/` — ingested offline.

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
config/          epochs, models, run profiles
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
