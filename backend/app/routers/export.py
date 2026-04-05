from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlmodel import Session, select
from datetime import datetime
import json
import io

from app.database import get_session
from app.models import (
    Paper, ReviewerDecision, FinalDecision, ConflictLog,
    Reviewer, Project,
)

router = APIRouter(tags=["export"])


@router.get("/projects/{project_id}/export/decisions")
def export_decisions(
    project_id: int,
    reviewer_id: int,
    phase: str = "screening",
    session: Session = Depends(get_session),
):
    """
    Export a reviewer's decisions as a JSON file for sharing with co-reviewers.
    This is the primary collaboration artefact in the async exchange model.
    """
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    reviewer = session.get(Reviewer, reviewer_id)
    if not reviewer or reviewer.project_id != project_id:
        raise HTTPException(404, "Reviewer not found")

    decisions = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.reviewer_id == reviewer_id)
        .where(ReviewerDecision.phase == phase)
        .where(ReviewerDecision.project_id == project_id)
    ).all()

    papers = {p.id: p for p in session.exec(
        select(Paper).where(Paper.project_id == project_id)
    ).all()}

    payload = {
        "project_title": project.title,
        "project_id": project_id,
        "reviewer_name": reviewer.name,
        "reviewer_role": reviewer.role,
        "phase": phase,
        "export_timestamp": datetime.utcnow().isoformat(),
        "decisions": [
            {
                "paper_citekey": papers[d.paper_id].citekey if d.paper_id in papers else None,
                "phase": d.phase,
                "decision": d.decision,
                "criterion_label": d.criterion_label,
                "rationale": d.rationale,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
            }
            for d in decisions
            if d.paper_id in papers
        ],
    }

    content = json.dumps(payload, indent=2, ensure_ascii=False)
    filename = f"reviq_decisions_{reviewer.role}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"

    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/projects/{project_id}/export/bibtex")
def export_bibtex(
    project_id: int,
    phase: str = "screening",
    decision: str = "I",
    session: Session = Depends(get_session),
):
    """Export papers with a given final decision as a BibTeX file."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    included_final = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == phase)
        .where(FinalDecision.decision == decision)
    ).all()

    paper_ids = {f.paper_id for f in included_final}
    papers = [session.get(Paper, pid) for pid in paper_ids if session.get(Paper, pid)]

    lines = []
    for p in papers:
        entry_type = p.entry_type or "misc"
        lines.append(f"@{entry_type}{{{p.citekey},")
        if p.title:
            lines.append(f"  title = {{{p.title}}},")
        if p.authors:
            lines.append(f"  author = {{{p.authors}}},")
        if p.year:
            lines.append(f"  year = {{{p.year}}},")
        if p.doi:
            lines.append(f"  doi = {{{p.doi}}},")
        if p.venue:
            lines.append(f"  journal = {{{p.venue}}},")
        lines.append("}")
        lines.append("")

    content = "\n".join(lines)
    filename = f"reviq_selected_{phase}_{datetime.utcnow().strftime('%Y%m%d')}.bib"

    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/x-bibtex",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/projects/{project_id}/export/stats")
def export_stats(project_id: int, session: Session = Depends(get_session)):
    """Return PRISMA-compatible counts for the project."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    all_papers = session.exec(select(Paper).where(Paper.project_id == project_id)).all()
    originals = [p for p in all_papers if p.dedup_status == "original"]
    duplicates = [p for p in all_papers if p.dedup_status != "original"]

    screening_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "screening")
        .where(FinalDecision.decision == "I")
    ).all()

    screening_excluded = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "screening")
        .where(FinalDecision.decision == "E")
    ).all()

    fulltext_included = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "full-text")
        .where(FinalDecision.decision == "I")
    ).all()

    fulltext_excluded = session.exec(
        select(FinalDecision)
        .where(FinalDecision.project_id == project_id)
        .where(FinalDecision.phase == "full-text")
        .where(FinalDecision.decision == "E")
    ).all()

    open_conflicts = session.exec(
        select(ConflictLog)
        .where(ConflictLog.project_id == project_id)
        .where(ConflictLog.resolved == False)
    ).all()

    return {
        "total_retrieved": len(all_papers),
        "total_unique": len(originals),
        "total_duplicates": len(duplicates),
        "screening_included": len(screening_included),
        "screening_excluded": len(screening_excluded),
        "screening_undecided": len(originals) - len(screening_included) - len(screening_excluded),
        "fulltext_included": len(fulltext_included),
        "fulltext_excluded": len(fulltext_excluded),
        "open_conflicts": len(open_conflicts),
    }
