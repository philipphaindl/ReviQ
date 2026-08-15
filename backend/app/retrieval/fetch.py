"""ScrapingBee client.

Called directly over httpx rather than through the vendor SDK, because the SDK
hides the `Spb-*` response headers — and those headers are exactly the
provenance this tool exists to record:

    Spb-Resolved-Url         final URL after redirects
    Spb-Initial-Status-Code  the FIRST status in the redirect chain (verified:
                             http://github.com reports 301, not the final 200)
    Spb-Cost                 credits consumed

Note that ScrapingBee does not report the origin's *final* status. When it
returns 200 with a body, the retrieval succeeded; what the last hop answered
is not observable, so it is not claimed anywhere.

`render_js` defaults to true at the API and costs 5 credits instead of 1. We
send render_js=false unless asked otherwise; see docs/retrieval/PLAN.md §5.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .redact import scrub

ENDPOINT = "https://app.scrapingbee.com/api/v1/"
# Generous: JS rendering plus a slow origin can legitimately take a while.
TIMEOUT = httpx.Timeout(120.0, connect=15.0)


@dataclass
class FetchResult:
    requested_url: str
    content: bytes | None
    final_url: str | None
    origin_status_first: int | None  # FIRST status in the redirect chain
    proxy_status: int | None     # ScrapingBee's own status
    content_type: str | None
    credits_cost: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None and self.content is not None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def fetch_url(
    api_key: str,
    url: str,
    *,
    render_js: bool = False,
    premium_proxy: bool = False,
    stealth_proxy: bool = False,
    wait_ms: int | None = None,
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> FetchResult:
    """Retrieve one URL. Never raises for an unreachable target — a failed
    fetch is a recorded observation, not a crash, so the run continues and the
    failure stays visible in the CSV."""
    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
    }
    if premium_proxy:
        params["premium_proxy"] = "true"
    if wait_ms:
        # Milliseconds to wait after load before returning. A JS challenge that
        # reports "Verification successful. Waiting for ... to respond" has
        # already passed and merely needs time to redirect to the real content
        # — a timing problem, not a block, and far cheaper to fix than by
        # escalating to stealth proxies.
        params["wait"] = str(wait_ms)
    if stealth_proxy:
        # Last resort for JS challenge walls (Cloudflare "Just a moment...").
        # 75 credits. Only reach for it once premium has demonstrably failed.
        params["stealth_proxy"] = "true"

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        last_error = None
        for attempt in range(max_retries):
            try:
                response = client.get(ENDPOINT, params=params)
            except httpx.HTTPError as exc:
                # The ScrapingBee key is a query parameter, so it is part of
                # the request URL. httpx does not put the URL into the string
                # form of its transport errors today — scrub anyway, because
                # this string is stored, exported and eventually rendered in
                # a browser, and that property should not have to hold.
                last_error = scrub(f"transport error: {exc}", api_key)
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                break

            headers = response.headers
            if response.status_code == 200:
                return FetchResult(
                    requested_url=url,
                    content=response.content,
                    final_url=headers.get("Spb-Resolved-Url") or url,
                    origin_status_first=_int_or_none(headers.get("Spb-Initial-Status-Code")),
                    proxy_status=response.status_code,
                    content_type=headers.get("Content-Type"),
                    credits_cost=_int_or_none(headers.get("Spb-Cost")),
                    error=None,
                )

            last_error = scrub(
                f"HTTP {response.status_code}: {response.text[:200]}", api_key
            )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue

            return FetchResult(
                requested_url=url,
                content=None,
                final_url=headers.get("Spb-Resolved-Url"),
                origin_status_first=_int_or_none(headers.get("Spb-Initial-Status-Code")),
                proxy_status=response.status_code,
                content_type=None,
                credits_cost=_int_or_none(headers.get("Spb-Cost")),
                error=last_error,
            )

        return FetchResult(
            requested_url=url, content=None, final_url=None, origin_status_first=None,
            proxy_status=None, content_type=None, credits_cost=None,
            error=last_error or "unknown fetch failure",
        )
    finally:
        if owned:
            client.close()
