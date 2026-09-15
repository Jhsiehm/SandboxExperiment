"""ALFRED vintage series questions. Live FRED API when FRED_API_KEY is set."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx

from psbx.io import read_json
from psbx.questions.base import QuestionGenerator
from psbx.schemas import Epoch, PriorSignal, Question

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"
MONTHS = (
    "January February March April May June July August "
    "September October November December"
).split()


def _month_name(obs: date) -> str:
    return f"{MONTHS[obs.month - 1]} {obs.year}"


def _compare(value: float, threshold: float, op: str) -> bool:
    return value >= threshold if op == "gte" else value > threshold


def _phrase(op: str) -> str:
    return "meet or exceed" if op == "gte" else "exceed"


class FredGenerator(QuestionGenerator):
    source_name = "gen_fred"

    def generate(self, epoch: Epoch, limit: int) -> Iterator[Question]:
        series_rows = self._load_series(epoch)
        emitted = 0
        for series in series_rows:
            for item in series.get("items", []):
                if emitted >= limit:
                    return
                obs = date.fromisoformat(item["obs_date"])
                resolution = date.fromisoformat(item["resolution_date"])
                if resolution > epoch.resolution_window_end:
                    continue
                if obs <= epoch.cutoff_date and resolution <= epoch.cutoff_date:
                    continue
                op = item.get("op", "gt")
                value = float(item["value"])
                threshold = float(item["threshold"])
                truth = _compare(value, threshold, op)
                last = series["cutoff_last"]
                qid = f"fred-{series['id'].lower()}-{obs.strftime('%Y-%m')}"
                verb = _phrase(op)
                text = (
                    f"Will the initial print of {series['title']} ({series['id']}) "
                    f"for {_month_name(obs)} {verb} {threshold} {series['units']}?"
                )
                yield Question(
                    id=qid,
                    epoch_id=epoch.id,
                    category="economic",
                    text=text,
                    resolution_criteria=(
                        f"Resolves YES if the ALFRED vintage of {series['id']} for "
                        f"{obs.isoformat()} "
                        f"as of {item['release_vintage']} {verb}s {threshold}. "
                        f"Observed vintage value={value}. Source: {series['source_url']}."
                    ),
                    cutoff_date=epoch.cutoff_date,
                    resolution_date=resolution,
                    ground_truth=truth,
                    generator=self.source_name,
                    source_url=series["source_url"],
                    prior_signal=PriorSignal(
                        kind="analyst_consensus",
                        probability=float(item["prior"]),
                        source=(
                            f"{series['consensus']}; last known "
                            f"{last['obs_date']}={last['value']}"
                        ),
                    ),
                )
                emitted += 1

    def _load_series(self, epoch: Epoch) -> list[dict[str, Any]]:
        snapshot = read_json("data/sources/alfred_e2012.json")
        key = os.environ.get("FRED_API_KEY")
        if not key:
            return list(snapshot["series"])
        refreshed: list[dict[str, Any]] = []
        for series in snapshot["series"]:
            try:
                refreshed.append(_refresh_series(series, epoch, key))
            except Exception:
                refreshed.append(series)
        return refreshed


def _refresh_series(series: dict[str, Any], epoch: Epoch, api_key: str) -> dict[str, Any]:
    """Re-read vintages from ALFRED; keep snapshot thresholds and priors."""
    items = []
    with httpx.Client(timeout=30.0) as client:
        for item in series["items"]:
            vintage = item["release_vintage"]
            params = {
                "series_id": series["id"],
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": vintage,
                "realtime_end": vintage,
                "observation_start": item["obs_date"],
                "observation_end": item["obs_date"],
            }
            resp = client.get(FRED_OBS, params=params)
            resp.raise_for_status()
            obs = resp.json().get("observations") or []
            if not obs or obs[0].get("value") in {".", ""}:
                items.append(item)
                continue
            updated = dict(item)
            updated["value"] = float(obs[0]["value"])
            items.append(updated)
    out = dict(series)
    out["items"] = items
    return out
