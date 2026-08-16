"""Quality-score aggregation tests against the qa-summary endpoint.

Three invariants a quality assessment has to hold, because a review reports
them as if they were arithmetic:
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


class TestQAReviewerScoping:
    """Multi-reviewer QA: aggregate view averages per criterion; the
    ``reviewer_id`` query param scopes the summary to one reviewer's own
    scores (used by the scoring UI so switching reviewers switches data)."""

    def _seed_two_reviewers(self, session):
        proj, r1 = _seed_project(session)
        r2 = Reviewer(project_id=proj.id, name="Rev 2", role="R2")
        session.add(r2); session.commit(); session.refresh(r2)
        return proj, r1, r2

    def test_aggregate_averages_instead_of_overwriting(self, client, db_session):
        proj, r1, r2 = self._seed_two_reviewers(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=2, max_score=1.0)
        p = _add_paper(db_session, proj.id, "dual")
        # R1 scores (1.0, 0.0); R2 scores (0.0, 1.0) → average 0.5 per criterion.
        for c, sc in zip(crits, [1.0, 0.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=r1.id))
        for c, sc in zip(crits, [0.0, 1.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=r2.id))
        db_session.commit()

        row = client.get(f"/api/projects/{proj.id}/qa-summary").json()["papers"][0]
        assert [s["score"] for s in row["scores"]] == [0.5, 0.5]
        assert row["total_score"] == pytest.approx(1.0)

    def test_reviewer_id_param_returns_own_scores(self, client, db_session):
        proj, r1, r2 = self._seed_two_reviewers(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=2, max_score=1.0)
        p = _add_paper(db_session, proj.id, "scoped")
        for c, sc in zip(crits, [1.0, 1.0]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=r1.id))
        for c, sc in zip(crits, [0.0, 0.5]):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=sc, scored_by_reviewer_id=r2.id))
        db_session.commit()

        r1_row = client.get(f"/api/projects/{proj.id}/qa-summary",
                            params={"reviewer_id": r1.id}).json()["papers"][0]
        r2_row = client.get(f"/api/projects/{proj.id}/qa-summary",
                            params={"reviewer_id": r2.id}).json()["papers"][0]
        assert [s["score"] for s in r1_row["scores"]] == [1.0, 1.0]
        assert [s["score"] for s in r2_row["scores"]] == [0.0, 0.5]
        assert r1_row["total_score"] == pytest.approx(2.0)
        assert r2_row["total_score"] == pytest.approx(0.5)

    def test_fully_scored_counts_distinct_criteria_not_rows(self, client, db_session):
        """Two reviewers scoring the SAME single criterion must not mark a
        two-criterion paper as fully scored (the row count is 2, but only
        one criterion is covered)."""
        proj, r1, r2 = self._seed_two_reviewers(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=2, max_score=1.0)
        p = _add_paper(db_session, proj.id, "partial")
        for rev in (r1, r2):
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id,
                                   criterion_id=crits[0].id, score=1.0,
                                   scored_by_reviewer_id=rev.id))
        db_session.commit()

        row = client.get(f"/api/projects/{proj.id}/qa-summary").json()["papers"][0]
        assert row["fully_scored"] is False

    def test_reviewer_scope_fully_scored_is_per_reviewer(self, client, db_session):
        proj, r1, r2 = self._seed_two_reviewers(db_session)
        crits = _add_qa_criteria(db_session, proj.id, n=2, max_score=1.0)
        p = _add_paper(db_session, proj.id, "split")
        # R1 covers both criteria; R2 covers only the first.
        for c in crits:
            db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=c.id,
                                   score=1.0, scored_by_reviewer_id=r1.id))
        db_session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=crits[0].id,
                               score=0.5, scored_by_reviewer_id=r2.id))
        db_session.commit()

        r1_row = client.get(f"/api/projects/{proj.id}/qa-summary",
                            params={"reviewer_id": r1.id}).json()["papers"][0]
        r2_row = client.get(f"/api/projects/{proj.id}/qa-summary",
                            params={"reviewer_id": r2.id}).json()["papers"][0]
        assert r1_row["fully_scored"] is True
        assert r2_row["fully_scored"] is False
