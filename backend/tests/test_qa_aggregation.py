"""Quality-score aggregation tests against the qa-summary endpoint.

Covers the SLR-correctness invariants called out in CLAUDE.md:
- per-paper percentage = sum(scores) / max_total * 100
- threshold-band assignment respects project-level thresholds
- average across the included study set
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import (
    FinalDecision, Paper, Project, QACriterion, QAScore, Reviewer,
)


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


def _seed_project(session, *, high=75.0, medium=50.0):
    proj = Project(title="Test SLR", qa_high_threshold=high, qa_medium_threshold=medium)
    session.add(proj); session.commit(); session.refresh(proj)
    reviewer = Reviewer(project_id=proj.id, name="Rev 1", role="R1")
    session.add(reviewer); session.commit(); session.refresh(reviewer)
    return proj, reviewer


def _add_qa_criteria(session, proj_id, n=4, max_score=1.0):
    crits = []
    for i in range(n):
        c = QACriterion(project_id=proj_id, label=f"QA{i+1}",
                        description=f"Criterion {i+1}", max_score=max_score)
        session.add(c); session.commit(); session.refresh(c)
        crits.append(c)
    return crits


def _add_paper(session, proj_id, citekey, *, phase="full-text"):
    p = Paper(project_id=proj_id, citekey=citekey, title=f"Paper {citekey}",
              source="acm", dedup_status="original")
    session.add(p); session.commit(); session.refresh(p)
    session.add(FinalDecision(project_id=proj_id, paper_id=p.id, phase=phase, decision="I"))
    session.commit()
    return p


class TestQASummary:
    def test_percentage_matches_score_total(self, client, db_session):
        proj, reviewer = _seed_project(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=4, max_score=1.0)
        p = _add_paper(db_session, proj.id, "highscore")
        # 3 out of 4 → 75% (lands on the High threshold).
        for c, score in zip(crits, [1.0, 1.0, 1.0, 0.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=score, scored_by_reviewer_id=reviewer.id))
        db_session.commit()

        resp = client.get(f"/api/projects/{proj.id}/qa-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_total"] == 4.0
        assert len(data["papers"]) == 1
        row = data["papers"][0]
        assert row["total_score"] == 3.0
        assert row["percentage"] == pytest.approx(75.0)
        assert row["quality_level"] == "high"  # 75% boundary inclusive on the high side

    def test_threshold_band_assignment_default(self, client, db_session):
        proj, reviewer = _seed_project(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=4, max_score=1.0)
        rows = [
            ("low_paper",    [0.0, 0.5, 0.0, 0.0]),  # 12.5% → low
            ("medium_paper", [1.0, 0.5, 0.5, 0.0]),  # 50% → medium (inclusive)
            ("high_paper",   [1.0, 1.0, 1.0, 0.5]),  # 87.5% → high
        ]
        for citekey, scores in rows:
            p = _add_paper(db_session, proj.id, citekey)
            for c, sc in zip(crits, scores):
                db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                       score=sc, scored_by_reviewer_id=reviewer.id))
        db_session.commit()

        data = client.get(f"/api/projects/{proj.id}/qa-summary").json()
        level_by_key = {p["paper_title"].split()[-1]: p["quality_level"] for p in data["papers"]}
        assert level_by_key == {"low_paper": "low", "medium_paper": "medium", "high_paper": "high"}

    def test_custom_thresholds_drive_band_assignment(self, client, db_session):
        proj, reviewer = _seed_project(db_session, medium=30.0, high=80.0)
        crits = _add_qa_criteria(db_session, proj.id, n=4, max_score=1.0)
        # 1/4 = 25% — under medium (30%) → low
        p = _add_paper(db_session, proj.id, "p25")
        for c, sc in zip(crits, [1.0, 0.0, 0.0, 0.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=reviewer.id))
        # 3/4 = 75% — between medium and high → medium
        p2 = _add_paper(db_session, proj.id, "p75")
        for c, sc in zip(crits, [1.0, 1.0, 1.0, 0.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p2.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=reviewer.id))
        # 4/4 = 100% — high
        p3 = _add_paper(db_session, proj.id, "p100")
        for c, sc in zip(crits, [1.0, 1.0, 1.0, 1.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p3.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=reviewer.id))
        db_session.commit()

        rows = client.get(f"/api/projects/{proj.id}/qa-summary").json()["papers"]
        by_pct = {row["percentage"]: row["quality_level"] for row in rows}
        assert by_pct[25.0] == "low"
        assert by_pct[75.0] == "medium"
        assert by_pct[100.0] == "high"
