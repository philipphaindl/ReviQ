"""
Reviewer decision endpoints and automatic conflict detection.

After each decision upsert the shared state machine
(services.decision_service.sync_decision_state) recomputes the paper's
FinalDecision/ConflictLog: agreement auto-creates a FinalDecision,
disagreement opens a ConflictLog and removes any provisional final,
solo-reviewer projects get a provisional FinalDecision immediately.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_session
from app.models import Paper, ReviewerDecision, FinalDecision, ConflictLog, Reviewer
from app.services.decision_service import sync_decision_state

router = APIRouter(tags=["decisions"])


class DecisionCreate(BaseModel):
    reviewer_id: int
    phase: str = "screening"
    decision: str  # I, E, U
    criterion_label: Optional[str] = None
    rationale: Optional[str] = None


class ConflictResolve(BaseModel):
    resolved_by_reviewer_id: int
    resolution: str  # I, E, U
    resolution_method: str  # agreement, discussion, arbitration
    resolution_note: Optional[str] = None


@router.get("/projects/{project_id}/papers/{paper_id}/decisions")
def get_paper_decisions(
    project_id: int,
    paper_id: int,
    phase: str = "screening",
    session: Session = Depends(get_session),
):
    paper = _require_paper(project_id, paper_id, session)
    decisions = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.paper_id == paper.id)
        .where(ReviewerDecision.phase == phase)
    ).all()
    final = session.exec(
        select(FinalDecision)
        .where(FinalDecision.paper_id == paper.id)
        .where(FinalDecision.phase == phase)
    ).first()
    return {"decisions": decisions, "final_decision": final}


@router.post("/projects/{project_id}/papers/{paper_id}/decisions")
def add_decision(
    project_id: int,
    paper_id: int,
    body: DecisionCreate,
    session: Session = Depends(get_session),
):
    """
    Add or update a reviewer's decision for a paper.
    If all reviewers agree, automatically creates a FinalDecision.
    If reviewers disagree, logs a ConflictLog entry.
    """
    paper = _require_paper(project_id, paper_id, session)
    reviewer = session.get(Reviewer, body.reviewer_id)
    if not reviewer or reviewer.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")

    # Upsert decision
    existing = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.paper_id == paper.id)
        .where(ReviewerDecision.reviewer_id == body.reviewer_id)
        .where(ReviewerDecision.phase == body.phase)
    ).first()

    if existing:
        existing.decision = body.decision
        existing.criterion_label = body.criterion_label
        existing.rationale = body.rationale
        existing.timestamp = datetime.utcnow()
        session.add(existing)
    else:
        dec = ReviewerDecision(
            project_id=project_id,
            paper_id=paper.id,
            reviewer_id=body.reviewer_id,
            phase=body.phase,
            decision=body.decision,
            criterion_label=body.criterion_label,
            rationale=body.rationale,
        )
        session.add(dec)

    session.commit()

    sync_decision_state(session, project_id, paper.id, body.phase)
    session.commit()
    return {"status": "ok", "decision": body.decision}


@router.get("/projects/{project_id}/conflicts")
def list_conflicts(
    project_id: int,
    phase: str = "screening",
    resolved: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    _require_project(project_id, session)
    stmt = (
        select(ConflictLog)
        .where(ConflictLog.project_id == project_id)
        .where(ConflictLog.phase == phase)
    )
    if resolved is not None:
        stmt = stmt.where(ConflictLog.resolved == resolved)
    conflicts = session.exec(stmt).all()

    # Enrich with paper title
    result = []
    for c in conflicts:
        paper = session.get(Paper, c.paper_id)
        entry = c.model_dump()
        entry["paper_title"] = paper.title if paper else None
        entry["paper_citekey"] = paper.citekey if paper else None
        result.append(entry)
    return result


@router.post("/projects/{project_id}/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    project_id: int,
    conflict_id: int,
    body: ConflictResolve,
    session: Session = Depends(get_session),
):
    conflict = session.get(ConflictLog, conflict_id)
    if not conflict or conflict.project_id != project_id:
        raise HTTPException(404, "Conflict not found")
    if conflict.resolved:
        raise HTTPException(400, "Conflict already resolved")

    conflict.resolved = True
    conflict.resolution = body.resolution
    conflict.resolution_method = body.resolution_method
    # `body.resolution_note` is always defined (it's Optional[str] on the
    # Pydantic schema), but ConflictLog itself does not yet carry the field.
    # Guard against the *model* missing the attribute rather than the body.
    if hasattr(conflict, 'resolution_note'):
        conflict.resolution_note = body.resolution_note
    conflict.resolved_by_reviewer_id = body.resolved_by_reviewer_id
    conflict.resolved_at = datetime.utcnow()
    session.add(conflict)

    # Update or create FinalDecision
    final = session.exec(
        select(FinalDecision)
        .where(FinalDecision.paper_id == conflict.paper_id)
        .where(FinalDecision.phase == conflict.phase)
    ).first()
    if final:
        final.decision = body.resolution
        final.resolution_method = body.resolution_method
        final.resolution_note = body.resolution_note if hasattr(body, 'resolution_note') else None
        final.resolved_by_reviewer_id = body.resolved_by_reviewer_id
        final.timestamp = datetime.utcnow()
        session.add(final)
    else:
        final = FinalDecision(
            project_id=project_id,
            paper_id=conflict.paper_id,
            phase=conflict.phase,
            decision=body.resolution,
            resolution_method=body.resolution_method,
            resolution_note=body.resolution_note if hasattr(body, 'resolution_note') else None,
            resolved_by_reviewer_id=body.resolved_by_reviewer_id,
        )
        session.add(final)

    session.commit()
    return {"status": "resolved", "final_decision": body.resolution}


def _require_paper(project_id: int, paper_id: int, session: Session) -> Paper:
    p = session.get(Paper, paper_id)
    if not p or p.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    return p


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
