from __future__ import annotations

import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ")
    return normalize_text(text)


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text).strip()


def document_id_for(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def parse_published_at(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    from dateutil import parser

    return parser.isoparse(value)
