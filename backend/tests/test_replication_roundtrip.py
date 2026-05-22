"""Replication-package round-trip test.

Per CLAUDE.md: export → ZIP → re-import → deep-equal on the resulting
project state (modulo timestamps and auto-increment IDs).
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import (
    DatabaseSearchString, ExtractionField, ExtractionRecord, FinalDecision,
    InclusionCriterion, Paper, Project, QACriterion, QAScore, Reviewer,
    TaxonomyEntry,
)


@pytest.fixture
def db_session():
    # StaticPool keeps the single in-memory connection alive across
    # threads/requests — without it, FastAPI's threadpool gets a fresh
    # `:memory:` connection with an empty schema.
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


def _seed_full_project(session):
    """Build a project with rows in every replication-relevant table."""
    proj = Project(title="Round Trip", description="round-trip fixture",
                   qa_high_threshold=80.0, qa_medium_threshold=40.0)
    session.add(proj); session.commit(); session.refresh(proj)

    r1 = Reviewer(project_id=proj.id, name="Alice", role="R1", email="a@x")
    r2 = Reviewer(project_id=proj.id, name="Bob",   role="R2")
    session.add(r1); session.add(r2); session.commit(); session.refresh(r1); session.refresh(r2)

    session.add(InclusionCriterion(project_id=proj.id, label="I1", description="Inclusion 1"))
    session.add(DatabaseSearchString(project_id=proj.id, db_name="acm",
                                     query_string="kw1 AND kw2", results_count=42))
    session.add(TaxonomyEntry(project_id=proj.id, taxonomy_type="contribution_type",
                              value="Tool", sort_order=0))
    qa = QACriterion(project_id=proj.id, label="QA1", description="Question 1", max_score=1.0)
    session.add(qa); session.commit(); session.refresh(qa)
    field = ExtractionField(project_id=proj.id, field_name="usage",
                             field_label="Usage", field_type="dropdown", sort_order=0)
    session.add(field); session.commit(); session.refresh(field)

    p1 = Paper(project_id=proj.id, citekey="p1", title="Paper One", source="acm",
               dedup_status="original", year=2020)
    p2 = Paper(project_id=proj.id, citekey="p2", title="Paper Two", source="acm",
               dedup_status="duplicate_of:p1", year=2021)
    session.add(p1); session.add(p2); session.commit()
    session.refresh(p1); session.refresh(p2)

    session.add(FinalDecision(project_id=proj.id, paper_id=p1.id, phase="full-text", decision="I"))
    session.add(QAScore(project_id=proj.id, paper_id=p1.id, criterion_id=qa.id,
                        score=1.0, rationale="strong", scored_by_reviewer_id=r1.id))
    session.add(ExtractionRecord(project_id=proj.id, paper_id=p1.id,
                                  field_name="usage", field_value="Direct",
                                  extracted_by_reviewer_id=r1.id))
    session.commit()
    return proj.id


def _snapshot(session, project_id):
    """Stable comparison snapshot — drops timestamps and re-bound IDs."""
    def rows(model, *fields):
        return sorted(
            [{f: getattr(r, f) for f in fields}
             for r in session.exec(
                 __import__("sqlmodel").select(model).where(model.project_id == project_id)
             ).all()],
            key=lambda d: tuple(str(v) for v in d.values()),
        )
    return {
        "reviewers": rows(Reviewer, "name", "role", "email"),
        "inclusion_criteria": rows(InclusionCriterion, "label", "description", "phase"),
        "qa_criteria":        rows(QACriterion, "label", "description", "max_score"),
        "taxonomy":           rows(TaxonomyEntry, "taxonomy_type", "value", "sort_order"),
        "extraction_fields":  rows(ExtractionField, "field_name", "field_label", "field_type", "sort_order"),
        "papers": rows(Paper, "citekey", "title", "year", "source", "dedup_status"),
        "final_decisions": rows(FinalDecision, "phase", "decision"),
        "qa_scores": rows(QAScore, "score", "rationale"),
        "extraction_records": rows(ExtractionRecord, "field_name", "field_value"),
    }


class TestReplicationRoundTrip:
    def test_export_then_import_preserves_project_state(self, client, db_session):
        proj_id = _seed_full_project(db_session)
        before = _snapshot(db_session, proj_id)

        resp = client.get(f"/api/projects/{proj_id}/replication/export")
        assert resp.status_code == 200
        zip_bytes = resp.content
        # Verify the ZIP is well-formed and contains the manifest.
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        assert "project.json" in zf.namelist()

        # Re-import as a fresh project (in the same in-memory DB).
        files = {"file": ("pkg.zip", zip_bytes, "application/zip")}
        rresp = client.post("/api/projects/replication/import", files=files)
        assert rresp.status_code == 200
        new_id = rresp.json()["id"]
        assert new_id != proj_id

        after = _snapshot(db_session, new_id)
        assert after == before

    def test_schema_version_is_v1(self, client, db_session):
        proj_id = _seed_full_project(db_session)
        resp = client.get(f"/api/projects/{proj_id}/replication/export")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        import json as _json
        pkg = _json.loads(zf.read("project.json"))
        assert pkg["_schema"].startswith("reviq-replication")
