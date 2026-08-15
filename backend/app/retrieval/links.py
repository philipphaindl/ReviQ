"""Outgoing-link extraction and the snowballing filter.

Snowballing in the Wohlin (2014) sense follows *citations* — curated,
semantically meaningful edges. An HTML link is not that. A typical page carries
50–200 outgoing links, and the overwhelming majority are navigation, footers,
social buttons and product pages. Following 10–20 arbitrary links per document
produces a corpus that is mostly noise, and at depth 2 the signal disappears
entirely.

So this module does not follow links; it *selects* them. Four rules, chosen to
be defensible in a methods section and cheap to state:

  1. **Links to PDFs are always kept.** In grey literature a linked PDF is
     almost always the document itself — a report, whitepaper or standard.
     This is the single highest-precision signal available without reading the
     target.
  2. **Otherwise, only off-host links.** Navigation, pagination and related-
     content links point back into the same host. An outbound link is the
     closest structural analogue to a citation.
  3. **Known noise is dropped** — social platforms, link shorteners, and the
     boilerplate paths every site carries (privacy, terms, careers, login).
  4. **A cap per source document**, PDFs first, so the cap never displaces the
     highest-value links.

The asymmetry is deliberate, as elsewhere in this tool: dropping a good link
costs a source, while keeping a bad one costs one fetch (1 credit) and a row
that screening will discard anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .urls import canonicalize, host_of, is_fetchable

# Platforms whose pages are posts, videos and profiles rather than documents.
# A retrieval here succeeds and still yields no article text, which is why
# `outcome.py` reads this set too: for those hosts an empty extraction is the
# expected result, not a tooling failure worth spending credits on again.
PLATFORM_HOSTS: frozenset[str] = frozenset({
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "pinterest.com", "reddit.com",
    "threads.net", "mastodon.social", "bsky.app", "t.me", "wa.me",
    "whatsapp.com", "vk.com", "xing.com", "weibo.com",
})

# Never a grey literature source. Matched on the host and its subdomains.
NOISE_HOSTS: frozenset[str] = PLATFORM_HOSTS | frozenset({
    # sharing / shorteners / trackers
    "addtoany.com", "sharethis.com", "addthis.com", "bit.ly", "goo.gl",
    "tinyurl.com", "ow.ly", "buff.ly", "doubleclick.net", "googletagmanager.com",
    # ubiquitous boilerplate targets
    "creativecommons.org", "w3.org", "gravatar.com", "wordpress.org",
    "adobe.com",  # "get acrobat reader"
})

# Path fragments that mark site furniture rather than content.
NOISE_PATH_MARKERS: tuple[str, ...] = (
    "/privacy", "/cookie", "/terms", "/legal", "/imprint", "/impressum",
    "/disclaimer", "/accessibility", "/contact", "/login", "/signin",
    "/sign-in", "/register", "/signup", "/subscribe", "/newsletter",
    "/careers", "/jobs", "/cart", "/checkout", "/sitemap", "/rss", "/feed",
    "/search?", "/share?", "/print", "/tag/", "/category/", "/author/",
)


@dataclass(frozen=True)
class Link:
    raw_href: str
    resolved_url: str
    canonical_url: str
    anchor_text: str
    is_pdf: bool


class _AnchorCollector(HTMLParser):
    """Collects (href, anchor text) pairs. Stdlib rather than lxml: this needs
    no more than <a href> and its text, and it keeps the dependency list short
    enough that the licence audit in docs/retrieval/decisions.md stays trivial."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def extract_anchors(html: bytes | str) -> list[tuple[str, str]]:
    """All (href, anchor text) pairs, unfiltered and unresolved."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    parser = _AnchorCollector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Malformed markup must never abort a run; whatever was collected
        # before the parser gave up is still usable.
        pass
    return parser.anchors


def _is_noise_host(host: str) -> bool:
    return any(host == noise or host.endswith("." + noise) for noise in NOISE_HOSTS)


def _looks_like_pdf(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith(".pdf")


def select_snowball_links(
    html: bytes | str,
    base_url: str,
    *,
    max_links: int = 20,
) -> list[Link]:
    """Apply the four rules and return at most `max_links` links, PDFs first.

    `base_url` should be the snapshot's resolved URL, so relative hrefs resolve
    against where the content actually came from rather than where it was
    requested.
    """
    source_host = host_of(base_url)
    pdfs: list[Link] = []
    others: list[Link] = []
    seen: set[str] = set()

    for raw_href, anchor_text in extract_anchors(html):
        href = raw_href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue

        resolved = urljoin(base_url, href)
        if not is_fetchable(resolved):
            continue

        target_host = host_of(resolved)
        if not target_host or _is_noise_host(target_host):
            continue

        canonical = canonicalize(resolved)
        if canonical in seen:
            continue

        is_pdf = _looks_like_pdf(resolved)
        if not is_pdf:
            # Rule 2: same-host links are navigation far more often than not.
            if target_host == source_host:
                continue
            # Rule 3: site furniture.
            lowered = resolved.lower()
            if any(marker in lowered for marker in NOISE_PATH_MARKERS):
                continue

        seen.add(canonical)
        link = Link(
            raw_href=raw_href,
            resolved_url=resolved,
            canonical_url=canonical,
            anchor_text=anchor_text or None,
            is_pdf=is_pdf,
        )
        (pdfs if is_pdf else others).append(link)

    # PDFs first so the cap never displaces the highest-precision links.
    return (pdfs + others)[:max_links]
