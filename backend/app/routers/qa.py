"""
Quality Assessment scoring and summary endpoints.

QA scores use a 3-point scale (0.0 / 0.5 / 1.0) per criterion per paper.
The summary endpoint computes aggregate quality levels (high/medium/low)
using project-level thresholds.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from app.database import get_session
from app.models import Paper, QACriterion, QAScore, FinalDecision, Reviewer

router = APIRouter(tags=["qa"])


class QAScoreUpsert(BaseModel):
    reviewer_id: int
    criterion_id: int
    score: float          # 0.0, 0.5, or 1.0
    rationale: Optional[str] = None


@router.get("/projects/{project_id}/qa-scores")
def list_qa_scores(project_id: int, session: Session = Depends(get_session)):
    """All QA scores for a project, grouped by paper."""
    scores = session.exec(
        select(QAScore).where(QAScore.project_id == project_id)
    ).all()
    return scores


@router.get("/projects/{project_id}/papers/{paper_id}/qa-scores")
def get_paper_qa_scores(project_id: int, paper_id: int, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper or paper.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    scores = session.exec(
        select(QAScore).where(QAScore.paper_id == paper_id)
    ).all()
    return scores


@router.post("/projects/{project_id}/papers/{paper_id}/qa-scores")
def upsert_qa_score(
    project_id: int,
    paper_id: int,
    body: QAScoreUpsert,
    session: Session = Depends(get_session),
):
    paper = session.get(Paper, paper_id)
    if not paper or paper.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    reviewer = session.get(Reviewer, body.reviewer_id)
    if not reviewer or reviewer.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")
    criterion = session.get(QACriterion, body.criterion_id)
    if not criterion or criterion.project_id != project_id:
        raise HTTPException(404, "QA criterion not found")
    if body.score not in (0.0, 0.5, 1.0):
        raise HTTPException(400, "Score must be 0.0, 0.5, or 1.0")

    existing = session.exec(
        select(QAScore)
        .where(QAScore.paper_id == paper_id)
        .where(QAScore.criterion_id == body.criterion_id)
        .where(QAScore.scored_by_reviewer_id == body.reviewer_id)
    ).first()

    if existing:
        existing.score = body.score
        existing.rationale = body.rationale
        session.add(existing)
    else:
        session.add(QAScore(
            project_id=project_id,
            paper_id=paper_id,
            criterion_id=body.criterion_id,
            score=body.score,
            rationale=body.rationale,
            scored_by_reviewer_id=body.reviewer_id,
        ))
    session.commit()
    return {"status": "ok"}


@router.get("/projects/{project_id}/qa-summary")
def qa_summary(
    project_id: int,
    reviewer_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """
    Returns all QA-eligible papers (included from full-text or screening)
    with their scores and computed quality level.

    With ``reviewer_id`` the scores are that reviewer's own; without it each
    criterion is averaged across all reviewers who scored it, so no single
    reviewer's value silently overwrites a co-reviewer's.
    """
    criteria = session.exec(
        select(QACriterion).where(QACriterion.project_id == project_id)
    ).all()
    max_total = sum(c.max_score for c in criteria)

    # Per SLR methodology (Kitchenham & Charters 2007):
    # QA-eligible papers = full-text included (Phase 4) + snowballing included (Phase 5)
    # If no full-text decisions exist, fall back to all screening-included (Phase 3).
    ft_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "full-text")
        .where(FinalDecision.decision == "I")
    ).all()
    screening_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "screening")
        .where(FinalDecision.decision == "I")
    ).all()

    if ft_included:
        # Per Wohlin (2014): snowballing papers must go through the same full-text
        # eligibility assessment as database papers. They appear here only after
        # receiving an 'I' (Include) full-text decision in Phase 4.
        eligible_paper_ids = [d.paper_id for d in ft_included]
    else:
        eligible_paper_ids = [d.paper_id for d in screening_included]

    all_scores = session.exec(
        select(QAScore).where(QAScore.project_id == project_id)
    ).all()
    if reviewer_id is not None:
        all_scores = [s for s in all_scores if s.scored_by_reviewer_id == reviewer_id]

    from app.models import Project
    proj = session.get(Project, project_id)
    high_t = proj.qa_high_threshold if proj else 75.0
    med_t  = proj.qa_medium_threshold if proj else 50.0

    result = []
    for pid in eligible_paper_ids:
        paper = session.get(Paper, pid)
        if not paper:
            continue
        # Average per criterion across the scores in scope. Reviewer-scoped
        # calls see at most one score per criterion (upsert-unique), so the
        # mean is that reviewer's own value.
        by_criterion: dict[int, list[float]] = {}
        for s in all_scores:
            if s.paper_id == pid:
                by_criterion.setdefault(s.criterion_id, []).append(s.score)
        scored = {cid: sum(vals) / len(vals) for cid, vals in by_criterion.items()}
        total = sum(scored.get(c.id, 0.0) for c in criteria)
        pct = (total / max_total * 100) if max_total > 0 else 0

        level = "high" if pct >= high_t else "medium" if pct >= med_t else "low"

        scored_criteria = sum(1 for c in criteria if c.id in scored)
        result.append({
            "paper_id": pid,
            "paper_title": paper.title,
            "paper_authors": paper.authors,
            "paper_year": paper.year,
            "paper_source": paper.source,
            "scores": [{"criterion_id": c.id, "label": c.label, "description": c.description,
                         "max_score": c.max_score, "score": scored.get(c.id)} for c in criteria],
            "total_score": round(total, 2),
            "max_score": round(max_total, 2),
            "percentage": round(pct, 1),
            "quality_level": level,
            "fully_scored": scored_criteria == len(criteria) and len(criteria) > 0,
        })

    result.sort(key=lambda x: x["percentage"], reverse=True)
    return {"criteria": [{"id": c.id, "label": c.label, "description": c.description,
                           "max_score": c.max_score} for c in criteria],
            "papers": result,
            "max_total": round(max_total, 2)}
