from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
import httpx

from app.database import get_session
from app.models import Paper, ReviewerDecision, FinalDecision, Reviewer

_CROSSREF_UA = "ReviQ/1.0 (SLR workbench; mailto:philipp.haindl@gmx.at)"

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


class VenueCategoryBody(BaseModel):
    venue: str
    category: Optional[str] = None  # None resets the override


@router.patch("/projects/{project_id}/papers/venue-category")
def set_venue_category(
    project_id: int,
    body: VenueCategoryBody,
    session: Session = Depends(get_session),
):
    """Bulk-set (or clear) venue_category_override for every paper whose venue matches."""
    _require_project(project_id, session)
    papers = session.exec(
        select(Paper)
        .where(Paper.project_id == project_id)
        .where(Paper.venue == body.venue)
    ).all()
    for p in papers:
        p.venue_category_override = body.category
        session.add(p)
    session.commit()
    return {"updated": len(papers)}


@router.post("/projects/{project_id}/papers/enrich-venues")
async def enrich_venues(
    project_id: int,
    session: Session = Depends(get_session),
):
    """Look up missing venue names via CrossRef for papers that have a DOI
    but no venue string.  Runs up to 10 requests concurrently so 400+
    papers complete in under 15 s.  Never overwrites existing venue data."""
    import asyncio

    _require_project(project_id, session)
    papers = session.exec(
        select(Paper)
        .where(Paper.project_id == project_id)
        .where(Paper.doi != None)   # noqa: E711
        .where(Paper.doi != "")
        .where((Paper.venue == None) | (Paper.venue == ""))  # noqa: E711
    ).all()

    candidates = {p.id: (p.doi or "").strip() for p in papers}
    found: dict[int, str] = {}

    sem = asyncio.Semaphore(10)   # polite pool: max 10 concurrent requests

    async def fetch_one(paper_id: int, doi: str) -> None:
        if not doi:
            return
        async with sem:
            try:
                async with httpx.AsyncClient(
                    headers={"User-Agent": _CROSSREF_UA}, timeout=8
                ) as client:
                    r = await client.get(f"https://api.crossref.org/works/{doi}")
                    if r.status_code != 200:
                        return
                    titles = r.json().get("message", {}).get("container-title", [])
                    if titles:
                        # Last title is the most specific (first may be a series name)
                        venue = titles[-1].strip()
                        if venue:
                            found[paper_id] = venue
            except Exception:
                pass

    await asyncio.gather(*[
        fetch_one(pid, doi) for pid, doi in candidates.items()
    ])

    updated = 0
    for paper in papers:
        venue = found.get(paper.id)
        if venue:
            paper.venue = venue
            session.add(paper)
            updated += 1

    session.commit()
    return {
        "updated": updated,
        "skipped": len(candidates) - updated,
        "total_candidates": len(candidates),
    }


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p
