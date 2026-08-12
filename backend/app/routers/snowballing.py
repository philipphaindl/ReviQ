from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from app.database import get_session
from app.models import SnowballingIteration, Paper, FinalDecision

router = APIRouter(tags=["snowballing"])


class IterationCreate(BaseModel):
    iteration_type: str = "forward"  # forward, backward


@router.get("/projects/{project_id}/snowballing")
def list_iterations(project_id: int, session: Session = Depends(get_session)):
    _require_project(project_id, session)
    iterations = session.exec(
        select(SnowballingIteration)
        .where(SnowballingIteration.project_id == project_id)
        .order_by(SnowballingIteration.iteration_number)
    ).all()
    result = []
    for it in iterations:
        source = f"snowballing:{it.iteration_number}"
        papers = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.source == source)
            .where(Paper.dedup_status == "original")
        ).all()
        paper_ids = [p.id for p in papers]
        included_count = 0
        if paper_ids:
            included = session.exec(
                select(FinalDecision)
                .where(FinalDecision.project_id == project_id)
                .where(FinalDecision.phase == "screening")
                .where(FinalDecision.paper_id.in_(paper_ids))
                .where(FinalDecision.decision == "I")
            ).all()
            included_count = len(included)
        entry = it.model_dump()
        entry["paper_count"] = len(papers)
        entry["included_count"] = included_count
        result.append(entry)
    return result


@router.post("/projects/{project_id}/snowballing")
def create_iteration(
    project_id: int,
    body: IterationCreate,
    session: Session = Depends(get_session),
):
    _require_project(project_id, session)
    existing = session.exec(
        select(SnowballingIteration)
        .where(SnowballingIteration.project_id == project_id)
        .order_by(SnowballingIteration.iteration_number.desc())
    ).first()
    n = (existing.iteration_number + 1) if existing else 1
    it = SnowballingIteration(
        project_id=project_id,
        iteration_number=n,
        iteration_type=body.iteration_type,
    )
    session.add(it)
    session.commit()
    session.refresh(it)
    entry = it.model_dump()
    entry["paper_count"] = 0
    entry["included_count"] = 0
    return entry


class IterationUpdate(BaseModel):
    iteration_type: str  # forward, backward


@router.put("/projects/{project_id}/snowballing/{iteration_id}")
def update_iteration(
    project_id: int,
    iteration_id: int,
    body: IterationUpdate,
    session: Session = Depends(get_session),
):
    it = session.get(SnowballingIteration, iteration_id)
    if not it or it.project_id != project_id:
        raise HTTPException(404, "Iteration not found")
    it.iteration_type = body.iteration_type
    session.add(it)
    session.commit()
    session.refresh(it)
    return it


@router.delete("/projects/{project_id}/snowballing/{iteration_id}", status_code=204)
def delete_iteration(
    project_id: int,
    iteration_id: int,
    session: Session = Depends(get_session),
):
    it = session.get(SnowballingIteration, iteration_id)
    if not it or it.project_id != project_id:
        raise HTTPException(404, "Iteration not found")
    # Delete all papers imported in this iteration
    source = f"snowballing:{it.iteration_number}"
    papers = session.exec(
        select(Paper).where(Paper.project_id == project_id).where(Paper.source == source)
    ).all()
    from app.models import ReviewerDecision, FinalDecision, ConflictLog
    for paper in papers:
        for model in (ReviewerDecision, FinalDecision, ConflictLog):
            for row in session.exec(select(model).where(model.paper_id == paper.id)).all():
                session.delete(row)
        session.delete(paper)
    session.delete(it)
    session.commit()


@router.put("/projects/{project_id}/snowballing/{iteration_id}/saturate")
def confirm_saturation(
    project_id: int,
    iteration_id: int,
    session: Session = Depends(get_session),
):
    it = session.get(SnowballingIteration, iteration_id)
    if not it or it.project_id != project_id:
        raise HTTPException(404, "Iteration not found")
    it.saturation_confirmed = True
    it.is_saturated = True
    session.add(it)
    session.commit()
    session.refresh(it)
    return it


@router.put("/projects/{project_id}/snowballing/{iteration_id}/unsaturate")
def revoke_saturation(
    project_id: int,
    iteration_id: int,
    session: Session = Depends(get_session),
):
    it = session.get(SnowballingIteration, iteration_id)
    if not it or it.project_id != project_id:
        raise HTTPException(404, "Iteration not found")
    it.saturation_confirmed = False
    it.is_saturated = False
    session.add(it)
    session.commit()
    session.refresh(it)
    return it


@router.post("/projects/{project_id}/snowballing/{iteration_id}/import")
async def import_snowballing_papers(
    project_id: int,
    iteration_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Import BibTeX for a specific snowballing iteration."""
    it = session.get(SnowballingIteration, iteration_id)
    if not it or it.project_id != project_id:
        raise HTTPException(404, "Iteration not found")

    from app.services import paper_import
    from app.services.bibtex_service import (
        parse_bib_content, detect_duplicates, entry_to_paper_dict, normalize_title,
    )

    content = (await file.read()).decode("utf-8", errors="replace")
    entries = parse_bib_content(content)
    source = f"snowballing:{it.iteration_number}"

    existing_papers = session.exec(
        select(Paper)
        .where(Paper.project_id == project_id)
        .where(Paper.dedup_status == "original")
    ).all()
    existing_dois: set[str] = set()
    existing_title_venues: set[str] = set()
    for p in existing_papers:
        if p.doi:
            existing_dois.add(p.doi.strip().lower())
        if p.title:
            tv = normalize_title(p.title) + "__" + normalize_title(p.venue or "")
            existing_title_venues.add(tv)

    unique, duplicates, _, _ = detect_duplicates(entries, existing_dois, existing_title_venues)

    # The same loop as the database-search importer, from the same module.
    # They were separate copies, and they had drifted: this one counted a
    # duplicate whether or not a row was written, the other only when one was,
    # so `detected_duplicates` meant two different things in the same UI tile.
    outcome = paper_import.apply_entries(
        session, project_id, unique, duplicates,
        to_paper_dict=lambda entry: entry_to_paper_dict(entry, source=source),
        extra_fields={"discovery": "snowball"},
    )
    session.commit()

    return {"source": source, **outcome.counts(len(entries))}


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
