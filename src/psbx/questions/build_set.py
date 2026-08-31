from __future__ import annotations

from pathlib import Path

from psbx.config import load_run
from psbx.io import write_jsonl
from psbx.paths import resolve
from psbx.questions.filters import filter_questions
from psbx.questions.gen_congress import CongressGenerator
from psbx.questions.gen_fred import FredGenerator
from psbx.questions.gen_gdelt import GdeltGenerator
from psbx.schemas import Epoch, Question

GENERATORS = [FredGenerator(), CongressGenerator(), GdeltGenerator()]


def build_questions(epoch: Epoch, limit: int, run_path: str = "config/run.yaml") -> list[Question]:
    run = load_run(run_path)
    raw: list[Question] = []
    per = max(limit, run.n_questions)
    for gen in GENERATORS:
        raw.extend(list(gen.generate(epoch, limit=per)))
    filtered = filter_questions(
        raw,
        resolution_window_end=epoch.resolution_window_end,
        category_balance=run.category_balance or None,
    )
    if len(filtered) > limit:
        filtered = filtered[:limit]
    return filtered


def write_question_set(epoch: Epoch, questions: list[Question]) -> Path:
    dest = resolve(f"data/questions/{epoch.id}.jsonl")
    write_jsonl(dest, questions)
    return dest
