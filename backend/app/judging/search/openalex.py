"""A small OpenAlex client for the quasi-gold standard and hit counts.

Plain httpx, like creel's SearchApi client: the requests are simple GETs, and
keeping them explicit keeps the raw response visible. The parser is pure and
tested against a response saved to `tests/judging/fixtures/`; that fixture is
built from OpenAlex's documented work schema and is replaced by a recorded
response on the first run with network access (PLAN.md, section 8).

The contact address goes into `mailto` (OpenAlex's "polite pool"); it comes
from `OPENALEX_EMAIL` and is the only identifying value sent.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

BASE = "https://api.openalex.org"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class OpenAlexError(RuntimeError):
    pass


@dataclass(frozen=True)
class Work:
    openalex_id: str
    doi: str | None
    title: str | None
    abstract: str | None
    keywords: str | None
    year: int | None
    work_type: str | None
    referenced_works: tuple[str, ...] = field(default_factory=tuple)
    is_oa: bool = False
    oa_url: str | None = None


def short_id(url_or_id: str) -> str:
    """'https://openalex.org/W123' -> 'W123'."""
    return url_or_id.rstrip("/").rsplit("/", 1)[-1]


def normalise_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi or None


def abstract_from_index(index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as an inverted index (word -> positions)."""
    if not index:
        return None
    positions: dict[int, str] = {}
    for word, places in index.items():
        for place in places:
            positions[place] = word
    return " ".join(positions[i] for i in sorted(positions)) or None


def parse_work(payload: dict) -> Work:
    keywords = [k.get("display_name") for k in payload.get("keywords") or []
                if k.get("display_name")]
    oa = payload.get("open_access") or {}
    return Work(
        openalex_id=short_id(payload["id"]),
        doi=normalise_doi(payload.get("doi")),
        title=payload.get("title") or payload.get("display_name"),
        abstract=abstract_from_index(payload.get("abstract_inverted_index")),
        keywords="; ".join(keywords) or None,
        year=payload.get("publication_year"),
        work_type=payload.get("type"),
        referenced_works=tuple(short_id(w) for w in payload.get("referenced_works") or []),
        is_oa=bool(oa.get("is_oa")),
        oa_url=oa.get("oa_url"),
    )


class OpenAlex:
    def __init__(self, client: httpx.Client | None = None, mailto: str | None = None,
                 delay: float = 0.1) -> None:
        self._client = client or httpx.Client(timeout=TIMEOUT)
        self._mailto = mailto if mailto is not None else os.environ.get("OPENALEX_EMAIL")
        self._delay = delay

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        params = dict(params or {})
        if self._mailto:
            params["mailto"] = self._mailto
        for attempt in range(3):
            response = self._client.get(BASE + path, params=params)
            if response.status_code == 200:
                if self._delay:
                    time.sleep(self._delay)
                return response.json()
            if response.status_code == 404:
                raise OpenAlexError(f"not found: {path}")
            if response.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise OpenAlexError(f"OpenAlex returned HTTP {response.status_code} for {path}")
        raise OpenAlexError(f"OpenAlex still failing for {path}")

    def work_by_doi(self, doi: str) -> Work:
        return parse_work(self._get(f"/works/doi:{quote(normalise_doi(doi) or '', safe='/')}"))

    def work_by_id(self, openalex_id: str) -> Work:
        return parse_work(self._get(f"/works/{short_id(openalex_id)}"))

    def work_by_title(self, title: str) -> Work | None:
        """Best match for a title; None if OpenAlex has nothing. The caller
        compares titles before trusting the match."""
        payload = self._get("/works", {"filter": f"title.search:{title.replace(',', ' ')}",
                                       "per-page": "1"})
        results = payload.get("results") or []
        return parse_work(results[0]) if results else None

    def count(self, search_filter: str) -> int:
        """`meta.count` for a filter value; one cheap request."""
        payload = self._get("/works", {"filter": search_filter, "per-page": "1"})
        return int(payload["meta"]["count"])
