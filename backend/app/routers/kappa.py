from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional

from app.database import get_session
from app.models import Paper, ReviewerDecision, FinalDecision, Reviewer
from app.services.kappa_service import calculate_kappa

router = APIRouter(tags=["kappa"])


@router.get("/projects/{project_id}/kappa")
def get_kappa(
    project_id: int,
    phase: str = Query("screening"),
    r1_id: Optional[int] = Query(None),
    r2_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
):
    """
    Calculate Cohen's κ between two reviewers for a given phase.

    The Kappa sample follows Kitchenham & Charters: all included papers
    + all uncertain + a stratified sample of excluded. In practice, we
    calculate on all papers where both reviewers have made a decision.

    If r1_id/r2_id not supplied, defaults to the two lowest-role reviewers.
    """
    _require_project(project_id, session)

    reviewers = session.exec(
        select(Reviewer).where(Reviewer.project_id == project_id).order_by(Reviewer.id)
    ).all()
    if len(reviewers) < 2:
        raise HTTPException(400, "At least 2 reviewers needed for Kappa calculation")

    # Resolve reviewer IDs
    if not r1_id:
        r1_id = reviewers[0].id
    if not r2_id:
        r2_id = reviewers[1].id

    r1_decisions_raw = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.reviewer_id == r1_id)
        .where(ReviewerDecision.phase == phase)
        .where(ReviewerDecision.project_id == project_id)
    ).all()

    r2_decisions_raw = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.reviewer_id == r2_id)
        .where(ReviewerDecision.phase == phase)
        .where(ReviewerDecision.project_id == project_id)
    ).all()

    r1_map = {str(d.paper_id): d.decision for d in r1_decisions_raw}
    r2_map = {str(d.paper_id): d.decision for d in r2_decisions_raw}

    result = calculate_kappa(r1_map, r2_map)
    if result is None:
        raise HTTPException(400, "No papers with decisions from both reviewers")

    r1_reviewer = session.get(Reviewer, r1_id)
    r2_reviewer = session.get(Reviewer, r2_id)

    return {
        **result.__dict__,
        "r1_name": r1_reviewer.name if r1_reviewer else str(r1_id),
        "r2_name": r2_reviewer.name if r2_reviewer else str(r2_id),
        "phase": phase,
    }


@router.get("/projects/{project_id}/kappa/all-pairs")
def get_kappa_all_pairs(
    project_id: int,
    phase: str = Query("screening"),
    session: Session = Depends(get_session),
):
    """Calculate κ for all reviewer pairs (C6 requirement)."""
    _require_project(project_id, session)

    reviewers = session.exec(
        select(Reviewer).where(Reviewer.project_id == project_id).order_by(Reviewer.id)
    ).all()

    results = []
    for i in range(len(reviewers)):
        for j in range(i + 1, len(reviewers)):
            r1, r2 = reviewers[i], reviewers[j]
            r1_decs = session.exec(
                select(ReviewerDecision)
                .where(ReviewerDecision.reviewer_id == r1.id)
                .where(ReviewerDecision.phase == phase)
                .where(ReviewerDecision.project_id == project_id)
            ).all()
            r2_decs = session.exec(
                select(ReviewerDecision)
                .where(ReviewerDecision.reviewer_id == r2.id)
                .where(ReviewerDecision.phase == phase)
                .where(ReviewerDecision.project_id == project_id)
            ).all()
            r1_map = {str(d.paper_id): d.decision for d in r1_decs}
            r2_map = {str(d.paper_id): d.decision for d in r2_decs}
            kappa_result = calculate_kappa(r1_map, r2_map)
            if kappa_result:
                results.append({
                    **kappa_result.__dict__,
                    "r1_name": r1.name,
                    "r2_name": r2.name,
                    "phase": phase,
                })

    return results


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
