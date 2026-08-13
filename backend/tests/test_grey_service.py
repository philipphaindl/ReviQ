"""Mapping a retrieval package into the grey literature stream.

Everything here is a pure function over dicts, so it runs without a database
or an HTTP client. The fixtures mirror a real 424-document pilot corpus
("AI maturity model", 20 queries, August 2026) — including its failure modes,
which are the part an importer is most likely to get quietly wrong.
"""
from __future__ import annotations

import json

import pytest

from app.services import grey_service as gs
from app.services.streams import GREY, RESERVED_SOURCE_PREFIXES, SEARCH, SNOWBALL


def record(**fields) -> dict:
    base = {
        "record_key": "oecd-org-3f2a91c07be4",
        "canonical_url": "https://oecd.org/ai-maturity",
        "host": "oecd.org",
        "discovery": "serp",
        "discovery_depth": 0,
        "retrieval_status": "ok",
        "retrieval_reason": None,
        "title": "AI Maturity in the Public Sector",
        "source_url": "https://www.oecd.org/ai-maturity/",
        "raw_url": "https://oecd.org/ai-maturity?utm_source=x",
        "retrieved_at_utc": "2026-08-11T19:36:06Z",
        "sha256": "a" * 64,
        "media_type": "html",
        "content_length": 51234,
        "author": "OECD",
        "publication_date": "2024-03-15",
        "language": "en",
        "word_count": 4210,
        "snippet": "A five-level model for assessing AI maturity in government.",
        "warc": {
            "run_id": "f18812ff-2511-477e-a5e1-5edc40466eb9",
            "filename": "snapshots.warc.gz",
            "offset": 56108,
            "record_id": "<urn:uuid:fefa3433>",
            "recorded_path": "data/runs/f18812ff/snapshots.warc.gz",
        },
        "observations": [
            {"query": '"AI maturity model"', "global_rank": 3, "run_id": "r1"},
            {"query": '"AI readiness assessment"', "global_rank": 11, "run_id": "r2"},
        ],
    }
    base.update(fields)
    return base


def package(records=None, **fields) -> dict:
    base = {
        "_schema": gs.SCHEMA,
        "_exported_at": "2026-08-12T13:41:52Z",
        "tool": {"name": "reviq-retrieval", "version": "0.1.0"},
        "canonicalization": "reviq.urls.canonicalize/1",
        "runs": [{"run_id": "r1", "engine": "google", "query": '"AI maturity model"'}],
        "archive": [],
        "counts": {"ok": 1, "documents": 1, "reasons": {}},
        "records": records if records is not None else [record()],
        "scope": {"kind": "batch", "id": "151514f7"},
    }
    base.update(fields)
    return base


# --- the package contract -------------------------------------------------


def test_a_valid_package_parses():
    assert gs.parse_package(json.dumps(package()))["_schema"] == gs.SCHEMA


def test_bytes_and_str_are_both_accepted():
    raw = json.dumps(package())
    assert gs.parse_package(raw.encode("utf-8")) == gs.parse_package(raw)


def test_a_foreign_json_file_is_refused_by_schema():
    """A file that merely has a `records` key would import as nonsense, with a
    provenance trail that looks authoritative because it came from a file."""
    with pytest.raises(gs.GreyImportError) as exc:
        gs.parse_package(json.dumps({"records": [{"title": "x"}]}))
    assert "glr-interchange-v1" in str(exc.value)


def test_a_future_schema_version_is_refused_rather_than_guessed():
    with pytest.raises(gs.GreyImportError):
        gs.parse_package(json.dumps(package(_schema="glr-interchange-v2")))


def test_the_error_says_how_to_produce_a_package():
    with pytest.raises(gs.GreyImportError) as exc:
        gs.parse_package("{}")
    assert "python -m app.retrieval export-json" in str(exc.value)


def test_a_legacy_schema_package_still_parses():
    """A package a co-reviewer exported before retrieval moved into ReviQ."""
    assert gs.parse_package(json.dumps(package(_schema=gs.LEGACY_SCHEMA)))


