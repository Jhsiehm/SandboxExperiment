# e2012 forecast — AgentSociety 2 scaffold

This experiment ports Prediction Sandbox onto the [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety) module layout:

- `custom/envs/frozen_epoch_env.py` — `EnvBase` + `@tool` search/fetch/evidence_pack (cutoff enforced)
- `custom/agents/forecaster_agent.py` — `ForecasterAgent` (`create` / `from_workspace`)
- `init_config.json` / `steps.yaml` — real AgentSociety CLI `InitConfig` + questionnaire steps (12 swarm bodies)

Clone the platform beside this repo. Do not vendor their city simulator. Scoring, questions, and the hybrid index stay in `src/psbx/`.

```bash
gh repo clone tsinghua-fib-lab/AgentSociety ../AgentSociety
```

## Export the 12-agent sandbox (this repo, no Ray)

```bash
psbx society export --config config/run-society-swarm.yaml --limit 1 \
  --dest examples/e2012_forecast
```

## Run (this repo, no Ray required)

```bash
PSBX_MOCK_LLM=1 psbx society run --config config/run-society-swarm-mock.yaml --limit 1
psbx eval baseline --run phase1-e2012-society-swarm-mock
```

Live 12-agent society swarm (OpenRouter key required; `allow_mock: false`):

```bash
psbx society run --config config/run-society-swarm.yaml --limit 1
psbx eval baseline --run phase2-e2012-society-swarm
```

Each of the 12 bodies is an explicit simulation persona from
`config/perspectives.yaml` (district/constituency-shaped: region, urbanicity,
party ID, age band, education, media diet). The shared FrozenEpochEnv pack is
the **media stimulus** (Track A). Surveys, ad metadata, and academic summaries
in the same cutoff-locked index **condition** those reactions (Track B). Score
closeness to later public/political outcomes, not impressiveness. PolicySim is
later.

## Run (AgentSociety 2 installed from the sibling clone)

```bash
pip install -e "../AgentSociety/packages/agentsociety2"
export WORKSPACE_PATH="$(pwd)"
export AGENTSOCIETY_LLM_API_KEY=...
export AGENTSOCIETY_LLM_API_BASE=https://openrouter.ai/api/v1
export AGENTSOCIETY_LLM_MODEL=openai/gpt-4.1-mini

# python -m agentsociety2.society.cli \
#   --config examples/e2012_forecast/init_config.json \
#   --steps examples/e2012_forecast/steps.yaml \
#   --run-dir data/runs/phase2-e2012-society-swarm/society
```

Until `agentsociety2` is installed, `psbx society run` uses the documented EnvBase/@tool contract via a local shim. Votes for the 12-agent mix stay on serialized OpenRouter so the species roster in `config/swarm.yaml` is preserved.

## Citation

Piao et al., AgentSociety 2, arXiv:2607.11895. Apache-2.0.
