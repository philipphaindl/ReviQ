"""
Paper import — BibTeX for the formal stream, glr packages for the grey one —
and reviewer decision import.

**BibTeX** deduplicates in two tiers (see bibtex_service.detect_duplicates):
  1. DOI match (exact, case-insensitive) — high confidence
  2. Normalized title + venue match — catches DOI-less or inconsistent entries
Both tiers run against the existing paper pool in the DB, so importing a second
database's BibTeX will correctly flag cross-database duplicates.

**Grey literature** arrives as a `glr-interchange-v1` package and deduplicates
on canonical URL and payload hash only — exact identities, never a title. The
reasoning is in `grey_service`; the short version is that a grey title is
whatever a page's `<title>` said and a false duplicate removes a source from a
review silently.

The two paths do not share a deduplication pool. A grey record carries no DOI
and its venue is a hostname, so neither BibTeX tier can recognise it, and a
grey copy of a formal paper is not detected as a duplicate of it. That is a
stated limitation rather than an oversight: over-inclusion is visible at
screening, silent exclusion is not.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
import json

from app.database import get_session
from app.models import Paper, ReviewerDecision, Reviewer, GreyImport, GreySource
from app.services import grey_service
from app.services.bibtex_service import parse_bib_content, detect_duplicates, entry_to_paper_dict
from app.services.decision_service import sync_decision_state

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
        # Anything other than "original" counts as a duplicate. Do not invent a
        # `duplicate_of:<citekey>` back-reference here: detect_duplicates does
        # not report which existing record matched, so the citekey would be a
        # fiction. Readers must test `!= "original"`, never a prefix.
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


@router.post("/projects/{project_id}/import/grey")
async def import_grey_package(
    project_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Import a `glr-interchange-v1` package into the grey literature stream.

    Every record becomes a paper, including the ones that could not be
    retrieved. That is deliberate on both sides: glr exports them so a
    consumer's "records identified" reconciles with its retrieval report, and a
    review that cannot say how much of its grey literature had rotted or sat
    behind a publisher's wall is hiding a limitation rather than not having
    one. They arrive with `full_text_inaccessible` set and their cause on the
    `GreySource` row, which is what lets those exclusions be reported by kind
    rather than as a single number.
    """
    _require_project(project_id, session)

    raw = await file.read()
    try:
        package = grey_service.parse_package(raw)
    except grey_service.GreyImportError as exc:
        raise HTTPException(400, str(exc))

    records = package["records"]
    engine = grey_service.engine_of(package)

    # Recognise against every grey source already in the project, whichever
    # package it came from: two packages for overlapping query sets return the
    # same document, and the second import must not create a second paper.
    known = session.exec(
        select(GreySource).where(GreySource.project_id == project_id)
    ).all()
    known_urls = {g.canonical_url.strip().lower() for g in known if g.canonical_url}
    known_hashes = {g.sha256.strip().lower() for g in known if g.sha256}

    unique, duplicates = grey_service.partition(records, known_urls, known_hashes)

    grey_import = GreyImport(
        project_id=project_id,
        **grey_service.package_metadata(package, filename=file.filename),
    )
    session.add(grey_import)
    session.commit()
    session.refresh(grey_import)

    imported: list[str] = []
    duplicate_citekeys: list[str] = []
    unretrievable = 0

    for record, is_duplicate in [(r, False) for r in unique] + [(r, True) for r in duplicates]:
        data = grey_service.record_to_paper_dict(record, engine)
        if not data["citekey"]:
            continue
        if is_duplicate:
            # Anything other than "original" counts as a duplicate; no
            # back-reference, for the reason given on the BibTeX path above.
            data["dedup_status"] = "duplicate"

        # A citekey is derived from the canonical URL, so a collision here is
        # the same document arriving again. `partition` has already caught that
        # for anything with a GreySource row; this covers the rest.
        existing = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == data["citekey"])
        ).first()
        if existing:
            continue

        paper = Paper(project_id=project_id, **data)
        session.add(paper)
        session.commit()
        session.refresh(paper)

        session.add(GreySource(
            project_id=project_id,
            paper_id=paper.id,
            grey_import_id=grey_import.id,
            **grey_service.record_to_provenance_dict(record),
        ))

        if is_duplicate:
            duplicate_citekeys.append(data["citekey"])
        else:
            imported.append(data["citekey"])
        if data["full_text_inaccessible"]:
            unretrievable += 1

    grey_import.imported_count = len(imported)
    grey_import.duplicate_count = len(duplicate_citekeys)
    session.add(grey_import)
    session.commit()

    counts = package.get("counts") or {}
    return {
        "grey_import_id": grey_import.id,
        "engine": engine,
        "scope": package.get("scope"),
        "queries": len(package.get("runs") or []),
        "total_in_package": len(records),
        "imported_unique": len(imported),
        "detected_duplicates": len(duplicate_citekeys),
        # Imported and not readable: identified by the search, excluded at the
        # retrieval stage rather than at screening. This is the number a PRISMA
        # "reports not retrieved" box wants, and the breakdown below is what
        # makes it defensible.
        "imported_unretrievable": unretrievable,
        "unretrievable_by_reason": grey_service.reason_breakdown(records),
        # The package's own totals, so a disagreement surfaces here rather than
        # in a finished diagram.
        "package_reported": {
            "documents": counts.get("documents"),
            "usable": counts.get("ok"),
        },
        "imported_citekeys": imported,
        "duplicate_citekeys": duplicate_citekeys,
    }


@router.get("/projects/{project_id}/grey-sources")
def list_grey_sources(project_id: int, session: Session = Depends(get_session)):
    """Retrieval provenance for the project's grey papers, joined on `paper_id`.

    Everything a grey citation needs that a `Paper` row has no column for: when
    the source was read, the digest of what was read, and where those bytes are
    archived.
    """
    _require_project(project_id, session)
    return session.exec(
        select(GreySource).where(GreySource.project_id == project_id)
    ).all()


@router.get("/projects/{project_id}/grey-imports")
def list_grey_imports(project_id: int, session: Session = Depends(get_session)):
    """The packages this project's grey literature came from."""
    _require_project(project_id, session)
    return session.exec(
        select(GreyImport).where(GreyImport.project_id == project_id)
    ).all()


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

        # Recompute final/conflict state via the shared state machine —
        # identical semantics to an interactive decision on this instance.
        status = sync_decision_state(session, project_id, paper.id, phase)
        if status == "conflict_opened":
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
