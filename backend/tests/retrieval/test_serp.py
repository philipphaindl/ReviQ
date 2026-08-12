"""SERP parsing tests, against a recorded fixture. No network."""

import json
from pathlib import Path

from app.retrieval.serp import parse_organic, search_id_of

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "searchapi_google_page1.json").read_text()
)


def test_parse_organic_extracts_hits():
    hits = parse_organic(FIXTURE, page=1)
    assert len(hits) == 3
    assert hits[0].raw_url == "https://example.org/ai-maturity-model"
    assert hits[0].title == "An AI Maturity Model for Organisations"
    assert hits[0].position == 1


def test_global_rank_spans_pages():
    """The number a methods section cites: position 2 on page 3 is rank 22."""
    hits = parse_organic(FIXTURE, page=3)
    assert [h.global_rank for h in hits] == [21, 22, 23]


def test_entries_without_link_are_skipped():
    payload = {"organic_results": [{"title": "no link here", "position": 1}]}
    assert parse_organic(payload, page=1) == []


def test_missing_organic_results_is_not_an_error():
    assert parse_organic({}, page=1) == []
    assert parse_organic({"organic_results": None}, page=1) == []


def test_search_id_is_captured():
    assert search_id_of(FIXTURE) == "search_abc123"
    assert search_id_of({}) is None


def test_google_redirect_wrappers_are_dropped():
    """Observed three times in a 20-query pilot: Google returns its own
    /goto?url=CAESY... wrapper as an organic result. The target is an opaque
    token, ScrapingBee rejects the host, and each one costs a wasted fetch."""
    payload = {"organic_results": [
        {"position": 1, "link": "https://www.google.com/goto?url=CAESYwHuR6pNAaarPl7"},
        {"position": 2, "link": "https://example.org/real-source"},
    ]}
    hits = parse_organic(payload, page=1)
    assert [h.raw_url for h in hits] == ["https://example.org/real-source"]


def test_other_search_plumbing_is_dropped():
    from app.retrieval.serp import is_non_source

    assert is_non_source("https://www.google.com/url?q=x")
    assert is_non_source("https://webcache.googleusercontent.com/search?q=cache:x")
    assert not is_non_source("https://google.com/about")
    assert not is_non_source("https://example.org/page")
