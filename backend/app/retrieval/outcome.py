"""Why a retrieval did not yield a usable document.

`retrieval_status` says *what* happened — blocked, failed, empty. It does not
say *why*, and the difference decides two things a review cannot fudge:

  * **What the methods section may claim.** A publisher's anti-bot wall, a
    platform page that never carried article text, and a 404 are three
    different sentences. "39 retrievals failed" reads as a defective tool;
    "32 sources sat behind publisher access control, and were excluded as
    white literature" is a documented scope decision. Only the second is
    defensible, and the numbers behind it have to come from somewhere.

  * **What is worth spending credits on again.** Of the same 39, some would
    come back with rendering enabled and some never will. Without the
    distinction the only options are re-fetching everything or nothing.

The vocabulary below is therefore not a taxonomy for its own sake: every entry
earns its place by leading to a different sentence in a paper or a different
decision about money.

**Classification happens at read time, not at fetch time.** A reason is an
interpretation of facts already recorded — proxy status, blocked reason, media
type, host, extractor message — and the facts are immutable. Deriving it in
`report` and `export-json` rather than storing it means a corpus
retrieved months ago reclassifies under an improved classifier without a single
byte being fetched again, which is the same property `extractions` already has
against the WARC. It also needs no new column, and D20 is explicit that
schema.sql can add tables but not columns.

The classifier is deliberately conservative. It reads what the proxy and the
extractor reported and stops there; it does not sniff the archived bytes to
guess whether a page was client-rendered. A wrong guess here would be laundered
into a methods section as a fact, and `no_main_content` — honest about not
knowing — is the better failure mode.
"""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple

from .links import PLATFORM_HOSTS

# retrieval_status values. Also imported by interchange.py, which exports them.
OK = "ok"
BLOCKED = "blocked"
FAILED = "failed"
EMPTY = "empty"
NOT_FETCHED = "not_fetched"


class Remedy(NamedTuple):
    """What, if anything, would change the result of trying again.

    `action` is the operation that could help, and the distinction between the
    two non-null values matters financially: `refetch` spends ScrapingBee
    credits, `reextract` runs against bytes already sitting in the WARC and
    costs nothing. Collapsing them into one "retryable" flag would invite
    re-fetching a scanned PDF to OCR it, which pays for bytes already owned.
    """

    action: str | None   # None | "refetch" | "reextract"
    hint: str


# Reason → remedy. A reason absent from this table is treated as terminal.
REMEDIES: dict[str, Remedy] = {
    # --- blocked -----------------------------------------------------------
    "bot_challenge": Remedy(
        "refetch",
        "--premium-proxy, then --wait, then --stealth-proxy; escalate in that order",
    ),
    # --- failed ------------------------------------------------------------
    "origin_unreachable": Remedy(
        "refetch",
        "--render-js, or --premium-proxy for a host that refuses datacentre IPs",
    ),
    "access_denied": Remedy(
        "refetch",
        "--premium-proxy; a 401/403 is often the IP range rather than the URL",
    ),
    "quota_exhausted": Remedy(
        "refetch",
        "no fault of the source — top up the ScrapingBee account and retry",
    ),
    "transport_error": Remedy("refetch", "a local network failure; simply retry"),
    "not_found": Remedy(
        None,
        "link rot: report it as a finding, it is characteristic of grey literature",
    ),
    "bad_request": Remedy(
        None,
        "the proxy rejected the request itself; the URL needs different parameters",
    ),
    "fetch_failed": Remedy("refetch", "cause not recorded; one retry is cheap"),
    # --- empty -------------------------------------------------------------
    "no_main_content": Remedy(
        "refetch",
        "--render-js: the delivered markup carried no article text",
    ),
    "no_text_layer": Remedy(
        "reextract",
        "--ocr: the bytes are archived, this costs no credits",
    ),
    "no_article_text": Remedy(
        None,
        "a platform post or video, not a document; exclude it and say so",
    ),
    "unsupported_media": Remedy(
        None,
        "neither HTML nor PDF; no extractor applies",
    ),
    "extractor_crashed": Remedy(
        "reextract",
        "the extractor raised on these bytes; costs no credits to try again",
    ),
    # --- not fetched -------------------------------------------------------
    "never_attempted": Remedy("refetch", "no retrieval was attempted for this document"),
}


