"""A glr package taken into a project, at the HTTP level.

`test_grey_service.py` covers the mapping as pure functions. What this file
covers is what only shows up once a database is involved: that the two streams
stay separate, that the retrieval provenance survives the round trip, and that
a second import of an overlapping package does not create a second paper.

The proportions come from a real 424-document pilot corpus ("AI maturity
model", 20 queries, August 2026): 358 usable, 39 failed, 22 empty, 5 blocked.
"""
from __future__ import annotations

import pytest

from app.services import streams


@pytest.fixture
def project(instance):
    return instance, instance.create_project(title="MLR")["id"]


def grey(key: str, url: str, **fields) -> dict:
    return {"record_key": key, "canonical_url": url,
            "sha256": key.ljust(64, "0"), **fields}


class _P:
    """A dict with attribute access, so `streams` can read an API response."""

    def __init__(self, data: dict):
        self.__dict__.update(data)


def _as_objects(papers: list[dict]) -> list[_P]:
    return [_P(p) for p in papers]


# --- the import itself ----------------------------------------------------


def test_a_package_becomes_grey_papers(project):
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a"),
        grey("who-2", "https://who.int/b"),
    ])

    assert result["imported_unique"] == 2
    assert result["engine"] == "google"
    papers = inst.papers(pid)
    assert len(papers) == 2
    assert {p["stream"] for p in papers} == {"grey"}
    assert {p["source"] for p in papers} == {"grey:google"}


def test_grey_papers_do_not_land_in_the_formal_stream(project):
    """The failure the stream split exists to prevent: a grey record counted as
    a database hit inflates the PRISMA "records identified from databases" box."""
    inst, pid = project
    inst.import_bib(pid, [{"citekey": "smith2020", "title": "A Formal Paper"}])
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")])

    by_stream = streams.by_stream(_as_objects(inst.papers(pid)))
    assert len(by_stream[streams.FORMAL]) == 1
    assert len(by_stream[streams.GREY]) == 1


def test_a_snowballed_grey_document_is_separated_from_a_search_hit(project):
    """Two sampling mechanisms with different biases; an MLR reports them apart."""
    inst, pid = project
    inst.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a", discovery="serp"),
        grey("blog-2", "https://blog.example/b", discovery="link", discovery_depth=1),
    ])

    papers = {p["citekey"]: p for p in inst.papers(pid)}
    assert papers["oecd-1"]["discovery"] == "search"
    assert papers["oecd-1"]["source"] == "grey:google"
    assert papers["blog-2"]["discovery"] == "snowball"
    assert papers["blog-2"]["source"] == "grey-snowball:google"


# --- the records that could not be retrieved ------------------------------


def test_unretrievable_records_are_imported_and_flagged(project):
    """They were identified by the search. Dropping them would shrink the
    PRISMA top box and hide how much grey literature could not be read."""
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("ok-1", "https://oecd.org/a"),
        grey("wall-2", "https://sciencedirect.com/b", retrieval_status="failed",
             retrieval_reason="origin_unreachable", sha256=None, warc=None),
        grey("video-3", "https://youtube.com/c", retrieval_status="empty",
             retrieval_reason="no_article_text", word_count=0),
        grey("gone-4", "https://gone.example/d", retrieval_status="failed",
             retrieval_reason="not_found", sha256=None, warc=None),
    ])

    assert result["imported_unique"] == 4
    assert result["imported_unretrievable"] == 3
    assert result["unretrievable_by_reason"] == {
        "no_article_text": 1, "not_found": 1, "origin_unreachable": 1,
    }

    papers = {p["citekey"]: p for p in inst.papers(pid)}
    assert papers["ok-1"]["full_text_inaccessible"] is False
    assert papers["wall-2"]["full_text_inaccessible"] is True
    assert papers["video-3"]["full_text_inaccessible"] is True


def test_an_unretrievable_record_stays_screenable(project):
    """Title and snippet come from the search result, so a source that could
    not be fetched can still be included or excluded on the evidence a screener
    would have had at this phase anyway."""
    inst, pid = project
    inst.import_grey(pid, [
        grey("wall-2", "https://sciencedirect.com/b", retrieval_status="failed",
             retrieval_reason="origin_unreachable", sha256=None, warc=None),
    ])

    paper = inst.paper_by_citekey(pid, "wall-2")
    assert paper["title"]
    assert paper["abstract"]


def test_the_cause_is_kept_per_source_not_just_as_a_total(project):
    """A publisher's wall, a platform post and a dead link are three different
    exclusion criteria. A review reporting one number cannot defend any."""
    inst, pid = project
    inst.import_grey(pid, [
        grey("wall-2", "https://sciencedirect.com/b", retrieval_status="failed",
             retrieval_reason="origin_unreachable", sha256=None, warc=None),
        grey("video-3", "https://youtube.com/c", retrieval_status="empty",
             retrieval_reason="no_article_text"),
    ])

    reasons = {g["record_key"]: g["retrieval_reason"] for g in inst.grey_sources(pid)}
    assert reasons == {"wall-2": "origin_unreachable", "video-3": "no_article_text"}


