"""Quasi-gold standard: import, human check, one deterministic split."""

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.judging import models  # noqa: F401
from app.judging.models import AiqmQgs
from app.judging.search import qgs
from app.judging.search.openalex import parse_work

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "openalex_work.json").read_text())


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _work(openalex_id, title, refs=()):
    payload = copy.deepcopy(FIXTURE)
    payload["id"] = f"https://openalex.org/{openalex_id}"
    payload["doi"] = None
    payload["title"] = title
    payload["referenced_works"] = list(refs)
    return parse_work(payload)


class FakeOpenAlex:
    def __init__(self):
        self.works = {
            "10.1/seed": _work("W1", "Seed model", refs=("W2", "W3")),
            "W2": _work("W2", "Cited one"),
            "W3": _work("W3", "Cited two"),
        }

    def work_by_doi(self, doi):
        return self.works[doi]

    def work_by_id(self, openalex_id):
        return self.works[openalex_id]

    def work_by_title(self, title):
        return _work("W9", "Something else entirely")


SEEDS = [
    {"role": "seed", "citation": "Seed", "doi": "10.1/seed", "expand": True},
    {"role": "review", "citation": "Unknown title", "title": "A review nobody indexed"},
]


def test_import_adds_seeds_and_their_references_and_reports_the_unresolved(session):
    report = qgs.import_seeds(session, "s", FakeOpenAlex(), SEEDS)
    assert report.added == 3 and report.unresolved == ["Unknown title"]
    rows = {r.key: r for r in session.exec(select(AiqmQgs))}
    assert rows["W1"].role == "seed" and rows["W2"].origin == "W1"
    again = qgs.import_seeds(session, "s", FakeOpenAlex(), SEEDS)
    assert again.added == 0 and again.already_present == 3


def test_a_title_match_with_a_different_title_is_not_trusted(session):
    report = qgs.import_seeds(session, "s", FakeOpenAlex(), SEEDS[1:])
    assert report.added == 0


def _accept_all(session, tmp_path, verdict="y"):
    import csv
    path = tmp_path / "qgs.csv"
    qgs.export_for_review(session, "s", path)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["accept"] = verdict
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=qgs.REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return qgs.apply_review(session, "s", path)


def test_split_refuses_unchecked_candidates_then_splits_once(session, tmp_path):
    qgs.import_seeds(session, "s", FakeOpenAlex(), SEEDS)
    with pytest.raises(qgs.QgsError, match="not checked"):
        qgs.split(session, "s", seed=1)
    assert _accept_all(session, tmp_path) == 3
    sizes = qgs.split(session, "s", seed=1)
    assert sizes == {"dev": 2, "holdout": 1}
    with pytest.raises(qgs.QgsError, match="already split"):
        qgs.split(session, "s", seed=1)


def test_the_split_is_the_same_for_the_same_seed(session, tmp_path):
    for i in range(20):
        session.add(AiqmQgs(study="a", key=f"W{i:03}", role="reference", accepted=True))
        session.add(AiqmQgs(study="b", key=f"W{i:03}", role="reference", accepted=True))
    session.commit()
    qgs.split(session, "a", seed=7)
    qgs.split(session, "b", seed=7)
    a = [r.key for r in qgs.dev_set(session, "a")]
    b = [r.key for r in qgs.dev_set(session, "b")]
    assert a == b and len(a) == 12 and len(qgs.holdout_set(session, "a")) == 8


def test_a_verdict_cannot_change_after_the_split(session, tmp_path):
    qgs.import_seeds(session, "s", FakeOpenAlex(), SEEDS)
    _accept_all(session, tmp_path)
    qgs.split(session, "s", seed=1)
    with pytest.raises(qgs.QgsError, match="already split"):
        _accept_all(session, tmp_path, verdict="n")


def test_the_shipped_seed_list_is_well_formed():
    seeds = qgs.load_seeds()
    assert {s["role"] for s in seeds} <= {"seed", "review", "related"}
    assert all(s.get("doi") or s.get("title") or s.get("arxiv") for s in seeds)
    dois = [s["doi"] for s in seeds if s.get("doi")]
    assert len(dois) == len(set(dois))
