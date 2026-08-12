"""The retrieval-outcome classifier.

The cases here are not invented. Each mirrors a row observed in a 424-document
pilot corpus ("AI maturity model", 20 queries, August 2026), which is why the
proportions in `test_pilot_corpus_distribution` are asserted at all: they are
the distribution the classifier has to reproduce to be worth anything.
"""

import pytest

from app.retrieval.outcome import (
    BLOCKED,
    EMPTY,
    FAILED,
    NOT_FETCHED,
    OK,
    REMEDIES,
    classify,
    is_platform_host,
)


def snap(**fields):
    """A snapshot row with every column present, as a current database has it."""
    row = {
        "blocked_reason": None, "fetch_error": None, "proxy_status": None,
        "origin_status_first": None, "media_type": "html", "content_length": 1000,
    }
    row.update(fields)
    return row


def extraction(**fields):
    row = {"word_count": 0, "extraction_error": None}
    row.update(fields)
    return row


# --- the happy path -------------------------------------------------------


def test_text_extracted_is_ok_with_no_reason():
    outcome = classify(snap(), extraction(word_count=1203), host="oecd.org")
    assert outcome == (OK, None)
    assert outcome.retry_action is None


# --- blocked --------------------------------------------------------------


def test_block_page_is_a_bot_challenge():
    outcome = classify(
        snap(blocked_reason="captcha challenge: 'captcha'"), None, host="linkedin.com"
    )
    assert outcome == (BLOCKED, "bot_challenge")
    assert outcome.retry_action == "refetch"


def test_block_wins_over_a_platform_host():
    """A blocked LinkedIn page is blocked, not 'a platform page with no text'.

    Both conditions hold for three rows in the pilot corpus. Reporting them as
    no_article_text would understate how often the wall was the actual reason.
    """
    outcome = classify(
        snap(blocked_reason="captcha challenge: 'captcha'"), None, host="linkedin.com"
    )
    assert outcome.reason == "bot_challenge"


# --- failed ---------------------------------------------------------------


def test_proxy_500_is_origin_unreachable_and_worth_a_retry():
    """32 of the pilot corpus's 39 failures, all at publisher hosts."""
    outcome = classify(
        snap(proxy_status=500,
             fetch_error='HTTP 500: {"error": "Error with your request, please '
                         'try again (you will not be charged for this request)."}'),
        None, host="sciencedirect.com",
    )
    assert outcome == (FAILED, "origin_unreachable")
    assert outcome.retry_action == "refetch"


def test_proxy_400_is_a_bad_request_and_terminal():
    """ScrapingBee refusing to scrape Google without custom_google=True.

    Retrying spends credits on a request the proxy has already declined.
    """
    outcome = classify(
        snap(proxy_status=400,
             fetch_error='HTTP 400: {"errors":{"query":{"custom_google":["If you '
                         'wish to scrape Google, use the custom_google=True param'),
        None, host="google.com",
    )
    assert outcome == (FAILED, "bad_request")
    assert outcome.retry_action is None


def test_404_is_link_rot_not_a_defect():
    outcome = classify(
        snap(proxy_status=404, fetch_error="HTTP 404: <!DOCTYPE html>"),
        None, host="example.org",
    )
    assert outcome == (FAILED, "not_found")
    assert outcome.retry_action is None
    assert "link rot" in outcome.remedy.hint


@pytest.mark.parametrize("status,reason", [
    (410, "not_found"),
    (402, "quota_exhausted"),
    (401, "access_denied"),
    (403, "access_denied"),
    (500, "origin_unreachable"),
    (502, "origin_unreachable"),
    (429, "fetch_failed"),
])
def test_status_codes_map_to_reasons(status, reason):
    outcome = classify(
        snap(proxy_status=status, fetch_error=f"HTTP {status}: ..."), None, host="x.org"
    )
    assert outcome.reason == reason


