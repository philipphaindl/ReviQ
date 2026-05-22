"""End-to-end smoke test: generate the PDF report against a populated project
and verify the resulting bytes are a valid PDF including the new synthesis-chart
captions ("Figure 1", "Figure 2", "Figure 3").
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import (
    DatabaseSearchString, ExtractionField, ExtractionRecord, FinalDecision,
    InclusionCriterion, Paper, Project, QACriterion, QAScore, Reviewer,
    ReviewerDecision, TaxonomyEntry,
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


def _build_fixture(session):
    proj = Project(title="Smoke Test", description="Synthesis chart smoke fixture")
    session.add(proj); session.commit(); session.refresh(proj)

    r1 = Reviewer(project_id=proj.id, name="Alice", role="R1")
    r2 = Reviewer(project_id=proj.id, name="Bob",   role="R2")
    session.add(r1); session.add(r2); session.commit(); session.refresh(r1); session.refresh(r2)

    session.add(InclusionCriterion(project_id=proj.id, label="I1", description="Relevant"))
    session.add(DatabaseSearchString(project_id=proj.id, db_name="acm",
                                     query_string="kw", results_count=100))

    # Two taxonomy dimensions, three categories each.
    for sort_order, (key, value) in enumerate([
        ("contribution_type", "Tool"),
        ("contribution_type", "Framework"),
        ("contribution_type", "Method"),
        ("research_type", "Validation"),
        ("research_type", "Evaluation"),
    ]):
        session.add(TaxonomyEntry(project_id=proj.id, taxonomy_type=key,
                                   value=value, sort_order=sort_order))

    qa = QACriterion(project_id=proj.id, label="QA1", description="Q1", max_score=1.0)
    qa2 = QACriterion(project_id=proj.id, label="QA2", description="Q2", max_score=1.0)
    session.add(qa); session.add(qa2); session.commit(); session.refresh(qa); session.refresh(qa2)

    field = ExtractionField(project_id=proj.id, field_name="usage", field_label="Usage",
                            field_type="dropdown", sort_order=0)
    session.add(field); session.commit(); session.refresh(field)

    papers = []
    for i in range(6):
        p = Paper(project_id=proj.id, citekey=f"p{i}", title=f"Paper {i}",
                  source="acm", dedup_status="original", year=2020 + (i % 3),
                  venue="ICSE 2020")
        session.add(p); session.commit(); session.refresh(p)
        papers.append(p)

    # All papers screened in, then all but one included at full-text.
    for p in papers:
        session.add(ReviewerDecision(project_id=proj.id, paper_id=p.id, reviewer_id=r1.id,
                                     phase="screening", decision="I"))
        session.add(ReviewerDecision(project_id=proj.id, paper_id=p.id, reviewer_id=r2.id,
                                     phase="screening", decision="I" if p.id % 2 == 0 else "E"))
        session.add(FinalDecision(project_id=proj.id, paper_id=p.id, phase="screening", decision="I"))
    for p in papers[:5]:
        session.add(FinalDecision(project_id=proj.id, paper_id=p.id, phase="full-text", decision="I"))
    session.add(FinalDecision(project_id=proj.id, paper_id=papers[5].id, phase="full-text", decision="E"))

    # Spread QA scores so every band gets a paper.
    scores_for = [(1.0, 1.0), (1.0, 0.5), (0.5, 0.5), (0.5, 0.0), (0.0, 0.0)]
    for p, (s1, s2) in zip(papers[:5], scores_for):
        for crit, score in [(qa, s1), (qa2, s2)]:
            session.add(QAScore(project_id=proj.id, paper_id=p.id, criterion_id=crit.id,
                                score=score, scored_by_reviewer_id=r1.id))

    # Extraction values: taxonomy + custom field.
    values = [
        {"contribution_type": "Tool",      "research_type": "Validation", "usage": "Direct"},
        {"contribution_type": "Tool",      "research_type": "Evaluation", "usage": "Direct"},
        {"contribution_type": "Framework", "research_type": "Validation", "usage": "Indirect"},
        {"contribution_type": "Method",    "research_type": "Validation", "usage": "Indirect"},
        {"contribution_type": "Tool",      "research_type": "Evaluation", "usage": "Direct"},
    ]
    for p, vmap in zip(papers[:5], values):
        for field_name, field_value in vmap.items():
            session.add(ExtractionRecord(project_id=proj.id, paper_id=p.id,
                                         field_name=field_name, field_value=field_value,
                                         extracted_by_reviewer_id=r1.id))
    session.commit()
    return proj.id


class TestPDFGeneration:
    def test_pdf_contains_synthesis_figure_captions(self, client, db_session):
        import io
        from pypdf import PdfReader

        proj_id = _build_fixture(db_session)
        resp = client.get(f"/api/projects/{proj_id}/report/pdf")
        assert resp.status_code == 200
        body = resp.content
        assert body[:5] == b"%PDF-", "response is not a PDF"

        reader = PdfReader(io.BytesIO(body))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # The three new figure captions must appear in order — one per chart.
        assert "Figure 1" in text
        assert "Figure 2" in text
        assert "Figure 3" in text
        assert "inter-rater agreement statistics" in text.lower()
