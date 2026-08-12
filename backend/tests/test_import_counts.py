"""Every import path accounts for every entry it read.

The counts these endpoints return are where a PRISMA "records identified" and
"duplicates removed" come from. An entry that lands in none of the buckets makes
those numbers unreconcilable for whoever reads the diagram afterwards — and
until this file existed, three of the four importers dropped entries that way.

The second thing held here is that the importers agree with each other.
`detected_duplicates` used to mean "a duplicate we wrote a row for" in the
database-search importer and "a duplicate we recognised" in the snowballing one,
under one field name and one UI tile. That is the `dedup_status` defect of
Increment 0 one level up, and a shared backend helper plus these tests are what
keep it closed.
"""
from __future__ import annotations

import json

import pytest

PAPER_OUTCOMES = ("imported_unique", "imported_duplicates", "already_present",
                  "skipped_incomplete")
DECISION_OUTCOMES = ("imported_decisions", "updated_decisions",
                     "unknown_citekey", "skipped_incomplete")


def bib(entries: list[dict]) -> bytes:
    """A BibTeX file from partial entries. A missing title stays missing."""
    out = []
    for e in entries:
        fields = {
            "author": e.get("authors", "Author"),
            "title": e.get("title", ""),
            "year": str(e.get("year", 2020)),
            "booktitle": e.get("venue", "ICSE"),
            "doi": e.get("doi", ""),
        }
        body = ",\n  ".join(f"{k} = {{{v}}}" for k, v in fields.items() if v)
        out.append(f"@inproceedings{{{e['citekey']},\n  {body}\n}}")
    return "\n\n".join(out).encode("utf-8")


def post_bib(inst, pid, entries, *, db_name="acm"):
    r = inst.client.post(
        f"/api/projects/{pid}/import/bib",
        data={"db_name": db_name},
        files={"file": ("f.bib", bib(entries), "application/x-bibtex")},
    )
    r.raise_for_status()
    return r.json()


def post_snowball(inst, pid, entries):
    """A fresh iteration per call; the endpoint numbers them itself."""
    created = inst.client.post(f"/api/projects/{pid}/snowballing",
                               json={"iteration_type": "forward"})
    created.raise_for_status()
    r = inst.client.post(
        f"/api/projects/{pid}/snowballing/{created.json()['id']}/import",
        files={"file": ("f.bib", bib(entries), "application/x-bibtex")},
    )
    r.raise_for_status()
    return r.json()


@pytest.fixture
def pid(instance):
    return instance, instance.create_project(title="P")["id"]


# --- the paper importers --------------------------------------------------


PAPER_CASES = [
    # nothing at all
    ("empty", []),
    # only new entries
    ("new only", [{"citekey": "a1", "title": "Alpha"},
                  {"citekey": "b2", "title": "Beta"}]),
    # a duplicate within the file: same DOI
    ("duplicate in file", [{"citekey": "a1", "title": "Alpha", "doi": "10.1/x"},
                           {"citekey": "b2", "title": "Alpha again", "doi": "10.1/x"}]),
    # an entry with no title — parsed, unusable
    ("no title", [{"citekey": "a1", "title": ""},
                  {"citekey": "b2", "title": "Beta"}]),
]


@pytest.mark.parametrize("label,entries", PAPER_CASES, ids=[c[0] for c in PAPER_CASES])
def test_the_database_import_accounts_for_every_entry(pid, label, entries):
    inst, project = pid
    result = post_bib(inst, project, entries)

    assert sum(result[k] for k in PAPER_OUTCOMES) == result["total_in_file"]


@pytest.mark.parametrize("label,entries", PAPER_CASES, ids=[c[0] for c in PAPER_CASES])
def test_the_snowballing_import_accounts_for_every_entry(pid, label, entries):
    inst, project = pid
    result = post_snowball(inst, project, entries)

    assert sum(result[k] for k in PAPER_OUTCOMES) == result["total_in_file"]


def test_a_re_imported_file_reports_its_entries_as_already_present(pid):
    """The defect in its clearest form: importing the same file twice used to
    report 2 in the file and 0 in every bucket."""
    inst, project = pid
    entries = [{"citekey": "a1", "title": "Alpha"}, {"citekey": "b2", "title": "Beta"}]
    post_bib(inst, project, entries)
    second = post_bib(inst, project, entries)

    assert second["total_in_file"] == 2
    assert second["already_present"] == 2
    assert second["imported_unique"] == 0
    assert sum(second[k] for k in PAPER_OUTCOMES) == 2


