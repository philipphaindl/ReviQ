"""The endpoint behind the dataset view.

What a reviewer needs in front of them to assess a grey source: when it was
read, the digest of what was read, where those bytes are archived, the text
itself, and what any figures showed.

The invariant this file exists to hold is D31's: there is no shape of the
response in which a caller holds the text without the status it was extracted
under. Two of the pilot corpus's five non-`ok` texts are bot-challenge
boilerplate, and a view that rendered them unqualified would put "Checking your
browser before accessing…" in front of a reviewer as the document.
"""
from __future__ import annotations

from sqlalchemy import event


def grey(key: str, url: str, **fields) -> dict:
    return {"record_key": key, "canonical_url": url,
            "sha256": key.ljust(64, "0"), **fields}


def figure(**over) -> dict:
    fig = {
        "raw_src": "/img/fig1.png",
        "resolved_url": "https://oecd.org/img/fig1.png",
        "alt_text": "Maturity levels",
        "caption": "Figure 1: the five levels",
        "sha256": "b" * 64, "content_type": "image/png", "byte_size": 20481,
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


def _record(instance, pid: int, citekey: str):
    paper = instance.paper_by_citekey(pid, citekey)
    r = instance.client.get(f"/api/projects/{pid}/papers/{paper['id']}/grey-record")
    r.raise_for_status()
    return r.json()


def test_the_record_carries_what_makes_a_grey_source_citable(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a",
             retrieved_at_utc="2026-08-11T19:36:06Z",
             text="The body of the source.", word_count=4210,
             extractor="trafilatura-2.2.0"),
    ])

    record = _record(instance, pid, "oecd-1")

    assert record["source"]["retrieved_at_utc"] == "2026-08-11T19:36:06Z"
    assert record["source"]["sha256"] == "oecd-1".ljust(64, "0")
    assert record["source"]["archive_filename"] == "snapshots.warc.gz"
    assert record["full_text"]["text"] == "The body of the source."
    assert record["full_text"]["word_count"] == 4210


def test_the_text_never_arrives_without_its_status(instance):
    """D31. The two are one object precisely so a caller cannot hold one half."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("blocked-1", "https://linkedin.com/posts/x",
             retrieval_status="blocked", retrieval_reason="bot_challenge",
             text="Checking your browser before accessing pubmed."),
    ])

    record = _record(instance, pid, "blocked-1")

    assert record["full_text"]["text"].startswith("Checking your browser")
    assert record["full_text"]["retrieval_status"] == "blocked"
    assert record["source"]["retrieval_reason"] == "bot_challenge"


def test_a_source_without_text_says_so_rather_than_returning_an_empty_string(instance):
    """None and "" are different findings: nothing was retrieved, versus a page
    that carried no prose. A view has to be able to tell them apart."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("blocked-1", "https://paywalled.example/a",
             retrieval_status="blocked", retrieval_reason="origin_unreachable"),
    ])

    record = _record(instance, pid, "blocked-1")

    assert record["full_text"] is None
    assert record["source"]["retrieval_reason"] == "origin_unreachable"


def test_figures_arrive_with_their_descriptions_attached(instance):
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("oecd-1", "https://oecd.org/a", figures=[figure()]),
    ])

    [fig] = _record(instance, pid, "oecd-1")["figures"]

    assert fig["caption"] == "Figure 1: the five levels"
    assert fig["alt_text"] == "Maturity levels"
    assert fig["descriptions"][0]["description"] == "A staircase of five levels."
    # Kept verbatim so a reader can say what produced this sentence.
    assert fig["descriptions"][0]["model"] == "claude-haiku-4-5"
    assert fig["descriptions"][0]["prompt"] == "Describe this figure."


def test_a_formal_paper_is_a_404_not_an_empty_envelope(instance):
    """An empty envelope would invite a view that renders blank provenance as
    though the retrieval had found nothing."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_bib(pid, [{"citekey": "smith2020", "title": "A Formal Paper"}])
    paper = instance.paper_by_citekey(pid, "smith2020")

    r = instance.client.get(f"/api/projects/{pid}/papers/{paper['id']}/grey-record")

    assert r.status_code == 404


def test_a_paper_from_another_project_is_not_readable_here(instance):
    a = instance.create_project(title="A")["id"]
    b = instance.create_project(title="B")["id"]
    instance.import_grey(a, [grey("a-1", "https://a.example/1", text="secret")])
    paper = instance.paper_by_citekey(a, "a-1")

    r = instance.client.get(f"/api/projects/{b}/papers/{paper['id']}/grey-record")

    assert r.status_code == 404


def test_an_unknown_paper_is_a_404(instance):
    pid = instance.create_project(title="P")["id"]
    assert instance.client.get(
        f"/api/projects/{pid}/papers/999999/grey-record").status_code == 404


def test_many_figures_do_not_cost_a_query_each(instance):
    """A source may carry dozens of images; the listing beside this endpoint was
    already fixed for the same reason."""
    pid = instance.create_project(title="MLR")["id"]
    instance.import_grey(pid, [
        grey("few", "https://a.example/1", figures=[
            figure(figure={"resolved_url": f"https://a.example/{i}.png"})
            for i in range(2)
        ]),
        grey("many", "https://b.example/2", figures=[
            figure(figure={"resolved_url": f"https://b.example/{i}.png"})
            for i in range(20)
        ]),
    ])

    def count(citekey: str) -> int:
        bind = instance.session.get_bind()
        seen: list[str] = []
        listener = lambda c, cur, s, p, ctx, m: seen.append(s)  # noqa: E731
        event.listen(bind, "before_cursor_execute", listener)
        try:
            _record(instance, pid, citekey)
        finally:
            event.remove(bind, "before_cursor_execute", listener)
        return len(seen)

    assert count("few") == count("many")