def test_quota_exhausted_is_not_blamed_on_the_source():
    """402 means our account ran dry mid-run. Excluding those sources as
    unreachable would be a sampling error caused by billing."""
    outcome = classify(
        snap(proxy_status=402, fetch_error="HTTP 402: ..."), None, host="oecd.org"
    )
    assert outcome.reason == "quota_exhausted"
    assert outcome.retry_action == "refetch"


def test_transport_error_is_our_network_not_theirs():
    outcome = classify(
        snap(proxy_status=None, fetch_error="transport error: ReadTimeout"),
        None, host="oecd.org",
    )
    assert outcome == (FAILED, "transport_error")
    assert outcome.retry_action == "refetch"


def test_status_is_recovered_from_the_error_prefix_when_the_column_is_null():
    """Older rows carry the status only inside fetch.py's own message."""
    outcome = classify(
        snap(proxy_status=None, fetch_error="HTTP 404: <!DOCTYPE html>"),
        None, host="example.org",
    )
    assert outcome.reason == "not_found"


def test_unparseable_failure_falls_back_rather_than_raising():
    outcome = classify(
        snap(proxy_status=None, fetch_error="something went wrong"), None, host="x.org"
    )
    assert outcome == (FAILED, "fetch_failed")


# --- empty ----------------------------------------------------------------


def test_platform_page_has_no_article_text_and_no_remedy():
    """facebook, youtube and instagram rows in the pilot corpus fetched fine —
    up to 1.2 MB of markup — and contain no document. No flag changes that."""
    outcome = classify(
        snap(content_length=1145516),
        extraction(extraction_error="no main content extracted"),
        host="youtube.com",
    )
    assert outcome == (EMPTY, "no_article_text")
    assert outcome.retry_action is None


@pytest.mark.parametrize("host", [
    "facebook.com", "www.facebook.com", "m.facebook.com", "youtu.be", "x.com",
])
def test_platform_hosts_match_their_subdomains(host):
    assert is_platform_host(host)


@pytest.mark.parametrize("host", ["oecd.org", "notfacebook.com", "facebook.com.co", ""])
def test_non_platform_hosts_do_not_match(host):
    assert not is_platform_host(host)


def test_no_main_content_is_worth_rendering_once():
    """Repository landing pages — uu.nl, ieeexplore, semanticscholar, mdpi —
    delivered 750-3200 bytes and no article. Those are the retry candidates."""
    outcome = classify(
        snap(content_length=751),
        extraction(extraction_error="no main content extracted"),
        host="studenttheses.uu.nl",
    )
    assert outcome == (EMPTY, "no_main_content")
    assert outcome.retry_action == "refetch"
    assert "--render-js" in outcome.remedy.hint


def test_scanned_pdf_is_re_extracted_not_re_fetched():
    """The bytes are already in the WARC. Paying ScrapingBee again to OCR them
    would buy something we own."""
    outcome = classify(
        snap(media_type="pdf"),
        extraction(extraction_error="no text layer (scanned PDF?); retry the run with --ocr"),
        host="oecd.org",
    )
    assert outcome == (EMPTY, "no_text_layer")
    assert outcome.retry_action == "reextract"


def test_unsupported_media_is_terminal():
    outcome = classify(
        snap(media_type="other"),
        extraction(extraction_error="unsupported media type: other"),
        host="isms.online",
    )
    assert outcome == (EMPTY, "unsupported_media")
    assert outcome.retry_action is None


def test_an_extractor_crash_is_distinguished_from_an_empty_page():
    """extract.py returns '<ExcType>: <message>' when trafilatura raised. That
    is a defect in the pipeline, not a property of the source, and it must not
    disappear into the same bucket as a page that genuinely had no article."""
    outcome = classify(
        snap(), extraction(extraction_error="ValueError: unterminated entity"),
        host="oecd.org",
    )
    assert outcome == (EMPTY, "extractor_crashed")
    assert outcome.retry_action == "reextract"


def test_missing_extraction_row_is_empty_not_a_crash():
    assert classify(snap(), None, host="oecd.org") == (EMPTY, "no_main_content")


