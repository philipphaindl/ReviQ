"""The retrievals a project can import from.

`/import/grey/from-retrieval` takes a run or batch id, and until this endpoint
existed the only way to learn one was to read it off the CLI's output. That put
a UUID between a user and their own corpus, which is why grey literature could
not be imported without a terminal.

Uses the file-backed instance: the listing reads the retrieval tables with
plain sqlite3, which cannot join SQLAlchemy's shared in-memory connection.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.retrieval import db as retrieval_db


@pytest.fixture
def instance(file_backed_instance):
    return file_backed_instance


@pytest.fixture
def retrieval_conn(tmp_path):
    """The retrieval side of the same file, as the CLI would open it. Shares
    `tmp_path` with `instance` — that is the point."""
    connection = retrieval_db.connect(tmp_path / "reviq.db")
    yield connection
    connection.close()


def seed_run(conn, *, run_id, project_id, query="AI maturity", engine="google",
             batch_id=None, started="2026-08-11T19:00:00Z", status="completed",
             documents=0):
    conn.execute(
        """INSERT INTO runs (run_id, query, engine, search_params_json,
                             started_at_utc, tool_version, status, batch_id,
                             project_id)
           VALUES (?, ?, ?, '{}', ?, '0.1.0', ?, ?, ?)""",
        (run_id, query, engine, started, status, batch_id, project_id),
    )
    for i in range(documents):
        url = f"https://example.test/{run_id}/{i}"
        conn.execute(
            """INSERT INTO documents (canonical_url, host, first_seen_run_id,
                                      first_seen_at_utc)
               VALUES (?, 'example.test', ?, ?)""",
            (url, run_id, started),
        )
        doc_id = conn.execute(
            "SELECT document_id FROM documents WHERE canonical_url = ?", (url,)
        ).fetchone()["document_id"]
        conn.execute(
            """INSERT INTO serp_results (run_id, page, position, global_rank,
                                         raw_url, canonical_url, title, snippet,
                                         retrieved_at_utc, document_id)
               VALUES (?, 1, ?, ?, ?, ?, 'T', 'S', ?, ?)""",
            (run_id, i + 1, i + 1, url, url, started, doc_id),
        )
    conn.commit()


def listing(instance, pid):
    r = instance.client.get(f"/api/projects/{pid}/retrievals")
    r.raise_for_status()
    return r.json()


def test_a_project_without_retrievals_gets_an_empty_list(instance):
    pid = instance.create_project(title="P")["id"]
    assert listing(instance, pid) == []


def test_a_single_run_is_offered_with_what_it_found(instance, retrieval_conn):
    pid = instance.create_project(title="P")["id"]
    seed_run(retrieval_conn, run_id="r1", project_id=pid,
             query='"AI maturity model"', documents=3)

    [entry] = listing(instance, pid)

    assert entry["kind"] == "run"
    assert entry["scope_id"] == "r1"
    assert entry["queries"] == ['"AI maturity model"']
    assert entry["documents"] == 3
    assert entry["already_imported"] is False


def test_a_batch_is_one_entry_not_one_per_query(instance, retrieval_conn):
    """`batch` issues a query set together, and that set is the unit a methods
    section describes — and the unit `from-retrieval` imports."""
    pid = instance.create_project(title="P")["id"]
    for i in range(3):
        seed_run(retrieval_conn, run_id=f"r{i}", project_id=pid, batch_id="b1",
                 query=f"query {i}", documents=2)

    [entry] = listing(instance, pid)

    assert entry["kind"] == "batch"
    assert entry["scope_id"] == "b1"
    assert entry["runs"] == 3
    assert sorted(entry["queries"]) == ["query 0", "query 1", "query 2"]
    assert entry["documents"] == 6


def test_another_projects_runs_are_not_offered(instance, retrieval_conn):
    """D28. A shared installation holds every project's corpus, and offering
    another review's runs would let one import the other's sources."""
    mine = instance.create_project(title="Mine")["id"]
    theirs = instance.create_project(title="Theirs")["id"]
    seed_run(retrieval_conn, run_id="mine", project_id=mine, documents=1)
    seed_run(retrieval_conn, run_id="theirs", project_id=theirs, documents=1)

    assert [e["scope_id"] for e in listing(instance, mine)] == ["mine"]


def test_a_run_belonging_to_no_project_is_not_offered(instance, retrieval_conn):
    """Runs made before the corpus was filed under a review carry a NULL
    project. They are adoptable, but not silently importable into whichever
    project happens to ask."""
    pid = instance.create_project(title="P")["id"]
    seed_run(retrieval_conn, run_id="orphan", project_id=None, documents=1)

    assert listing(instance, pid) == []


def test_an_unfinished_batch_says_so(instance, retrieval_conn):
    """A batch whose last run died leaves a partial corpus. Importable, but the
    number it contributes to "records identified" is not the number the
    protocol asked for."""
    pid = instance.create_project(title="P")["id"]
    seed_run(retrieval_conn, run_id="ok", project_id=pid, batch_id="b1",
             documents=2, status="completed")
    seed_run(retrieval_conn, run_id="died", project_id=pid, batch_id="b1",
             documents=0, status="failed")

    [entry] = listing(instance, pid)

    assert entry["incomplete"] is True


def test_an_already_imported_scope_is_marked(instance, retrieval_conn):
    """Re-importing changes nothing — every record reports as already present —
    but silently doing nothing is worse than saying so beforehand."""
    pid = instance.create_project(title="P")["id"]
    seed_run(retrieval_conn, run_id="r1", project_id=pid, documents=1)

    instance.client.post(
        f"/api/projects/{pid}/import/grey/from-retrieval",
        json={"scope_id": "r1"},
    ).raise_for_status()

    [entry] = listing(instance, pid)
    assert entry["already_imported"] is True


def test_the_newest_retrieval_comes_first(instance, retrieval_conn):
    pid = instance.create_project(title="P")["id"]
    seed_run(retrieval_conn, run_id="old", project_id=pid,
             started="2026-08-01T10:00:00Z")
    seed_run(retrieval_conn, run_id="new", project_id=pid,
             started="2026-08-12T10:00:00Z")

    assert [e["scope_id"] for e in listing(instance, pid)] == ["new", "old"]


def test_many_runs_do_not_cost_a_query_each(instance, retrieval_conn):
    """A twenty-query batch is ordinary, and the import page calls this on
    every open."""
    pid = instance.create_project(title="P")["id"]
    for i in range(2):
        seed_run(retrieval_conn, run_id=f"few{i}", project_id=pid, batch_id="few")
    for i in range(20):
        seed_run(retrieval_conn, run_id=f"many{i}", project_id=pid, batch_id="many")

    bind = instance.session.get_bind()
    seen: list[str] = []
    listener = lambda c, cur, s, p, ctx, m: seen.append(s)  # noqa: E731
    event.listen(bind, "before_cursor_execute", listener)
    try:
        listing(instance, pid)
    finally:
        event.remove(bind, "before_cursor_execute", listener)

    # 22 runs must not mean 22 statements on the review side.
    assert len(seen) < 10


def test_an_unknown_project_is_a_404(instance):
    assert instance.client.get(
        "/api/projects/9999/retrievals").status_code == 404
