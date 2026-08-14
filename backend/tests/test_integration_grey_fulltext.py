"""Full text and figures survive the grey import, at the HTTP level.

`test_grey_service.py` covers the mapping as pure functions. What this file
covers is what only a database shows: that the text lands in its own table
rather than on `Paper`, that `abstract` still holds what the search engine
displayed, and that a source which could not be retrieved carries no text row
at all.

The last one is the point of the increment. A reviewer assessing a grey source
against inclusion criteria has to read it, and re-fetching a page that may have
changed since is not the same evidence — but a *blocked* source has no text,
and inventing an empty one would hide that.
"""
from __future__ import annotations

from sqlmodel import select

from app.models import GreyFigure, GreyFigureDescription, GreyFullText, Paper


def grey(key: str, url: str, **fields) -> dict:
    return {"record_key": key, "canonical_url": url,
            "sha256": key.ljust(64, "0"), **fields}


def figure(**over) -> dict:
    fig = {
        "raw_src": "/img/fig1.png",
        "resolved_url": "https://oecd.org/img/fig1.png",
        "alt_text": "Maturity levels",
        "caption": "Figure 1: the five levels",
        "sha256": "b" * 64,
        "content_type": "image/png",
        "byte_size": 20481,
        "fetch_error": None,
        "warc": {"run_id": "r1", "filename": "figures.warc.gz", "offset": 4096,
                 "record_id": "<urn:uuid:aa>",
                 "recorded_path": "data/runs/r1/figures.warc.gz"},
    }
    fig.update(over.pop("figure", {}))
    return {"kind": "model_generated", "figure": fig,
            "descriptions": over.pop("descriptions", [{
                "description": "A staircase of five levels.",
                "model": "claude-haiku-4-5", "prompt": "Describe this figure.",
                "described_at_utc": "2026-08-11T20:00:00Z", "error": None,
            }])}


def _texts(instance, pid: int) -> list[GreyFullText]:
    return instance.session.exec(
        select(GreyFullText).where(GreyFullText.project_id == pid)).all()


# --- full text ------------------------------------------------------------


def test_the_extracted_text_arrives_and_is_readable(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a",
             text="A five-level model for assessing AI maturity.",
             word_count=4210, extractor="trafilatura-2.2.0"),
    ])

    [stored] = _texts(instance, pid)
    assert stored.text.startswith("A five-level model")
    assert stored.word_count == 4210
    assert stored.extractor == "trafilatura-2.2.0"


def test_the_text_never_lands_in_the_abstract(instance):
    """`abstract` is the snippet the engine displayed — what a screener saw
    when deciding. Overwriting it with body text would change, months later,
    the evidence a recorded screening decision rests on."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a",
             snippet="The snippet a screener saw.",
             text="A far longer body text that must not replace the snippet."),
    ])

    paper = instance.session.exec(
        select(Paper).where(Paper.project_id == pid)).one()
    assert paper.abstract == "The snippet a screener saw."
    assert "far longer body text" not in (paper.abstract or "")


def test_the_text_is_not_a_column_on_paper(instance):
    """Kept structural rather than incidental: a text column would be dragged
    through `list_papers`, which the screening view calls on every filter."""
    assert "text" not in Paper.model_fields


def test_a_source_that_yielded_nothing_carries_no_text_row(instance):
    """No bytes were fetched, so there is nothing to have extracted. An empty
    row would read as "this page had no prose", which is a different finding."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("blocked-1", "https://paywalled.example/a",
             retrieval_status="blocked", retrieval_reason="origin_unreachable"),
    ])

    assert _texts(instance, pid) == []
    # The paper itself still exists — the PRISMA top box counts it.
    assert len(instance.papers(pid)) == 1


def test_text_from_a_blocked_retrieval_is_kept_and_carries_its_status(instance):
    """Verified against the real pilot corpus, where this is five records.

    Under a bot challenge the extractor returns whatever the page served. Three
    of those five are LinkedIn posts whose visible text is genuine source
    content; two are challenge pages reading "Checking your browser before
    accessing…". Nothing separates them mechanically — both are
    `blocked`/`bot_challenge` — so the text is kept and the status travels with
    it, rather than the first three being discarded or the last two passing as
    documents.
    """
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("post-1", "https://linkedin.com/posts/x",
             retrieval_status="blocked", retrieval_reason="bot_challenge",
             text="We've just launched the AI Maturity Self Assessment tool."),
        grey("wall-1", "https://pubmed.example/1",
             retrieval_status="blocked", retrieval_reason="bot_challenge",
             text="Checking your browser before accessing pubmed."),
    ])

    stored = _texts(instance, pid)
    assert len(stored) == 2
    # The qualifier a dataset view has to render beside the text: whoever can
    # reach the text can reach the reason to distrust it.
    assert {t.retrieval_status for t in stored} == {"blocked"}


