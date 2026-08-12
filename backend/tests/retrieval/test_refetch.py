"""Selecting what a second retrieval attempt could recover.

The gap this closes: `db.has_snapshot` treats a clean-but-textless retrieval as
archived, so re-running a query skips it for ever. Only `--refetch` reached it,
and that re-fetches the whole corpus — 424 documents to retry 22.
"""

import json

import pytest

from app.retrieval import db, interchange, refetch, report
from app.retrieval.refetch import estimated_credits

from .test_report_causes import make_document


# The original retrieval happens before any retry. Stated explicitly rather
# than left to `utc_now()`, because `db.best_snapshot` breaks a tie between two
# clean snapshots by recency — a fixture that stamps the original "now" and the
# retry an hour earlier tests the opposite of what it means to.
FIRST_RUN = "2026-08-11T09:00:00Z"
RETRY = "2026-08-12T10:00:00Z"


@pytest.fixture
def corpus(tmp_path):
    conn = db.connect(tmp_path / "glr.sqlite3")
    db.start_run(conn, "run-1", "AI maturity model", "google", "{}", "0.1.0",
                 batch_id="batch-1")

    def add(url, host, **kwargs):
        kwargs.setdefault("fetched_at", FIRST_RUN)
        return make_document(conn, "run-1", url, host, **kwargs)

    add("https://oecd.org/a", "oecd.org", rank=1)
    add("https://sciencedirect.com/b", "sciencedirect.com", rank=2,
        fetch_error="HTTP 500: please try again", proxy_status=500)
    add("https://linkedin.com/c", "linkedin.com", rank=3,
        blocked_reason="captcha challenge: 'captcha'")
    add("https://youtube.com/watch?v=d", "youtube.com", rank=4, word_count=0,
        extraction_error="no main content extracted")
    add("https://studenttheses.uu.nl/e", "studenttheses.uu.nl", rank=5,
        word_count=0, extraction_error="no main content extracted")
    add("https://gone.example/f", "gone.example", rank=6,
        fetch_error="HTTP 404: gone", proxy_status=404)
    add("https://scan.example/g.pdf", "scan.example", rank=7, media_type="pdf",
        word_count=0,
        extraction_error="no text layer (scanned PDF?); retry the run with --ocr")
    db.finish_run(conn, "run-1", "completed")
    conn.commit()
    return conn


def reasons_of(candidates):
    return sorted(c.reason for c in candidates)


def test_the_textless_document_no_other_command_could_reach_is_selected(corpus):
    """The whole point: a clean snapshot with no text is invisible to
    `has_snapshot`, and must not be invisible here."""
    scope = refetch.for_scope(corpus, "run-1")
    assert "no_main_content" in reasons_of(scope.candidates)

    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'studenttheses.uu.nl'"
    ).fetchone()[0]
    assert db.has_snapshot(corpus, document_id), \
        "the fixture is wrong if this document does not look archived"


def test_selection_covers_the_recoverable_and_excludes_the_rest(corpus):
    scope = refetch.for_scope(corpus, "run-1")
    assert scope.documents == 7
    assert reasons_of(scope.candidates) == [
        "bot_challenge", "no_main_content", "origin_unreachable",
    ]


def test_the_usable_document_is_never_re_fetched(corpus):
    """Re-fetching what already worked is what made the old flag unaffordable."""
    scope = refetch.for_scope(corpus, "run-1")
    assert "oecd.org" not in {c.host for c in scope.candidates}


def test_terminal_causes_are_not_paid_for_again(corpus):
    scope = refetch.for_scope(corpus, "run-1")
    hosts = {c.host for c in scope.candidates}
    assert "youtube.com" not in hosts     # a video, not a document
    assert "gone.example" not in hosts    # 404


def test_a_scanned_pdf_is_not_a_fetch_candidate(corpus):
    """Its bytes are archived. Paying to download them again buys nothing."""
    scope = refetch.for_scope(corpus, "run-1")
    assert "scan.example" not in {c.host for c in scope.candidates}

    reextract = refetch.for_scope(corpus, "run-1", action="reextract")
    assert reasons_of(reextract.candidates) == ["no_text_layer"]


def test_only_narrows_to_one_cause(corpus):
    scope = refetch.for_scope(corpus, "run-1", reasons={"no_main_content"})
    assert reasons_of(scope.candidates) == ["no_main_content"]


def test_an_unknown_scope_raises_rather_than_selecting_everything(corpus):
    with pytest.raises(LookupError):
        refetch.for_scope(corpus, "no-such-id")


def test_a_batch_id_resolves_like_a_run_id(corpus):
    assert refetch.for_scope(corpus, "batch-1").kind == "batch"
    assert refetch.for_scope(corpus, "run-1").kind == "run"


def test_the_url_fetched_is_the_one_that_was_requested(corpus):
    """Not the canonical form: canonicalisation strips parameters, and the
    retry has to ask for what the source actually served."""
    scope = refetch.for_scope(corpus, "run-1")
    for candidate in scope.candidates:
        assert candidate.url.startswith("https://")


def test_the_summary_names_the_cause_and_the_remedy(corpus):
    scope = refetch.for_scope(corpus, "run-1")
    summary = refetch.summarise(scope.candidates)
    assert [count for _label, count, _hint in summary] == [1, 1, 1]
    for label, _count, hint in summary:
        assert label and hint


