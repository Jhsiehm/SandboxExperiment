from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from psbx.paths import resolve

T = TypeVar("T", bound=BaseModel)


def write_jsonl(path: str | Path, rows: Iterable[BaseModel]) -> Path:
    dest = resolve(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.model_dump_json() + "\n")
    return dest


def read_jsonl(path: str | Path, model: type[T]) -> list[T]:
    src = resolve(path)
    rows: list[T] = []
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(model.model_validate_json(line))
    return rows


def iter_jsonl(path: str | Path, model: type[T]) -> Iterator[T]:
    with resolve(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield model.model_validate_json(line)


def write_json(path: str | Path, payload: BaseModel | dict) -> Path:
    dest = resolve(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    dest.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return dest


def read_json(path: str | Path) -> dict:
    return json.loads(resolve(path).read_text(encoding="utf-8"))
