"""The retrieval report has to reconcile with the interchange export.

Both describe the same corpus, so a reviewer who counts sources in the report
and records in the export must get the same number. Two things used to break
that: the report counted a retrieved-but-textless document as a usable source,
and it counted snapshot rows rather than documents, so a document retried
inside a batch appeared twice.
"""

import json

import pytest

from glr import db, interchange, report
from glr.outcome import LABELS


def make_document(conn, run_id, url, host, *, rank=1, query_title="A title",
                  fetch_error=None, blocked_reason=None, proxy_status=200,
                  media_type="html", word_count=100, extraction_error=None,
                  fetched_at=None, document_id=None):
    """One document with one snapshot, and an extraction unless the fetch failed."""
    if document_id is None:
        document_id = db.upsert_document(conn, url, host, run_id)
        db.insert_serp_result(
            conn, run_id, 1, rank, rank, url, url, query_title, "snippet",
            host, db.utc_now(), "search_x", document_id,
        )
    snapshot_id = db.insert_snapshot(
        conn, document_id=document_id, run_id=run_id, requested_url=url,
        final_url=url, origin_status_first=proxy_status, proxy_status=proxy_status,
        content_type="text/html", content_length=1000,
        sha256=None if fetch_error else "a" * 64, media_type=media_type,
        fetched_at_utc=fetched_at or db.utc_now(),
        warc_path=f"data/runs/{run_id}/snapshots.warc.gz", warc_offset=0,
        warc_record_id="urn:uuid:x", credits_cost=1,
        fetch_error=fetch_error, blocked_reason=blocked_reason,
    )
    if not fetch_error and not blocked_reason:
        db.insert_extraction(
            conn, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
            title=query_title, text="Body text." if word_count else None,
            word_count=word_count, extracted_at_utc=db.utc_now(),
            extraction_error=extraction_error,
        )
    return document_id


@pytest.fixture
def corpus(tmp_path):
    """A miniature of the pilot corpus: one of each outcome that matters."""
    conn = db.connect(tmp_path / "glr.sqlite3")
    run_id = "run-1"
    db.start_run(conn, run_id, "AI maturity model", "google", "{}", "0.1.0",
                 batch_id="batch-1")

    make_document(conn, run_id, "https://oecd.org/a", "oecd.org", rank=1)
    make_document(conn, run_id, "https://sciencedirect.com/b", "sciencedirect.com",
                  rank=2, fetch_error='HTTP 500: {"error": "please try again"}',
                  proxy_status=500)
    make_document(conn, run_id, "https://linkedin.com/c", "linkedin.com", rank=3,
                  blocked_reason="captcha challenge: 'captcha'")
    make_document(conn, run_id, "https://youtube.com/watch?v=d", "youtube.com",
                  rank=4, word_count=0,
                  extraction_error="no main content extracted")
    make_document(conn, run_id, "https://studenttheses.uu.nl/e", "studenttheses.uu.nl",
                  rank=5, word_count=0,
                  extraction_error="no main content extracted")
    make_document(conn, run_id, "https://gone.example/f", "gone.example", rank=6,
                  fetch_error="HTTP 404: <!DOCTYPE html>", proxy_status=404)
    db.finish_run(conn, run_id, "completed")
    conn.commit()
    return conn, tmp_path


def test_a_retrieved_but_textless_document_is_not_a_usable_source(corpus, tmp_path):
    """The regression this file exists for: a clean fetch that yielded no text
    was counted among the sources a review could cite."""
    conn, _ = corpus
    text = report.report_run(conn, "run-1", tmp_path / "r.md").read_text()

    assert "| Sources retrieved and usable | 1 |" in text
    assert "| **Total identified** | **6** |" in text


def test_causes_are_reported_separately_not_as_one_failure_count(corpus, tmp_path):
    conn, _ = corpus
    text = report.report_run(conn, "run-1", tmp_path / "r.md").read_text()

    for reason in ("origin_unreachable", "bot_challenge", "no_article_text",
                   "no_main_content", "not_found"):
        assert LABELS[reason] in text, f"{reason} is not named in the report"


def test_a_platform_page_and_a_render_candidate_do_not_share_a_bucket(corpus, tmp_path):
    """Both are 'retrieved, no text'. Only one is worth spending credits on."""
    conn, _ = corpus
    text = report.report_run(conn, "run-1", tmp_path / "r.md").read_text()

    assert "youtube.com" in text and "studenttheses.uu.nl" in text
    assert "Not recoverable by retrying" in text   # the platform page
    assert "glr refetch` selects exactly these" in text  # the render candidate