def test_a_package_predating_retrieval_reason_still_imports(project):
    """`retrieval_reason` was added to the format after it was first published,
    as an optional field. A package without it must import unchanged, with the
    cause simply unknown."""
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("wall-2", "https://sciencedirect.com/b", retrieval_status="failed",
             retrieval_reason=None, sha256=None, warc=None),
    ])

    assert result["imported_unique"] == 1
    assert result["imported_unretrievable"] == 1
    assert result["unretrievable_by_reason"] == {}
    assert inst.grey_sources(pid)[0]["retrieval_reason"] is None


# --- provenance -----------------------------------------------------------


def test_the_citation_triple_survives_the_import(project):
    """When it was read, the digest of what was read, where those bytes are.
    For a grey source those are the citation: the page may be edited or gone by
    the time anyone checks."""
    inst, pid = project
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")])

    source = inst.grey_sources(pid)[0]
    assert source["retrieved_at_utc"] == "2026-08-11T19:36:06Z"
    assert source["sha256"] == "oecd-1".ljust(64, "0")
    assert source["archive_filename"] == "snapshots.warc.gz"
    assert source["archive_offset"] == 56108
    assert source["canonical_url"] == "https://oecd.org/a"


def test_provenance_is_joinable_to_its_paper(project):
    inst, pid = project
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")])

    paper = inst.paper_by_citekey(pid, "oecd-1")
    assert inst.grey_sources(pid)[0]["paper_id"] == paper["id"]


def test_the_package_is_recorded_so_the_search_stays_reproducible(project):
    inst, pid = project
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")])

    imports = inst.grey_imports(pid)
    assert len(imports) == 1
    record = imports[0]
    # glr pins the algorithm that produced every canonical URL and warns a
    # consumer never to re-canonicalise with its own copy.
    assert record["canonicalization"] == "glr.urls.canonicalize/1"
    assert record["tool_version"] == "0.1.0"
    assert record["scope_id"] == "batch-1"
    assert record["filename"] == "records.json"
    assert record["imported_count"] == 1


def test_the_packages_own_counts_are_kept_for_reconciliation(project):
    """If the package's totals and what was imported disagree, the PRISMA
    diagram is wrong and someone has to be able to see which side moved."""
    inst, pid = project
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")],
                     counts={"documents": 424, "ok": 358})

    record = inst.grey_imports(pid)[0]
    assert record["documents_reported"] == 424
    assert record["usable_reported"] == 358


# --- deduplication --------------------------------------------------------


def test_re_importing_an_overlapping_package_creates_no_second_paper(project):
    """Two query sets return the same document. The second import must
    recognise it, not duplicate the review's unit of work.

    It is `already_present`, not a removed duplicate: the document was not
    newly identified at all, and counting it as one would inflate the PRISMA
    "duplicates removed" box on every re-import.
    """
    inst, pid = project
    inst.import_grey(pid, [grey("oecd-1", "https://oecd.org/a")])
    second = inst.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a"),
        grey("who-2", "https://who.int/b"),
    ])

    assert second["imported_unique"] == 1
    assert second["already_present"] == 1
    assert second["imported_duplicates"] == 0
    originals = [p for p in inst.papers(pid) if p["dedup_status"] == "original"]
    assert len(originals) == 2


def test_byte_identical_content_under_two_urls_is_one_source(project):
    """Observed in the pilot corpus: the same IEEE-USA PDF via a download
    gateway and via its direct path. Two URLs, one document."""
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("direct-1", "https://ieeeusa.org/assets/model.pdf", sha256="d" * 64),
        grey("gateway-2", "https://ieeeusa.org/?download_id=56531", sha256="d" * 64),
    ])

    assert result["imported_unique"] == 1
    assert result["imported_duplicates"] == 1


OUTCOMES = ("imported_unique", "imported_duplicates", "already_present",
            "skipped_no_citekey")


@pytest.mark.parametrize("first,second", [
    # nothing at all
    ([], []),
    # only new records
    ([], [grey("a-1", "https://a.example/1"), grey("b-2", "https://b.example/2")]),
    # a duplicate within the package
    ([], [grey("a-1", "https://a.example/1", sha256="d" * 64),
          grey("b-2", "https://b.example/2", sha256="d" * 64)]),
    # a record the project already has
    ([grey("a-1", "https://a.example/1")],
     [grey("a-1", "https://a.example/1"), grey("b-2", "https://b.example/2")]),
    # a record with no key at all
    ([], [grey("", "https://a.example/1"), grey("b-2", "https://b.example/2")]),
    # every kind at once
    ([grey("a-1", "https://a.example/1")],
     [grey("a-1", "https://a.example/1"),
      grey("b-2", "https://b.example/2", sha256="e" * 64),
      grey("c-3", "https://c.example/3", sha256="e" * 64),
      grey("", "https://d.example/4")]),
])
def test_the_four_outcomes_add_up(project, first, second):
    """Every record lands in exactly one bucket, and the buckets total the
    package.

    The regression guard for the defect this replaced: a record already in the
    project returned early without being counted anywhere, so an overlapping
    re-import reported one record fewer than it had read. This response is
    where a PRISMA "records identified" comes from, and a record that falls out
    of every bucket cannot be reconciled by anyone reading the diagram later.
    """
    inst, pid = project
    if first:
        inst.import_grey(pid, first)
    result = inst.import_grey(pid, second)

    assert sum(result[k] for k in OUTCOMES) == result["total_in_package"]
    assert result["total_in_package"] == len(second)


