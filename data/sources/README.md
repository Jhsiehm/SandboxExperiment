# Rebuildable source snapshots

These files are the Phase 1 manifest. Generators read them when API keys are
absent; with `FRED_API_KEY` the FRED generator re-queries ALFRED vintages and
overwrites observation values only.

| file | role |
| --- | --- |
| `alfred_e2012.json` | Vintage prints + consensus thresholds |
| `congress_e2012.json` | 112th/113th bills and nominations live as of 2012-06-30 |
| `gdelt_e2012.json` | Geopolitical items with pre-cutoff mention counts |
| `gallup_mip_2012.json` | Gallup MIP series for agenda-setting validation |

Live Wayback/GDELT pulls cache under `data/corpus-cache/` (gitignored).
Seed documents are code in `src/psbx/corpus/seed_documents.py` so the index
rebuilds without a multi-day crawl.
