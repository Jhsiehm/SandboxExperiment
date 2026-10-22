"""Check prior experiment artifacts against the cleanup baseline without modifying them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "reports/implementation-audit-20261020"
    baseline = json.loads((folder / "baseline.json").read_text())
    changed = []
    for name, expected in baseline["frozen_artifact_sha256"].items():
        path = root / name
        if not path.is_file():
            changed.append({"path": name, "reason": "missing"})
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            changed.append({"path": name, "reason": "content changed"})
    result = {
        "checked_prior_artifacts": len(baseline["frozen_artifact_sha256"]),
        "changed_prior_artifacts": changed,
        "verified": not changed,
        "scope": "Byte preservation only; does not independently establish scientific validity.",
    }
    (folder / "frozen-integrity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