def test_write_side_and_read_side_agree_on_the_schema_identifier():
    """`interchange.SCHEMA` is what the exporter stamps on every package; if it
    drifts from what this reader accepts, every export written after the drift
    fails to import — silently, until the next upload. `dedup_status` and
    `detected_duplicates` diverged exactly this way once already."""
    from app.retrieval import interchange
    assert interchange.SCHEMA in gs.ACCEPTED_SCHEMAS


@pytest.mark.parametrize("raw", ["not json", "", "[]", '"a string"'])
def test_malformed_input_raises_the_importer_error_not_a_json_error(raw):
    with pytest.raises(gs.GreyImportError):
        gs.parse_package(raw)


def test_a_package_whose_records_are_not_a_list_is_refused():
    broken = package()
    broken["records"] = "not a list"
    with pytest.raises(gs.GreyImportError):
        gs.parse_package(json.dumps(broken))


# --- the engine label -----------------------------------------------------


def test_the_engine_comes_from_the_package_not_from_the_user():
    assert gs.engine_of(package()) == "google"


def test_several_engines_report_mixed():
    p = package(runs=[{"engine": "google"}, {"engine": "bing"}])
    assert gs.engine_of(p) == "mixed"


def test_a_refetch_run_does_not_become_the_engine_label():
    """A `refetch` run records `engine: none` — it issued no search. It says
    nothing about where the documents came from."""
    p = package(runs=[{"engine": "google"}, {"engine": "none"}])
    assert gs.engine_of(p) == "google"


def test_a_package_with_only_refetch_runs_is_unknown_not_none():
    assert gs.engine_of(package(runs=[{"engine": "none"}])) == "unknown"


def test_no_runs_at_all():
    assert gs.engine_of(package(runs=[])) == "unknown"


# --- the source label and the stream axes ---------------------------------


def test_a_search_hit_gets_the_reserved_grey_prefix():
    assert gs.source_label(record(), "google") == "grey:google"


def test_a_snowballed_document_gets_the_snowball_prefix():
    assert gs.source_label(record(discovery="link"), "google") == "grey-snowball:google"


def test_both_prefixes_are_the_ones_streams_reserves():
    """If these drift, a grey paper is read as a database hit and inflates the
    PRISMA "records identified from databases" box."""
    assert gs.GREY_SEARCH_PREFIX in RESERVED_SOURCE_PREFIXES
    assert gs.GREY_SNOWBALL_PREFIX in RESERVED_SOURCE_PREFIXES


def test_every_paper_is_in_the_grey_stream():
    for disc in ("serp", "link"):
        assert gs.record_to_paper_dict(record(discovery=disc), "google")["stream"] == GREY


def test_the_two_sampling_mechanisms_map_to_reviqs_names():
    assert gs.record_to_paper_dict(record(discovery="serp"), "g")["discovery"] == SEARCH
    assert gs.record_to_paper_dict(record(discovery="link"), "g")["discovery"] == SNOWBALL


def test_a_record_with_no_discovery_field_is_treated_as_a_search_hit():
    r = record(); del r["discovery"]
    assert gs.record_to_paper_dict(r, "google")["discovery"] == SEARCH


# --- the paper fields -----------------------------------------------------


def test_the_paper_carries_what_a_screener_needs():
    paper = gs.record_to_paper_dict(record(), "google")
    assert paper["citekey"] == "oecd-org-3f2a91c07be4"
    assert paper["title"] == "AI Maturity in the Public Sector"
    assert paper["authors"] == "OECD"
    assert paper["year"] == 2024
    assert paper["language"] == "en"
    assert paper["abstract"].startswith("A five-level model")
    assert paper["full_text_url"] == "https://www.oecd.org/ai-maturity/"
    assert paper["full_text_inaccessible"] is False


def test_the_host_becomes_the_venue():
    """For grey literature the publishing organisation is the venue in every
    sense a review cares about, and an empty one drops the source out of every
    venue table."""
    assert gs.record_to_paper_dict(record(), "google")["venue"] == "oecd.org"


