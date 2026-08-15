"""URL canonicalisation and the deduplication key.

Deliberately hand-written on top of `urllib.parse` rather than delegated to a
library such as courlan. A canonicaliser that strips query parameters too
eagerly silently merges distinct documents,
and in grey literature parameters are often content-bearing (`?id=`, `?doc=`,
`?report=`). That failure mode is invisible in the output — you simply end up
with fewer sources and no error.

So the rule here is: normalise only what is provably not content-bearing, keep
everything else, and keep the blocklist short enough to quote in a methods
section. `raw_url` is stored alongside the canonical form in every case, so no
normalisation decision is irreversible.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Analytics and click-attribution parameters. None of these change which
# document is served; all of them fragment the deduplication key.
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        # Google / Urchin
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
        "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
        # Facebook / Microsoft / Twitter / Mailchimp / HubSpot / Matomo
        "fbclid", "msclkid", "twclid", "igshid",
        "mc_cid", "mc_eid",
        "_hsenc", "_hsmi", "hsCtaTracking",
        "mtm_source", "mtm_medium", "mtm_campaign", "mtm_keyword", "mtm_content",
        "pk_source", "pk_medium", "pk_campaign", "pk_keyword", "pk_content",
        # Misc referral noise
        "ref", "referrer", "source", "spm", "scid", "yclid", "s_cid", "cmpid",
    }
)

# Hosts where a trailing "index.*" is a synonym for the directory itself.
_INDEX_FILENAMES = ("index.html", "index.htm", "index.php", "default.html", "default.htm")

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def canonicalize(url: str) -> str:
    """Return the deduplication key for a URL.

    Applied, in order:
      * strip surrounding whitespace
      * lowercase scheme and host (path and query stay case-sensitive — they
        are case-sensitive on most origin servers)
      * drop the default port for the scheme
      * drop the fragment (never sent to the server, so never content-bearing)
      * drop a leading "www." (a near-universal alias)
      * drop tracking parameters, keep all others, and sort what remains so
        parameter order stops fragmenting the key
      * collapse a trailing index file to its directory
      * drop a single trailing slash, except on the bare root path

    Anything not listed is left untouched on purpose.
    """
    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    if host.startswith("www."):
        host = host[4:]

    netloc = host
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    path = parts.path or "/"
    for index_name in _INDEX_FILENAMES:
        if path.endswith("/" + index_name):
            path = path[: -len(index_name)]
            break
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))

    return urlunsplit((scheme, netloc, path, query, ""))


def host_of(url: str) -> str | None:
    """Hostname without a leading "www.".

    Deliberately not the registered domain: deriving that correctly needs the
    Public Suffix List (``bbc.co.uk`` has two suffix labels, ``bbc.com`` one),
    and a two-label heuristic would be quietly wrong for exactly the
    government and NGO domains grey literature lives on. Reporting the host is
    correct; reporting a guessed registered domain would not be.
    """
    host = urlsplit(url).hostname
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def is_fetchable(url: str) -> bool:
    """Reject anything that is not a plain http(s) resource."""
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname)