def test_cleanly_retrieved_text_is_marked_as_such(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("ok-1", "https://oecd.org/a", retrieval_status="ok", text="real content"),
    ])

    [stored] = _texts(instance, pid)
    assert stored.retrieval_status == "ok"


def test_a_package_without_text_imports_unchanged(instance):
    """An export made with --no-text, or from a corpus retrieved before text
    was carried. Absence is silence, not an error."""
    pid = instance.create_project(title="MLR")["id"]
    result = instance.import_grey(pid, [grey("a-1", "https://a.example/1")])

    assert result["imported_unique"] == 1
    assert _texts(instance, pid) == []


def test_each_paper_keeps_its_own_text(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("a-1", "https://a.example/1", text="text of A"),
        grey("b-2", "https://b.example/2", text="text of B"),
    ])

    by_paper = {t.paper_id: t.text for t in _texts(instance, pid)}
    papers = {p["citekey"]: p["id"] for p in instance.papers(pid)}
    assert by_paper[papers["a-1"]] == "text of A"
    assert by_paper[papers["b-2"]] == "text of B"


def test_text_does_not_leak_across_projects(instance):
    a = instance.create_project(title="A")["id"]
    b = instance.create_project(title="B")["id"]
    instance.import_grey(a, [grey("a-1", "https://a.example/1", text="only in A")])

    assert len(_texts(instance, a)) == 1
    assert _texts(instance, b) == []


# --- figures --------------------------------------------------------------


def test_figures_and_their_descriptions_both_arrive(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a", figures=[figure()]),
    ])

    [fig] = instance.session.exec(
        select(GreyFigure).where(GreyFigure.project_id == pid)).all()
    assert fig.caption == "Figure 1: the five levels"
    assert fig.alt_text == "Maturity levels"
    assert fig.archive_filename == "figures.warc.gz"

    [desc] = instance.session.exec(
        select(GreyFigureDescription)
        .where(GreyFigureDescription.grey_figure_id == fig.id)).all()
    assert desc.description == "A staircase of five levels."
    assert desc.model == "claude-haiku-4-5"
    assert desc.prompt == "Describe this figure."


def test_a_description_stays_attached_to_its_own_figure(instance):
    """Two images on one page must not share a description — the failure mode
    a flush-ordering bug actually produces."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a", figures=[
            figure(figure={"resolved_url": "https://oecd.org/one.png"},
                   descriptions=[{"description": "the first image",
                                  "model": "m", "prompt": "p"}]),
            figure(figure={"resolved_url": "https://oecd.org/two.png"},
                   descriptions=[{"description": "the second image",
                                  "model": "m", "prompt": "p"}]),
        ]),
    ])

    figures = instance.session.exec(
        select(GreyFigure).where(GreyFigure.project_id == pid)).all()
    by_url = {f.resolved_url: f.id for f in figures}
    described = {
        d.grey_figure_id: d.description
        for d in instance.session.exec(select(GreyFigureDescription)).all()
    }
    assert described[by_url["https://oecd.org/one.png"]] == "the first image"
    assert described[by_url["https://oecd.org/two.png"]] == "the second image"


def test_a_figure_the_retrieval_could_not_fetch_is_still_recorded(instance):
    """That the source carried an image nobody could read is a gap a reader
    should see, not a row worth dropping."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a", figures=[
            figure(figure={"fetch_error": "403", "sha256": None}, descriptions=[]),
        ]),
    ])

    [fig] = instance.session.exec(
        select(GreyFigure).where(GreyFigure.project_id == pid)).all()
    assert fig.fetch_error == "403"
    assert instance.session.exec(select(GreyFigureDescription)).all() == []


def test_the_counts_still_reconcile_when_text_and_figures_travel(instance):
    """Adding rows must not disturb the four disjoint outcomes a PRISMA
    "records identified" is derived from."""
    pid = instance.create_project(title="MLR")["id"]
    result = instance.import_grey(pid, [
        grey("a-1", "https://a.example/1", text="one", figures=[figure()]),
        grey("b-2", "https://b.example/2", text="two"),
        grey("c-3", "https://c.example/3", retrieval_status="blocked"),
    ])

    assert result["total_in_package"] == 3
    assert (result["imported_unique"] + result["imported_duplicates"]
            + result["already_present"] + result["skipped_no_citekey"]) == 3
    assert len(_texts(instance, pid)) == 2
