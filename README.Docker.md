# Sealed ANES area experiment

`docker init` generated the starter files; these have been adapted for the existing
Python package and a batch experiment. No web server or port is needed.

From SandboxExperiment, using the existing local Python environment and licensed data:

```sh
docker build -t psbx-anes-area:local .
.venv/bin/python scripts/run_anes_area.py --state-fips 39 --run-id anes2012-ohio-20261004
```

Use a fresh run ID for each execution. The script refuses to overwrite a run.
It selects all respondents in the chosen state, prepares eight pre-election fields,
verifies their seals, and runs 30 paired replications with groups of 12 and three
interaction rounds. Targets are opened on the host only after prediction sealing.

The container uses no network, a read-only root, a non-root user, dropped capabilities,
no-new-privileges, and CPU/memory/PID limits. Only the runtime profile file and output
directory are mounted. Source microdata, the evaluation vault, and credentials are
excluded. `--env-file /dev/null` prevents Compose from loading the local `.env`.
The Dockerfile installs pyproject.toml dependencies and copies only application code.

Results, resolved container configuration, image ID, hashes, and logs are under
`data/runs/<run-id>/`. This records the exact local image; dependency versions are not
locked, so future rebuilds may differ. Retain the recorded image for exact reruns.

This is the provider-free structural mock, not a live LLM swarm or conclusive evidence
of human-response fidelity. The live provider runner remains a separate workflow and
requires working authentication. Modern models cannot be made temporally unaware of
post-2012 events merely by placing the orchestrator in Docker. The ANES survey weights
are national survey weights; state-subset estimates are descriptive, not certified
state election results or a state-specific survey calibration.

## Live independent validation with an offline container boundary

The October 12 follow-up uses `psbx.experiments.reserved_validation`. Its planner
and response validator run in network-disabled containers. A trusted host broker
sends only frozen prompt jobs to OpenRouter, and a separate host evaluator opens
held-out labels after prediction sealing. Remote inference is outside Docker.

```sh
docker build -t psbx-anes-validation-deps:20261012 .
docker build -f Dockerfile.validation -t psbx-anes-validation:local .
.venv/bin/python -m psbx.experiments.reserved_validation prepare
.venv/bin/python -m psbx.experiments.reserved_validation run
.venv/bin/python -m psbx.experiments.reserved_validation evaluate
```

The first command builds dependencies; the second copies the final source over
that image without downloading dependencies again. Each experiment records and
uses its immutable local image ID. Runtime probes and Docker inspection verify
read-only mounts/root, no external network interface, non-root execution,
no-new-privileges, and absent credentials/target mounts. On Docker Desktop, dormant
kernel tunnel interfaces may exist even with network mode `none`; the probe checks
that none are active, not that their names are absent.

The 120-case follow-up reserves 50 other respondent IDs, compares sparse/rich
profiles without context, and makes 480 planned calls. Existing provider rate
limits remain unchanged, including maximum concurrency one. Three application
workers therefore do not imply three simultaneous provider requests. A laptop
that suspends can extend wall time and interrupt in-flight requests; preserve
checkpoints and resume the same contract rather than rerunning completed calls.
Provider failures without a usage response retain unreconciled ledger reservations.

See `docs/ANES_RESERVED_VALIDATION_PROTOCOL.md` for the exact design and limits.
This is a local workflow: current contract paths are absolute and dependencies are
range-specified. A clean-checkout portable reproduction has not been established.
