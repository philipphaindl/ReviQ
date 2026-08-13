"""Taking a corpus out of a separate retrieval database into ReviQ's own.

The pilot corpus — 424 documents, 20 runs, 207 MB of WARC — was retrieved while
retrieval kept its own SQLite file. Merging the databases without this command
would strand it, and re-retrieving it costs 2 120 credits. So the property under
test is not "adopt runs" but "adopt loses nothing and invents nothing".

Three things can go wrong quietly, and each has a test here:

  * an integer key copied verbatim points at whatever row happens to hold that
    number in the target — an extraction attached to a stranger's snapshot;
  * a second run after an interrupted first duplicates everything;
  * an archive file that was never moved is only noticed on first read, long
    after the corpus was declared adopted.
"""

import sqlite3

import pytest

from app.retrieval import adopt, db


def seed_run(conn, run_id, urls, *, runs_dir, batch_id="batch-1", warc=True):
    """One run with a SERP hit, a snapshot and an extraction per URL."""
    db.start_run(conn, run_id, "AI maturity model", "google", "{}", "0.1.0",
                 batch_id=batch_id)
    warc_path = None
    if warc:
        warc_path = runs_dir / run_id / "snapshots.warc.gz"
        warc_path.parent.mkdir(parents=True, exist_ok=True)
        warc_path.write_bytes(b"not a real warc, but it exists")
    for position, url in enumerate(urls, start=1):
        document_id = db.upsert_document(conn, url, "example.org", run_id)
        db.insert_serp_result(
            conn, run_id, 1, position, position, url, url, "A title", "A snippet",
            "example.org", db.utc_now(), "search_x", document_id,
        )
        snapshot_id = db.insert_snapshot(
            conn, document_id=document_id, run_id=run_id, requested_url=url,
            final_url=url, origin_status_first=200, proxy_status=200,
            content_type="text/html", content_length=1000, sha256="a" * 64,
            media_type="html", fetched_at_utc=db.utc_now(),
            warc_path=str(warc_path) if warc_path else None,
            warc_offset=0, warc_record_id="urn:uuid:x", credits_cost=1,
        )
        db.insert_extraction(
            conn, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
            title=f"Document {position}", text="Body text.", word_count=2,
            extracted_at_utc=db.utc_now(),
        )
    conn.commit()


@pytest.fixture
def runs_dir(tmp_path):
    return tmp_path / "runs"


@pytest.fixture
def source(tmp_path, runs_dir):
    """A retrieval database as the standalone tool left it: two runs sharing
    one document, which is the case that exercises the mapping."""
    path = tmp_path / "old.sqlite3"
    conn = db.connect(path)
    seed_run(conn, "run-a", ["https://example.org/a", "https://example.org/shared"],
             runs_dir=runs_dir)
    seed_run(conn, "run-b", ["https://example.org/shared", "https://example.org/b"],
             runs_dir=runs_dir)
    conn.close()
    return path


@pytest.fixture
def target(tmp_path):
    conn = db.connect(tmp_path / "reviq.db")
    yield conn
    conn.close()


def counts(conn) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("runs", "documents", "serp_results", "snapshots", "extractions")
    }


# --- the dry run is the real run ------------------------------------------


def test_a_dry_run_writes_nothing(source, target, runs_dir):
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir, dry_run=True)
    src.close()

    assert counts(target) == {"runs": 0, "documents": 0, "serp_results": 0,
                              "snapshots": 0, "extractions": 0}


def test_the_dry_run_reports_exactly_what_the_real_run_does(source, target, runs_dir):
    """The dry run performs the work and rolls it back rather than predicting
    it. A second implementation that predicts is how a report and an export
    ended up disagreeing about the size of one corpus."""
    src = adopt.open_source(source)
    dry = adopt.adopt(src, target, project_id=1, runs_dir=runs_dir, dry_run=True)
    real = adopt.adopt(src, target, project_id=1, runs_dir=runs_dir, dry_run=False)
    src.close()

    assert [(t.table, t.adopted, t.skipped) for t in dry.tables] == \
           [(t.table, t.adopted, t.skipped) for t in real.tables]
    assert (dry.documents_new, dry.documents_reused) == \
           (real.documents_new, real.documents_reused)
    assert dry.runs == real.runs


# --- nothing lost ---------------------------------------------------------


def test_every_row_arrives(source, target, runs_dir):
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    # Three distinct URLs across two runs: the shared one is one document.
    assert counts(target) == {"runs": 2, "documents": 3, "serp_results": 4,
                              "snapshots": 4, "extractions": 4}


def test_the_shared_document_stays_one_document(source, target, runs_dir):
    """`canonical_url` is UNIQUE and a URL is a URL — the same rule the grey
    import applies. Two runs observing it is two observations, not two
    documents."""
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    rows = target.execute(
        "SELECT COUNT(*) FROM documents WHERE canonical_url = ?",
        ("https://example.org/shared",),
    ).fetchone()[0]
    assert rows == 1


def test_no_row_points_at_a_key_from_the_other_database(source, target, runs_dir):
    """The failure this whole module exists for. An `extraction_id` means
    nothing outside the file that assigned it, so an extraction copied verbatim
    lands on whatever snapshot holds that number here."""
    # Give the target rows of its own first, so the source's ids collide with
    # different rows rather than happening to line up.
    seed_run(target, "run-existing", ["https://other.example/x",
                                      "https://other.example/y",
                                      "https://other.example/z"],
             runs_dir=runs_dir, batch_id="batch-0")

    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    dangling = target.execute("""
        SELECT
          (SELECT COUNT(*) FROM extractions e
            LEFT JOIN snapshots s ON s.snapshot_id = e.snapshot_id
            WHERE s.snapshot_id IS NULL),
          (SELECT COUNT(*) FROM snapshots s
            LEFT JOIN documents d ON d.document_id = s.document_id
            WHERE d.document_id IS NULL),
          (SELECT COUNT(*) FROM serp_results r
            LEFT JOIN documents d ON d.document_id = r.document_id
            WHERE r.document_id IS NOT NULL AND d.document_id IS NULL)
    """).fetchone()
    assert tuple(dangling) == (0, 0, 0)