def test_report_and_export_agree_on_the_corpus_size(corpus, tmp_path):
    """The property the export docstring promises: the two reconcile."""
    conn, _ = corpus
    text = report.report_run(conn, "run-1", tmp_path / "r.md").read_text()
    interchange.write_package(conn, "run-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())

    assert "| **Total identified** | **6** |" in text
    assert package["counts"]["documents"] == 6
    assert package["counts"]["ok"] == 1
    assert "| Sources retrieved and usable | 1 |" in text


def test_a_document_retried_inside_a_batch_is_counted_once(tmp_path):
    """A failure in the run for query 1 is retried when query 5 returns the same
    URL — `has_snapshot` treats only clean retrievals as archived. Both
    snapshots are in scope for a batch report, and the document is one document.
    """
    conn = db.connect(tmp_path / "glr.sqlite3")
    for run_id, query in (("run-1", "query one"), ("run-2", "query five")):
        db.start_run(conn, run_id, query, "google", "{}", "0.1.0", batch_id="batch-1")

    document_id = make_document(
        conn, "run-1", "https://oecd.org/a", "oecd.org",
        fetch_error='HTTP 500: {"error": "please try again"}', proxy_status=500,
        fetched_at="2026-08-11T10:00:00Z",
    )
    make_document(
        conn, "run-2", "https://oecd.org/a", "oecd.org", word_count=900,
        fetched_at="2026-08-11T11:00:00Z", document_id=document_id,
    )
    for run_id in ("run-1", "run-2"):
        db.finish_run(conn, run_id, "completed")
    conn.commit()

    text = report.report_batch(conn, "batch-1", tmp_path / "r.md").read_text()
    interchange.write_package(conn, "batch-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())

    assert "| **Total identified** | **1** |" in text
    assert "| Sources retrieved and usable | 1 |" in text
    assert package["counts"]["documents"] == 1
    assert package["counts"]["ok"] == 1


def test_the_successful_retry_wins_over_the_earlier_failure(tmp_path):
    """Same shape, opposite order in time: the clean snapshot must win whether
    it was written first or second."""
    conn = db.connect(tmp_path / "glr.sqlite3")
    for run_id in ("run-1", "run-2"):
        db.start_run(conn, run_id, "q", "google", "{}", "0.1.0", batch_id="batch-1")

    document_id = make_document(
        conn, "run-1", "https://oecd.org/a", "oecd.org", word_count=900,
        fetched_at="2026-08-11T10:00:00Z",
    )
    make_document(
        conn, "run-2", "https://oecd.org/a", "oecd.org",
        fetch_error="HTTP 500: x", proxy_status=500,
        fetched_at="2026-08-11T11:00:00Z", document_id=document_id,
    )
    conn.commit()

    text = report.report_batch(conn, "batch-1", tmp_path / "r.md").read_text()
    assert "| Sources retrieved and usable | 1 |" in text
    assert "| **Total identified** | **1** |" in text


def test_the_export_carries_the_reason_alongside_the_status(corpus, tmp_path):
    conn, _ = corpus
    interchange.write_package(conn, "run-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())

    reasons = {r["host"]: r["retrieval_reason"] for r in package["records"]}
    assert reasons["oecd.org"] is None
    assert reasons["sciencedirect.com"] == "origin_unreachable"
    assert reasons["linkedin.com"] == "bot_challenge"
    assert reasons["youtube.com"] == "no_article_text"
    assert reasons["studenttheses.uu.nl"] == "no_main_content"
    assert reasons["gone.example"] == "not_found"

    assert package["counts"]["reasons"] == {
        "bot_challenge": 1, "no_article_text": 1, "no_main_content": 1,
        "not_found": 1, "origin_unreachable": 1,
    }


def test_a_document_identified_but_never_fetched_is_reported(tmp_path):
    """The search returned it and the snowball limit or an interruption stopped
    before it. The export counts it as `not_fetched`; the report used to drop it
    entirely, because it joined snapshots inner."""
    conn = db.connect(tmp_path / "glr.sqlite3")
    db.start_run(conn, "run-1", "q", "google", "{}", "0.1.0")
    document_id = db.upsert_document(conn, "https://oecd.org/a", "oecd.org", "run-1")
    db.insert_serp_result(
        conn, "run-1", 1, 1, 1, "https://oecd.org/a", "https://oecd.org/a",
        "A title", "snippet", "oecd.org", db.utc_now(), "search_x", document_id,
    )
    conn.commit()

    text = report.report_run(conn, "run-1", tmp_path / "r.md").read_text()
    interchange.write_package(conn, "run-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())

    assert "| **Total identified** | **1** |" in text
    assert LABELS["never_attempted"] in text
    assert package["counts"]["not_fetched"] == 1
    assert package["counts"]["documents"] == 1


def test_counts_still_reconcile_with_the_record_list(corpus, tmp_path):
    conn, _ = corpus
    interchange.write_package(conn, "run-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())
    counts = package["counts"]

    assert sum(counts["reasons"].values()) == counts["documents"] - counts["ok"]
    assert (counts["ok"] + counts["blocked"] + counts["failed"]
            + counts["empty"] + counts["not_fetched"]) == counts["documents"]


def test_every_archive_a_record_points_into_is_listed(tmp_path):
    """`archive[]` used to be collected per run in scope while records resolve
    their snapshot across all runs. A document archived by an earlier run then
    pointed at a WARC the package did not list — 8 of 424 records in the pilot
    corpus — so a reader following `warc.recorded_path` found a file with no
    digest to check it against."""
    conn = db.connect(tmp_path / "glr.sqlite3")
    db.start_run(conn, "old-run", "an earlier query", "google", "{}", "0.1.0")
    document_id = make_document(conn, "old-run", "https://oecd.org/a", "oecd.org",
                                word_count=900, fetched_at="2026-08-01T09:00:00Z")

    # A later batch observes the same URL. `has_snapshot` skips re-fetching, so
    # this run holds the observation and the earlier run holds the bytes.
    db.start_run(conn, "run-1", "AI maturity model", "google", "{}", "0.1.0",
                 batch_id="batch-1")
    db.insert_serp_result(
        conn, "run-1", 1, 1, 1, "https://oecd.org/a", "https://oecd.org/a",
        "A title", "snippet", "oecd.org", db.utc_now(), "search_x", document_id,
    )
    conn.commit()

    interchange.write_package(conn, "batch-1", tmp_path / "p.json")
    package = json.loads((tmp_path / "p.json").read_text())

    listed = {(a["run_id"], a["filename"]) for a in package["archive"]}
    for record in package["records"]:
        warc = record.get("warc")
        if warc:
            assert (warc["run_id"], warc["filename"]) in listed, \
                f"{record['record_key']} points at an unlisted archive"
    assert listed, "the archive listing must not be empty when a record has bytes"
