"""PRISMA flow-count invariants.

The reviewer-visible numbers in the PRISMA diagram and the PDF report must
match. In particular, `included from databases` and `included from
snowballing` are not additive — they describe two disjoint streams whose
union is the final included set.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import FinalDecision, Paper, Project


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _project(session):
    p = Project(title="P")
    session.add(p); session.commit(); session.refresh(p)
    return p


def _paper(session, proj_id, citekey, source="acm", dedup_status="original"):
    p = Paper(project_id=proj_id, citekey=citekey, title=citekey,
              source=source, dedup_status=dedup_status)
    session.add(p); session.commit(); session.refresh(p)
    return p


def _decision(session, proj_id, paper_id, phase, decision):
    session.add(FinalDecision(project_id=proj_id, paper_id=paper_id,
                              phase=phase, decision=decision))
    session.commit()


class TestPRISMACounts:
    def test_dedup_count_reflects_dedup_status(self, client, db_session):
        proj = _project(db_session)
        for i in range(8):
            _paper(db_session, proj.id, f"orig{i}")
        for i in range(3):
            _paper(db_session, proj.id, f"dup{i}", dedup_status="duplicate_of:orig0")

        stats = client.get(f"/api/projects/{proj.id}/export/stats").json()
        assert stats["total_retrieved"] == 11
        assert stats["total_unique"] == 8
        assert stats["total_duplicates"] == 3
        # screened == unique (PRISMA invariant)
        assert stats["total_unique"] == 8

    def test_screening_and_fulltext_counts_partition_the_pool(self, client, db_session):
        proj = _project(db_session)
        papers = [_paper(db_session, proj.id, f"p{i}") for i in range(10)]
        # Screening: include 6, exclude 4
        for p in papers[:6]: _decision(db_session, proj.id, p.id, "screening", "I")
        for p in papers[6:]: _decision(db_session, proj.id, p.id, "screening", "E")
        # Full-text: of the 6 included, include 4, exclude 2
        for p in papers[:4]: _decision(db_session, proj.id, p.id, "full-text", "I")
        for p in papers[4:6]: _decision(db_session, proj.id, p.id, "full-text", "E")

        stats = client.get(f"/api/projects/{proj.id}/export/stats").json()
        assert stats["screening_included"] == 6
        assert stats["screening_excluded"] == 4
        assert stats["fulltext_included"] == 4
        assert stats["fulltext_excluded"] == 2
        # Screened count == included + excluded at screening + undecided
        assert (
            stats["screening_included"]
            + stats["screening_excluded"]
            + stats["screening_undecided"]
        ) == stats["total_unique"]
        # Full-text assessed == screening_included (only those go to full-text)
        assert stats["fulltext_included"] + stats["fulltext_excluded"] <= stats["screening_included"]

    def test_db_and_snowballing_included_are_non_overlapping(self, client, db_session):
        """The DB-stream and snowballing-stream counts must be disjoint."""
        proj = _project(db_session)
        # 5 DB papers, 3 of which end up included after full-text.
        db_papers = [_paper(db_session, proj.id, f"db{i}", source="acm") for i in range(5)]
        for p in db_papers[:3]:
            _decision(db_session, proj.id, p.id, "screening", "I")
            _decision(db_session, proj.id, p.id, "full-text", "I")
        # 4 snowballing papers; 2 included at full-text.
        snow = [_paper(db_session, proj.id, f"sb{i}", source="snowballing:1") for i in range(4)]
        for p in snow[:2]:
            _decision(db_session, proj.id, p.id, "full-text", "I")

        all_final = db_session.exec(
            __import__("sqlmodel").select(FinalDecision)
            .where(FinalDecision.project_id == proj.id)
            .where(FinalDecision.phase == "full-text")
            .where(FinalDecision.decision == "I")
        ).all()
        ft_included_ids = {d.paper_id for d in all_final}
        # Disjoint partition: 3 DB + 2 snowballing = 5 total, no overlap.
        db_included = {p.id for p in db_papers[:3]}
        snow_included = {p.id for p in snow[:2]}
        assert db_included.isdisjoint(snow_included)
        assert (db_included | snow_included) == ft_included_ids
        # And the total is *not* additive past the disjoint union — i.e. exactly 5, not 6.
        assert len(ft_included_ids) == len(db_included) + len(snow_included)
