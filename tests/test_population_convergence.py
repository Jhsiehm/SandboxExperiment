import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from psbx.population.convergence import parse_integer_list, run_convergence_experiment


def test_convergence_experiment_is_offline_deterministic_and_costed(tmp_path: Path):
    directory = tmp_path / "e2012" / "fixture-weighted"
    directory.mkdir(parents=True)
    cells = pd.DataFrame(
        {
            "cell_id": ["a", "b", "c", "d"],
            "age_band": ["18_24", "18_24", "65_plus", "65_plus"],
            "race_ethnicity": ["x", "y", "x", "y"],
            "population_weight": [10, 20, 30, 40],
        }
    )
    cells_path = directory / "representative_cells.csv"
    cells.to_csv(cells_path, index=False)
    digest = hashlib.sha256(cells_path.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "population_id": "fixture-weighted",
                "epoch_id": "e2012",
                "passed": True,
                "represented_population": 100,
                "representative_cells": 4,
                "output_sha256": {"representative_cells.csv": digest},
            }
        ),
        encoding="utf-8",
    )
    result = run_convergence_experiment(
        "fixture-weighted",
        population_root=tmp_path,
        budgets=[2, 4],
        seeds=[1, 2],
        dimensions=["age_band", "race_ethnicity"],
        input_tokens_per_call=100,
        output_tokens_per_call=20,
    )
    assert result["passed"] is True
    assert result["config"]["actual_llm_calls"] == 0
    assert {row["condition"] for row in result["summary"]} == {
        "2",
        "4",
        "full_representative_cells",
        "full_records",
    }
    assert (Path(result["output_dir"]) / "replications.csv").is_file()
    finite = [row for row in result["summary"] if row["condition"] in {"2", "4"}]
    assert all("max_between_seed_category_variance" in row for row in finite)
    assert all("p95_replication_max_dimension_tvd" in row for row in finite)
    second = run_convergence_experiment(
        "fixture-weighted",
        population_root=tmp_path,
        budgets=[2, 4],
        seeds=[1, 2],
        dimensions=["age_band", "race_ethnicity"],
        input_tokens_per_call=100,
        output_tokens_per_call=20,
    )
    assert second["status"] == "skipped_valid"
    summary_path = Path(result["output_dir"]) / "summary.csv"
    summary_path.unlink()
    repaired = run_convergence_experiment(
        "fixture-weighted",
        population_root=tmp_path,
        budgets=[2, 4],
        seeds=[1, 2],
        dimensions=["age_band", "race_ethnicity"],
        input_tokens_per_call=100,
        output_tokens_per_call=20,
    )
    assert repaired["status"] == "complete"
    assert summary_path.is_file()


def test_parse_integer_list_deduplicates_in_order():
    assert parse_integer_list("25,50,25,100") == [25, 50, 100]


def test_convergence_output_is_stable_across_python_hash_seeds(tmp_path: Path):
    directory = tmp_path / "e2012/fixture-weighted"
    directory.mkdir(parents=True)
    cells_path = directory / "representative_cells.csv"
    pd.DataFrame(
        {
            "cell_id": ["a", "b", "c", "d"],
            "dimension": ["z", "a", "m", "z"],
            "population_weight": [10, 20, 30, 40],
        }
    ).to_csv(cells_path, index=False)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "passed": True,
                "represented_population": 100,
                "representative_cells": 4,
                "output_sha256": {
                    "representative_cells.csv": hashlib.sha256(
                        cells_path.read_bytes()
                    ).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    code = (
        "from psbx.population.convergence import run_convergence_experiment;"
        f"run_convergence_experiment('fixture-weighted', population_root={str(tmp_path)!r},"
        "budgets=[5], seeds=[1,2,3,4,5], dimensions=['dimension'], force=True)"
    )
    hashes = []
    for hash_seed in ("1", "999"):
        environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            cwd=Path.cwd(),
            env=environment,
        )
        summary = next(directory.glob("experiments/*/summary.csv"))
        hashes.append(hashlib.sha256(summary.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1]
