"""
BibTeX import with cross-database deduplication, and reviewer decision import.

Deduplication uses a two-tier strategy (see bibtex_service.detect_duplicates):
  1. DOI match (exact, case-insensitive) — high confidence
  2. Normalized title + venue match — catches DOI-less or inconsistent entries
Both tiers run against the existing paper pool in the DB, so importing a second
database's BibTeX will correctly flag cross-database duplicates.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
import json

from app.database import get_session
from app.models import Paper, ReviewerDecision, ConflictLog, Reviewer
from app.services.bibtex_service import parse_bib_content, detect_duplicates, entry_to_paper_dict

router = APIRouter(tags=["import"])


@router.post("/projects/{project_id}/import/bib")
async def import_bib_file(
    project_id: int,
    db_name: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Import a BibTeX file for a given database name.
    Performs cross-database deduplication using DOIs and normalized title+venue.
    """
    _require_project(project_id, session)

    content = (await file.read()).decode("utf-8", errors="replace")
    entries = parse_bib_content(content)

    # Build dedup reference sets from papers already in the project.
    # Only "original" papers count — previously-detected duplicates are excluded
    # so they don't shadow legitimate new entries with the same title.
    existing_papers = session.exec(
        select(Paper).where(Paper.project_id == project_id).where(Paper.dedup_status == "original")
    ).all()
    existing_dois: set[str] = set()
    existing_title_venues: set[str] = set()
    for p in existing_papers:
        if p.doi:
            existing_dois.add(p.doi.strip().lower())
        if p.title:
            from app.services.bibtex_service import normalize_title
            tv = normalize_title(p.title) + "__" + normalize_title(p.venue or "")
            existing_title_venues.add(tv)

    unique, duplicates, _, _ = detect_duplicates(entries, existing_dois, existing_title_venues)

    imported = []
    duplicate_records = []

    for entry in unique:
        data = entry_to_paper_dict(entry, source=db_name)
        if not data["citekey"] or not data["title"]:
            continue
        # Avoid re-importing same citekey
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
        data = entry_to_paper_dict(entry, source=db_name)
        data["dedup_status"] = "duplicate"
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
        duplicate_records.append(data["citekey"])

    session.commit()

    return {
        "db_name": db_name,
        "total_in_file": len(entries),
        "imported_unique": len(imported),
        "detected_duplicates": len(duplicate_records),
        "imported_citekeys": imported,
        "duplicate_citekeys": duplicate_records,
    }


@router.get("/projects/{project_id}/import/stats")
def import_stats(project_id: int, session: Session = Depends(get_session)):
    """Per-database counts: total retrieved, originals, duplicates."""
    _require_project(project_id, session)

    papers = session.exec(select(Paper).where(Paper.project_id == project_id)).all()

    stats: dict[str, dict] = {}
    for p in papers:
        src = p.source
        if src not in stats:
            stats[src] = {"total": 0, "original": 0, "duplicate": 0}
        stats[src]["total"] += 1
        if p.dedup_status == "original":
            stats[src]["original"] += 1
        else:
            stats[src]["duplicate"] += 1

    return {
        "by_source": stats,
        "total_papers": len(papers),
        "total_original": sum(1 for p in papers if p.dedup_status == "original"),
        "total_duplicates": sum(1 for p in papers if p.dedup_status != "original"),
    }


@router.get("/projects/{project_id}/import/duplicates")
def list_duplicates(project_id: int, session: Session = Depends(get_session)):
    """List all papers flagged as duplicates."""
    _require_project(project_id, session)
    dupes = session.exec(
        select(Paper)
        .where(Paper.project_id == project_id)
        .where(Paper.dedup_status != "original")
    ).all()
    return dupes


