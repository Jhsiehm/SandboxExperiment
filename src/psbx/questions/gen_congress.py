"""Legislative and nomination outcome questions from GovTrack/Congress snapshots."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from psbx.io import read_json
from psbx.questions.base import QuestionGenerator
from psbx.schemas import Epoch, PriorSignal, Question


class CongressGenerator(QuestionGenerator):
    source_name = "gen_congress"

    def generate(self, epoch: Epoch, limit: int) -> Iterator[Question]:
        payload = read_json("data/sources/congress_e2012.json")
        emitted = 0
        for item in payload["items"]:
            if emitted >= limit:
                return
            introduced = date.fromisoformat(item["introduced"])
            resolution = date.fromisoformat(item["resolution_date"])
            if resolution > epoch.resolution_window_end:
                continue
            # Must have been a live instrument by cutoff, or a continuation
            # of a pre-cutoff fight (tax rates, sequester, immigration).
            if introduced > epoch.cutoff_date and "112th" in item.get("source_url", ""):
                continue
            yield Question(
                id=f"congress-{item['id']}",
                epoch_id=epoch.id,
                category="legislative",
                text=item["text"],
                resolution_criteria=item["resolution_criteria"],
                cutoff_date=epoch.cutoff_date,
                resolution_date=resolution,
                ground_truth=bool(item["ground_truth"]),
                generator=self.source_name,
                source_url=item.get("source_url"),
                prior_signal=PriorSignal(
                    kind=item.get("prior_kind", "base_rate"),
                    probability=float(item["prior"]),
                    source=item["prior_source"],
                ),
            )
            emitted += 1