# How each reason is named in a retrieval report. Phrased as a finding about
# the source rather than about the tool, because that is the sentence a methods
# section has to carry: "excluded, behind publisher access control" is a scope
# decision a reviewer can assess, "fetch error" is not.
LABELS: dict[str, str] = {
    "bot_challenge": "Blocked by a firewall or bot challenge",
    "origin_unreachable": "Origin did not answer the proxy (commonly publisher access control)",
    "access_denied": "Access refused (401/403)",
    "quota_exhausted": "Retrieval budget exhausted — not a property of the source",
    "transport_error": "Local network failure during retrieval",
    "not_found": "Gone (404/410) — link rot",
    "bad_request": "The request itself was rejected by the proxy",
    "fetch_failed": "Retrieval failed, cause not recorded",
    "no_main_content": "Retrieved, but the markup carried no article text",
    "no_text_layer": "PDF without a text layer (not OCR'd)",
    "no_article_text": "A platform post or video rather than a document",
    "unsupported_media": "Neither HTML nor PDF",
    "extractor_crashed": "The text extractor failed on these bytes",
    "never_attempted": "No retrieval was attempted",
}


class Outcome(NamedTuple):
    status: str
    reason: str | None

    @property
    def remedy(self) -> Remedy:
        return REMEDIES.get(self.reason or "", Remedy(None, ""))

    @property
    def retry_action(self) -> str | None:
        return self.remedy.action

    @property
    def label(self) -> str:
        return LABELS.get(self.reason or "", self.reason or "")


def _get(row: Mapping[str, Any] | Any, key: str) -> Any:
    """Read a column that an older database may not have.

    D20 leaves column-level upgrades manual, so a read command must survive a
    missing column rather than assume schema.sql has caught up.
    """
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def is_platform_host(host: str | None) -> bool:
    """True for a host whose pages are posts and videos rather than documents."""
    host = (host or "").lower()
    return any(host == p or host.endswith("." + p) for p in PLATFORM_HOSTS)


def _status_from_error(error: str) -> int | None:
    """The status code out of fetch.py's own `HTTP <code>: <body>` prefix."""
    head = error[:16]
    if not head.startswith("HTTP "):
        return None
    digits = head[5:].split(":", 1)[0].strip()
    return int(digits) if digits.isdigit() else None


def _failure_reason(snapshot: Mapping[str, Any]) -> str:
    """Why a fetch failed, from the proxy's own status code.

    ScrapingBee passes an origin error status through as its own, so a 404 here
    is the source's 404. Its *own* failures are the 5xx range and 402: the
    string "you will not be charged for this request" in the body is the
    house style of a proxy that could not reach the target at all.
    """
    error = _get(snapshot, "fetch_error") or ""
    status = _get(snapshot, "proxy_status")
    if status is None:
        # No HTTP exchange completed; fetch.py records these as
        # "transport error: ..." after exhausting its own retries.
        if "transport error" in error.lower():
            return "transport_error"
        # Fallback for rows written before proxy_status was populated. The
        # prefix is fetch.py's own format string, not a third party's, so
        # reading it back is parsing this repo's output rather than guessing.
        status = _status_from_error(error)
        if status is None:
            return "fetch_failed"
    if status in (404, 410):
        return "not_found"
    if status == 402:
        return "quota_exhausted"
    if status in (401, 403):
        return "access_denied"
    if status >= 500:
        return "origin_unreachable"
    if status == 400:
        return "bad_request"
    return "fetch_failed"


def _empty_reason(
    snapshot: Mapping[str, Any], extraction: Mapping[str, Any] | None, host: str | None
) -> str:
    """Why a successful retrieval yielded no text.

    Host is checked before the extractor message on purpose: on a platform host
    the extractor is not failing, it is correctly reporting that a video page
    has no article in it. Calling that an extraction problem would put it in
    the queue for a retry that cannot succeed.
    """
    if is_platform_host(host):
        return "no_article_text"
    if (_get(snapshot, "media_type") or "") == "other":
        return "unsupported_media"
    error = (_get(extraction, "extraction_error") or "").lower()
    if "text layer" in error:
        return "no_text_layer"
    if "unsupported media type" in error:
        return "unsupported_media"
    # extract.py returns "<ExcType>: <message>" when the extractor raised, and
    # a fixed phrase when it simply found nothing. Only the first is a defect.
    if error and "no main content" not in error and "produced no text" not in error:
        return "extractor_crashed"
    return "no_main_content"


def classify(
    snapshot: Mapping[str, Any] | None,
    extraction: Mapping[str, Any] | None,
    host: str | None = None,
) -> Outcome:
    """The status of one document's best retrieval, and why.

    `snapshot` is the row chosen by `db.best_snapshot`; `extraction`
    is its extraction, if any. Both are read defensively, so this works on a
    database written by an older version of the tool.
    """
    if snapshot is None:
        return Outcome(NOT_FETCHED, "never_attempted")
    if _get(snapshot, "blocked_reason"):
        return Outcome(BLOCKED, "bot_challenge")
    if _get(snapshot, "fetch_error"):
        return Outcome(FAILED, _failure_reason(snapshot))
    if extraction is None or not (_get(extraction, "word_count") or 0):
        return Outcome(EMPTY, _empty_reason(snapshot, extraction, host))
    return Outcome(OK, None)
