"""DuckDB warehouse for questions and predictions."""

from __future__ import annotations

from pathlib import Path

import duckdb

from psbx.paths import resolve
from psbx.schemas import Prediction, Question


def connect(path: str | Path = "data/runs/psbx.duckdb") -> duckdb.DuckDBPyConnection:
    dest = resolve(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(dest))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id VARCHAR PRIMARY KEY,
            payload JSON
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            run_id VARCHAR,
            question_id VARCHAR,
            model_id VARCHAR,
            payload JSON,
            PRIMARY KEY (run_id, question_id, model_id)
        )
        """
    )
    return con


def upsert_questions(questions: list[Question], path: str | Path = "data/runs/psbx.duckdb") -> None:
    con = connect(path)
    for q in questions:
        con.execute(
            "INSERT OR REPLACE INTO questions VALUES (?, ?)",
            [q.id, q.model_dump_json()],
        )
    con.close()


def upsert_predictions(preds: list[Prediction], path: str | Path = "data/runs/psbx.duckdb") -> None:
    con = connect(path)
    for p in preds:
        con.execute(
            "INSERT OR REPLACE INTO predictions VALUES (?, ?, ?, ?)",
            [p.run_id, p.question_id, p.model_id, p.model_dump_json()],
        )
    con.close()