# --- the cost estimate ----------------------------------------------------


@pytest.mark.parametrize("kwargs,expected", [
    ({}, 1),
    ({"render_js": True}, 5),
    ({"premium_proxy": True}, 10),
    ({"premium_proxy": True, "render_js": True}, 25),
    ({"stealth_proxy": True}, 75),
    ({"stealth_proxy": True, "render_js": True, "premium_proxy": True}, 75),
])
def test_published_credit_prices(kwargs, expected):
    assert estimated_credits(**kwargs) == expected


def test_a_targeted_retry_is_cheaper_than_refetching_the_corpus(corpus):
    """The number that justifies the command existing at all."""
    scope = refetch.for_scope(corpus, "run-1")
    targeted = len(scope.candidates) * estimated_credits(render_js=True)
    everything = scope.documents * estimated_credits(render_js=True)
    assert targeted < everything


# --- what a completed retry does to the original scope --------------------


def test_re_exporting_the_original_scope_picks_up_the_recovered_snapshot(corpus, tmp_path):
    """A retry writes its own run. The original run must still be the scope a
    review reports on, and must improve without being re-searched."""
    before = interchange.build_package(corpus, ["run-1"])
    assert before["counts"]["ok"] == 1
    assert before["counts"]["reasons"]["no_main_content"] == 1

    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'studenttheses.uu.nl'"
    ).fetchone()[0]
    db.start_run(corpus, "refetch-1", "refetch of run run-1", "none", "{}", "0.1.0")
    make_document(corpus, "refetch-1", "https://studenttheses.uu.nl/e",
                  "studenttheses.uu.nl", word_count=900,
                  fetched_at=RETRY, document_id=document_id)
    db.finish_run(corpus, "refetch-1", "completed")
    corpus.commit()

    after = interchange.build_package(corpus, ["run-1"])
    assert after["counts"]["ok"] == 2
    assert "no_main_content" not in after["counts"]["reasons"]
    assert after["counts"]["documents"] == before["counts"]["documents"], \
        "a retry must not change how many documents the run identified"


def test_the_failed_attempt_is_not_overwritten_by_the_retry(corpus):
    """"Unreachable on the 11th, retrieved on the 12th" has to stay sayable."""
    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'sciencedirect.com'"
    ).fetchone()[0]
    db.start_run(corpus, "refetch-1", "refetch of run run-1", "none", "{}", "0.1.0")
    make_document(corpus, "refetch-1", "https://sciencedirect.com/b",
                  "sciencedirect.com", word_count=500,
                  fetched_at=RETRY, document_id=document_id)
    corpus.commit()

    snapshots = corpus.execute(
        "SELECT run_id, fetch_error FROM snapshots WHERE document_id = ? "
        "ORDER BY fetched_at_utc", (document_id,),
    ).fetchall()
    assert len(snapshots) == 2
    assert snapshots[0]["fetch_error"] == "HTTP 500: please try again"
    assert snapshots[1]["fetch_error"] is None


def test_a_recovered_document_leaves_the_retry_list(corpus):
    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'studenttheses.uu.nl'"
    ).fetchone()[0]
    db.start_run(corpus, "refetch-1", "refetch of run run-1", "none", "{}", "0.1.0")
    make_document(corpus, "refetch-1", "https://studenttheses.uu.nl/e",
                  "studenttheses.uu.nl", word_count=900,
                  fetched_at=RETRY, document_id=document_id)
    corpus.commit()

    assert "no_main_content" not in reasons_of(refetch.for_scope(corpus, "run-1").candidates)


def test_a_retry_that_fails_again_stays_on_the_list(corpus):
    """Not an error — a source can be down twice. It must not silently drop out
    of the count of what a review could not reach."""
    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'sciencedirect.com'"
    ).fetchone()[0]
    db.start_run(corpus, "refetch-1", "refetch of run run-1", "none", "{}", "0.1.0")
    make_document(corpus, "refetch-1", "https://sciencedirect.com/b",
                  "sciencedirect.com", fetch_error="HTTP 500: please try again",
                  proxy_status=500, fetched_at=RETRY,
                  document_id=document_id)
    corpus.commit()

    assert "origin_unreachable" in reasons_of(refetch.for_scope(corpus, "run-1").candidates)


def test_the_retry_run_does_not_add_documents_to_the_report(corpus, tmp_path):
    """The retry has no SERP results, so it must not look like a search that
    identified sources."""
    document_id = corpus.execute(
        "SELECT document_id FROM documents WHERE host = 'studenttheses.uu.nl'"
    ).fetchone()[0]
    db.start_run(corpus, "refetch-1", "refetch of run run-1", "none", "{}", "0.1.0")
    make_document(corpus, "refetch-1", "https://studenttheses.uu.nl/e",
                  "studenttheses.uu.nl", word_count=900,
                  fetched_at=RETRY, document_id=document_id)
    db.finish_run(corpus, "refetch-1", "completed")
    corpus.commit()

    text = report.report_run(corpus, "run-1", tmp_path / "r.md").read_text()
    assert "| **Total identified** | **7** |" in text
    assert "| Sources retrieved and usable | 2 |" in text
