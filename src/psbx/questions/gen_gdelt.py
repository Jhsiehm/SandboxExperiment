"""Geopolitical questions: pre-cutoff mention stream as signal, post-cutoff events as truth."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from psbx.io import read_json
from psbx.questions.base import QuestionGenerator
from psbx.schemas import Epoch, PriorSignal, Question


class GdeltGenerator(QuestionGenerator):
    source_name = "gen_gdelt"

    def generate(self, epoch: Epoch, limit: int) -> Iterator[Question]:
        payload = read_json("data/sources/gdelt_e2012.json")
        emitted = 0
        for item in payload["items"]:
            if emitted >= limit:
                return
            if int(item.get("mentions_pre_cutoff") or 0) < 200:
                continue
            resolution = date.fromisoformat(item["resolution_date"])
            if resolution > epoch.resolution_window_end:
                continue
            yield Question(
                id=f"gdelt-{item['id']}",
                epoch_id=epoch.id,
                category="geopolitical",
                text=item["text"],
                resolution_criteria=item["resolution_criteria"],
                cutoff_date=epoch.cutoff_date,
                resolution_date=resolution,
                ground_truth=bool(item["ground_truth"]),
                generator=self.source_name,
                source_url=item.get("source_url"),
                prior_signal=PriorSignal(
                    kind=item.get("prior_kind", "analyst_consensus"),
                    probability=float(item["prior"]),
                    source=item["prior_source"],
                ),
            )
            emitted += 1
