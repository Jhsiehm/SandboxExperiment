"""GDELT event + mention ingest. Fixture path for Phase 1; live CSV optional."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from urllib.request import urlopen

from psbx.io import read_json
from psbx.schemas import Document, Epoch

UTC = timezone.utc
GDELT_EVENTS = "http://data.gdeltproject.org/events/{yyyymmdd}.export.CSV.zip"


def load_fixture_mentions() -> list[dict]:
    payload = read_json("data/sources/gdelt_e2012.json")
    return list(payload["items"])


def ingest_gdelt(epoch: Epoch, live: bool = False) -> list[Document]:
    """Structured events become documents only when live=True.

    Question generation uses the fixture mention stream regardless.
    """
    if not live:
        return []
    docs: list[Document] = []
    # Sample a handful of daily files just before cutoff so a live rebuild works.
    day = epoch.cutoff_date
    stamp = day.strftime("%Y%m%d")
    url = GDELT_EVENTS.format(yyyymmdd=stamp)
    try:
        raw = urlopen(url, timeout=60).read()  # noqa: S310 - pinned GDELT URL
    except Exception:
        return []
    import zipfile

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as fh:
            reader = csv.reader(
                io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                delimiter="\t",
            )
            for i, row in enumerate(reader):
                if i >= 25:
                    break
                if len(row) < 58:
                    continue
                text = " ".join(row[57:61])
                if len(text) < 40:
                    continue
                docs.append(
                    Document(
                        id=f"gdelt-{stamp}-{i}",
                        url=(
                            row[57]
                            if row[57].startswith("http")
                            else f"https://gdeltproject.org/event/{row[0]}"
                        ),
                        outlet="GDELT",
                        published_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
                        title=text[:160],
                        text=text[:5000],
                        source_type="wire",
                        prominence=0.0,
                    )
                )
    return docs
