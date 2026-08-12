"""Re-running extraction against the archive.

The design says the WARC is written before anything is extracted, so
extraction is repeatable at any later time. Nothing exercised that until now,
and a corpus stayed frozen at whatever the extractor of the day produced —
`language` was empty for all 358 usable documents of the pilot corpus for
exactly that reason.

The archive reading itself is covered in `test_archive.py`, against real
warcio. What is here is the selection and the bookkeeping: which documents get
re-read, and what happens to the extraction that is replaced.
"""

import pytest

from glr import db, refetch

from test_report_causes import make_document

FIRST_RUN = "2026-08-11T09:00:00Z"


@pytest.fixture
def corpus(tmp_path):
    """One of each: usable, scanned PDF, blocked, failed, and never fetched."""
    conn = db.connect(tmp_path / "glr.sqlite3")
    db.start_run(conn, "run-1", "AI maturity model", "google", "{}", "0.1.0",
                 batch_id="batch-1")

    def add(url, host, **kwargs):
        kwargs.setdefault("fetched_at", FIRST_RUN)
        return make_document(conn, "run-1", url, host, **kwargs)

    add("https://oecd.org/a", "oecd.org", rank=1, word_count=2400)
    add("https://who.int/b", "who.int", rank=2, word_count=900)
    add("https://scan.example/c.pdf", "scan.example", rank=3, media_type="pdf",
        word_count=0,
        extraction_error="no text layer (scanned PDF?); retry the run with --ocr")
    add("https://linkedin.com/d", "linkedin.com", rank=4,
        blocked_reason="captcha challenge: 'captcha'")
    add("https://sciencedirect.com/e", "sciencedirect.com", rank=5,
        fetch_error="HTTP 500: please try again", proxy_status=500)
    db.finish_run(conn, "run-1", "completed")
    conn.commit()
    return conn


def scope_ids(conn):
    from glr import interchange
    return interchange.document_ids(conn, ["run-1"])


# --- what --all selects ---------------------------------------------------


def test_all_selects_every_document_whose_bytes_are_archived(corpus):
    """Including the ones that extracted perfectly well. An extractor that
    starts collecting a field it did not collect before has to re-read those,
    and they carry no recorded cause pointing at them."""
    targets = refetch.archived(corpus, scope_ids(corpus))
    assert {t.host for t in targets} == {"oecd.org", "who.int", "scan.example"}


def test_a_failed_retrieval_has_no_bytes_to_re_extract(corpus):
    targets = refetch.archived(corpus, scope_ids(corpus))
    assert "sciencedirect.com" not in {t.host for t in targets}


def test_a_block_page_is_not_re_extracted(corpus):
    """Its bytes are archived on purpose — they evidence that the source was
    unreachable — but they are a firewall's page. Re-extracting one would only
    produce a cleaner rendering of a block notice for the corpus to trip over."""
    targets = refetch.archived(corpus, scope_ids(corpus))
    assert "linkedin.com" not in {t.host for t in targets}


def test_the_archive_reference_needed_to_read_the_bytes_comes_along(corpus):
    targets = refetch.archived(corpus, scope_ids(corpus))
    for target in targets:
        assert target.warc_path
        assert target.warc_offset is not None
        assert target.snapshot_id


def test_a_document_with_no_warc_path_is_skipped(tmp_path):
    conn = db.connect(tmp_path / "glr.sqlite3")
    db.start_run(conn, "run-1", "q", "google", "{}", "0.1.0")
    document_id = db.upsert_document(conn, "https://oecd.org/a", "oecd.org", "run-1")
    db.insert_snapshot(conn, document_id=document_id, run_id="run-1",
                       requested_url="https://oecd.org/a", sha256="a" * 64,
                       media_type="html", fetched_at_utc=FIRST_RUN)
    conn.commit()

    assert refetch.archived(conn, [document_id]) == []


# --- what the narrow selection picks --------------------------------------


