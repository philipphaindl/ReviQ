"""SearchApi.io client.

Called directly over httpx rather than through a vendor SDK: the request is a
plain GET, and keeping it explicit means the raw response stays visible for
provenance.

Note on result depth: Google deprecated the `num` parameter on 2025-09-11, so
`engine=google` returns 10 results per request and depth comes from paging.
See docs/retrieval/PLAN.md R2.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .redact import scrub

ENDPOINT = "https://www.searchapi.io/api/v1/search"
RESULTS_PER_PAGE = 10

# Google occasionally returns its own redirect wrapper as an organic result
# (https://www.google.com/goto?url=CAESY...). These are not sources: the target
# is an opaque token, ScrapingBee rejects the host outright, and each one costs
# a wasted fetch. Observed three times in a single 20-query pilot.
NON_SOURCE_HOSTS: tuple[str, ...] = (
    "google.com/goto", "google.com/url", "google.com/aclk",
    "googleadservices.com", "webcache.googleusercontent.com",
)
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class SerpHit:
    page: int
    position: int
    global_rank: int
    raw_url: str
    title: str | None
    snippet: str | None
    displayed_link: str | None


class SerpError(RuntimeError):
    pass


def parse_organic(payload: dict, page: int) -> list[SerpHit]:
    """Turn one SearchApi response into hits. Pure — no I/O, so it is testable
    against a recorded fixture."""
    hits: list[SerpHit] = []
    for entry in payload.get("organic_results") or []:
        link = entry.get("link")
        if not link or is_non_source(link):
            continue
        # `position` is reported per page by the API; global_rank is what a
        # methods section should cite.
        position = int(entry.get("position") or len(hits) + 1)
        hits.append(
            SerpHit(
                page=page,
                position=position,
                global_rank=(page - 1) * RESULTS_PER_PAGE + position,
                raw_url=link,
                title=entry.get("title"),
                snippet=entry.get("snippet"),
                displayed_link=entry.get("displayed_link") or entry.get("domain"),
            )
        )
    return hits


def is_non_source(url: str) -> bool:
    """True for search-engine plumbing that is not a retrievable document."""
    lowered = url.lower()
    return any(marker in lowered for marker in NON_SOURCE_HOSTS)


def search_id_of(payload: dict) -> str | None:
    """The provider-side receipt for this query, kept as external provenance."""
    metadata = payload.get("search_metadata") or {}
    return metadata.get("id")


def fetch_page(
    api_key: str,
    query: str,
    page: int,
    *,
    engine: str = "google",
    gl: str | None = None,
    hl: str | None = None,
    location: str | None = None,
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> dict:
    """Fetch one SERP page. The API key travels in the Authorization header so
    it does not end up in proxy logs or in `search_metadata.request_url`."""
    params: dict[str, str] = {"engine": engine, "q": query, "page": str(page)}
    if gl:
        params["gl"] = gl
    if hl:
        params["hl"] = hl
    if location:
        params["location"] = location

    headers = {"Authorization": f"Bearer {api_key}"}
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        for attempt in range(max_retries):
            response = client.get(ENDPOINT, params=params, headers=headers)
            if response.status_code == 200:
                return response.json()
            # 429/5xx are worth retrying; anything else is a real error.
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
            # The body is a third party's text and ends up in a stored error
            # message. Scrub before it travels any further — see redact.py.
            raise SerpError(scrub(
                f"SearchApi returned HTTP {response.status_code} for page {page}: "
                f"{response.text[:200]}",
                api_key,
            ))
        raise SerpError(f"SearchApi still failing after {max_retries} attempts")
    finally:
        if owned:
            client.close()