# --- not fetched ----------------------------------------------------------


def test_no_snapshot_at_all():
    outcome = classify(None, None, host="oecd.org")
    assert outcome == (NOT_FETCHED, "never_attempted")
    assert outcome.retry_action == "refetch"


# --- robustness against an older database ---------------------------------


def test_a_row_missing_columns_still_classifies():
    """D20 leaves column-level upgrades manual, so a read command meets rows
    without the columns it wants. It must classify them, not raise."""
    outcome = classify({"blocked_reason": None, "fetch_error": None}, None, host="oecd.org")
    assert outcome.status == EMPTY


def test_sqlite_rows_work_not_only_dicts():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT NULL AS blocked_reason, 'HTTP 404: x' AS fetch_error, "
        "404 AS proxy_status, 'html' AS media_type"
    ).fetchone()
    assert classify(row, None, host="example.org").reason == "not_found"


# --- the vocabulary itself ------------------------------------------------


def test_every_reason_the_classifier_can_produce_has_a_remedy():
    """A reason with no entry silently reads as terminal, which would quietly
    drop retryable documents out of `refetch`."""
    produced = {
        "bot_challenge", "origin_unreachable", "access_denied", "quota_exhausted",
        "transport_error", "not_found", "bad_request", "fetch_failed",
        "no_main_content", "no_text_layer", "no_article_text", "unsupported_media",
        "extractor_crashed", "never_attempted",
    }
    assert produced <= set(REMEDIES)
    assert set(REMEDIES) == produced, "REMEDIES has entries the classifier never emits"


@pytest.mark.parametrize("reason,remedy", sorted(REMEDIES.items()))
def test_remedies_are_actionable(reason, remedy):
    assert remedy.action in (None, "refetch", "reextract")
    assert remedy.hint, f"{reason} has no hint to act on"


def test_platform_hosts_are_a_subset_of_the_snowball_noise_list():
    """One list, two readers. If a host is not worth following as a link, it is
    also not worth re-fetching for text — and the two must not drift apart."""
    from app.retrieval.links import NOISE_HOSTS, PLATFORM_HOSTS

    assert PLATFORM_HOSTS <= NOISE_HOSTS


# --- the pilot corpus, reproduced -----------------------------------------


def test_pilot_corpus_distribution():
    """The 66 non-ok documents of the pilot corpus, by recorded cause.

    Three numbers carry the point: 32 publisher walls that are a scope
    decision, 13 pages worth one render, and 7 platform pages that never held
    a document. Before this classifier all 66 were "failed, blocked or empty".
    """
    rows = (
        [(snap(proxy_status=500, fetch_error="HTTP 500: ..."), None, "sciencedirect.com")] * 32
        + [(snap(proxy_status=400, fetch_error="HTTP 400: ..."), None, "google.com")] * 3
        + [(snap(proxy_status=404, fetch_error="HTTP 404: ..."), None, "webflow.io")] * 4
        + [(snap(blocked_reason="captcha"), None, "linkedin.com")] * 5
        + [(snap(), extraction(extraction_error="no main content extracted"), "uu.nl")] * 13
        + [(snap(), extraction(extraction_error="no main content extracted"), "facebook.com")] * 7
        + [(snap(media_type="other"),
            extraction(extraction_error="unsupported media type: other"), "isms.online")] * 1
    )
    assert len(rows) == 65  # + 1 platform row that is also blocked, counted above

    counts: dict[str, int] = {}
    for s, e, host in rows:
        counts[classify(s, e, host).reason] = counts.get(classify(s, e, host).reason, 0) + 1

    assert counts == {
        "origin_unreachable": 32,
        "bad_request": 3,
        "not_found": 4,
        "bot_challenge": 5,
        "no_main_content": 13,
        "no_article_text": 7,
        "unsupported_media": 1,
    }

    refetchable = sum(
        n for reason, n in counts.items() if REMEDIES[reason].action == "refetch"
    )
    assert refetchable == 50, "the documents a targeted retry would actually attempt"
