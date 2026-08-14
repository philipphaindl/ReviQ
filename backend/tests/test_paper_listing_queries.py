"""The paper listing must not issue queries per paper.

`list_papers` enriched each paper with its final decision and its reviewer
decisions by querying for that one paper — 2N+1 statements for N papers. That
was survivable while a project held a few dozen BibTeX records. Grey literature
changes the size: the pilot corpus alone is 424 documents, and this endpoint is
what the screening view calls on every filter change.

The assertion is deliberately *not* a fixed statement count. What matters is
that the number does not grow with the number of papers; pinning an exact
number would break on any unrelated change to how SQLModel emits a select and
would tell a reader nothing about why the test exists.
"""
from __future__ import annotations

from sqlalchemy import event


def _count_statements(session, fn):
    """Run `fn`, returning (result, number of SQL statements executed)."""
    bind = session.get_bind()
    seen = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(bind, "before_cursor_execute", before)
    try:
        result = fn()
    finally:
        event.remove(bind, "before_cursor_execute", before)
    return result, len(seen)


def _seed(instance, pid: int, reviewer_id: int, count: int, *, offset: int = 0):
    """`count` papers, each carrying one reviewer decision."""
    instance.import_bib(pid, [
        {"citekey": f"p{offset + i}", "title": f"Paper {offset + i}", "year": 2020}
        for i in range(count)
    ])
    for paper in instance.papers(pid):
        instance.decide(pid, paper["id"], reviewer_id=reviewer_id, decision="I")


def test_listing_papers_does_not_scale_its_query_count(instance):
    """Five papers and twenty-five must cost the same number of statements."""
    small = instance.create_project(title="Small")["id"]
    large = instance.create_project(title="Large")["id"]
    r_small = instance.add_reviewer(small, name="A")["id"]
    r_large = instance.add_reviewer(large, name="B")["id"]

    _seed(instance, small, r_small, 5)
    _seed(instance, large, r_large, 25)

    small_result, small_queries = _count_statements(
        instance.session, lambda: instance.papers(small))
    large_result, large_queries = _count_statements(
        instance.session, lambda: instance.papers(large))

    assert len(small_result) == 5 and len(large_result) == 25
    assert small_queries == large_queries, (
        f"5 papers cost {small_queries} statements, 25 cost {large_queries} — "
        "the listing is querying per paper again"
    )


def test_the_listing_still_reports_each_paper_its_own_decisions(instance):
    """Grouping in Python must not hand one paper another's decisions."""
    pid = instance.create_project(title="P")["id"]
    reviewer = instance.add_reviewer(pid, name="A")["id"]
    instance.import_bib(pid, [
        {"citekey": "included", "title": "Included", "year": 2020},
        {"citekey": "excluded", "title": "Excluded", "year": 2021},
        {"citekey": "untouched", "title": "Untouched", "year": 2022},
    ])
    by_key = {p["citekey"]: p for p in instance.papers(pid)}
    instance.decide(pid, by_key["included"]["id"], reviewer_id=reviewer, decision="I")
    instance.decide(pid, by_key["excluded"]["id"], reviewer_id=reviewer, decision="E")

    listed = {p["citekey"]: p for p in instance.papers(pid)}

    assert [d["decision"] for d in listed["included"]["decisions"]] == ["I"]
    assert [d["decision"] for d in listed["excluded"]["decisions"]] == ["E"]
    # The paper nobody judged must come back empty rather than inheriting a
    # neighbour's row — the failure mode a dict-grouping bug actually produces.
    assert listed["untouched"]["decisions"] == []
    assert listed["untouched"]["reviewer_decision_count"] == 0


def test_a_paper_without_decisions_still_appears(instance):
    """The bulk queries must not turn the enrichment into an inner join."""
    pid = instance.create_project(title="P")["id"]
    instance.import_bib(pid, [{"citekey": "lonely", "title": "Lonely", "year": 2020}])

    listed = instance.papers(pid)

    assert len(listed) == 1
    assert listed[0]["final_decision"] is None
    assert listed[0]["decisions"] == []


def test_decisions_from_another_phase_do_not_leak_in(instance):
    """The phase filter has to survive the move into the grouped query."""
    pid = instance.create_project(title="P")["id"]
    reviewer = instance.add_reviewer(pid, name="A")["id"]
    instance.import_bib(pid, [{"citekey": "p1", "title": "P1", "year": 2020}])
    paper_id = instance.papers(pid)[0]["id"]
    instance.decide(pid, paper_id, reviewer_id=reviewer,
                    phase="full-text", decision="I")

    screening = instance.client.get(
        f"/api/projects/{pid}/papers", params={"phase": "screening"}).json()
    full_text = instance.client.get(
        f"/api/projects/{pid}/papers", params={"phase": "full-text"}).json()

    assert screening[0]["decisions"] == []
    assert [d["decision"] for d in full_text[0]["decisions"]] == ["I"]
