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

    imported = []
    dup_citekeys = []

    for entry in unique:
        data = entry_to_paper_dict(entry, source=source)
        if not data["citekey"] or not data["title"]:
            continue
        existing = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == data["citekey"])
        ).first()
        if existing:
            continue
        paper = Paper(project_id=project_id, **data)
        session.add(paper)
        imported.append(data["citekey"])

    for entry in duplicates:
        data = entry_to_paper_dict(entry, source=source)
        if not data["citekey"] or not data["title"]:
            continue
        dup_citekeys.append(data.get("citekey", "?"))
        existing = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == data["citekey"])
        ).first()
        if not existing:
            paper = Paper(
                project_id=project_id,
                **{**data, "dedup_status": "duplicate_of:existing"},
            )
            session.add(paper)

    session.commit()
    return {
        "source": source,
        "imported_unique": len(imported),
        "detected_duplicates": len(dup_citekeys),
        "imported_citekeys": imported,
    }


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
