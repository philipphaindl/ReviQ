"""Credential scrubbing. No network, no keys needed."""

from glr.redact import MIN_SECRET_LENGTH, REDACTED, scrub


def test_a_secret_is_replaced_everywhere_it_appears():
    key = "SBEE_live_9f3a2b71c4"
    text = f"transport error: GET https://app.scrapingbee.com/?api_key={key}&url=x ({key})"
    result = scrub(text, key)
    assert key not in result
    assert result.count(REDACTED) == 2


def test_surrounding_text_survives():
    result = scrub("HTTP 401: bad key SBEE_live_9f3a2b71c4 for account 12", "SBEE_live_9f3a2b71c4")
    assert result == f"HTTP 401: bad key {REDACTED} for account 12"


def test_empty_and_none_are_returned_unchanged():
    assert scrub(None, "secret-value") is None
    assert scrub("", "secret-value") == ""


def test_a_missing_key_is_not_an_error():
    """Callers pass whatever they hold; an unset credential must not blow up
    the error path it was supposed to make safe."""
    assert scrub("nothing to hide", None) == "nothing to hide"
    assert scrub("nothing to hide") is not None


def test_short_values_are_left_alone():
    """A placeholder or empty-ish value would otherwise match everywhere and
    corrupt the very message it was meant to protect."""
    short = "x" * (MIN_SECRET_LENGTH - 1)
    text = f"HTTP 500: {short}yz internal error"
    assert scrub(text, short) == text


def test_environment_is_used_when_no_secret_is_passed(monkeypatch):
    """The storing code should not have to know which credentials exist."""
    monkeypatch.setenv("SCRAPINGBEE_API_KEY", "env_secret_value_1234")
    assert "env_secret_value_1234" not in scrub("leaked env_secret_value_1234 here")


def test_an_unset_environment_variable_scrubs_nothing(monkeypatch):
    monkeypatch.delenv("SCRAPINGBEE_API_KEY", raising=False)
    monkeypatch.delenv("SEARCHAPI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert scrub("ordinary message") == "ordinary message"
