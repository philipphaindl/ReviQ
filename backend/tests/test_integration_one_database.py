"""Retrieval and review in one file, reached two ways.

Every other test in this suite runs on an in-memory database, which is fast and
which the retrieval side cannot open: it uses plain sqlite3, and a raw
connection cannot join SQLAlchemy's shared in-memory one. So the claim M2
actually makes — *one file, two access layers, under WAL* — is not exercised
anywhere else. It is exercised here, on a real file, and this is the test to
run first when something about the merge looks wrong.

What it holds:

  * a retrieval written with sqlite3 is visible to a request served through
    SQLAlchemy, and the other way round;
  * importing that retrieval needs no file passing through disk;
  * the grey source that results carries join keys into the retrieval tables,
    so the archived bytes are one join away rather than a re-parsed package;
  * an uploaded package from elsewhere leaves those keys empty, because the
    integer ids in it belonged to someone else's database.
"""
from __future__ import annotations

import hashlib

import pytest

from app.retrieval import db as retrieval_db

URL_A = "https://oecd.org/ai-maturity"
URL_B = "https://who.int/digital-health"


@pytest.fixture
def instance(file_backed_instance):
    """A ReviQ deployment on a real file — both halves of it."""
    return file_backed_instance


@pytest.fixture
def conn(tmp_path):
    """The retrieval side of the same file, as the CLI would open it.

    Shares `tmp_path` with `file_backed_instance`, which is the point: this is
    the same file the API is serving from, reached the other way."""
    connection = retrieval_db.connect(tmp_path / "reviq.db")
    yield connection
    connection.close()


def retrieve(conn, run_id, urls, *, project_id, batch_id="batch-1", clean=True):
    """A retrieval as `python -m app.retrieval run` would leave it.

    The digest is derived from the URL, not from the position in the run. A
    digest stands for the content, and the grey import deduplicates on it: two
    distinct documents sharing one would be recognised as byte-identical — which
    is correct behaviour and is tested in `test_integration_grey_import.py`, but
    it is not what any test here is about, and a per-run counter collides as
    soon as a fixture uses two runs of one document each.
    """
    retrieval_db.start_run(conn, run_id, "AI maturity model", "google", "{}",
                           "0.1.0", batch_id=batch_id, project_id=project_id)
    for position, url in enumerate(urls, start=1):
        document_id = retrieval_db.upsert_document(conn, url, url.split("/")[2], run_id)
        retrieval_db.insert_serp_result(
            conn, run_id, 1, position, position, url, url, f"Title {position}",
            "A snippet", url.split("/")[2], retrieval_db.utc_now(), "search_x",
            document_id,
        )
        snapshot_id = retrieval_db.insert_snapshot(
            conn, document_id=document_id, run_id=run_id, requested_url=url,
            final_url=url, origin_status_first=200, proxy_status=200,
            content_type="text/html", content_length=51234,
            # NULL on a failed fetch, as the real path leaves it: there were no
            # bytes to digest.
            sha256=hashlib.sha256(url.encode("utf-8")).hexdigest() if clean else None,
            media_type="html",
            fetched_at_utc=retrieval_db.utc_now(),
            warc_path=f"data/runs/{run_id}/snapshots.warc.gz", warc_offset=0,
            warc_record_id="urn:uuid:x", credits_cost=1,
            fetch_error=None if clean else "connect timeout",
        )
        if clean:
            retrieval_db.insert_extraction(
                conn, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
                title=f"Title {position}", text="Body text here.", word_count=3,
                extracted_at_utc=retrieval_db.utc_now(),
            )
    conn.commit()


# --- the two layers see the same file -------------------------------------


def test_a_retrieval_written_with_sqlite3_is_visible_to_the_api(instance, conn):
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A, URL_B], project_id=project)

    result = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    )
    result.raise_for_status()
    body = result.json()

    assert body["total_in_package"] == 2
    assert body["imported_unique"] == 2
    assert body["scope"] == {"kind": "run", "id": "run-1"}


def test_the_counts_still_add_up_on_the_internal_path(instance, conn):
    """The M1a invariant, on the path that did not exist when M1a was written.
    Two entry points counting the same thing separately is exactly how
    `detected_duplicates` came to mean two different things."""
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A, URL_B], project_id=project)

    first = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    ).json()
    second = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    ).json()

    for body in (first, second):
        assert (body["imported_unique"] + body["imported_duplicates"]
                + body["already_present"] + body["skipped_no_citekey"]
                ) == body["total_in_package"]
    assert second["already_present"] == 2
    assert second["imported_unique"] == 0


