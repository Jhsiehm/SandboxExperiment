# Statistical reference and next data/design stage

The existing statistical reference is preserved. The next stage is a linked-panel data and baseline study, with **no further language-model training**. Preparation and synthetic validation are complete; real panel ingestion is not yet admitted.

## What is complete

`reports/statistical-reference-20261023/manifest.json` binds the exact existing six-category DEBATE Laplace-one transition table, its original prediction seal, and both failed candidate results. Its baseline SHA-256 is `ffc4ecc705c209841dfe51bcab5b40f68159c91cb914ef4e362c4abdda46b245`. No coefficients were refitted or replaced with the calibrated control.

The associated aggregate data audit verifies 92 people across 23 groups and 21 topics. Forty-eight answers were unchanged and 44 changed. All required initial/final categories, identities, topics and initial text are present and valid in this admitted fitting export. Initial-category sample sizes range from 10 to 22, so complete records do not establish adequate support for a complicated model. This audit does not measure selection losses before the admitted export or turn these inspected people into confirmation data.

The next design is recorded in `config/anes-panel-design-v1.json`. It proposes ANES seven-category party identification, 2016 pre → 2020 pre development, then a separately frozen 2020 pre → 2024 pre evaluation. The seven-category panel reference must be newly fitted on its own authorized development records; the six-category DEBATE table cannot be reused. The first stage is baseline-only. A later enhanced candidate, practical improvement margin and uncertainty procedure remain explicitly unset.

`psbx.experiments.panel_development` implements a strict harmonized development-export auditor, a fixed seven-category Laplace-one reference function, normalized ordinal RPS, and change-event Brier scoring. It accepts only observed 2016/2020 pre-election development rows; rejects future waves, duplicate person-wave rows, extra fields, ambiguous duplicate JSON keys, and invalid/missing codes; and preserves documented missingness. The audit distinguishes absent follow-up rows, documented noninterview and item nonresponse, and reports retention by initial category. Person folds depend on a fixed ID hash, not answers. The tool emits aggregate evidence and never silently imputes a target.

The auditor requires source field names and SHA-256 lineage but cannot certify that a trusted importer mapped the raw questionnaire correctly. Its report deliberately does not mark the crosswalk, weights or precision as verified. Its five-fold structural check is not a power assessment; PSU/household dependence needs separate review before inference.

## Why ingestion is still gated

The official-documentation pass identified the linked ID, candidate pre-election summary variables, modes, missing codes and panel weight fields. See `ANES_PANEL_METADATA_READINESS.md` for primary-source links and evidence distinctions. Five source issues remain:

1. The 2024 summary construction includes an additional web follow-up. Matching seven-category labels do not by themselves establish equivalent construction across waves.
2. Official document downloads returned HTTP 403. Browser-rendered evidence was available, but original source bytes and their checksums were not obtained. The saved paraphrase hash is explicitly not an original-source hash.
3. The official repeated-variable download is an archive whose member schema and release have not been verified.
4. The merged release page and errata page report different release dates; exact source alignment remains unresolved.
5. Raw merged-column casing, linkage uniqueness, wave availability and missing encodings have not yet been checked. No respondent dataset was downloaded for this work.

`scripts/assess_panel_readiness.py` produces the exclusive, read-only readiness snapshot. It requires affirmative resolution evidence and actual archived-byte hash checks; deleting a blocker is insufficient. Even if source gates clear, it reports that the raw-to-development projection must be frozen before ingestion. Later-wave evaluation, model training, paid calls and existing reserve access remain disabled.

## The next executable sequence

First obtain and archive the official documentation, resolve the summary construction and release mapping, and freeze a trusted projection that exports only the approved development fields. Keep later-wave outcomes outside that export. Then run the harmonized-export audit and account for original-universe selection, missingness, mode and category support before fitting a new seven-category reference.

For an admitted development export, the auditor command is:

```sh
PYTHONPATH=.:src python -m psbx.experiments.panel_development \
  --development-export /absolute/path/to/harmonized-development.json \
  --output /absolute/path/to/new-development-audit.json
```

The JSON export has exactly `schema: "harmonized-panel-development-v1"` and `rows`. Each row has exactly `person_id`, `wave`, `phase`, `role`, `party_id`, `missing_reason`, `mode`, `source_field`, `source_sha256`, and `value_origin`. Permitted values and missing-reason categories are enforced by the module. This command is not a raw ANES importer; do not point it at a mixed-wave respondent file.

After the real development audit, assess precision and attrition using development information, select one bounded candidate and matched feature set, and freeze a justified decision margin and design-aware uncertainty plan. Only after predictions and evaluator are sealed should a later-wave readout occur. Do not inherit the previous experiment's 0.01 margin without a panel-specific rationale.

With only one early transition, the initial design cannot support a matched earlier-history ablation. Reusing people across the temporal boundary tests later-wave prediction for known panel members. Modern checkpoints and later survey releases also make this retrospective transfer, not a historical operational forecast. Weighted population estimates, autonomous rollouts, assimilation and social interaction need their own verified information contracts.

## Verification and location

All 52 relevant tests passed: 18 harmonized-export tests, eight readiness tests, eight statistical-reference tests and 18 dashboard tests. Independent review reproduced the 26 panel/readiness tests and found no remaining blocking implementation issue. Tests include real-byte hash drift, positive source-evidence gates, exact disabled execution flags, CLI rejection of future rows, exclusive outputs and aggregate-only preview fields. No new model inference, paid API request or neural training occurred.

Source metadata, failed-download receipts and the readiness snapshot are in `reports/anes-panel-readiness-20261023/`. The preserved reference and aggregate audit are in `reports/statistical-reference-20261023/`. The dashboard presents these separately from the completed negative calibration experiment.
