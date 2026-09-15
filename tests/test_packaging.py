from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_contains_viewer_package_and_static_assets(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env={**os.environ, "PIP_NO_INDEX": "1"},
        text=True,
    )

    wheel = next(tmp_path.glob("prediction_sandbox-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        packaged_files = set(archive.namelist())

    required_files = {
        "leaderboard/app.py",
        "leaderboard/static/app.css",
        "leaderboard/static/app.js",
        "leaderboard/static/index.html",
        "leaderboard/static/geography-map.js",
        "leaderboard/static/agents/openai.png",
        "leaderboard/static/fonts/LICENSE-IBM-PLEX.txt",
        "leaderboard/static/geography/e2012/manifest.json",
        "leaderboard/static/vendor/three/three.module.min.js",
    }
    assert required_files <= packaged_files