def test_the_citekey_lists_match_their_counts(project):
    """The lists are what a reviewer inspects when a number looks wrong."""
    inst, pid = project
    inst.import_grey(pid, [grey("a-1", "https://a.example/1")])
    result = inst.import_grey(pid, [
        grey("a-1", "https://a.example/1"),
        grey("b-2", "https://b.example/2", sha256="f" * 64),
        grey("c-3", "https://c.example/3", sha256="f" * 64),
    ])

    assert len(result["imported_citekeys"]) == result["imported_unique"]
    assert len(result["duplicate_citekeys"]) == result["imported_duplicates"]
    assert len(result["already_present_citekeys"]) == result["already_present"]
    assert result["already_present_citekeys"] == ["a-1"]


def test_the_stored_import_row_adds_up_like_the_response(project):
    """`GreyImport` is the stored version of the same PRISMA number. A category
    missing there makes it unreconcilable months later, when the response is
    long gone."""
    inst, pid = project
    inst.import_grey(pid, [grey("a-1", "https://a.example/1")])
    result = inst.import_grey(pid, [
        grey("a-1", "https://a.example/1"),
        grey("b-2", "https://b.example/2", sha256="f" * 64),
        grey("c-3", "https://c.example/3", sha256="f" * 64),
        grey("", "https://d.example/4"),
    ])

    row = [i for i in inst.grey_imports(pid) if i["id"] == result["grey_import_id"]][0]
    assert row["imported_count"] == result["imported_unique"]
    assert row["duplicate_count"] == result["imported_duplicates"]
    assert row["already_present_count"] == result["already_present"]
    assert row["skipped_count"] == result["skipped_no_citekey"]
    assert (row["imported_count"] + row["duplicate_count"]
            + row["already_present_count"] + row["skipped_count"]
            == row["records_in_package"])


def test_two_sources_sharing_a_generic_title_are_both_kept(project):
    """The decisive deduplication case for grey literature. A shared title is
    common, and a false duplicate removes a source from the review silently."""
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("a-1", "https://a.example/1", title="AI Maturity Model", sha256="1" * 64),
        grey("b-2", "https://b.example/2", title="AI Maturity Model", sha256="2" * 64),
    ])

    assert result["imported_unique"] == 2


def test_failed_records_do_not_collapse_into_one(project):
    """Every failed retrieval has `sha256: null`. Treating that as an identity
    would merge all of them into a single source."""
    inst, pid = project
    result = inst.import_grey(pid, [
        grey("a-1", "https://a.example/1", retrieval_status="failed",
             sha256=None, warc=None),
        grey("b-2", "https://b.example/2", retrieval_status="failed",
             sha256=None, warc=None),
    ])

    assert result["imported_unique"] == 2


def test_a_duplicate_is_kept_as_a_record_not_discarded(project):
    """PRISMA has a "duplicates removed" box; the number has to come from
    somewhere, and the BibTeX path stores them the same way."""
    inst, pid = project
    inst.import_grey(pid, [
        grey("direct-1", "https://a.example/1", sha256="d" * 64),
        grey("gateway-2", "https://a.example/2", sha256="d" * 64),
    ])

    papers = inst.papers(pid)
    assert len(papers) == 2
    assert sum(1 for p in papers if p["dedup_status"] != "original") == 1


# --- refusals -------------------------------------------------------------


def test_a_foreign_json_file_is_refused(instance):
    """A file that merely has a `records` key would import as nonsense, with a
    provenance trail that looks authoritative because it came from a file."""
    pid = instance.create_project(title="P")["id"]
    response = instance.client.post(
        f"/api/projects/{pid}/import/grey",
        files={"file": ("x.json", b'{"records": [{"title": "x"}]}', "application/json")},
    )

    assert response.status_code == 400
    assert "glr-interchange-v1" in response.json()["detail"]


def test_a_future_schema_version_is_refused_rather_than_guessed(instance):
    pid = instance.create_project(title="P")["id"]
    with pytest.raises(Exception):
        instance.import_grey(pid, [grey("a-1", "https://a.example/1")],
                             schema="glr-interchange-v2")


def test_an_unknown_project_is_a_404(instance):
    response = instance.client.post(
        "/api/projects/9999/import/grey",
        files={"file": ("x.json", b"{}", "application/json")},
    )

    assert response.status_code == 404
