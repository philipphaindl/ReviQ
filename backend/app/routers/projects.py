from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_session
from app.models import (
    Project, Reviewer, InclusionCriterion, ExclusionCriterion,
    QACriterion, TaxonomyEntry, DatabaseSearchString,
)

router = APIRouter(tags=["projects"])


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    lead_researcher: str
    qa_high_threshold: float = 75.0
    qa_medium_threshold: float = 50.0
    post_year_threshold: int = 2018


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    lead_researcher: Optional[str] = None
    qa_high_threshold: Optional[float] = None
    qa_medium_threshold: Optional[float] = None
    post_year_threshold: Optional[int] = None


@router.get("/projects")
def list_projects(session: Session = Depends(get_session)):
    return session.exec(select(Project)).all()


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, session: Session = Depends(get_session)):
    project = Project(**body.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    # Auto-create R1 (lead reviewer) using the lead researcher's name
    r1 = Reviewer(project_id=project.id, name=body.lead_researcher, role='R1')
    session.add(r1)
    session.commit()
    return project


@router.get("/projects/{project_id}")
def get_project(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.put("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    session.delete(p)
    session.commit()


# ── Reviewers ─────────────────────────────────────────────────────────────────

class ReviewerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    role: str


class ReviewerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


@router.get("/projects/{project_id}/reviewers")
def list_reviewers(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(select(Reviewer).where(Reviewer.project_id == project_id)).all()


@router.post("/projects/{project_id}/reviewers", status_code=201)
def add_reviewer(project_id: int, body: ReviewerCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    r = Reviewer(project_id=project_id, **body.model_dump())
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


@router.put("/projects/{project_id}/reviewers/{reviewer_id}")
def update_reviewer(project_id: int, reviewer_id: int, body: ReviewerUpdate, session: Session = Depends(get_session)):
    r = session.get(Reviewer, reviewer_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


@router.delete("/projects/{project_id}/reviewers/{reviewer_id}", status_code=204)
def delete_reviewer(project_id: int, reviewer_id: int, session: Session = Depends(get_session)):
    r = session.get(Reviewer, reviewer_id)
    if not r or r.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")
    session.delete(r)
    session.commit()


# ── Inclusion Criteria ────────────────────────────────────────────────────────

class CriterionCreate(BaseModel):
    label: str
    description: str
    phase: str = "screening"


class CriterionUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    phase: Optional[str] = None


@router.get("/projects/{project_id}/criteria/inclusion")
def list_inclusion(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(select(InclusionCriterion).where(InclusionCriterion.project_id == project_id)).all()


@router.post("/projects/{project_id}/criteria/inclusion", status_code=201)
def add_inclusion(project_id: int, body: CriterionCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    c = InclusionCriterion(project_id=project_id, **body.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.put("/projects/{project_id}/criteria/inclusion/{criterion_id}")
def update_inclusion(project_id: int, criterion_id: int, body: CriterionUpdate, session: Session = Depends(get_session)):
    c = session.get(InclusionCriterion, criterion_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "Criterion not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.delete("/projects/{project_id}/criteria/inclusion/{criterion_id}", status_code=204)
def delete_inclusion(project_id: int, criterion_id: int, session: Session = Depends(get_session)):
    c = session.get(InclusionCriterion, criterion_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "Criterion not found")
    session.delete(c)
    session.commit()


# ── Exclusion Criteria ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/criteria/exclusion")
def list_exclusion(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(select(ExclusionCriterion).where(ExclusionCriterion.project_id == project_id)).all()


@router.post("/projects/{project_id}/criteria/exclusion", status_code=201)
def add_exclusion(project_id: int, body: CriterionCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    c = ExclusionCriterion(project_id=project_id, **body.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.put("/projects/{project_id}/criteria/exclusion/{criterion_id}")
def update_exclusion(project_id: int, criterion_id: int, body: CriterionUpdate, session: Session = Depends(get_session)):
    c = session.get(ExclusionCriterion, criterion_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "Criterion not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.delete("/projects/{project_id}/criteria/exclusion/{criterion_id}", status_code=204)
def delete_exclusion(project_id: int, criterion_id: int, session: Session = Depends(get_session)):
    c = session.get(ExclusionCriterion, criterion_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "Criterion not found")
    session.delete(c)
    session.commit()


# ── QA Criteria ───────────────────────────────────────────────────────────────

class QACriterionCreate(BaseModel):
    label: str
    description: str
    max_score: float = 1.0


class QACriterionUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    max_score: Optional[float] = None


@router.get("/projects/{project_id}/qa-criteria")
def list_qa(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(select(QACriterion).where(QACriterion.project_id == project_id)).all()


@router.post("/projects/{project_id}/qa-criteria", status_code=201)
def add_qa(project_id: int, body: QACriterionCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    c = QACriterion(project_id=project_id, **body.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.put("/projects/{project_id}/qa-criteria/{qa_id}")
def update_qa(project_id: int, qa_id: int, body: QACriterionUpdate, session: Session = Depends(get_session)):
    c = session.get(QACriterion, qa_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "QA criterion not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.delete("/projects/{project_id}/qa-criteria/{qa_id}", status_code=204)
def delete_qa(project_id: int, qa_id: int, session: Session = Depends(get_session)):
    c = session.get(QACriterion, qa_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "QA criterion not found")
    session.delete(c)
    session.commit()


# ── Taxonomies ────────────────────────────────────────────────────────────────

class TaxonomyCreate(BaseModel):
    value: str
    sort_order: int = 0


@router.get("/projects/{project_id}/taxonomies/{taxonomy_type}")
def list_taxonomy(project_id: int, taxonomy_type: str, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(
        select(TaxonomyEntry)
        .where(TaxonomyEntry.project_id == project_id)
        .where(TaxonomyEntry.taxonomy_type == taxonomy_type)
        .order_by(TaxonomyEntry.sort_order)
    ).all()


@router.post("/projects/{project_id}/taxonomies/{taxonomy_type}", status_code=201)
def add_taxonomy(project_id: int, taxonomy_type: str, body: TaxonomyCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    entry = TaxonomyEntry(project_id=project_id, taxonomy_type=taxonomy_type, **body.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.delete("/projects/{project_id}/taxonomies/{entry_id}", status_code=204)
def delete_taxonomy(project_id: int, entry_id: int, session: Session = Depends(get_session)):
    e = session.get(TaxonomyEntry, entry_id)
    if not e or e.project_id != project_id:
        raise HTTPException(404, "Taxonomy entry not found")
    session.delete(e)
    session.commit()


@router.get("/projects/{project_id}/taxonomy-types")
def list_taxonomy_types(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    rows = session.exec(
        select(TaxonomyEntry.taxonomy_type)
        .where(TaxonomyEntry.project_id == project_id)
        .distinct()
    ).all()
    return list(rows)


class TaxonomyTypeRename(BaseModel):
    new_type: str


@router.put("/projects/{project_id}/taxonomy-types/{taxonomy_type}")
def rename_taxonomy_type(project_id: int, taxonomy_type: str, body: TaxonomyTypeRename, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    entries = session.exec(
        select(TaxonomyEntry)
        .where(TaxonomyEntry.project_id == project_id)
        .where(TaxonomyEntry.taxonomy_type == taxonomy_type)
    ).all()
    for e in entries:
        e.taxonomy_type = body.new_type
        session.add(e)
    session.commit()
    return {"renamed": len(entries)}


@router.delete("/projects/{project_id}/taxonomy-types/{taxonomy_type}", status_code=204)
def delete_taxonomy_type(project_id: int, taxonomy_type: str, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    entries = session.exec(
        select(TaxonomyEntry)
        .where(TaxonomyEntry.project_id == project_id)
        .where(TaxonomyEntry.taxonomy_type == taxonomy_type)
    ).all()
    for e in entries:
        session.delete(e)
    session.commit()


# ── Database Search Strings ───────────────────────────────────────────────────

class SearchStringCreate(BaseModel):
    db_name: str
    query_string: Optional[str] = None
    filter_settings: Optional[str] = None
    search_date: Optional[str] = None


class SearchStringUpdate(BaseModel):
    db_name: Optional[str] = None
    query_string: Optional[str] = None
    filter_settings: Optional[str] = None
    search_date: Optional[str] = None


@router.get("/projects/{project_id}/search-strings")
def list_search_strings(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    return session.exec(select(DatabaseSearchString).where(DatabaseSearchString.project_id == project_id)).all()


@router.post("/projects/{project_id}/search-strings", status_code=201)
def add_search_string(project_id: int, body: SearchStringCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    s = DatabaseSearchString(project_id=project_id, **body.model_dump())
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


@router.put("/projects/{project_id}/search-strings/{ss_id}")
def update_search_string(project_id: int, ss_id: int, body: SearchStringUpdate, session: Session = Depends(get_session)):
    s = session.get(DatabaseSearchString, ss_id)
    if not s or s.project_id != project_id:
        raise HTTPException(404, "Search string not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


@router.delete("/projects/{project_id}/search-strings/{ss_id}", status_code=204)
def delete_search_string(project_id: int, ss_id: int, session: Session = Depends(get_session)):
    s = session.get(DatabaseSearchString, ss_id)
    if not s or s.project_id != project_id:
        raise HTTPException(404, "Search string not found")
    session.delete(s)
    session.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_project(project_id: int, session: Session) -> Project:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p
