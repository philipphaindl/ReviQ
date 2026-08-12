"""The core scientific guarantee: re-running a query versions cleanly.

A second run must add observations and snapshots, and must not duplicate
documents. These tests exercise the database layer directly — no network, no
API keys — because that is where the guarantee actually lives (UNIQUE
constraints plus ON CONFLICT), not in the CLI.
"""

import sqlite3

import pytest

from app.retrieval import db, urls


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.sqlite3")
    db.init_db(connection)
    yield connection
    connection.close()


def _start(connection, run_id, query="AI maturity assessment model"):
    db.start_run(connection, run_id, query, "google", "{}", "0.1.0")


def test_same_url_twice_in_one_run_yields_one_document(conn):
    _start(conn, "run-1")
    first = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    second = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_second_run_reuses_documents_but_adds_observations(conn):
    for run_id in ("run-1", "run-2"):
        _start(conn, run_id)
        document_id = db.upsert_document(conn, "https://example.org/a", "example.org", run_id)
        db.insert_serp_result(
            conn, run_id, 1, 1, 1, "https://example.org/a", "https://example.org/a",
            "Title", "Snippet", "example.org", db.utc_now(), "search_x", document_id,
        )
        conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM serp_results").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2

    # first_seen must still point at the run that discovered the document
    row = conn.execute("SELECT first_seen_run_id FROM documents").fetchone()
    assert row["first_seen_run_id"] == "run-1"


def test_serp_position_is_unique_per_run(conn):
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    for _ in range(2):
        db.insert_serp_result(
            conn, "run-1", 1, 1, 1, "https://example.org/a", "https://example.org/a",
            None, None, None, db.utc_now(), None, document_id,
        )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM serp_results").fetchone()[0] == 1


def test_url_variants_collapse_to_one_document(conn):
    """Canonicalisation and storage together: the tracking-tagged and
    fragment-tagged variants are the same source."""
    _start(conn, "run-1")
    variants = [
        "https://www.example.org/report/",
        "https://example.org/report?utm_source=twitter",
        "https://example.org/report#summary",
        "HTTPS://Example.org/report",
    ]
    ids = {
        db.upsert_document(conn, urls.canonicalize(v), urls.host_of(v), "run-1")
        for v in variants
    }
    assert len(ids) == 1


def test_has_snapshot_drives_the_no_refetch_default(conn):
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    assert not db.has_snapshot(conn, document_id)

    db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/a", sha256="abc", media_type="html",
        fetched_at_utc=db.utc_now(),
    )
    conn.commit()
    assert db.has_snapshot(conn, document_id)


def test_failed_fetch_does_not_count_as_a_snapshot(conn):
    """A failed retrieval must stay retryable on the next run."""
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/a", fetched_at_utc=db.utc_now(),
        fetch_error="HTTP 500",
    )
    conn.commit()
    assert not db.has_snapshot(conn, document_id)


def test_one_snapshot_per_document_per_run(conn):
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    first = db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/a", sha256="abc",
        media_type="html", fetched_at_utc=db.utc_now(),
    )
    second = db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/a", sha256="def",
        media_type="html", fetched_at_utc=db.utc_now(),
    )
    conn.commit()
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1


def test_refetch_in_a_later_run_versions_the_snapshot(conn):
    """Two runs, two snapshots, one document — that is what versioning means."""
    document_id = None
    for run_id, digest in (("run-1", "aaa"), ("run-2", "bbb")):
        _start(conn, run_id)
        document_id = db.upsert_document(conn, "https://example.org/a", "example.org", run_id)
        db.insert_snapshot(
            conn, document_id=document_id, run_id=run_id,
            requested_url="https://example.org/a", sha256=digest,
            media_type="html", fetched_at_utc=db.utc_now(),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT sha256 FROM snapshots WHERE document_id = ? ORDER BY run_id", (document_id,)
    ).fetchall()
    assert [r["sha256"] for r in rows] == ["aaa", "bbb"]


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_document(conn, "https://example.org/a", "example.org", "nonexistent-run")


def test_block_page_is_retried_on_the_next_run(conn):
    """A snapshot flagged as a block page must not count as archived, so a
    later run with --premium-proxy picks up exactly the blocked sources."""
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", "run-1")
    db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/a", sha256="abc", media_type="html",
        fetched_at_utc=db.utc_now(), blocked_reason="F5 BIG-IP ASM: 'access denied'",
    )
    conn.commit()
    assert not db.has_snapshot(conn, document_id)


def test_a_clean_snapshot_still_counts_as_archived(conn):
    _start(conn, "run-1")
    document_id = db.upsert_document(conn, "https://example.org/b", "example.org", "run-1")
    db.insert_snapshot(
        conn, document_id=document_id, run_id="run-1",
        requested_url="https://example.org/b", sha256="def", media_type="html",
        fetched_at_utc=db.utc_now(),
    )
    conn.commit()
    assert db.has_snapshot(conn, document_id)
