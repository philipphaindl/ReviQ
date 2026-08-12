"""A database is routinely older than the binary opening it.

A corpus retrieved months ago is exactly what a review comes back to, and the
tables added in between must not make a read-only command fail. These tests
simulate that by dropping tables from a current database and reopening it.

The concrete failure this pins: a pilot corpus retrieved before `figures` and
`figure_descriptions` existed made both `export-json` and `report` die
with `sqlite3.OperationalError: no such table: figures` — on a database whose
only fault was being older than the code.
"""

import sqlite3

import pytest

from app.retrieval import db, interchange, report

LATER_TABLES = ("figure_descriptions", "figures")


def seed(conn, run_id="run-1"):
    db.start_run(conn, run_id, "AI maturity model", "google", "{}", "0.1.0")
    document_id = db.upsert_document(conn, "https://example.org/a", "example.org", run_id)
    db.insert_serp_result(
        conn, run_id, 1, 1, 1, "https://example.org/a", "https://example.org/a",
        "A title", "A snippet", "example.org", db.utc_now(), "search_x", document_id,
    )
    snapshot_id = db.insert_snapshot(
        conn, document_id=document_id, run_id=run_id,
        requested_url="https://example.org/a", final_url="https://example.org/a",
        origin_status_first=200, proxy_status=200, content_type="text/html",
        content_length=1000, sha256="a" * 64, media_type="html",
        fetched_at_utc=db.utc_now(), warc_path="data/runs/run-1/snapshots.warc.gz",
        warc_offset=0, warc_record_id="urn:uuid:x", credits_cost=1,
    )
    db.insert_extraction(
        conn, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
        title="A Maturity Model", text="Body text.", word_count=2,
        extracted_at_utc=db.utc_now(),
    )
    conn.commit()
    return run_id


@pytest.fixture
def older_db(tmp_path):
    """A populated database that predates the figure tables."""
    path = tmp_path / "older.sqlite3"
    conn = db.connect(path)
    seed(conn)
    for table in LATER_TABLES:
        conn.execute(f"DROP TABLE {table}")
    conn.commit()
    conn.close()
    return path


def test_the_fixture_really_is_missing_the_tables(older_db):
    """Guards the guard: if the drop stopped working, every test below would
    pass for the wrong reason."""
    raw = sqlite3.connect(older_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            raw.execute("SELECT 1 FROM figures").fetchall()
    finally:
        raw.close()


def test_connecting_adds_what_is_missing(older_db):
    conn = db.connect(older_db)
    try:
        assert conn.execute("SELECT * FROM figures").fetchall() == []
        assert conn.execute("SELECT * FROM figure_descriptions").fetchall() == []
    finally:
        conn.close()


def test_existing_data_survives_the_upgrade(older_db):
    """The whole point of an additive schema: nothing already there is touched."""
    conn = db.connect(older_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM serp_results").fetchone()[0] == 1
        assert conn.execute(
            "SELECT title FROM extractions"
        ).fetchone()[0] == "A Maturity Model"
    finally:
        conn.close()


def test_export_json_works_on_an_older_database(older_db):
    conn = db.connect(older_db)
    try:
        package = interchange.build_package(conn, ["run-1"])
    finally:
        conn.close()
    assert len(package["records"]) == 1
    # An empty table is the honest answer: this corpus genuinely has no figures.
    assert package["counts"]["figures_described"] == 0
    assert "figures" not in package["records"][0]


def test_report_works_on_an_older_database(older_db, tmp_path):
    """`report` reads figure_descriptions for its model-output disclosure, so
    it had exactly the same latent failure as the exporter."""
    conn = db.connect(older_db)
    try:
        out = tmp_path / "report.md"
        report.report_run(conn, "run-1", out)
    finally:
        conn.close()
    text = out.read_text(encoding="utf-8")
    assert "AI maturity model" in text
    # No figures, so no vision-model disclosure should appear.
    assert "vision model" not in text.lower()


def test_reopening_repeatedly_is_idempotent(older_db):
    for _ in range(3):
        conn = db.connect(older_db)
        conn.close()
    conn = db.connect(older_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        indexes = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_figures_document'"
        ).fetchone()[0]
        assert indexes == 1
    finally:
        conn.close()
