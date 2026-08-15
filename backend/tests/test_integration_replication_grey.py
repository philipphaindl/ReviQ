"""Grey-literature retrieval survives a replication round trip.

v1 exported papers only: a grey paper arrived at the other installation with
its title and abstract but none of what makes it a *grey* source — no
SHA-256, no archive pointer, no retrieval timestamp. v2 carries `grey_sources`,
`grey_imports`, and the retrieval rows behind them, and remaps every integer
key through `app.retrieval.adopt` on the way in — the same command this
installation already uses to bring in the pilot corpus, scoped here to one
project's own runs rather than a whole database — the shared retrieval file
holds every project's corpus.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.database import get_retrieval_conn, get_session
from app.main import app
from app.retrieval import db as retrieval_db
from app.routers.replication import _optional_retrieval_conn
from tests.conftest import make_instance


@pytest.fixture
def two_file_backed_instances(tmp_path, reset_overrides):
    """A pair of file-backed deployments, so both sides can open retrieval."""
    a_path = tmp_path / "a.db"
    b_path = tmp_path / "b.db"
    a = make_instance("a", db_path=a_path)
    b = make_instance("b", db_path=b_path)
    paths = {"a": a_path, "b": b_path}

    def use(inst):
        app.dependency_overrides[get_session] = lambda: inst.session
        conn_path = paths[inst.label]

        def retrieval_conn():
            conn = retrieval_db.connect(conn_path)
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_retrieval_conn] = retrieval_conn
        app.dependency_overrides[_optional_retrieval_conn] = retrieval_conn

    use(a)  # make_instance("b", ...) last set the overrides to b; reset to a
    return SimpleNamespace(a=a, b=b, paths=paths, use=use)


def seed_retrieval(conn, run_id: str, project_id: int, urls: list[str],
                   *, batch_id: str = "batch-1") -> None:
    """One run, filed under `project_id`, with a snapshot and extraction per URL."""
    retrieval_db.start_run(conn, run_id, "AI maturity model", "google", "{}",
                           "0.1.0", batch_id=batch_id, project_id=project_id)
    for position, url in enumerate(urls, start=1):
        document_id = retrieval_db.upsert_document(conn, url, "example.org", run_id)
        retrieval_db.insert_serp_result(
            conn, run_id, 1, position, position, url, url, "A title", "A snippet",
            "example.org", retrieval_db.utc_now(), "search_x", document_id,
        )
        snapshot_id = retrieval_db.insert_snapshot(
            conn, document_id=document_id, run_id=run_id, requested_url=url,
            final_url=url, origin_status_first=200, proxy_status=200,
            content_type="text/html", content_length=1000,
            sha256=f"{position:064x}", media_type="html",
            fetched_at_utc=retrieval_db.utc_now(),
            warc_path=None, warc_offset=None, warc_record_id=None, credits_cost=1,
        )
        retrieval_db.insert_extraction(
            conn, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
            title=f"Document {position}", text="Body text.", word_count=2,
            extracted_at_utc=retrieval_db.utc_now(),
        )
    conn.commit()


def test_grey_source_ids_resolve_after_a_replication_round_trip(two_file_backed_instances):
    two = two_file_backed_instances
    two.use(two.a)
    pid = two.a.create_project(title="Source")["id"]

    conn = retrieval_db.connect(two.paths["a"])
    urls = ["https://oecd.org/ai-maturity", "https://who.int/ai-governance"]
    seed_retrieval(conn, "run-1", pid, urls)
    conn.close()

    resp = two.a.client.post(f"/api/projects/{pid}/import/grey/from-retrieval",
                             json={"scope_id": "run-1"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported_unique"] == 2

    export = two.a.client.get(f"/api/projects/{pid}/replication/export")
    assert export.status_code == 200, export.text
    zip_bytes = export.content

    two.use(two.b)
    resp = two.b.client.post(
        "/api/projects/replication/import",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    new_pid = resp.json()["id"]

    grey_sources = two.b.client.get(f"/api/projects/{new_pid}/grey-sources").json()
    assert len(grey_sources) == 2

    tconn = retrieval_db.connect(two.paths["b"])
    for gs in grey_sources:
        assert gs["document_id"] is not None, gs
        assert gs["snapshot_id"] is not None, gs
        doc = tconn.execute(
            "SELECT canonical_url FROM documents WHERE document_id = ?",
            (gs["document_id"],),
        ).fetchone()
        assert doc is not None and doc["canonical_url"] == gs["canonical_url"]
        snap = tconn.execute(
            "SELECT sha256 FROM snapshots WHERE snapshot_id = ?",
            (gs["snapshot_id"],),
        ).fetchone()
        assert snap is not None and snap["sha256"] == gs["sha256"]
    tconn.close()


def test_a_v1_style_package_with_no_grey_data_still_imports(two_file_backed_instances):
    """A package with no grey papers at all — the common case — must not be
    forced through the retrieval machinery."""
    two = two_file_backed_instances
    two.use(two.a)
    pid = two.a.create_project(title="Formal only")["id"]
    two.a.import_bib(pid, [{"citekey": "smith2020", "title": "A Formal Paper"}])

    export = two.a.client.get(f"/api/projects/{pid}/replication/export")
    assert export.status_code == 200

    two.use(two.b)
    resp = two.b.client.post(
        "/api/projects/replication/import",
        files={"file": ("pkg.zip", export.content, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    new_pid = resp.json()["id"]
    assert len(two.b.papers(new_pid)) == 1


def test_a_second_import_of_the_same_package_still_resolves_the_ids(two_file_backed_instances):
    """The second import's `adopt` call finds every run already present and
    returns empty maps (nothing new to adopt) — the fallback lookup by
    `canonical_url`/`sha256` is what has to carry `document_id`/`snapshot_id`
    then, not the map a fresh import would use."""
    two = two_file_backed_instances
    two.use(two.a)
    pid = two.a.create_project(title="Source")["id"]
    conn = retrieval_db.connect(two.paths["a"])
    seed_retrieval(conn, "run-1", pid, ["https://oecd.org/ai-maturity"])
    conn.close()
    two.a.client.post(f"/api/projects/{pid}/import/grey/from-retrieval",
                      json={"scope_id": "run-1"}).raise_for_status()
    zip_bytes = two.a.client.get(f"/api/projects/{pid}/replication/export").content

    two.use(two.b)
    for _ in range(2):
        resp = two.b.client.post(
            "/api/projects/replication/import",
            files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 200, resp.text
        new_pid = resp.json()["id"]

    grey_sources = two.b.client.get(f"/api/projects/{new_pid}/grey-sources").json()
    assert len(grey_sources) == 1
    assert grey_sources[0]["document_id"] is not None
    assert grey_sources[0]["snapshot_id"] is not None


def test_with_archive_bundles_the_warc_and_the_import_places_it(
        two_file_backed_instances, tmp_path, monkeypatch):
    """Without `--with-archive` the metadata still lands (proven above); with
    it, the bytes travel too and land where `runs_dir` expects them."""
    data_dir_a = tmp_path / "data-a"
    data_dir_b = tmp_path / "data-b"
    (data_dir_a / "runs" / "run-1").mkdir(parents=True)
    (data_dir_a / "runs" / "run-1" / "snapshots.warc.gz").write_bytes(b"a warc")

    two = two_file_backed_instances
    two.use(two.a)
    pid = two.a.create_project(title="Source")["id"]
    conn = retrieval_db.connect(two.paths["a"])
    seed_retrieval(conn, "run-1", pid, ["https://oecd.org/ai-maturity"])
    conn.close()
    two.a.client.post(f"/api/projects/{pid}/import/grey/from-retrieval",
                      json={"scope_id": "run-1"}).raise_for_status()

    monkeypatch.setenv("DATA_DIR", str(data_dir_a))
    export = two.a.client.get(
        f"/api/projects/{pid}/replication/export", params={"with_archive": "true"})
    assert export.status_code == 200

    import zipfile, io
    zf = zipfile.ZipFile(io.BytesIO(export.content))
    assert "archives/run-1/snapshots.warc.gz" in zf.namelist()

    two.use(two.b)
    monkeypatch.setenv("DATA_DIR", str(data_dir_b))
    resp = two.b.client.post(
        "/api/projects/replication/import",
        files={"file": ("pkg.zip", export.content, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    assert (data_dir_b / "runs" / "run-1" / "snapshots.warc.gz").read_bytes() == b"a warc"