def test_each_extraction_still_belongs_to_its_own_snapshot(source, target, runs_dir):
    """Stronger than "the key resolves": it has to resolve to the *right* row.
    Every extraction's title was written next to its document's URL."""
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    pairs = target.execute("""
        SELECT d.canonical_url, e.title
        FROM extractions e
        JOIN snapshots s ON s.snapshot_id = e.snapshot_id
        JOIN documents d ON d.document_id = s.document_id
        ORDER BY d.canonical_url, e.title
    """).fetchall()
    # run-a: /a is position 1, /shared is 2. run-b: /shared is 1, /b is 2.
    assert [(r[0], r[1]) for r in pairs] == [
        ("https://example.org/a", "Document 1"),
        ("https://example.org/b", "Document 2"),
        ("https://example.org/shared", "Document 1"),
        ("https://example.org/shared", "Document 2"),
    ]


# --- idempotency ----------------------------------------------------------


def test_adopting_twice_changes_nothing(source, target, runs_dir):
    """A first attempt interrupted halfway has to be safe to repeat. `run_id`
    is a UUID and survives the move, which is what makes that decidable."""
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    after_first = counts(target)

    second = adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    assert second.runs == []
    assert len(second.runs_already_present) == 2
    assert counts(target) == after_first


# --- the archive ----------------------------------------------------------


def test_warc_paths_are_rewritten_to_this_installation(source, target, runs_dir):
    """The stored path was relative to whatever directory the old tool ran in.
    Only the file name carries over; the directory is rebuilt from the run id."""
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    for row in target.execute("SELECT run_id, warc_path FROM snapshots"):
        assert row["warc_path"] == str(runs_dir / row["run_id"] / "snapshots.warc.gz")


def test_a_missing_archive_refuses_and_writes_nothing(source, target, runs_dir, tmp_path):
    """`read_payload` verifies digests, so a wrong path is loud eventually —
    but by then the corpus has been adopted and the review has moved on."""
    (runs_dir / "run-a" / "snapshots.warc.gz").unlink()

    src = adopt.open_source(source)
    with pytest.raises(adopt.AdoptError) as exc:
        adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    assert "run-a" in str(exc.value)
    assert counts(target)["runs"] == 0


def test_a_missing_archive_is_reported_by_the_dry_run_too(source, target, runs_dir):
    (runs_dir / "run-b" / "snapshots.warc.gz").unlink()

    src = adopt.open_source(source)
    with pytest.raises(adopt.AdoptError):
        adopt.adopt(src, target, project_id=1, runs_dir=runs_dir, dry_run=True)
    src.close()


# --- the project ----------------------------------------------------------


def test_the_adopted_runs_belong_to_the_named_project(source, target, runs_dir):
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=7, runs_dir=runs_dir)
    src.close()

    projects = {r[0] for r in target.execute("SELECT DISTINCT project_id FROM runs")}
    assert projects == {7}


def test_adopting_without_a_project_leaves_the_runs_unowned(source, target, runs_dir):
    """Permitted, and honest about what it means: a run with no project is
    visible to every project, which is the pre-M2 behaviour."""
    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=None, runs_dir=runs_dir)
    src.close()

    projects = {r[0] for r in target.execute("SELECT DISTINCT project_id FROM runs")}
    assert projects == {None}


# --- the source ------------------------------------------------------------


def test_the_source_is_not_modified(source, target, runs_dir):
    """Opened read-only in SQLite's sense, not by convention: `db.connect`
    would apply the current schema to it and add `runs.project_id` on the way
    in."""
    before = sqlite3.connect(source)
    columns_before = [r[1] for r in before.execute("PRAGMA table_info(runs)")]
    before.close()

    src = adopt.open_source(source)
    adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    with pytest.raises(sqlite3.OperationalError):
        src.execute("INSERT INTO runs (run_id, query, engine, search_params_json,"
                    " started_at_utc, tool_version, status) "
                    "VALUES ('x', 'q', 'e', '{}', 't', 'v', 'running')")
    src.close()

    after = sqlite3.connect(source)
    assert [r[1] for r in after.execute("PRAGMA table_info(runs)")] == columns_before
    after.close()


def test_a_database_that_is_not_a_corpus_is_refused(tmp_path, target, runs_dir):
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()

    with pytest.raises(adopt.AdoptError, match="not a retrieval database"):
        adopt.adopt(adopt.open_source(path), target, project_id=1, runs_dir=runs_dir)


def test_a_source_that_does_not_exist_says_so(tmp_path):
    with pytest.raises(adopt.AdoptError, match="no such database"):
        adopt.open_source(tmp_path / "nope.sqlite3")


# --- an older source -------------------------------------------------------


def test_a_source_predating_a_table_still_adopts(source, target, runs_dir):
    """The normal case for this command: the corpus was retrieved before some
    of today's tables existed."""
    raw = sqlite3.connect(source)
    raw.executescript("DROP TABLE figure_descriptions; DROP TABLE figures;")
    raw.commit()
    raw.close()

    src = adopt.open_source(source)
    result = adopt.adopt(src, target, project_id=1, runs_dir=runs_dir)
    src.close()

    assert counts(target)["snapshots"] == 4
    assert dict((t.table, t.adopted) for t in result.tables)["figures"] == 0
