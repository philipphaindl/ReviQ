"""Two reviews in one database do not share each other's retrievals.

Merging the databases put every project's runs in one file. The saving on offer
is real — project B need not spend a credit on a URL project A already
archived — and it is the wrong saving: B's retrieval report would then name a
date on which nothing was retrieved for B, and cite bytes fetched under
someone else's protocol. One credit against the one thing the credit buys.

The subtle half is that this has to hold for *both* snapshot readers. Scoping
only `has_snapshot` would have B pay for its own fetch and then, whenever that
fetch was blocked, still be handed A's clean snapshot by `best_snapshot` — the
same leak, now also charged for.
"""

import pytest

from app.retrieval import db, interchange, refetch, report

FIRST = "2026-08-01T10:00:00Z"
LATER = "2026-08-11T10:00:00Z"

URL = "https://example.org/shared"


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "reviq.db")
    yield connection
    connection.close()


def run_for(conn, run_id, project_id, *, batch_id=None):
    db.start_run(conn, run_id, "AI maturity model", "google", "{}", "0.1.0",
                 batch_id=batch_id, project_id=project_id)


def snapshot(conn, document_id, run_id, *, when, blocked=None, failed=None):
    return db.insert_snapshot(
        conn, document_id=document_id, run_id=run_id, requested_url=URL,
        final_url=URL, origin_status_first=200, proxy_status=200,
        content_type="text/html", content_length=1000,
        sha256=None if failed else "a" * 64, media_type="html",
        fetched_at_utc=when, warc_path="data/runs/x/snapshots.warc.gz",
        warc_offset=0, warc_record_id="urn:uuid:x", credits_cost=1,
        fetch_error=failed, blocked_reason=blocked,
    )


# --- the two readers agree -------------------------------------------------


def test_a_project_does_not_see_another_projects_snapshot(conn):
    run_for(conn, "run-a", 1)
    document_id = db.upsert_document(conn, URL, "example.org", "run-a")
    snapshot(conn, document_id, "run-a", when=FIRST)
    conn.commit()

    assert db.has_snapshot(conn, document_id, 1) is True
    assert db.has_snapshot(conn, document_id, 2) is False
    assert db.best_snapshot(conn, document_id, 2) is None


def test_without_a_project_the_global_view_is_unchanged(conn):
    """What the CLI outside a review asks for, and what every test written
    before projects existed still means."""
    run_for(conn, "run-a", 1)
    document_id = db.upsert_document(conn, URL, "example.org", "run-a")
    snapshot(conn, document_id, "run-a", when=FIRST)
    conn.commit()

    assert db.has_snapshot(conn, document_id) is True
    assert db.best_snapshot(conn, document_id) is not None


def test_a_blocked_own_snapshot_does_not_fall_back_to_the_other_project(conn):
    """The leak that scoping only `has_snapshot` would have left open: B pays
    for a fetch, B's fetch is blocked, and B is handed A's clean snapshot —
    with A's retrieval date on it."""
    run_for(conn, "run-a", 1)
    run_for(conn, "run-b", 2)
    document_id = db.upsert_document(conn, URL, "example.org", "run-a")
    snapshot(conn, document_id, "run-a", when=FIRST)
    snapshot(conn, document_id, "run-b", when=LATER, blocked="cf_challenge")
    conn.commit()

    chosen = db.best_snapshot(conn, document_id, 2)
    assert chosen["run_id"] == "run-b"
    assert chosen["blocked_reason"] == "cf_challenge"

    # Project A is unaffected by B's failed attempt.
    assert db.best_snapshot(conn, document_id, 1)["run_id"] == "run-a"


