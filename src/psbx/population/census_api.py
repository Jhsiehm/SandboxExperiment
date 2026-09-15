"""Cache-first Census API helper.

Network access is opt-in and intended only for controlled population-data construction. It must
never be used by an agent at forecast runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

MAX_CENSUS_RESPONSE_BYTES = 20_000_000
_DATASET = re.compile(r"\d{4}/[A-Za-z0-9][A-Za-z0-9/_-]{0,127}")
_VARIABLE = re.compile(r"[A-Za-z0-9_]{1,80}")
_GEOGRAPHY = re.compile(r"[A-Za-z0-9 ()*:._-]{1,200}")


class CensusApiClient:
    def __init__(
        self,
        *,
        cache_root: str | Path = "data/census-cache/api",
        allow_network: bool = False,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.cache_root = Path(cache_root)
        self.allow_network = allow_network
        self.api_key = api_key or os.environ.get("CENSUS_API_KEY")
        self.timeout_s = timeout_s

    @staticmethod
    def _cache_key(url: str, params: list[tuple[str, str]]) -> str:
        payload = json.dumps([url, sorted(params)], separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _request_json(self, url: str, params: list[tuple[str, str]] | None = None):
        params = params or []
        key = self._cache_key(url, params)
        body_path = self.cache_root / f"{key}.json"
        meta_path = self.cache_root / f"{key}.meta.json"
        if body_path.exists():
            if body_path.stat().st_size > MAX_CENSUS_RESPONSE_BYTES:
                raise RuntimeError("cached Census response exceeds the local size limit")
            return json.loads(body_path.read_text(encoding="utf-8"))
        if not self.allow_network:
            raise RuntimeError(
                "Census network access is disabled and no matching cache entry exists. "
                "Run a controlled sync with allow_network=True."
            )
        request_params = list(params)
        if self.api_key:
            request_params.append(("key", self.api_key))
        try:
            with httpx.Client(timeout=self.timeout_s, follow_redirects=False) as client:
                response = client.get(url, params=request_params)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Census API request failed: {type(exc).__name__}"
            ) from None
        if 300 <= response.status_code < 400:
            raise RuntimeError("Census API redirect refused to protect the API credential")
        if response.status_code >= 400:
            raise RuntimeError(f"Census API request failed with status {response.status_code}")
        if len(response.content) > MAX_CENSUS_RESPONSE_BYTES:
            raise RuntimeError("Census API response exceeds the local size limit")
        data = response.json()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        body_temp = body_path.with_suffix(".json.tmp")
        meta_temp = meta_path.with_suffix(".json.tmp")
        body_temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(body_temp, body_path)
        meta_temp.write_text(
            json.dumps(
                {
                    "url": url,
                    # Cache provenance must never persist a Census API key.
                    "params": params,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(body_path.read_bytes()).hexdigest(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(meta_temp, meta_path)
        return data

    def query(
        self,
        *,
        dataset: str,
        variables: Iterable[str],
        for_clause: str,
        in_clauses: Iterable[str] = (),
    ) -> pd.DataFrame:
        normalized_dataset = dataset.strip("/")
        if not _DATASET.fullmatch(normalized_dataset):
            raise ValueError("unsafe Census dataset identifier")
        url = f"https://api.census.gov/data/{normalized_dataset}"
        get_fields = [str(value) for value in variables]
        if "NAME" not in get_fields:
            get_fields.insert(0, "NAME")
        if not get_fields or any(not _VARIABLE.fullmatch(value) for value in get_fields):
            raise ValueError("unsafe Census variable identifier")
        clauses = [for_clause, *in_clauses]
        if any(not _GEOGRAPHY.fullmatch(str(clause)) for clause in clauses):
            raise ValueError("unsafe Census geography clause")
        params: list[tuple[str, str]] = [("get", ",".join(get_fields)), ("for", for_clause)]
        params.extend(("in", clause) for clause in clauses[1:])
        data = self._request_json(url, params)
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError("unexpected Census API response shape")
        header = data[0]
        if not isinstance(header, list):
            raise ValueError("unexpected Census API header")
        return pd.DataFrame(data[1:], columns=header)

    def group_metadata(self, *, dataset: str, group: str) -> dict:
        normalized_dataset = dataset.strip("/")
        if not _DATASET.fullmatch(normalized_dataset) or not _VARIABLE.fullmatch(group):
            raise ValueError("unsafe Census dataset or group identifier")
        url = (
            f"https://api.census.gov/data/{normalized_dataset}/groups/"
            f"{group}.json"
        )
        data = self._request_json(url)
        if not isinstance(data, dict) or "variables" not in data:
            raise ValueError("unexpected Census group metadata response")
        return data