def test_both_paper_importers_mean_the_same_thing_by_the_same_field(pid):
    """The regression guard for the actual finding. Given the same situation —
    an entry already in the project — both importers must put it in the same
    bucket. They did not: one counted it as a duplicate, the other not at all.
    """
    inst, project = pid
    entry = [{"citekey": "shared", "title": "A Paper Both Runs See"}]
    post_bib(inst, project, entry)

    from_bib = post_bib(inst, project, entry)
    from_snowball = post_snowball(inst, project, entry)

    for field in PAPER_OUTCOMES:
        assert from_bib[field] == from_snowball[field], (
            f"{field} differs between the two importers: "
            f"bib={from_bib[field]} snowball={from_snowball[field]}"
        )


def test_the_citekey_lists_match_their_counts(pid):
    inst, project = pid
    post_bib(inst, project, [{"citekey": "a1", "title": "Alpha"}])
    result = post_bib(inst, project, [
        {"citekey": "a1", "title": "Alpha"},
        {"citekey": "b2", "title": "Beta", "doi": "10.1/y"},
        {"citekey": "c3", "title": "Beta again", "doi": "10.1/y"},
    ])

    assert len(result["imported_citekeys"]) == result["imported_unique"]
    assert len(result["duplicate_citekeys"]) == result["imported_duplicates"]
    assert len(result["already_present_citekeys"]) == result["already_present"]
    assert result["already_present_citekeys"] == ["a1"]


# --- the decision importer ------------------------------------------------


def decisions(pairs: list[tuple[str, str]], *, reviewer="Bob") -> dict:
    return {
        "reviewer_name": reviewer,
        "reviewer_role": "R2",
        "decisions": [{"paper_citekey": key, "phase": "screening", "decision": d}
                      for key, d in pairs],
    }


def post_decisions(inst, pid, payload):
    r = inst.client.post(
        f"/api/projects/{pid}/import/reviewer-decisions",
        files={"file": ("d.json", json.dumps(payload).encode("utf-8"),
                        "application/json")},
    )
    r.raise_for_status()
    return r.json()


def test_the_decision_outcomes_add_up(pid):
    inst, project = pid
    post_bib(inst, project, [{"citekey": "a1", "title": "Alpha"},
                             {"citekey": "b2", "title": "Beta"}])

    result = post_decisions(inst, project, decisions([
        ("a1", "I"),          # new
        ("b2", "E"),          # new
        ("nope", "I"),        # no such paper here
        ("", "I"),            # unusable
    ]))

    assert result["total_in_file"] == 4
    assert sum(result[k] for k in DECISION_OUTCOMES) == 4


def test_a_file_for_another_project_says_so_instead_of_reporting_nothing(pid):
    """The dangerous case. Every citekey unknown used to report
    `imported_decisions: 0, new_conflicts_detected: 0` — the same output as a
    file that had already been applied."""
    inst, project = pid
    post_bib(inst, project, [{"citekey": "a1", "title": "Alpha"}])

    result = post_decisions(inst, project, decisions([
        ("other-project-1", "I"), ("other-project-2", "E"),
    ]))

    assert result["imported_decisions"] == 0
    assert result["unknown_citekey"] == 2
    assert result["unknown_citekeys"] == ["other-project-1", "other-project-2"]


def test_a_re_import_reports_updates_rather_than_silence(pid):
    """Re-importing a corrected file changed every decision and reported 0."""
    inst, project = pid
    post_bib(inst, project, [{"citekey": "a1", "title": "Alpha"},
                             {"citekey": "b2", "title": "Beta"}])
    post_decisions(inst, project, decisions([("a1", "I"), ("b2", "I")]))

    second = post_decisions(inst, project, decisions([("a1", "E"), ("b2", "E")]))

    assert second["imported_decisions"] == 0
    assert second["updated_decisions"] == 2
    assert sum(second[k] for k in DECISION_OUTCOMES) == second["total_in_file"]


def test_the_unknown_citekey_sample_is_capped(pid):
    """A file for the wrong project makes every entry unknown; the count says
    so, and the sample is only there to recognise which project it is."""
    inst, project = pid
    post_bib(inst, project, [{"citekey": "a1", "title": "Alpha"}])

    result = post_decisions(inst, project,
                            decisions([(f"foreign-{i}", "I") for i in range(25)]))

    assert result["unknown_citekey"] == 25
    assert len(result["unknown_citekeys"]) == 10