def test_a_grey_record_never_claims_a_doi():
    assert gs.record_to_paper_dict(record(), "google")["doi"] is None


def test_the_snippet_becomes_the_abstract_not_the_extracted_text():
    """The snippet is what the screener saw in the search results, which is the
    role an abstract plays at this phase. Full text can run to 46,000 words."""
    paper = gs.record_to_paper_dict(record(text="x" * 100000), "google")
    assert paper["abstract"].startswith("A five-level model")
    assert "text" not in paper


@pytest.mark.parametrize("raw,expected", [
    ("2024", 2024),
    ("2024-03-15", 2024),
    ("March 2024", 2024),
    ("15.03.2024", 2024),
    (2024, 2024),
    (None, None),
    ("", None),
    ("no date here", None),
    ("1823", None),          # before the web
    ("9999", None),
    ("Chapter 12", None),
])
def test_year_parsing(raw, expected):
    assert gs.year_of(raw) == expected


def test_a_record_without_a_title_falls_back_to_its_url():
    """`Paper.title` cannot be null, and "Untitled" would put a placeholder
    where a reviewer expects a source."""
    paper = gs.record_to_paper_dict(record(title=None), "google")
    assert paper["title"] == "https://oecd.org/ai-maturity"


def test_a_record_with_neither_title_nor_url_still_yields_a_title():
    paper = gs.record_to_paper_dict(record(title=None, canonical_url=""), "google")
    assert paper["title"] == "(no title)"


# --- the records that could not be retrieved ------------------------------


@pytest.mark.parametrize("status", ["blocked", "failed", "empty", "not_fetched"])
def test_an_unretrievable_record_is_imported_and_flagged(status):
    """Dropping these would silently shrink the PRISMA top box and hide how
    much of the grey literature had rotted or sat behind a wall."""
    paper = gs.record_to_paper_dict(record(retrieval_status=status), "google")
    assert paper["full_text_inaccessible"] is True
    assert paper["title"]          # still screenable on title and snippet
    assert paper["stream"] == GREY


def test_a_publisher_wall_keeps_its_cause():
    prov = gs.record_to_provenance_dict(
        record(retrieval_status="failed", retrieval_reason="origin_unreachable")
    )
    assert prov["retrieval_status"] == "failed"
    assert prov["retrieval_reason"] == "origin_unreachable"


def test_causes_are_counted_separately_not_as_one_failure_number():
    """32 publisher walls, 7 platform posts and 4 dead links are three
    different exclusion criteria."""
    records = (
        [record(retrieval_status="failed", retrieval_reason="origin_unreachable")] * 32
        + [record(retrieval_status="empty", retrieval_reason="no_article_text")] * 7
        + [record(retrieval_status="failed", retrieval_reason="not_found")] * 4
        + [record()] * 358
    )
    assert gs.reason_breakdown(records) == {
        "origin_unreachable": 32, "no_article_text": 7, "not_found": 4,
    }


def test_a_retrievable_record_contributes_no_reason():
    assert gs.reason_breakdown([record()]) == {}


# --- provenance -----------------------------------------------------------


def test_the_citation_triple_survives_the_import():
    """Retrieval time, payload digest and archive location. For a grey source
    those are the citation — the page may be edited or gone by the time anyone
    checks."""
    prov = gs.record_to_provenance_dict(record())
    assert prov["retrieved_at_utc"] == "2026-08-11T19:36:06Z"
    assert prov["sha256"] == "a" * 64
    assert prov["archive_filename"] == "snapshots.warc.gz"
    assert prov["archive_offset"] == 56108


def test_provenance_survives_a_record_with_no_archive():
    prov = gs.record_to_provenance_dict(record(warc=None, sha256=None))
    assert prov["archive_filename"] is None
    assert prov["sha256"] is None
    assert prov["canonical_url"] == "https://oecd.org/ai-maturity"


def test_the_search_observations_are_summarised():
    """How many queries returned a document, and its best position, are the
    numbers a search-strategy evaluation needs."""
    prov = gs.record_to_provenance_dict(record())
    assert prov["search_observations"] == 2
    assert prov["best_rank"] == 3


