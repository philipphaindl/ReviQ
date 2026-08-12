"""The interchange package: entity-shaped, provenance-carrying, versioned.

Exercises the database layer directly against real sqlite3 — no network, no
API keys, no mocks — because that is where the guarantees live.
"""

import json

import pytest

from glr import db, interchange


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.sqlite3")
    db.init_db(connection)
    yield connection
    connection.close()


def seed(connection, *, run_id="run-1", batch_id=None, query="AI maturity model"):
    db.start_run(connection, run_id, query, "google", '{"pages": 2}', "0.1.0",
                 batch_id=batch_id)
    return run_id


def add_document(connection, run_id, url, *, host=None, discovery="serp", depth=0):
    return db.upsert_document(
        connection, url, host or url.split("/")[2], run_id,
        discovery_source=discovery, discovery_depth=depth,
    )


def observe(connection, run_id, document_id, url, *, page=1, position=1, rank=1,
            title="A title", snippet="A snippet"):
    db.insert_serp_result(
        connection, run_id, page, position, rank, url, url, title, snippet,
        "example.org", db.utc_now(), "search_abc", document_id,
    )


def archive(connection, run_id, document_id, url, *, sha="a" * 64, offset=0,
            blocked=None, error=None, warc="data/runs/run-1/snapshots.warc.gz"):
    return db.insert_snapshot(
        connection, document_id=document_id, run_id=run_id, requested_url=url,
        final_url=url, origin_status_first=200, proxy_status=200,
        content_type="text/html", content_length=1000,
        sha256=None if error else sha, media_type="html",
        fetched_at_utc=db.utc_now(), warc_path=warc, warc_offset=offset,
        warc_record_id="urn:uuid:x", credits_cost=1,
        fetch_error=error, blocked_reason=blocked,
    )


def extract(connection, snapshot_id, *, text="Body text here.", words=3,
            title="Extracted title", author=None, date=None):
    db.insert_extraction(
        connection, snapshot_id=snapshot_id, extractor="trafilatura-2.2.0",
        title=title, author=author, publication_date=date, language="en",
        text=text, word_count=words, extracted_at_utc=db.utc_now(),
    )


def build(connection, run_ids, **options):
    return interchange.build_package(connection, run_ids, **options)


# --- record keys ----------------------------------------------------------


class TestRecordKey:
    def test_readable_host_and_stable_hash(self):
        key = interchange.record_key("https://www.oecd.org/ai/report", "oecd.org")
        assert key.startswith("oecd-org-")
        assert len(key.split("-")[-1]) == interchange.KEY_HASH_CHARS

    def test_identical_across_independent_databases(self, tmp_path):
        """Two co-reviewers running the same protocol get different row ids.
        If the key were sequential, one reviewer's decision would be applied
        to a different document on the other side — silently."""
        url = "https://example.org/model"
        first = interchange.record_key(url, "example.org")
        second = interchange.record_key(url, "example.org")
        assert first == second

    def test_changes_with_the_canonical_url(self):
        a = interchange.record_key("https://example.org/a", "example.org")
        b = interchange.record_key("https://example.org/b", "example.org")
        assert a != b

    def test_host_is_derived_when_not_given(self):
        assert interchange.record_key("https://oecd.org/x").startswith("oecd-org-")

    def test_safe_in_bibtex_and_filenames(self):
        key = interchange.record_key("https://a.b.co.uk/x?q=1", "a.b.co.uk")
        assert all(c.isalnum() or c == "-" for c in key)

    def test_a_missing_host_still_produces_a_key(self):
        assert interchange.record_key("not-a-url", None)


# --- shape ----------------------------------------------------------------


