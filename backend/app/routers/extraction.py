from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from app.database import get_session
from app.models import ExtractionField, ExtractionRecord, Paper, Reviewer

router = APIRouter(tags=["extraction"])


# ── Field schema (project-level) ─────────────────────────────────────────────

class FieldCreate(BaseModel):
    field_name: str
    field_label: str
    field_type: str   # text, dropdown, boolean, number
    options: Optional[str] = None  # JSON array for dropdown
    sort_order: int = 0


class FieldUpdate(BaseModel):
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("/projects/{project_id}/extraction/fields")
def list_fields(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    fields = session.exec(
        select(ExtractionField)
        .where(ExtractionField.project_id == project_id)
        .order_by(ExtractionField.sort_order, ExtractionField.id)
    ).all()
    return fields


@router.post("/projects/{project_id}/extraction/fields")
def create_field(project_id: int, body: FieldCreate, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    # Ensure unique field_name within project
    existing = session.exec(
        select(ExtractionField)
        .where(ExtractionField.project_id == project_id)
        .where(ExtractionField.field_name == body.field_name)
    ).first()
    if existing:
        raise HTTPException(400, "A field with this name already exists")
    field = ExtractionField(project_id=project_id, **body.model_dump())
    session.add(field)
    session.commit()
    session.refresh(field)
    return field


@router.put("/projects/{project_id}/extraction/fields/{field_id}")
def update_field(
    project_id: int, field_id: int, body: FieldUpdate, session: Session = Depends(get_session)
):
    field = session.get(ExtractionField, field_id)
    if not field or field.project_id != project_id:
        raise HTTPException(404, "Field not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(field, k, v)
    session.add(field)
    session.commit()
    session.refresh(field)
    return field


@router.delete("/projects/{project_id}/extraction/fields/{field_id}", status_code=204)
def delete_field(project_id: int, field_id: int, session: Session = Depends(get_session)):
    field = session.get(ExtractionField, field_id)
    if not field or field.project_id != project_id:
        raise HTTPException(404, "Field not found")
    # Delete all records for this field
    for rec in session.exec(
        select(ExtractionRecord)
        .where(ExtractionRecord.project_id == project_id)
        .where(ExtractionRecord.field_name == field.field_name)
    ).all():
        session.delete(rec)
    session.delete(field)
    session.commit()


# ── Records (per-paper values) ────────────────────────────────────────────────

class RecordUpsert(BaseModel):
    reviewer_id: int
    field_name: str
    field_value: Optional[str] = None


@router.get("/projects/{project_id}/extraction/records")
def list_records(project_id: int, session: Session = Depends(get_session)):
    """All extraction records for the project, grouped will be done client-side."""
    _require_project(project_id, session)
    records = session.exec(
        select(ExtractionRecord).where(ExtractionRecord.project_id == project_id)
    ).all()
    return records


@router.get("/projects/{project_id}/papers/{paper_id}/extraction")
def get_paper_extraction(project_id: int, paper_id: int, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper or paper.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    records = session.exec(
        select(ExtractionRecord).where(ExtractionRecord.paper_id == paper_id)
    ).all()
    return records


@router.post("/projects/{project_id}/papers/{paper_id}/extraction")
def upsert_record(
    project_id: int,
    paper_id: int,
    body: RecordUpsert,
    session: Session = Depends(get_session),
):
    paper = session.get(Paper, paper_id)
    if not paper or paper.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    reviewer = session.get(Reviewer, body.reviewer_id)
    if not reviewer or reviewer.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")

    existing = session.exec(
        select(ExtractionRecord)
        .where(ExtractionRecord.paper_id == paper_id)
        .where(ExtractionRecord.field_name == body.field_name)
        .where(ExtractionRecord.extracted_by_reviewer_id == body.reviewer_id)
    ).first()

    if existing:
        existing.field_value = body.field_value
        session.add(existing)
    else:
        session.add(ExtractionRecord(
            project_id=project_id,
            paper_id=paper_id,
            field_name=body.field_name,
            field_value=body.field_value,
            extracted_by_reviewer_id=body.reviewer_id,
        ))
    session.commit()
    return {"status": "ok"}


@router.get("/projects/{project_id}/extraction/summary")
def extraction_summary(project_id: int, session: Session = Depends(get_session)):
    """Return all included papers with their extraction records."""
    from app.models import FinalDecision
    _require_project(project_id, session)

    fields = session.exec(
        select(ExtractionField)
        .where(ExtractionField.project_id == project_id)
        .order_by(ExtractionField.sort_order, ExtractionField.id)
    ).all()

    # Papers included from full-text, fallback to screening
    ft_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "full-text")
        .where(FinalDecision.decision == "I")
    ).all()
    sc_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "screening")
        .where(FinalDecision.decision == "I")
    ).all()

    paper_ids = [d.paper_id for d in ft_included] if ft_included else [d.paper_id for d in sc_included]

    all_records = session.exec(
        select(ExtractionRecord).where(ExtractionRecord.project_id == project_id)
    ).all()
    rec_map: dict = {}
    for r in all_records:
        rec_map.setdefault(r.paper_id, {})[r.field_name] = r.field_value

    result = []
    for pid in paper_ids:
        paper = session.get(Paper, pid)
        if not paper:
            continue
        vals = rec_map.get(pid, {})
        filled = sum(1 for f in fields if vals.get(f.field_name) not in (None, ""))
        result.append({
            "paper_id": pid,
            "citekey": paper.citekey,
            "title": paper.title,
            "authors": paper.authors,
            "year": paper.year,
            "source": paper.source,
            "values": vals,
            "filled": filled,
            "total_fields": len(fields),
        })

    return {"fields": [f.model_dump() for f in fields], "papers": result}


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
