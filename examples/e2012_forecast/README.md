# e2012 forecast — AgentSociety 2 scaffold

This experiment ports Prediction Sandbox onto the [AgentSociety 2](https://github.com/tsinghua-fib-lab/AgentSociety) module layout:

- `custom/envs/frozen_epoch_env.py` — `EnvBase` + `@tool` search/fetch (cutoff enforced)
- `custom/agents/forecaster_agent.py` — `ForecasterAgent` (`AgentBase`)
- `init_config.json` / `steps.yaml` — society CLI-shaped metadata

We cite AgentSociety; we do not vendor their city simulator. Scoring, questions, and the hybrid index stay in `src/psbx/`.

## Run (this repo, no Ray required)

```bash
PSBX_MOCK_LLM=1 psbx society run --config config/run-society.yaml --limit 2
```

Search goes through `FrozenEpochEnv`, not a raw index client.

## Run (AgentSociety 2 installed)

```bash
pip install -e ".[society]"
export WORKSPACE_PATH="$(pwd)"
export AGENTSOCIETY_LLM_API_KEY=...
export AGENTSOCIETY_LLM_API_BASE=https://api.openai.com/v1
export AGENTSOCIETY_LLM_MODEL=gpt-4.1-mini

# After custom scan (AgentSociety backend on :8001):
# python -m agentsociety2.society.cli \
#   --config examples/e2012_forecast/init_config.json \
#   --steps examples/e2012_forecast/steps.yaml \
#   --run-dir data/runs/phase2-e2012-real/society
```

Until `agentsociety2` is installed, `psbx society run` uses the documented EnvBase/@tool contract via a local shim and the existing host-side forecast loop.

## Citation

Piao et al., AgentSociety 2, arXiv:2607.11895. Apache-2.0.