def test_a_snowballed_document_has_no_rank():
    prov = gs.record_to_provenance_dict(record(discovery="link", observations=[]))
    assert prov["search_observations"] == 0
    assert prov["best_rank"] is None


# --- deduplication --------------------------------------------------------


def test_the_same_url_twice_is_one_source():
    unique, dupes = gs.partition([record(), record()], set(), set())
    assert len(unique) == 1 and len(dupes) == 1


def test_the_same_bytes_under_two_urls_is_one_source():
    """The retrieval package reports byte-identical content under different
    URLs; the same document mirrored on two hosts is one source."""
    other = record(canonical_url="https://mirror.example/x", record_key="mirror-1")
    unique, dupes = gs.partition([record(), other], set(), set())
    assert len(unique) == 1 and len(dupes) == 1


def test_a_url_already_in_the_project_is_recognised():
    """Two packages for overlapping query sets return the same document."""
    unique, dupes = gs.partition(
        [record()], {"https://oecd.org/ai-maturity"}, set()
    )
    assert unique == [] and len(dupes) == 1


def test_matching_ignores_case_and_whitespace_in_the_stored_key():
    unique, _ = gs.partition([record()], {"https://oecd.org/ai-maturity"}, set())
    assert unique == []


def test_two_different_documents_are_both_kept():
    other = record(canonical_url="https://who.int/y", record_key="who-int-1",
                   sha256="b" * 64)
    unique, dupes = gs.partition([record(), other], set(), set())
    assert len(unique) == 2 and dupes == []


def test_titles_are_never_matched_on():
    """The decisive case. Two genuinely different documents routinely share a
    generic grey title; a title test would drop one of them silently."""
    a = record(title="AI Maturity Model", canonical_url="https://a.example/1",
               record_key="a-1", sha256="c" * 64)
    b = record(title="AI Maturity Model", canonical_url="https://b.example/2",
               record_key="b-2", sha256="d" * 64)
    unique, dupes = gs.partition([a, b], set(), set())
    assert len(unique) == 2, "a shared title must not merge two sources"
    assert dupes == []


def test_a_record_with_no_identity_is_treated_as_new():
    """An unidentifiable record is not evidence of duplication."""
    blank = record(canonical_url="", sha256=None, record_key="blank-1")
    unique, dupes = gs.partition([blank, blank], set(), set())
    assert len(unique) == 2 and dupes == []


def test_failed_records_share_no_hash_and_stay_distinct():
    """Every failed retrieval has `sha256: null`. Treating that as an identity
    would collapse all of them into one."""
    a = record(retrieval_status="failed", sha256=None,
               canonical_url="https://a.example/1", record_key="a-1")
    b = record(retrieval_status="failed", sha256=None,
               canonical_url="https://b.example/2", record_key="b-2")
    unique, dupes = gs.partition([a, b], set(), set())
    assert len(unique) == 2 and dupes == []


# --- package metadata -----------------------------------------------------


def test_the_canonicalisation_algorithm_is_recorded():
    """The retrieval tool pins the algorithm that produced every canonical URL
    and warns a consumer never to re-canonicalise with its own copy. Recording
    it is what lets a later reader notice two imports are not joinable."""
    meta = gs.package_metadata(package(), filename="records.json")
    assert meta["canonicalization"] == "reviq.urls.canonicalize/1"
    assert meta["tool_version"] == "0.1.0"
    assert meta["scope_kind"] == "batch"
    assert meta["scope_id"] == "151514f7"
    assert meta["filename"] == "records.json"


def test_the_packages_own_counts_are_kept_for_reconciliation():
    meta = gs.package_metadata(package(counts={"documents": 424, "ok": 358}))
    assert meta["documents_reported"] == 424
    assert meta["usable_reported"] == 358


def test_metadata_survives_a_sparse_package():
    meta = gs.package_metadata({"_schema": gs.SCHEMA, "records": []})
    assert meta["records_in_package"] == 0
    assert meta["scope_id"] is None