def test_within_one_project_the_cross_run_rule_still_holds(conn):
    """Narrowing must not break what `best_snapshot` is for: a refetch belongs
    to the same review as the run it repairs, so the repaired snapshot has to
    win over the failure it replaces."""
    run_for(conn, "run-a", 1, batch_id="batch-1")
    run_for(conn, "run-retry", 1)
    document_id = db.upsert_document(conn, URL, "example.org", "run-a")
    snapshot(conn, document_id, "run-a", when=FIRST, failed="timeout")
    snapshot(conn, document_id, "run-retry", when=LATER)
    conn.commit()

    chosen = db.best_snapshot(conn, document_id, 1)
    assert chosen["run_id"] == "run-retry"
    assert chosen["fetch_error"] is None


# --- the project is derived, not restated ---------------------------------


def test_the_project_comes_from_the_runs_in_scope(conn):
    run_for(conn, "run-a", 3, batch_id="batch-1")
    run_for(conn, "run-b", 3, batch_id="batch-1")
    conn.commit()

    assert db.project_of_runs(conn, ["run-a", "run-b"]) == 3
    assert db.project_of_runs(conn, []) is None


def test_runs_from_more_than_one_project_fall_back_to_the_global_view(conn):
    """Cannot arise from one run id or one batch id, so it means the ids were
    assembled by hand. Showing a few rows too many beats silently dropping the
    other project's."""
    run_for(conn, "run-a", 1)
    run_for(conn, "run-b", 2)
    conn.commit()

    assert db.project_of_runs(conn, ["run-a", "run-b"]) is None


def test_runs_predating_projects_read_as_global(conn):
    run_for(conn, "run-old", None)
    conn.commit()

    assert db.project_of_runs(conn, ["run-old"]) is None


# --- report, export and refetch see the same corpus -----------------------


def _two_projects_over_one_url(conn):
    """Project 1 holds the URL cleanly; project 2's own attempt failed."""
    run_for(conn, "run-a", 1, batch_id="batch-a")
    run_for(conn, "run-b", 2, batch_id="batch-b")
    document_id = db.upsert_document(conn, URL, "example.org", "run-a")
    for run_id, when in (("run-a", FIRST), ("run-b", LATER)):
        db.insert_serp_result(
            conn, run_id, 1, 1, 1, URL, URL, "A title", "A snippet",
            "example.org", when, "search_x", document_id,
        )
    clean = snapshot(conn, document_id, "run-a", when=FIRST)
    db.insert_extraction(
        conn, snapshot_id=clean, extractor="trafilatura-2.2.0", title="A title",
        text="Body text.", word_count=2, extracted_at_utc=FIRST,
    )
    snapshot(conn, document_id, "run-b", when=LATER, failed="timeout")
    conn.commit()
    return document_id


def test_the_export_shows_a_project_its_own_retrieval(conn):
    _two_projects_over_one_url(conn)

    package_b = interchange.build_package(conn, ["run-b"])
    record = package_b["records"][0]

    assert record["retrieval_status"] == "failed"
    assert record["retrieved_at_utc"] == LATER


def test_the_report_agrees_with_the_export(conn, tmp_path):
    """D23 in its project-scoped form. The report expresses `best_snapshot` as
    a window function for speed; if the two rules drifted apart, the report and
    the export would again disagree about how large the corpus is."""
    _two_projects_over_one_url(conn)

    out = report.report_batch(conn, "batch-b", tmp_path / "b.md")
    text = out.read_text(encoding="utf-8")

    package = interchange.build_package(conn, ["run-b"])
    usable = package["counts"]["ok"]

    assert f"Usable sources | {usable}" in text or f"| {usable} " in text
    assert LATER in text
    assert FIRST not in text


def test_a_refetch_is_priced_against_the_projects_own_snapshots(conn):
    """A retry that counted another project's clean snapshot as its own would
    quote the reviewer a smaller bill than the run it is about to make — and,
    the other way round, would offer to retry a document this project holds
    perfectly well."""
    _two_projects_over_one_url(conn)

    scope_b = refetch.for_scope(conn, "batch-b")
    scope_a = refetch.for_scope(conn, "batch-a")

    assert scope_b.project_id == 2
    assert [c.reason for c in scope_b.candidates] == ["fetch_failed"]
    assert scope_a.project_id == 1
    assert scope_a.candidates == []