def test_a_batch_id_works_as_well_as_a_run_id(instance, conn):
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A], project_id=project, batch_id="batch-7")
    retrieve(conn, "run-2", [URL_B], project_id=project, batch_id="batch-7")

    body = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "batch-7"},
    ).json()

    assert body["scope"] == {"kind": "batch", "id": "batch-7"}
    assert body["queries"] == 2
    assert body["imported_unique"] == 2


def test_an_unknown_scope_is_a_404_not_an_empty_import(instance, conn):
    """An empty import and a typo'd id used to be indistinguishable in every
    other importer in this codebase. Not this one."""
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A], project_id=project)

    response = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-does-not-exist"},
    )
    assert response.status_code == 404


# --- the join keys ---------------------------------------------------------


def test_the_grey_source_points_back_into_the_retrieval_tables(instance, conn):
    """The point of one database. Without these the archived text of a source
    is reachable only by re-parsing the package it was imported from."""
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A], project_id=project)
    instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    ).raise_for_status()

    source = instance.client.get(f"/api/projects/{project}/grey-sources").json()[0]
    assert source["document_id"] is not None
    assert source["snapshot_id"] is not None

    # And they resolve — to the row whose digest the grey source already carries.
    row = conn.execute(
        "SELECT d.canonical_url, s.sha256 FROM snapshots s "
        "JOIN documents d ON d.document_id = s.document_id "
        "WHERE s.snapshot_id = ?",
        (source["snapshot_id"],),
    ).fetchone()
    assert row["canonical_url"] == source["canonical_url"]
    assert row["sha256"] == source["sha256"]


def test_the_archived_text_is_one_join_away(instance, conn):
    """What the join keys are for, spelled out: from a paper in the review to
    the text extracted from the archived bytes, without touching a package."""
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A], project_id=project)
    instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    ).raise_for_status()

    source = instance.client.get(f"/api/projects/{project}/grey-sources").json()[0]
    text = conn.execute(
        "SELECT text FROM extractions WHERE snapshot_id = ?",
        (source["snapshot_id"],),
    ).fetchone()
    assert text["text"] == "Body text here."


def test_an_uploaded_package_leaves_the_join_keys_empty(instance):
    """A package from a co-reviewer names documents this database may not hold,
    and the integer ids in it belonged to theirs. NULL is the honest answer."""
    project = instance.create_project(title="MLR")["id"]
    instance.import_grey(project, [{"record_key": "oecd-1",
                                    "canonical_url": URL_A}])

    source = instance.client.get(f"/api/projects/{project}/grey-sources").json()[0]
    assert source["document_id"] is None
    assert source["snapshot_id"] is None


# --- projects do not share a retrieval ------------------------------------


def test_one_projects_import_does_not_pick_up_anothers_runs(instance, conn):
    project_a = instance.create_project(title="A")["id"]
    project_b = instance.create_project(title="B")["id"]
    retrieve(conn, "run-a", [URL_A], project_id=project_a)
    retrieve(conn, "run-b", [URL_B], project_id=project_b)

    body = instance.client.post(
        f"/api/projects/{project_b}/import/grey/from-retrieval",
        json={"scope_id": "run-b"},
    ).json()

    assert body["imported_unique"] == 1
    sources = instance.client.get(f"/api/projects/{project_b}/grey-sources").json()
    assert [s["canonical_url"] for s in sources] == [URL_B]


def test_an_unretrievable_record_imports_with_its_cause(instance, conn):
    """Unchanged from the upload path, and it has to stay unchanged: these are
    the PRISMA "reports not retrieved" and the reason they are defensible."""
    project = instance.create_project(title="MLR")["id"]
    retrieve(conn, "run-1", [URL_A], project_id=project, clean=False)

    body = instance.client.post(
        f"/api/projects/{project}/import/grey/from-retrieval",
        json={"scope_id": "run-1"},
    ).json()

    assert body["imported_unretrievable"] == 1
    source = instance.client.get(f"/api/projects/{project}/grey-sources").json()[0]
    assert source["retrieval_status"] == "failed"
    assert source["retrieval_reason"] == "fetch_failed"
