# Track B architecture

## Research question

Track B should test whether a Census-constrained, survey-grounded synthetic population can reproduce
held-out historical human-response and aggregate geographic distributions. It is separate from
Track A's historical event forecasting question.

## Modes

### Fixed benchmark personas

Keep the current twelve explicit personas unchanged as a stable regression suite. Their purposes are
prompt sensitivity, provider comparison, evidence-condition checks, UI testing, and reproducibility.
They are not a statistically representative township.

### Census-grounded population

Build a synthetic population from:

1. local aggregate constraints;
2. anonymized donor microdata carrying realistic joint attributes;
3. an explicit synthesis algorithm and seed;
4. a validation report against every fitted marginal;
5. multiple population realizations when estimates contain margins of error.

### Custom scenario

Allow users to change a distribution only after loading a baseline. Every changed field must show
its delta from the observed baseline and the result must be labeled hypothetical.

### Survey replication

Hide selected historical survey outcomes, create a matching weighted population, run the behavior
engine, and compare predicted response distributions with held-out responses/toplines.

## Four data zones

```text
Population build zone
  Census/ACS aggregates, PUMS donors, geography, checksums
  Never exposed as searchable runtime documents

Behavior training zone
  Properly licensed survey microdata and weighting documentation
  Never exposed as raw respondent rows to runtime agents

Runtime profile zone
  Synthetic profile, frozen evidence pack, task, and permitted model state

Evaluation vault
  Held-out survey outcomes and certified aggregate historical results
  Revealed only after simulation output is sealed
```

## Data lineage

```text
Small-area Census/ACS constraints
                +
Regional PUMS donor records
                |
                v
Raking / population synthesis
                |
                v
Synthetic person records
                |
                +--> weighted representative cells
                |          |
                |          +--> statistical behavior prior
                |          +--> optional LLM contextual adjustment
                |
                v
Weighted aggregate outputs
                |
                v
Held-out survey and historical aggregate validation
```

## MVP method

The included implementation performs person-level raking:

1. Canonicalize donor variables.
2. Filter to the declared population universe.
3. Fit donor expansion weights to local marginal constraints.
4. Integerize weights to exactly `target_population` synthetic rows.
5. Validate every fitted marginal and any separately marked held-out population constraints.
6. Compress rows into representative cells.
7. Allocate a separate reasoning-call budget.

This preserves joint combinations already present in donor records. It does not yet guarantee that
whole donor households are selected together. A household-level iterative proportional updating or
combinatorial optimization stage should be added before making household-network claims.

## Population universes

- `all_residents`
- `adults_18_plus`
- `voting_age`
- `citizen_voting_age`
- `registered_voters`
- `likely_voters`

The final two require an election-administration or survey behavior layer. Census data alone cannot
establish registration or likely-voter status.

## Behavior engine order

1. Weighted survey baseline.
2. Hierarchical or poststratified probability model.
3. Optional LLM adjustment using frozen evidence.
4. Weighted aggregation.
5. Held-out validation.

Demographics must not be converted into deterministic political choices. The output is a
probability distribution with residual heterogeneity.

## Agent-count experiment

Keep the represented population fixed and vary only the computational representation:

```text
25, 100, 500, 1,000, 5,000, full representative cells, and full records
```

For each condition, run multiple seeds and report aggregate/subgroup stability, held-out error,
between-seed variance, coverage, model calls, tokens, and cost. More calls reduce Monte Carlo noise
but do not necessarily reduce shared model bias.

The represented population size is a statistical weight, never an LLM-agent count. Do not launch
one paid model call per represented resident. Start with 25 or 100 systematically sampled weighted
cells, increase only while held-out error or between-seed variance materially improves, and use the
full population only for deterministic tabulation. "Full representative cells" and "full records"
are offline comparison conditions unless a non-LLM behavior engine makes them computationally safe.

## Main limitations to display

- Synthetic records are not actual residents.
- Public PUMS records generally identify PUMAs, not a specific township or precinct.
- Aggregate election returns do not reveal individual demographic vote choices.
- Survey data contain sampling, weighting, response, and measurement error.
- The person-level MVP does not preserve exact household membership.
- LLM outputs share model-level biases and are not independent human respondents.
