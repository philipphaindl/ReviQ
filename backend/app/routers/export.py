"""
Export endpoints: reviewer decisions (JSON), selected papers (BibTeX),
PRISMA-compatible statistics, and per-database search metrics.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlmodel import Session, select
from datetime import datetime
import json
import io

from app.database import get_session
from app.models import (
    Paper, ReviewerDecision, FinalDecision, ConflictLog,
    Reviewer, Project, DatabaseSearchString, PaperDatabaseLink,
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


# Canonical key aliases — mirrors the frontend's normalizeDbKey
_DB_ALIASES: dict[str, str] = {
    "springer": "springerlink",
    "springer link": "springerlink",
    "springerlink": "springerlink",
    "ieee xplore": "ieee",
    "ieee explore": "ieee",
    "ieee": "ieee",
    "scopus": "scopus",
    "elsevier": "scopus",
    "elsevier scopus": "scopus",
    "acm": "acm",
    "acm digital library": "acm",
    "wiley": "wiley",
    "wiley online library": "wiley",
    "dblp": "dblp",
    "dblp library": "dblp",
}


def _normalize_db_key(raw: str) -> str:
    return _DB_ALIASES.get(raw.lower().strip(), raw.lower().strip())


@router.get("/projects/{project_id}/export/search-metrics")
def search_metrics(project_id: int, session: Session = Depends(get_session)):
    """Per-database search metrics: precision (yield), relative recall, F1."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    search_strings = session.exec(
        select(DatabaseSearchString).where(DatabaseSearchString.project_id == project_id)
    ).all()

    all_papers = session.exec(
        select(Paper).where(Paper.project_id == project_id)
    ).all()

    # Papers with a final full-text inclusion decision
    included_paper_ids = {
        d.paper_id for d in session.exec(
            select(FinalDecision)
            .where(FinalDecision.project_id == project_id)
            .where(FinalDecision.phase == "full-text")
            .where(FinalDecision.decision == "I")
        ).all()
    }
    total_included = len(included_paper_ids)

    # Check if PaperDatabaseLink entries exist (multi-source tracking)
    db_links = session.exec(
        select(PaperDatabaseLink).where(PaperDatabaseLink.project_id == project_id)
    ).all()
    use_links = len(db_links) > 0

    # Build link lookup: canonical_key -> set of paper_ids found by that DB
    link_map: dict[str, set[int]] = {}
    if use_links:
        for link in db_links:
            canonical = _normalize_db_key(link.db_name)
            link_map.setdefault(canonical, set()).add(link.paper_id)

    # Build a map: canonical_key -> results_count (from search protocol)
    db_results_count: dict[str, int | None] = {}
    for ss in search_strings:
        if ss.db_name:
            canonical = _normalize_db_key(ss.db_name)
            if canonical not in db_results_count:
                db_results_count[canonical] = ss.results_count

    rows = []
    for canonical_name, results_count in db_results_count.items():
        # Match papers whose source normalizes to this canonical key
        db_papers = [
            p for p in all_papers
            if _normalize_db_key(p.source) == canonical_name and p.dedup_status == "original"
        ]
        imported = len(db_papers)

        if use_links:
            # Use link table: count included papers that were found by this DB
            linked_pids = link_map.get(canonical_name, set())
            included_from_db = len(linked_pids & included_paper_ids)
        else:
            # Fallback: only count papers whose primary source matches
            included_from_db = sum(1 for p in db_papers if p.id in included_paper_ids)

        # Prefer results_count from search protocol over imported count as denominator
        retrieved = results_count if results_count is not None else imported

        precision = included_from_db / retrieved if retrieved > 0 else 0.0
        # "relative" recall — true population unknown, using union of included as reference
        relative_recall = included_from_db / total_included if total_included > 0 else 0.0
        denom = precision + relative_recall
        f1 = (2 * precision * relative_recall / denom) if denom > 0 else 0.0

        rows.append({
            "db_name": canonical_name,
            "results_count": results_count,
            "imported": imported,
            "included": included_from_db,
            "precision": round(precision, 4),
            "relative_recall": round(relative_recall, 4),
            "f1": round(f1, 4),
        })

    rows.sort(key=lambda x: x["db_name"])
    return {"total_included": total_included, "databases": rows}
