from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from app.database import get_session
from app.models import Paper, ReviewerDecision, FinalDecision, Reviewer

router = APIRouter(tags=["papers"])


@router.get("/projects/{project_id}/papers")
def list_papers(
    project_id: int,
    source: Optional[str] = Query(None),
    dedup_status: Optional[str] = Query(None),
    phase: Optional[str] = Query("screening"),
    decision_status: Optional[str] = Query(None),  # decided, undecided, conflict
    session: Session = Depends(get_session),
):
    """
    List papers for a project with optional filters.
    Returns papers with their final screening decision (if any).
    """
    _require_project(project_id, session)

    stmt = select(Paper).where(Paper.project_id == project_id)
    if source:
        stmt = stmt.where(Paper.source == source)
    if dedup_status:
        stmt = stmt.where(Paper.dedup_status == dedup_status)

    papers = session.exec(stmt).all()

    # Enrich with final decisions and conflict status
    result = []
    for paper in papers:
        final = session.exec(
            select(FinalDecision)
            .where(FinalDecision.paper_id == paper.id)
            .where(FinalDecision.phase == (phase or "screening"))
        ).first()

        reviewer_decisions = session.exec(
            select(ReviewerDecision)
            .where(ReviewerDecision.paper_id == paper.id)
            .where(ReviewerDecision.phase == (phase or "screening"))
        ).all()

        entry = paper.model_dump()
        entry["final_decision"] = final.model_dump() if final else None
        entry["reviewer_decision_count"] = len(reviewer_decisions)
        entry["decisions"] = [d.model_dump() for d in reviewer_decisions]
        result.append(entry)

    # Filter by decision status if requested
    if decision_status == "undecided":
        result = [r for r in result if r["final_decision"] is None and r["reviewer_decision_count"] == 0]
    elif decision_status == "decided":
        result = [r for r in result if r["final_decision"] is not None]

    return result


@router.get("/projects/{project_id}/papers/{paper_id}")
def get_paper(project_id: int, paper_id: int, session: Session = Depends(get_session)):
    p = session.get(Paper, paper_id)
    if not p or p.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    return p


class PaperUpdate(BaseModel):
    full_text_url: Optional[str] = None
    full_text_inaccessible: Optional[bool] = None


@router.put("/projects/{project_id}/papers/{paper_id}")
def update_paper(project_id: int, paper_id: int, body: PaperUpdate, session: Session = Depends(get_session)):
    p = session.get(Paper, paper_id)
    if not p or p.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p
