"""arXiv Atom feed parsing tests, against a recorded fixture. No network."""

from pathlib import Path

from app.retrieval.arxiv import parse_entries

FIXTURE = (Path(__file__).parent / "fixtures" / "arxiv_page1.xml").read_text()


def test_parse_entries_prefers_the_pdf_link():
    hits = parse_entries(FIXTURE, page=1)
    assert len(hits) == 2
    assert hits[0].raw_url == "http://arxiv.org/pdf/2301.00001v2"
    assert hits[0].title == "An AI Maturity Model for Organisations"
    assert hits[0].position == 1


def test_parse_entries_falls_back_to_the_abstract_page_without_a_pdf_link():
    hits = parse_entries(FIXTURE, page=1)
    assert hits[1].raw_url == "http://arxiv.org/abs/2301.00002v1"


def test_entries_without_id_or_pdf_link_are_skipped():
    hits = parse_entries(FIXTURE, page=1)
    assert all("no id" not in (h.title or "") for h in hits)


def test_global_rank_spans_pages():
    """The number a methods section cites: position 2 on page 3 is rank 22."""
    hits = parse_entries(FIXTURE, page=3)
    assert [h.global_rank for h in hits] == [21, 22]


def test_snippet_and_displayed_link():
    hits = parse_entries(FIXTURE, page=1)
    assert hits[0].snippet.startswith("We propose a maturity model")
    assert hits[0].displayed_link == "arxiv.org"


def test_empty_feed_is_not_an_error():
    empty = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    assert parse_entries(empty, page=1) == []
