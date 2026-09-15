# Track B dashboard specification

Add Track B as a separate workspace. Do not merge it into the existing forecast scoreboard.

## Population Builder

Fields:

- mode: fixed benchmark, Census-grounded, custom scenario, survey replication;
- epoch and cutoff;
- geography type and historical GEOID;
- population universe;
- source/data vintage;
- target represented population;
- attributes used as raking constraints;
- population realization count;
- representative-agent budget;
- behavior engine;
- model backend;
- evidence exposure mode;
- random seed/replications.

For custom scenarios, show Census baseline, scenario value, and delta side by side.

## Population Fidelity

Display:

- represented population;
- synthetic records;
- unique profiles;
- representative cells;
- fitted dimensions;
- raking convergence;
- target versus actual by category;
- total variation by dimension;
- direct versus imputed fields;
- ACS margins of error;
- household-integrity status;
- source/version/checksum manifest.

## Behavior Validation

Display:

- statistical baseline;
- LLM-adjusted result;
- held-out survey target;
- aggregate historical target;
- overall and subgroup error;
- calibration;
- missing/weak-support cells;
- uncertainty intervals;
- number of real survey respondents supporting each estimate.

## Agent-count Convergence

For every condition show:

- population represented;
- synthetic records;
- representative cells;
- reasoning calls;
- replications;
- mean estimate;
- between-seed interval;
- subgroup stability;
- held-out error;
- token/cost totals.

## Required warning text

> This is a synthetic population constrained to published aggregate estimates. It does not
> reconstruct actual residents or identify how any real person voted.

## Suggested API routes

```text
GET  /api/population/sources
POST /api/population/plan
POST /api/population/build
GET  /api/population/builds
GET  /api/population/builds/{population_id}
GET  /api/population/builds/{population_id}/validation
GET  /api/population/builds/{population_id}/cells
POST /api/population/experiments
GET  /api/population/experiments/{run_id}
```

Do not add network download actions to agent-runtime routes. Source synchronization must be a
separate explicit build-time operation.
