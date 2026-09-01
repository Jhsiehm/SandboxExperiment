# Rebuildable source snapshots

These files are the Phase 1 manifest. Generators read them when API keys are
absent; with `FRED_API_KEY` the FRED generator re-queries ALFRED vintages and
overwrites observation values only.

| file | role |
| --- | --- |
| `alfred_e2012.json` | Vintage prints + consensus thresholds |
| `congress_e2012.json` | 112th/113th bills and nominations live as of 2012-06-30 |
| `gdelt_e2012.json` | Geopolitical items with pre-cutoff mention counts |
| `gallup_mip_2012.json` | Gallup MIP series. Months ≤ cutoff enter the index as survey docs; later months are **eval targets only** (agenda-setting / human baseline), never agent search |
| `surveys_e2012.json` | Attributed public poll toplines (Gallup/Pew/RCP summaries). Aggregates only — no respondent PII |
| `ads_e2012.json` | FEC/OpenSecrets-style independent-expenditure **metadata** (committee, theme, market, spend band). No creative, no targeting lists |
| `academic_e2012.json` | Short original summaries of pre-cutoff findings. Not full papers |

Live Wayback/GDELT pulls cache under `data/corpus-cache/` (gitignored).
e2012 web is Wayback (`to=20120630`), not the CC-MAIN-2012 dump and not
CC-MAIN-2013-20. Seed documents are code in `src/psbx/corpus/seed_documents.py`
so the index rebuilds without a multi-day crawl.

Do not scrape the live 2026 web into this training corpus. Collecting more than
attributed metadata/toplines (interview microdata, ad creative, full papers)
would violate the minimize-data stance — flag it rather than adding it.