def test_without_all_only_a_recorded_extraction_failure_is_selected(corpus):
    """The scanned PDF. Not the two that extracted fine, and not the ones
    whose bytes never arrived."""
    candidates = refetch.select(corpus, scope_ids(corpus), action="reextract")
    assert [c.host for c in candidates] == ["scan.example"]
    assert [c.reason for c in candidates] == ["no_text_layer"]


def test_the_narrow_selection_never_costs_credits(corpus):
    """`reextract` and `refetch` must not overlap: a document is on one list or
    the other, never both, or the free path would pay for the same bytes."""
    reex = {c.document_id
            for c in refetch.select(corpus, scope_ids(corpus), action="reextract")}
    refe = {c.document_id
            for c in refetch.select(corpus, scope_ids(corpus), action="refetch")}
    assert reex & refe == set()


# --- what happens to the extraction being replaced ------------------------


def snapshot_of(conn, host):
    row = conn.execute(
        "SELECT s.snapshot_id FROM snapshots s JOIN documents d USING(document_id) "
        "WHERE d.host = ?", (host,),
    ).fetchone()
    return row["snapshot_id"]


def test_the_replaced_extraction_is_kept_not_lost(corpus):
    """The only operation in the tool that replaces a content-bearing row. It
    is defensible only because the row it replaces is kept — a review that
    quoted the earlier text must still be able to find it."""
    db.start_run(corpus, "reex-1", "reextract of run run-1", "none", "{}", "0.1.0")
    snapshot_id = snapshot_of(corpus, "oecd.org")

    superseded = db.replace_extraction(
        corpus, snapshot_id, "reex-1", extractor="trafilatura-2.3.0",
        title="A better title", text="New text.", word_count=2,
        language="en", extracted_at_utc="2026-08-12T10:00:00Z",
    )
    corpus.commit()

    assert superseded is True
    history = corpus.execute(
        "SELECT * FROM extraction_history WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchall()
    assert len(history) == 1
    assert history[0]["extractor"] == "trafilatura-2.2.0"
    assert history[0]["word_count"] == 2400
    assert history[0]["superseded_by_run"] == "reex-1"
    assert history[0]["superseded_at_utc"]


def test_the_current_extraction_is_the_new_one(corpus):
    db.start_run(corpus, "reex-1", "r", "none", "{}", "0.1.0")
    snapshot_id = snapshot_of(corpus, "oecd.org")
    db.replace_extraction(
        corpus, snapshot_id, "reex-1", extractor="trafilatura-2.3.0",
        text="New text.", word_count=2, language="de",
        extracted_at_utc="2026-08-12T10:00:00Z",
    )
    corpus.commit()

    rows = corpus.execute(
        "SELECT * FROM extractions WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchall()
    assert len(rows) == 1, "the UNIQUE(snapshot_id) invariant must still hold"
    assert rows[0]["language"] == "de"
    assert rows[0]["extractor"] == "trafilatura-2.3.0"


def test_re_extracting_twice_keeps_both_earlier_versions(corpus):
    snapshot_id = snapshot_of(corpus, "oecd.org")
    for index, run_id in enumerate(("reex-1", "reex-2"), start=1):
        db.start_run(corpus, run_id, "r", "none", "{}", "0.1.0")
        db.replace_extraction(
            corpus, snapshot_id, run_id, extractor=f"trafilatura-2.{index}.0",
            text=f"Version {index}.", word_count=index,
            extracted_at_utc=f"2026-08-1{index}T10:00:00Z",
        )
    corpus.commit()

    history = corpus.execute(
        "SELECT extractor FROM extraction_history WHERE snapshot_id = ? "
        "ORDER BY history_id", (snapshot_id,),
    ).fetchall()
    assert [h["extractor"] for h in history] == ["trafilatura-2.2.0", "trafilatura-2.1.0"]


def test_a_snapshot_with_no_previous_extraction_writes_no_history(corpus):
    db.start_run(corpus, "reex-1", "r", "none", "{}", "0.1.0")
    document_id = db.upsert_document(corpus, "https://new.example/x", "new.example",
                                     "run-1")
    snapshot_id = db.insert_snapshot(
        corpus, document_id=document_id, run_id="reex-1",
        requested_url="https://new.example/x", sha256="f" * 64, media_type="html",
        fetched_at_utc=FIRST_RUN, warc_path="w.warc.gz", warc_offset=0,
    )

    superseded = db.replace_extraction(
        corpus, snapshot_id, "reex-1", extractor="trafilatura-2.3.0",
        text="Text.", word_count=1, extracted_at_utc="2026-08-12T10:00:00Z",
    )
    corpus.commit()

    assert superseded is False
    assert corpus.execute(
        "SELECT COUNT(*) FROM extraction_history WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()[0] == 0


def test_every_extraction_column_is_carried_into_the_history(corpus):
    """Enumerated from `EXTRACTION_FIELDS` rather than written out, so a new
    column is carried by default instead of being dropped silently on the next
    re-extraction."""
    snapshot_id = snapshot_of(corpus, "oecd.org")
    columns = {row[1] for row in corpus.execute("PRAGMA table_info(extractions)")}
    history_columns = {row[1] for row in
                       corpus.execute("PRAGMA table_info(extraction_history)")}

    carried = columns - {"extraction_id", "snapshot_id"}
    assert carried <= history_columns
    assert carried <= set(db.EXTRACTION_FIELDS), \
        "a column was added to extractions without adding it to EXTRACTION_FIELDS"


# --- the export sees the re-extraction ------------------------------------


def test_a_re_extraction_reaches_the_export(corpus):
    """The point of the exercise: filling a field across an existing corpus
    without re-fetching anything."""
    from glr import interchange

    before = interchange.build_package(corpus, ["run-1"])
    assert {r["language"] for r in before["records"] if r.get("language")} == set()

    db.start_run(corpus, "reex-1", "reextract of run run-1", "none", "{}", "0.1.0")
    for host in ("oecd.org", "who.int"):
        db.replace_extraction(
            corpus, snapshot_of(corpus, host), "reex-1",
            extractor="trafilatura-2.2.0", text="Body text.", word_count=2,
            language="en", extracted_at_utc="2026-08-12T10:00:00Z",
        )
    corpus.commit()

    after = interchange.build_package(corpus, ["run-1"])
    assert sum(1 for r in after["records"] if r.get("language") == "en") == 2
    assert after["counts"]["documents"] == before["counts"]["documents"], \
        "re-extraction must not change how many documents the run identified"


def test_a_re_extraction_that_finds_text_moves_a_document_out_of_empty(corpus):
    """The scanned PDF, once OCR is available. `empty` becomes `ok` without a
    single credit being spent."""
    from glr import interchange

    before = interchange.build_package(corpus, ["run-1"])
    assert before["counts"]["empty"] == 1

    db.start_run(corpus, "reex-1", "r", "none", "{}", "0.1.0")
    db.replace_extraction(
        corpus, snapshot_of(corpus, "scan.example"), "reex-1",
        extractor="ocr-tesseract", text="Scanned body text.", word_count=3,
        extracted_at_utc="2026-08-12T10:00:00Z",
    )
    corpus.commit()

    after = interchange.build_package(corpus, ["run-1"])
    assert after["counts"]["empty"] == 0
    assert after["counts"]["ok"] == before["counts"]["ok"] + 1


def test_a_schema_older_than_the_history_table_gains_it_on_connect(tmp_path):
    """D20: a corpus retrieved before this feature existed must not have to be
    re-initialised to use it."""
    import sqlite3

    path = tmp_path / "older.sqlite3"
    conn = db.connect(path)
    conn.execute("DROP TABLE extraction_history")
    conn.commit()
    conn.close()

    raw = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            raw.execute("SELECT 1 FROM extraction_history").fetchall()
    finally:
        raw.close()

    reopened = db.connect(path)
    try:
        assert reopened.execute("SELECT * FROM extraction_history").fetchall() == []
    finally:
        reopened.close()
