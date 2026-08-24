"""arXiv API client.

The other search engine `run`/`batch` accept, alongside `serp.py`'s
SearchApi.io-backed ones. arXiv publishes its own Atom feed
(https://export.arxiv.org/api_basics) — free, keyless, and structured, so this
engine needs no `SEARCHAPI_API_KEY`. `SCRAPINGBEE_API_KEY` is still used
downstream in `cli.cmd_run` to fetch and archive whatever URL a hit resolves
to, exactly as for any other source.

Usage policy: no more than one request every three seconds, one connection at
a time. `fetch_page` sleeps before every page after the first to honour that;
nothing here enforces it across separate queries in a batch, which is a
courtesy gap the codebase already accepts elsewhere (`cmd_run`'s `--delay`
is the same kind of best-effort pacing, not a hard guarantee).
"""

from __future__ import annotations

import time
from xml.etree import ElementTree

import httpx

from .serp import SerpHit

ARXIV_API = "http://export.arxiv.org/api/query"
RESULTS_PER_PAGE = 10
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MIN_REQUEST_INTERVAL = 3.0

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivError(RuntimeError):
    pass


def _text(entry: ElementTree.Element, tag: str) -> str | None:
    raw = entry.findtext(f"{ATOM_NS}{tag}")
    if raw is None:
        return None
    normalized = " ".join(raw.split())
    return normalized or None


def _pdf_link(entry: ElementTree.Element) -> str | None:
    """The direct PDF, when arXiv offers one — full text beats an abstract."""
    for link in entry.findall(f"{ATOM_NS}link"):
        if link.get("title") == "pdf" and link.get("href"):
            return link.get("href")
    return None


def parse_entries(
    xml_text: str, page: int, *, results_per_page: int = RESULTS_PER_PAGE
) -> list[SerpHit]:
    """Turn one arXiv Atom response into hits. Pure — no I/O, so it is
    testable against a recorded fixture, matching `serp.parse_organic`."""
    root = ElementTree.fromstring(xml_text)
    hits: list[SerpHit] = []
    for position, entry in enumerate(root.findall(f"{ATOM_NS}entry"), start=1):
        raw_url = _pdf_link(entry) or _text(entry, "id")
        if not raw_url:
            continue
        hits.append(
            SerpHit(
                page=page,
                position=position,
                global_rank=(page - 1) * results_per_page + position,
                raw_url=raw_url,
                title=_text(entry, "title"),
                snippet=_text(entry, "summary"),
                displayed_link="arxiv.org",
            )
        )
    return hits


def fetch_page(
    query: str,
    page: int,
    *,
    results_per_page: int = RESULTS_PER_PAGE,
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> str:
    """Fetch one arXiv API page as raw Atom XML. Parsing is `parse_entries`'s
    job, so a recorded fixture can be replayed without a network call."""
    params = {
        "search_query": f"all:{query}",
        "start": str((page - 1) * results_per_page),
        "max_results": str(results_per_page),
    }
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        if page > 1:
            time.sleep(MIN_REQUEST_INTERVAL)
        for attempt in range(max_retries):
            response = client.get(ARXIV_API, params=params)
            if response.status_code == 200:
                return response.text
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
            raise ArxivError(
                f"arXiv API returned HTTP {response.status_code} for page {page}: "
                f"{response.text[:200]}"
            )
        raise ArxivError(f"arXiv API still failing after {max_retries} attempts")
    finally:
        if owned:
            client.close()