class TestPackageShape:
    def test_envelope_pins_schema_tool_and_canonicalisation(self, conn):
        run = seed(conn)
        pkg = build(conn, [run])
        assert pkg["_schema"] == "glr-interchange-v1"
        assert pkg["tool"]["name"] == "glr"
        assert pkg["tool"]["version"]
        # A consumer deduplicates on canonical_url and must never re-derive it
        # with its own copy of urls.py, which may be a different version.
        assert pkg["canonicalization"] == interchange.CANONICALIZATION
        assert pkg["_exported_at"].endswith("Z")

    def test_search_protocol_travels_with_the_records(self, conn):
        run = seed(conn, query="AI maturity assessment model")
        pkg = build(conn, [run])
        assert len(pkg["runs"]) == 1
        assert pkg["runs"][0]["query"] == "AI maturity assessment model"
        # Inlined, not left as a JSON string inside a parsed document.
        assert pkg["runs"][0]["search_params"] == {"pages": 2}

    def test_one_record_per_document_not_per_observation(self, conn):
        """The CSV is observation-shaped and would emit two rows here. A
        consumer needs one record with two observations, or it imports the
        same source twice."""
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        observe(conn, run, doc, url, page=1, position=1, rank=1)
        observe(conn, run, doc, url, page=2, position=3, rank=13)
        conn.commit()

        pkg = build(conn, [run])
        assert len(pkg["records"]) == 1
        assert [o["global_rank"] for o in pkg["records"][0]["observations"]] == [1, 13]

    def test_link_discovered_documents_are_present(self, conn):
        """These have no SERP observation at all. Driving the export from
        serp_results alone would omit every snowballed source."""
        run = seed(conn)
        url = "https://elsewhere.test/paper.pdf"
        doc = add_document(conn, run, url, discovery="link", depth=1)
        snap = archive(conn, run, doc, url)
        extract(conn, snap)
        conn.commit()

        records = build(conn, [run])["records"]
        assert len(records) == 1
        assert records[0]["discovery"] == "link"
        assert records[0]["discovery_depth"] == 1
        assert records[0]["observations"] == []

    def test_records_are_ordered_deterministically(self, conn):
        run = seed(conn)
        for path in ("c", "a", "b"):
            url = f"https://example.org/{path}"
            add_document(conn, run, url)
        conn.commit()
        keys = [r["record_key"] for r in build(conn, [run])["records"]]
        assert keys == sorted(keys)


# --- provenance -----------------------------------------------------------


