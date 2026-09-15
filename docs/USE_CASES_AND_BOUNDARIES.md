# Track B uses and boundaries

## Primary research uses

### 1. Fixed-persona regression benchmark

Keep the existing twelve personas unchanged. Re-run them after prompt, model, retrieval, or UI
changes to detect regressions and measure persona sensitivity. This mode does not claim population
representativeness.

### 2. Population-fidelity benchmark

Generate a synthetic population for a declared geography, year, and universe, then measure whether
its marginal and held-out joint distributions reproduce the published demographic constraints.
No political outcome is needed for this test.

### 3. Historical survey replication

Hold out selected historical survey responses or toplines, build the population and behavior prior
without those targets, and test whether weighted synthetic responses recover the held-out
aggregate and subgroup distributions.

### 4. Historical aggregate validation

Compare sealed synthetic aggregates with later certified historical turnout, participation, or
other aggregate civic outcomes. Aggregate fit must not be interpreted as identifying how an
individual demographic group voted.

### 5. Agent-count convergence

Hold the represented population fixed while varying representative cells, model invocations, and
replications. Identify where aggregate and subgroup metrics stabilize. One synthetic resident is
not automatically one model call.

### 6. Model, evidence, and profile ablations

Cross population profiles with model backends and evidence conditions. Separate demographic,
attitudinal, model, evidence, and random-seed effects rather than zipping one persona to one model.

### 7. Information-exposure experiments

Compare a common-evidence condition with a documented differential-exposure condition. Keep this
separate from population composition so media effects are not confused with demographic effects.

### 8. Hypothetical demographic scenarios

Start from a published baseline, let a user change selected distributions, display every delta, and
label the result hypothetical. Do not relabel a modified scenario as the observed township.

### 9. Uncertainty decomposition

Run multiple plausible population realizations and separate Census/ACS estimate uncertainty,
population-synthesis uncertainty, behavior-model error, model instability, and Monte Carlo noise.

## Not appropriate uses

- Reconstructing or identifying actual residents.
- Inferring protected characteristics from names, addresses, ZIP codes, browsing, or behavior.
- Producing real-person voter files, targeting segments, persuasion strategies, or suppression
  strategies.
- Treating demographics as deterministic political preferences.
- Ranking candidates, parties, public officials, legislation, or ballot measures.
- Producing live-election winner probabilities.
- Using aggregate precinct results to claim individual-level demographic vote choices.
- Exposing raw respondent microdata or evaluation targets to runtime agents.
- Treating a larger number of calls to the same model as independent human evidence.
