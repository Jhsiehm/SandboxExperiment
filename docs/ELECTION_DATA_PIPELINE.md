# Election and electoral-demography data pipeline

## What is implemented

The system now has four separate layers. Keeping them separate prevents a downloaded file from
being mistaken for a usable population or a final result.

1. `config/election_sources.yaml` records authoritative source scope and coverage.
2. `psbx elections sync-federal` plans or downloads official FEC source documents.
3. `psbx elections sync-census` plans or executes ACS 5-year queries for states, counties,
   Census places, congressional districts, and both state-legislative chambers.
4. `psbx elections import-fec` safely reads the House and Senate result sheets in an official
   FEC workbook; `import-results` handles already-canonical state/local adapters.
5. Both import commands validate canonical aggregate result rows and write a
   checksum-bound dataset manifest. The dashboard receives these manifests as filterable,
   path-free data layers through `/api/data/catalog?epoch=e2012` (also embedded at
   `/api/population` → `data_catalog`).

No command makes paid model calls. Network access is off unless `--execute` is passed to a sync
command. Imported election records are evaluation data, not population constraints.

## Start with federal elections

Inspect the coverage plan first:

```bash
psbx elections plan --start-year 1982 --through-year 2026 --as-of 2026-09-14
psbx elections sync-federal --years 1982-2024
```

Add `--execute` only when ready to download the official FEC documents. The default downloader
selects primary publications, caps each artifact at 250 MB, caps the whole sync at 500 MB, and
pins content signatures and SHA-256 hashes. `--include-supplements` is an explicit opt-in for the
many component tables and maps on older pages. Raw PDFs and workbooks are stored under ignored
`data/elections/raw/`; they are not called normalized until a source adapter produces the
canonical result schema and the importer validates it.

Normalize a downloaded official 2016–2022 combined FEC workbook without loading macros,
drawings, or embedded media. Older publications stay pinned as raw evidence until a reviewed
legacy-XLS or PDF adapter is added. The release date is required because the FEC workbook itself
does not expose a reliable
machine-readable publication timestamp; verify that date independently before relying on a
historical cutoff.

```bash
psbx elections import-fec \
  --workbook data/elections/raw/federal/2022/federalelections2022.xlsx \
  --year 2022 \
  --source-release-date 2026-09-14 \
  --cutoff 2026-09-14 \
  --dataset-id fec-federal-2022 \
  --label "Official FEC federal general results · 2022"
```

The November 3, 2026 federal general election is a future event as of September 14, 2026. The
planner reports it as `future_pending`; it cannot supply certified 2026 results before they exist.

## Pull Census demographics for electoral comparisons

The default plan is 306 API requests: six geography levels for 50 states plus D.C. Planning is
offline and free.

```bash
# Inspect a small plan.
psbx elections sync-census \
  --year 2024 \
  --states ca,tx \
  --levels congressional_district,state_legislative_upper,state_legislative_lower

# Execute the nationwide, bounded plan.
psbx elections sync-census --year 2024 --states all --levels all --execute
```

The verified maximum is currently the 2024 ACS 5-year release. A newer year fails closed until
its exact dataset and release are reviewed. The default `--max-requests 350` bounds accidental
network volume. Census API calls do not use an LLM and do not incur model-token charges.
The current Census API requires a free `CENSUS_API_KEY`; the client never writes that key into
cache metadata.

## Canonical election-result import

An adapter must produce every named column in `ElectionResultRow`, including blank optional
columns. Key fields include:

- exact election and source-release dates;
- stage, office level, contest ID, candidate, votes, and certification status;
- an explicit vote status so an unopposed contest with no vote total is not mistaken for a
  zero-vote loss;
- state/district/county/municipality identifiers as applicable;
- a geography vintage and authoritative source URL.

Then import it:

```bash
psbx elections import-results \
  --input data/staging/federal-2020.csv \
  --dataset-id federal-2020 \
  --label "Certified federal results · 2020" \
  --cutoff 2021-01-01
```

The importer rejects negative votes, duplicate candidate rows, mismatched dates, missing
geography keys, uncertified results by default, and sources released after the requested cutoff.
Use `--allow-uncertified` only for an explicitly labeled provisional dataset.

## Filling the district map correctly

The checked-in state and district boxes are boundary selectors, not population profiles. A local
state profile may appear only after its ignored build artifacts and validation manifest exist.
Filling real-geography profiles requires this sequence for each election vintage:

1. download ACS estimates for the matching district plan;
2. pin the matching TIGER/Line boundary vintage;
3. build district constraints and an explicit donor/crosswalk method;
4. synthesize and validate a district population;
5. publish only the aggregate profile/manifest to the map catalog.

`GeographySpec` now has explicit congressional, upper-chamber, lower-chamber, and municipality
types so those builds cannot be mislabeled as generic voting districts. Census places do not
always equal municipal election jurisdictions, and Census voting districts do not always equal
precincts; local adapters must preserve the actual election authority's identifiers and a
documented crosswalk.

## Nationwide expansion order

- Phase 1: federal general/primary/runoff records, 1982–2024, by state and House district.
- Phase 2: state legislative and statewide offices through per-state official adapters.
- Phase 3: county and municipal contests through state/local portals and election-office
  directories.
- Phase 4: historical boundary crosswalks, completeness audits, and held-out evaluation packs.

There is no authoritative single national file containing every county, municipal, state-house,
and state-senate result. Coverage must therefore be reported by year, state, office, stage, and
geography—not as one misleading nationwide boolean.

## Run-comparison filter contract

The map may send a `dataset_selection` object with a run request containing `kind`, `layer_id`,
optional `compare_layer_id`, `year`, `geography_level`, and `source_ids`. The server sanitizes and
stores this object in the run manifest and run-list response. It is explicitly marked
`runtime_access: false`: election outcomes and comparison layers are display/evaluation
provenance and are never inserted into agent prompts or retrieval.
