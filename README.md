# Prediction Sandbox

A contamination-controlled forecasting benchmark. Agents are dropped into a
frozen historical epoch with a search tool scoped to a reconstructed
contemporaneous web corpus, then scored on real outcomes they cannot look up.

**Phase 1:** epoch `e2012` (cutoff 2012-06-30), 50 questions, 3 model configs,
end to end.

This is not another live leaderboard. ForecastBench, MIRAI, FutureX, Halawi et
al., and OracleProto already cover that shape. The contribution is:

1. **Deep-history epochs** existing work does not test.
2. **Legislative and policy outcome questions** no existing benchmark covers.
3. **Single-agent vs swarm** (swarm is stubbed until Phase 3).

Agent loop scaffolding follows [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety)
(`custom/envs`, `custom/agents`, `examples/e2012_forecast`). Cite Piao et al.
(arXiv:2607.11895); do not duplicate their urban simulator.

Cite those papers; do not duplicate them. Brier scoring matches ForecastBench:
`(f - o)²` on binary questions, plus their Brier Index `(1 − √Brier) × 100`.

## Design constraints

1. **No future leakage through the tool layer.** The index contains only
   documents with `published_at <= epoch.cutoff_date`. Enforced at build time
   and re-checked at query time.
2. **No future leakage through the clock.** Phase 1 injects the frozen date
   into the prompt and hard-filters the index. Container `libfaketime` is
   stubbed for a later hardening pass.
3. **No network egress for search.** Search is a local service / in-process
   index, not an internet call.
4. **Parametric contamination is measured, not wished away.** Every model
   carries a declared pretraining cutoff. The accuracy-vs-cutoff-gap curve is
   a headline output.
5. **Every prediction must cite retrieved documents.** Uncited or
   non-supporting spans are flagged for contamination review.
6. **Reproducible by a stranger.** Question set, corpus manifest, and scoring
   code are in-repo. The corpus rebuilds from fixtures; `--live` adds Wayback.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

psbx questions build --epoch e2012 --limit 50
psbx corpus build --epoch e2012
PSBX_MOCK_LLM=1 psbx run --config config/run.yaml
psbx score --run phase1-e2012-smoke
psbx agenda --epoch e2012
```

With no API keys, `psbx run` uses a retrieval heuristic (`PSBX_MOCK_LLM=1`)
so the pipeline is exercisable. Point `config/models.yaml` at real endpoints
and set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `VLLM_BASE_URL` to score
actual models.

## Layout

See `src/psbx/` for schemas, generators, the hybrid index, the host-side
harness, and scoring. AgentSociety-shaped modules live in `custom/` and
`examples/e2012_forecast/`. Config lives in `config/`. Bundled ALFRED /
Congress / GDELT snapshots live in `data/sources/`. Built indices and run
outputs are gitignored and rebuildable.

## AgentSociety scaffold

```bash
PSBX_MOCK_LLM=1 psbx society run --config config/run-society.yaml --limit 2
```

That routes search/fetch through `FrozenEpochEnv` (cutoff asserted on every
tool call) and writes `data/runs/phase1-e2012-society/` without clobbering
the Phase 1 smoke. Optional: `pip install -e ".[society]"` then point
`WORKSPACE_PATH` at this repo for the real CodeGenRouter / society CLI.
See `examples/e2012_forecast/README.md`.

## Phase 1 limitation

The agent loop still runs on the host. The optional search sidecar
(`psbx sandbox up`) freezes the clock with libfaketime and uses
`--network none`. Vendor model APIs cannot live in that container.

## Rebuild the live corpus

```bash
# Optional: identify an AI-driven crawl per archive.org bot rules
# export PSBX_IA_USER_AGENT_SUFFIX="cursor-grok-4.6"

psbx corpus build --epoch e2012 --live
```

`--live` hits the Internet Archive CDX/snapshot APIs at **index build** only,
with User-Agent `PredictionSandbox/0.1.0 (psbx; corpus-builder)`, 5s pacing,
and 429 / Retry-After handling. Agent search stays on the local index.

Drop Common Crawl / pywb WARCs in `data/corpus-cache/commoncrawl/` and dated
wiki JSONL in `data/corpus-cache/wikipedia/` — they are ingested offline, no
egress. pywb is a replay appliance, not the scored search UI.

Wayback ingest is slow. The fixture seed is enough for the 50-question smoke.

## Frozen search sidecar (libfaketime)

Uses the distro `libfaketime` package ([wolfcw/libfaketime](https://github.com/wolfcw/libfaketime.git)), not a vendored clone. Search runs in Docker with a frozen cutoff clock and `--network none`. The host talks over a Unix socket. Anthropic/OpenAI stay on the host.

```bash
psbx sandbox up --epoch e2012
psbx sandbox clock    # today should be 2012-06-30
# then set sandbox_mode: container in config/run.yaml
psbx sandbox down
```

Without Docker, search stays in-process (`sandbox_mode: host`). The prompt still injects the cutoff; the index still hard-filters.

## Tests

```bash
pytest
```