@router.post("/projects/{project_id}/papers/{paper_id}/override-dedup")
def override_dedup(project_id: int, paper_id: int, session: Session = Depends(get_session)):
    """Mark a duplicate paper as original (manual override)."""
    p = session.get(Paper, paper_id)
    if not p or p.project_id != project_id:
        raise HTTPException(404, "Paper not found")
    p.dedup_status = "original"
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@router.post("/projects/{project_id}/import/reviewer-decisions")
async def import_reviewer_decisions(
    project_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Import a reviewer decision JSON file exported by another reviewer.
    Detects conflicts with existing decisions.
    """
    _require_project(project_id, session)

    content = (await file.read()).decode("utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    # Validate structure
    required_keys = {"reviewer_name", "decisions"}
    if not required_keys.issubset(data.keys()):
        raise HTTPException(400, "Missing required fields: reviewer_name, decisions")

    reviewer_name: str = data["reviewer_name"]
    reviewer_role: str = data.get("reviewer_role", "R2")
    decisions_list: list = data.get("decisions", [])
    source_file: str = file.filename or "imported"

    # Find or create reviewer
    reviewer = session.exec(
        select(Reviewer)
        .where(Reviewer.project_id == project_id)
        .where(Reviewer.name == reviewer_name)
    ).first()
    if not reviewer:
        reviewer = Reviewer(project_id=project_id, name=reviewer_name, role=reviewer_role)
        session.add(reviewer)
        session.commit()
        session.refresh(reviewer)

    imported_count = 0
    conflict_count = 0
    new_conflicts = []

    for dec in decisions_list:
        citekey = dec.get("paper_citekey")
        phase = dec.get("phase", "screening")
        decision = dec.get("decision")
        criterion_label = dec.get("criterion_label")
        rationale = dec.get("rationale")

        if not citekey or not decision:
            continue

        paper = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == citekey)
        ).first()
        if not paper:
            continue

        # Upsert: if reviewer already has a decision, update it
        existing_dec = session.exec(
            select(ReviewerDecision)
            .where(ReviewerDecision.paper_id == paper.id)
            .where(ReviewerDecision.reviewer_id == reviewer.id)
            .where(ReviewerDecision.phase == phase)
        ).first()

        from datetime import datetime
        if existing_dec:
            existing_dec.decision = decision
            existing_dec.criterion_label = criterion_label
            existing_dec.rationale = rationale
            existing_dec.timestamp = datetime.utcnow()
            existing_dec.source_file = source_file
            session.add(existing_dec)
        else:
            new_dec = ReviewerDecision(
                project_id=project_id,
                paper_id=paper.id,
                reviewer_id=reviewer.id,
                phase=phase,
                decision=decision,
                criterion_label=criterion_label,
                rationale=rationale,
                source_file=source_file,
            )
            session.add(new_dec)
            imported_count += 1

        # Check conflicts with R1 (first reviewer)
        r1 = session.exec(
            select(Reviewer)
            .where(Reviewer.project_id == project_id)
            .where(Reviewer.role == "R1")
        ).first()
        if r1 and r1.id != reviewer.id:
            r1_dec = session.exec(
                select(ReviewerDecision)
                .where(ReviewerDecision.paper_id == paper.id)
                .where(ReviewerDecision.reviewer_id == r1.id)
                .where(ReviewerDecision.phase == phase)
            ).first()
            if r1_dec and r1_dec.decision != decision:
                # Check if conflict already logged
                existing_conflict = session.exec(
                    select(ConflictLog)
                    .where(ConflictLog.paper_id == paper.id)
                    .where(ConflictLog.phase == phase)
                    .where(ConflictLog.resolved == False)
                ).first()
                if not existing_conflict:
                    conflict = ConflictLog(
                        project_id=project_id,
                        paper_id=paper.id,
                        phase=phase,
                        r1_reviewer_id=r1.id,
                        r2_reviewer_id=reviewer.id,
                        r1_decision=r1_dec.decision,
                        r2_decision=decision,
                        r1_rationale=r1_dec.rationale,
                        r2_rationale=rationale,
                    )
                    session.add(conflict)
                    conflict_count += 1
                    new_conflicts.append(citekey)

    session.commit()

    return {
        "reviewer_name": reviewer_name,
        "imported_decisions": imported_count,
        "new_conflicts_detected": conflict_count,
        "conflict_papers": new_conflicts,
    }


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p
