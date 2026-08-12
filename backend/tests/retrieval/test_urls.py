"""Canonicalisation tests.

The negative cases matter more than the positive ones: over-normalisation
silently merges distinct documents, which is invisible in the output.
"""

import pytest

from glr.urls import canonicalize, host_of, is_fetchable


@pytest.mark.parametrize(
    "raw, expected",
    [
        # scheme and host are case-insensitive, path is not
        ("HTTPS://Example.COM/Path", "https://example.com/Path"),
        # www. is a near-universal alias
        ("https://www.example.com/a", "https://example.com/a"),
        # fragments never reach the server
        ("https://example.com/a#section-2", "https://example.com/a"),
        # default ports carry no information
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        # a non-default port does
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        # trailing slash, except on the bare root
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        # index files are directory synonyms
        ("https://example.com/docs/index.html", "https://example.com/docs"),
        # tracking parameters go
        ("https://example.com/a?utm_source=x&utm_medium=y", "https://example.com/a"),
        ("https://example.com/a?fbclid=123", "https://example.com/a"),
        # parameter order must not fragment the key
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
    ],
)
def test_canonicalize(raw, expected):
    assert canonicalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com/report?id=4711",
        "https://example.com/view?doc=annual-2025",
        "https://example.com/search?q=maturity+model",
        "https://example.com/p?page=3",
    ],
)
def test_content_bearing_parameters_are_preserved(raw):
    """Risk R7: these identify *different documents*. Dropping them would
    silently collapse distinct sources into one."""
    assert canonicalize(raw) == raw


def test_tracking_removal_does_not_touch_neighbours():
    assert (
        canonicalize("https://example.com/r?id=7&utm_source=news&lang=de")
        == "https://example.com/r?id=7&lang=de"
    )


def test_equivalent_urls_share_one_key():
    variants = [
        "https://www.example.com/report/",
        "http://example.com/report",  # scheme differs -> different key, by design
    ]
    assert canonicalize(variants[0]) == "https://example.com/report"
    # http and https are NOT merged: they can legitimately serve different content.
    assert canonicalize(variants[1]) != canonicalize(variants[0])


def test_host_of():
    assert host_of("https://www.bbc.co.uk/news") == "bbc.co.uk"
    assert host_of("https://example.com") == "example.com"
    assert host_of("not a url") is None


def test_is_fetchable():
    assert is_fetchable("https://example.com/a")
    assert not is_fetchable("mailto:someone@example.com")
    assert not is_fetchable("ftp://example.com/file")
    assert not is_fetchable("https://")
