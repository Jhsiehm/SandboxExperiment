# Track B data governance

## Provenance contract

Every source artifact must record:

- registry source ID;
- provider and title;
- exact artifact filename/version;
- reference period;
- release date;
- release-date verification method;
- geography vintage;
- download date;
- SHA-256 checksum;
- access/license terms;
- data zone;
- cutoff decision;
- transformations applied.

## Cutoff rules

In `sealed_forecast` mode, a population-build source must:

1. permit the `population_build` zone;
2. have a verified release date;
3. have `release_date <= cutoff_date`;
4. use the exact historical artifact version;
5. be checksum-pinned.

A post-cutoff survey or election result may exist in the evaluation vault, but it may not influence
population construction, behavior priors, prompts, retrieval, or agent state for that sealed run.

`retrospective_reconstruction` may use later-released historical estimates only when clearly labeled.
It must never be compared directly with sealed runs without displaying the different information set.

## Privacy and minimization

- Do not collect respondent PII.
- Do not infer protected traits from names, addresses, ZIP codes, browsing, or behavior.
- Do not retain unnecessary raw fields.
- Keep raw microdata out of the runtime agent container and searchable corpus.
- Store synthetic IDs, not names.
- Do not publish small-cell outputs that could be confused with real individuals.
- Respect source-specific licenses and registration terms.

## Three identities that must remain separate

```text
Actual resident        not present in the system
Anonymized donor row   source record used to preserve joint structure
Synthetic resident     generated record representing a plausible person
```

No output may imply that a donor row or synthetic resident is an actual local person.

## Geography

Use historical boundary vintages. Preserve explicit crosswalks between Census geographies, VTDs,
local election precincts, townships/county subdivisions, and districts. Never assume a modern
precinct polygon matches the historical election geography.

## Storage

Recommended ignored paths:

```text
data/population-input/
data/population/
data/census-cache/
data/survey-microdata/
data/evaluation-vault/
```

Commit only code, registries, small synthetic fixtures, documentation, and tests.

## Behavior-training artifacts

Survey/CPS microdata used to estimate behavior priors belongs in `behavior_training`, not in the
population-count layer and not in the frozen search corpus. Final outcomes used for scoring remain
in `evaluation`.
