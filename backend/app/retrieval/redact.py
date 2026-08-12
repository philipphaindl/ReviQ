"""Keep API keys out of stored text.

Error strings from this tool do not stay in a terminal: they are written to
`snapshots.fetch_error`, exported to CSV, printed in the Markdown retrieval
report, and — once a run is driven from a web UI — rendered in a browser. Any
one of those is a place a credential must never reach.

The ScrapingBee key travels as a *query parameter*, so it is part of a request
URL rather than a header. httpx does not put the URL into the string form of
its ordinary transport errors, so no leak is demonstrated today; this module
exists so that the property does not depend on that continuing to hold, nor on
what a third party chooses to echo back in an error body.

Redaction is deliberately dumb: exact substring replacement, no parsing. A
smarter version would have cases where it does not fire.
"""

from __future__ import annotations

import os

REDACTED = "[REDACTED]"

# Environment variables holding credentials this tool sends anywhere.
SECRET_ENV_VARS: tuple[str, ...] = (
    "SEARCHAPI_API_KEY",
    "SCRAPINGBEE_API_KEY",
    "ANTHROPIC_API_KEY",
)

# Below this length a "secret" is more likely to be an accident (an empty or
# placeholder value) than a credential, and replacing it would corrupt
# unrelated text. Real keys from all three providers are far longer.
MIN_SECRET_LENGTH = 8


def scrub(text: str | None, *secrets: str | None) -> str | None:
    """Replace every occurrence of each secret in `text`.

    Passing no secrets falls back to the values currently in the environment,
    which is what callers storing an error string want: they should not have
    to know which credentials exist.
    """
    if not text:
        return text

    values = secrets if secrets else tuple(os.environ.get(v) for v in SECRET_ENV_VARS)
    for secret in values:
        if secret and len(secret) >= MIN_SECRET_LENGTH:
            text = text.replace(secret, REDACTED)
    return text