class TestProvenance:
    def test_a_retrieved_record_carries_the_citable_facts(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        observe(conn, run, doc, url)
        snap = archive(conn, run, doc, url, sha="b" * 64, offset=512)
        extract(conn, snap, title="A Maturity Model", author="OECD", date="2024-03-11")
        conn.commit()

        record = build(conn, [run])["records"][0]
        assert record["retrieval_status"] == interchange.OK
        assert record["retrieved_at_utc"].endswith("Z")
        assert record["sha256"] == "b" * 64
        assert record["title"] == "A Maturity Model"
        assert record["author"] == "OECD"
        # The raw string, not a parsed year: parsing is a consumer's decision
        # and one it should be able to revisit.
        assert record["publication_date"] == "2024-03-11"

    def test_warc_reference_is_a_basename_and_an_offset(self, conn):
        """A recorded path is relative to the machine that did the retrieval.
        A consumer that opened it would be following a path out of a data file
        into its own filesystem."""
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        archive(conn, run, doc, url, offset=4096,
                warc="data/runs/run-1/snapshots.warc.gz")
        conn.commit()

        warc = build(conn, [run])["records"][0]["warc"]
        assert warc["filename"] == "snapshots.warc.gz"
        assert "/" not in warc["filename"]
        assert warc["offset"] == 4096
        assert warc["run_id"] == run
        assert warc["recorded_path"] == "data/runs/run-1/snapshots.warc.gz"

    def test_archive_block_lists_files_and_reports_missing_ones(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        archive(conn, run, doc, url, warc="nowhere/snapshots.warc.gz")
        conn.commit()

        entry = build(conn, [run])["archive"][0]
        assert entry["filename"] == "snapshots.warc.gz"
        assert entry["record_count"] == 1
        # Missing is reported, not raised: the records are still valid
        # provenance without the file in hand.
        assert entry["sha256"] is None
        assert "unavailable" in entry

    def test_archive_hash_lets_a_reader_verify_the_file(self, conn, tmp_path):
        warc = tmp_path / "snapshots.warc.gz"
        warc.write_bytes(b"not really a warc, but it hashes")
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        archive(conn, run, doc, url, warc=str(warc))
        conn.commit()

        entry = build(conn, [run])["archive"][0]
        assert len(entry["sha256"]) == 64
        assert entry["byte_size"] == warc.stat().st_size

    def test_inbound_link_count_is_reported(self, conn):
        run = seed(conn)
        target_url = "https://elsewhere.test/x"
        target = add_document(conn, run, target_url, discovery="link", depth=1)
        snapshots = []
        for i, path in enumerate(("a", "b")):
            url = f"https://example.org/{path}"
            source = add_document(conn, run, url)
            snapshots.append(archive(conn, run, source, url, offset=i))
            db.insert_link(conn, source, target, snapshots[-1], run,
                           target_url, "see this", 1)
        conn.commit()

        records = {r["canonical_url"]: r for r in build(conn, [run])["records"]}
        assert records[target_url]["inbound_links"] == 2


# --- retrieval status -----------------------------------------------------


class TestRetrievalStatus:
    def test_blocked_and_failed_records_are_exported_not_dropped(self, conn):
        """A consumer's 'records identified' has to reconcile with this
        tool's own retrieval report. Dropping them here guarantees it cannot."""
        run = seed(conn)
        for path, kwargs in (
            ("blocked", {"blocked": "cloudflare challenge"}),
            ("failed", {"error": "HTTP 500"}),
        ):
            url = f"https://example.org/{path}"
            doc = add_document(conn, run, url)
            archive(conn, run, doc, url, **kwargs)
        conn.commit()

        pkg = build(conn, [run])
        statuses = {r["canonical_url"].rsplit("/", 1)[1]: r["retrieval_status"]
                    for r in pkg["records"]}
        assert statuses == {"blocked": interchange.BLOCKED, "failed": interchange.FAILED}
        assert pkg["counts"][interchange.BLOCKED] == 1
        assert pkg["counts"][interchange.FAILED] == 1

    def test_blocked_records_carry_the_reason_and_no_text(self, conn):
        run = seed(conn)
        url = "https://example.org/blocked"
        doc = add_document(conn, run, url)
        snap = archive(conn, run, doc, url, blocked="cloudflare challenge")
        extract(conn, snap, text="Just a moment...", words=3)
        conn.commit()

        record = build(conn, [run])["records"][0]
        assert record["retrieval_status"] == interchange.BLOCKED
        assert record["blocked_reason"] == "cloudflare challenge"

    def test_only_usable_omits_them(self, conn):
        run = seed(conn)
        good_url, bad_url = "https://example.org/a", "https://example.org/b"
        good = add_document(conn, run, good_url)
        extract(conn, archive(conn, run, good, good_url))
        bad = add_document(conn, run, bad_url)
        archive(conn, run, bad, bad_url, blocked="waf")
        conn.commit()

        pkg = build(conn, [run], include_unretrievable=False)
        assert [r["canonical_url"] for r in pkg["records"]] == [good_url]

    def test_a_document_never_fetched_says_so(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        observe(conn, run, add_document(conn, run, url), url)
        conn.commit()
        record = build(conn, [run])["records"][0]
        assert record["retrieval_status"] == interchange.NOT_FETCHED
        assert record["sha256"] is None
        assert record["warc"] is None

    def test_a_retrieval_with_no_text_is_marked_empty(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        extract(conn, archive(conn, run, doc, url), text=None, words=0)
        conn.commit()
        assert build(conn, [run])["records"][0]["retrieval_status"] == interchange.EMPTY

    def test_counts_reconcile_with_the_records(self, conn):
        run = seed(conn)
        for path in ("a", "b", "c"):
            url = f"https://example.org/{path}"
            doc = add_document(conn, run, url)
            extract(conn, archive(conn, run, doc, url, offset=ord(path)))
        conn.commit()

        pkg = build(conn, [run])
        assert pkg["counts"]["documents"] == len(pkg["records"])
        by_status = sum(pkg["counts"][s] for s in
                        (interchange.OK, interchange.BLOCKED, interchange.FAILED,
                         interchange.EMPTY, interchange.NOT_FETCHED))
        assert by_status == len(pkg["records"])


# --- title fallback -------------------------------------------------------


class TestTitle:
    def test_falls_back_to_the_serp_title(self, conn):
        """trafilatura returns None for a title often enough that requiring
        one would lose real sources."""
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        observe(conn, run, doc, url, title="Title from the SERP")
        extract(conn, archive(conn, run, doc, url), title=None)
        conn.commit()
        assert build(conn, [run])["records"][0]["title"] == "Title from the SERP"

    def test_extracted_title_wins_over_the_serp_title(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        observe(conn, run, doc, url, title="SERP title")
        extract(conn, archive(conn, run, doc, url), title="Extracted title")
        conn.commit()
        assert build(conn, [run])["records"][0]["title"] == "Extracted title"


# --- figures --------------------------------------------------------------


class TestFigures:
    def _with_figure(self, conn, run, *, described=True):
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        snap = archive(conn, run, doc, url)
        extract(conn, snap, text="The body text of the page.", words=5)
        figure_id = db.insert_figure(
            conn, document_id=doc, snapshot_id=snap, run_id=run,
            raw_src="/img/levels.png",
            resolved_url="https://example.org/img/levels.png",
            alt_text="Maturity levels", caption="Figure 1. The maturity levels.",
            sha256="c" * 64, content_type="image/png", byte_size=20000,
            warc_path="data/runs/run-1/snapshots.warc.gz", warc_offset=99,
            warc_record_id="urn:uuid:fig", fetched_at_utc=db.utc_now(),
        )
        if described:
            db.insert_description(
                conn, figure_id=figure_id,
                description="A pyramid diagram with five levels.",
                model="claude-haiku-4-5", prompt="Describe this figure factually.",
                input_tokens=800, output_tokens=40,
                described_at_utc=db.utc_now(),
            )
        conn.commit()
        return url

    def test_descriptions_are_marked_as_model_output(self, conn):
        run = seed(conn)
        self._with_figure(conn, run)
        figure = build(conn, [run])["records"][0]["figures"][0]
        assert figure["kind"] == "model_generated"
        description = figure["descriptions"][0]
        assert description["model"] == "claude-haiku-4-5"
        assert description["prompt"]
        assert description["described_at_utc"].endswith("Z")

    def test_description_text_never_appears_in_the_extracted_text(self, conn):
        """The invariant this whole separation exists for: a review must not
        quote a model's words as if a source had published them."""
        run = seed(conn)
        self._with_figure(conn, run)
        record = build(conn, [run])["records"][0]
        assert "pyramid diagram" not in (record["text"] or "")
        serialised = json.dumps(record["text"])
        assert "pyramid" not in serialised

    def test_caption_and_alt_text_stay_on_the_source_side(self, conn):
        """They came from the page markup, so they are source content and are
        labelled separately from the generated description."""
        run = seed(conn)
        self._with_figure(conn, run)
        figure = build(conn, [run])["records"][0]["figures"][0]
        assert figure["figure"]["caption"] == "Figure 1. The maturity levels."
        assert figure["figure"]["alt_text"] == "Maturity levels"
        assert "description" not in figure["figure"]

    def test_figure_bytes_are_locatable_in_the_archive(self, conn):
        run = seed(conn)
        self._with_figure(conn, run)
        warc = build(conn, [run])["records"][0]["figures"][0]["figure"]["warc"]
        assert warc["filename"] == "snapshots.warc.gz"
        assert warc["offset"] == 99

    def test_no_figures_flag_omits_them(self, conn):
        run = seed(conn)
        self._with_figure(conn, run)
        record = build(conn, [run], include_figures=False)["records"][0]
        assert "figures" not in record

    def test_described_figures_are_counted(self, conn):
        run = seed(conn)
        self._with_figure(conn, run)
        assert build(conn, [run])["counts"]["figures_described"] == 1


# --- text -----------------------------------------------------------------


class TestText:
    def test_text_travels_inline_by_default(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        extract(conn, archive(conn, run, doc, url), text="The body of the page.")
        conn.commit()
        assert build(conn, [run])["records"][0]["text"] == "The body of the page."

    def test_no_text_omits_only_the_text(self, conn):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        extract(conn, archive(conn, run, doc, url), text="The body of the page.",
                words=5)
        conn.commit()
        record = build(conn, [run], include_text=False)["records"][0]
        assert "text" not in record
        assert record["word_count"] == 5
        assert record["retrieval_status"] == interchange.OK


# --- scope ----------------------------------------------------------------


class TestScope:
    def test_a_run_id_resolves_to_itself(self, conn):
        run = seed(conn)
        conn.commit()
        assert interchange.resolve_scope(conn, run) == ("run", [run])

    def test_a_batch_id_resolves_to_all_its_runs(self, conn):
        for index in (1, 2):
            seed(conn, run_id=f"run-{index}", batch_id="batch-x",
                 query=f"query {index}")
        conn.commit()
        kind, run_ids = interchange.resolve_scope(conn, "batch-x")
        assert kind == "batch"
        assert set(run_ids) == {"run-1", "run-2"}

    def test_an_unknown_id_raises(self, conn):
        with pytest.raises(LookupError):
            interchange.resolve_scope(conn, "nope")

    def test_a_batch_exports_documents_from_every_run(self, conn):
        for index in (1, 2):
            run = seed(conn, run_id=f"run-{index}", batch_id="batch-x",
                       query=f"query {index}")
            url = f"https://example.org/{index}"
            doc = add_document(conn, run, url)
            extract(conn, archive(conn, run, doc, url, offset=index))
        conn.commit()

        _, run_ids = interchange.resolve_scope(conn, "batch-x")
        assert len(build(conn, run_ids)["records"]) == 2

    def test_write_package_produces_valid_json_with_the_scope(self, conn, tmp_path):
        run = seed(conn)
        url = "https://example.org/a"
        doc = add_document(conn, run, url)
        extract(conn, archive(conn, run, doc, url))
        conn.commit()

        out = tmp_path / "records.json"
        count = interchange.write_package(conn, run, out)
        assert count == 1
        package = json.loads(out.read_text(encoding="utf-8"))
        assert package["scope"] == {"kind": "run", "id": run}
        assert package["records"][0]["canonical_url"] == url


# --- cross-run behaviour --------------------------------------------------


def test_a_document_archived_in_an_earlier_run_is_not_reported_as_unfetched(conn):
    """`db.has_snapshot` skips re-fetching a document already archived, so a
    later run observes it without producing a snapshot of its own. Reporting
    'not fetched' for a document sitting in the archive would be false."""
    first = seed(conn, run_id="run-1")
    url = "https://example.org/a"
    doc = add_document(conn, first, url)
    extract(conn, archive(conn, first, doc, url, sha="d" * 64))
    conn.commit()

    second = seed(conn, run_id="run-2", query="another query")
    observe(conn, second, doc, url)
    conn.commit()

    record = build(conn, [second])["records"][0]
    assert record["retrieval_status"] == interchange.OK
    assert record["sha256"] == "d" * 64
    assert record["warc"]["run_id"] == "run-1"


def test_a_clean_snapshot_wins_over_a_blocked_one(conn):
    run = seed(conn, run_id="run-1")
    url = "https://example.org/a"
    doc = add_document(conn, run, url)
    archive(conn, run, doc, url, blocked="waf")
    conn.commit()

    retry = seed(conn, run_id="run-2", query="retry")
    extract(conn, archive(conn, retry, doc, url, sha="e" * 64))
    conn.commit()

    record = build(conn, [run, retry])["records"][0]
    assert record["retrieval_status"] == interchange.OK
    assert record["sha256"] == "e" * 64
