# Moving Prediction Sandbox to another laptop

Use two synchronized layers:

1. **Git** carries code, documentation, configuration, questions, small source
   snapshots, test fixtures, and geography assets.
2. A **research-asset bundle** carries the ignored local state: source-document
   caches, Census inputs, election publications, generated populations, sealed
   evaluation inputs, built corpora, and experiment runs.

This split is intentional. The current local research assets are several
gigabytes, include already-compressed archives, and contain individual files
that are hundreds of megabytes. Putting those files in ordinary Git history
would make every clone heavy and fragile. Some registered datasets also may not
be redistributed. The bundle stays private and records a SHA-256 checksum for
every transferred file.

The transfer tool never includes `.env`, `.git`, `.venv`, build outputs,
Python caches, or the transient sandbox PID/socket directory.

## On this laptop

First, commit and push all code and documentation you want on the new laptop.
Do not commit `.env`.

```bash
git status
git push -u origin HEAD
```

Inspect the private data that will move:

```bash
python3 scripts/transfer_workspace.py inventory
```

Export it to an empty directory on an encrypted external drive or an approved
private cloud-sync folder:

```bash
python3 scripts/transfer_workspace.py export \
  /Volumes/TRANSFER/polisim-research-assets
python3 scripts/transfer_workspace.py verify \
  /Volumes/TRANSFER/polisim-research-assets
```

The export is a normal directory so interrupted external-drive or cloud copies
can be resumed with the platform's file-copy tools. Keep
`workspace-transfer-manifest.json` beside the `payload/` directory.

## On the new laptop

Clone the Git repository and switch to the branch you pushed:

```bash
git clone git@github.com:Jhsiehm/SandboxExperiment.git
cd SandboxExperiment
git switch <your-branch>
```

Restore the private assets. Existing identical files are skipped; differing
files stop the import instead of being overwritten.

```bash
python3 scripts/transfer_workspace.py import \
  /path/to/polisim-research-assets
```

Only use `--replace` if you have inspected the conflict and deliberately want
the bundle's file to replace the local one.

Create a new environment instead of moving `.venv` between machines:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Add API keys to the new `.env` from a password manager or your organization's
approved secret store. Never put API keys in the transfer bundle or Git. On a
work-managed laptop, confirm that local third-party datasets and model-provider
keys are allowed by company policy before importing them.

Verify the restored project:

```bash
psbx practice status --epoch e2012
pytest -q
python -m compileall -q src leaderboard
```

## If you do not transfer the private bundle

A clean checkout still supports deterministic provider-free practice:

```bash
psbx practice prepare --epoch e2012
```

The larger research inputs can be downloaded again from the checked-in source
registries and checksum pins:

```bash
psbx corpus sync-surveys --epoch e2012 --rebuild
psbx population sync-census --execute
psbx population verify-census
psbx elections sync-federal --years 1982-2024 --execute --max-total-mb 1000
```

Generated real-geography populations require the normalization and build steps
described in `docs/TRACK_B_ARCHITECTURE.md`. Sealed or registration-gated data
cannot be recreated automatically and should come from the private bundle only
when its license and workplace policy permit the transfer.

## Day-to-day work on two laptops

- Use a Git branch per piece of code work; pull before starting and push when
  stopping on either laptop.
- Treat downloaded source inputs as immutable. Transfer them once, then use the
  manifest to verify them.
- Give new experiments unique run IDs. If a run must move between laptops,
  create a fresh bundle after the run completes.
- If research data needs to sync frequently, graduate the bundle to DVC or an
  object store approved by your workplace. Keep Git as the source of truth for
  code and metadata.
