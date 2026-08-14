"""
Paper import — BibTeX for the formal stream, retrieval packages for the grey
one — and reviewer decision import.

**BibTeX** deduplicates in two tiers (see bibtex_service.detect_duplicates):
  1. DOI match (exact, case-insensitive) — high confidence
  2. Normalized title + venue match — catches DOI-less or inconsistent entries
Both tiers run against the existing paper pool in the DB, so importing a second
database's BibTeX will correctly flag cross-database duplicates.

**Grey literature** arrives as a `reviq-grey-v1` package (or the legacy
`glr-interchange-v1`) and deduplicates
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

from app.database import get_retrieval_conn, get_session
from app.models import (
    GreyFigure, GreyFigureDescription, GreyFullText, GreyImport, GreySource,
    Paper, Reviewer, ReviewerDecision,
)
from app.retrieval import db, interchange
from app.services import grey_service, paper_import
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

    outcome = paper_import.apply_entries(
        session, project_id, unique, duplicates,
        to_paper_dict=lambda entry: entry_to_paper_dict(entry, source=db_name),
    )
    session.commit()

    return {"db_name": db_name, **outcome.counts(len(entries))}


@router.post("/projects/{project_id}/import/grey")
async def import_grey_package(
    project_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Import a `reviq-grey-v1` package file into the grey stream.

    The path for a package from a co-reviewer, or from a retrieval made
    elsewhere. Retrieval run by this installation goes through
    `/import/grey/from-retrieval` below and needs no file at all — but this one
    stays: handing a colleague a corpus is a real thing to do, and the
    interchange format is how.

    Every record becomes a paper, including the ones that could not be
    retrieved. That is deliberate on both sides: the exporter includes them so a
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

    # No join keys. A package from elsewhere names documents by URL and digest;
    # its integer ids belonged to another database and mean nothing here.
    return _apply_grey_package(session, project_id, package,
                               filename=file.filename)


class RetrievalImport(BaseModel):
    """A run id or a batch id this installation retrieved itself."""
    scope_id: str


@router.post("/projects/{project_id}/import/grey/from-retrieval")
def import_grey_from_retrieval(
    project_id: int,
    body: RetrievalImport,
    session: Session = Depends(get_session),
    retrieval=Depends(get_retrieval_conn),
):
    """Import a retrieval this installation made, without the file detour.

    The primary path now that both halves live in one database. It builds the
    same `reviq-grey-v1` package the exporter writes and applies it through
    the same function the upload endpoint uses — the format is not bypassed,
    only the round trip through disk.

    Because the package is assembled from the very database it is imported
    into, the retrieval keys are known exactly rather than guessed from a URL,
    and each `GreySource` gets them. That is what turns "show me the archived
    text of this source" from re-parsing a package into a join.
    """
    _require_project(project_id, session)

    try:
        kind, run_ids = interchange.resolve_scope(retrieval, body.scope_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))

    package = interchange.build_package(retrieval, run_ids)
    package["scope"] = {"kind": kind, "id": body.scope_id}

    return _apply_grey_package(
        session, project_id, package,
        filename=f"{kind}:{body.scope_id}",
        locate=_retrieval_keys(retrieval, db.project_of_runs(retrieval, run_ids)),
    )


def _retrieval_keys(conn, project_id: int | None):
    """A lookup from canonical URL to (document_id, snapshot_id) in this database.

    The snapshot is resolved through `db.best_snapshot` with the same project
    scope the export used, so the row a `GreySource` points at is the row the
    package described. Resolving it any other way would let the stored keys and
    the stored digest describe two different retrievals.
    """
    def locate(canonical_url: str) -> tuple[int | None, int | None]:
        row = conn.execute(
            "SELECT document_id FROM documents WHERE canonical_url = ?",
            (canonical_url,),
        ).fetchone()
        if row is None:
            return None, None
        document_id = int(row["document_id"])
        snapshot = db.best_snapshot(conn, document_id, project_id)
        return document_id, (int(snapshot["snapshot_id"]) if snapshot else None)

    return locate


def _apply_grey_package(session: Session, project_id: int, package: dict, *,
                        filename: str | None, locate=None) -> dict:
    """Turn a parsed package into papers and provenance, and count what happened.

    One implementation for both entry points. The four outcomes below are where
    a PRISMA "records identified" and "duplicates removed" come from, and having
    the upload path and the internal path count them separately is precisely how
    two importers of the same thing ended up meaning different things by
    `detected_duplicates`.

    `locate` maps a canonical URL to this database's `(document_id,
    snapshot_id)`, or is None when the package came from elsewhere and there is
    nothing honest to fill them with.
    """
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
        **grey_service.package_metadata(package, filename=filename),
    )
    session.add(grey_import)
    session.commit()
    session.refresh(grey_import)

    # Four disjoint outcomes, and every record lands in exactly one. They have
    # to add up to the number of records in the package: this response is where
    # a PRISMA "records identified" and "duplicates removed" come from, and a
    # record that falls out of all of them cannot be reconciled by anyone
    # reading the diagram afterwards. An earlier version returned early for a
    # record already in the project without counting it anywhere, so re-importing
    # an overlapping package reported one record fewer than it had read.
    imported: list[str] = []
    duplicate_citekeys: list[str] = []
    already_present: list[str] = []
    skipped_no_citekey = 0
    unretrievable = 0

    for record, is_duplicate in [(r, False) for r in unique] + [(r, True) for r in duplicates]:
        data = grey_service.record_to_paper_dict(record, engine)
        if not data["citekey"]:
            skipped_no_citekey += 1
            continue
        if is_duplicate:
            # Anything other than "original" counts as a duplicate; no
            # back-reference, for the reason given on the BibTeX path above.
            data["dedup_status"] = "duplicate"

        # A citekey is derived from the canonical URL, so a collision here is
        # the same document arriving again — not a different one with the same
        # name. `partition` catches that for anything carrying a GreySource row;
        # this covers the rest, and is a separate outcome from a duplicate
        # *within* this package: the document was not newly identified at all,
        # so counting it as a removed duplicate would inflate that box.
        existing = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == data["citekey"])
        ).first()
        if existing:
            already_present.append(data["citekey"])
            continue

        paper = Paper(project_id=project_id, **data)
        session.add(paper)
        session.commit()
        session.refresh(paper)

        provenance = grey_service.record_to_provenance_dict(record)
        if locate is not None:
            document_id, snapshot_id = locate(provenance["canonical_url"])
            provenance["document_id"] = document_id
            provenance["snapshot_id"] = snapshot_id
        session.add(GreySource(
            project_id=project_id,
            paper_id=paper.id,
            grey_import_id=grey_import.id,
            **provenance,
        ))

        # The extracted text and the figures, if the package carried them. Both
        # are optional in the format — an export made with --no-text or from a
        # corpus retrieved before figures existed simply has neither — so their
        # absence is silence, not an error.
        fulltext = grey_service.record_to_fulltext_dict(record)
        if fulltext is not None:
            session.add(GreyFullText(
                project_id=project_id, paper_id=paper.id, **fulltext,
            ))

        for figure_fields, descriptions in grey_service.record_to_figure_dicts(record):
            figure = GreyFigure(
                project_id=project_id, paper_id=paper.id, **figure_fields,
            )
            session.add(figure)
            # Flushed rather than committed: the descriptions need the figure's
            # id, and committing per figure would make one import of a source
            # with twenty images twenty transactions.
            session.flush()
            for description in descriptions:
                session.add(GreyFigureDescription(
                    grey_figure_id=figure.id, **description,
                ))

        if is_duplicate:
            duplicate_citekeys.append(data["citekey"])
        else:
            imported.append(data["citekey"])
        if data["full_text_inaccessible"]:
            unretrievable += 1

    grey_import.imported_count = len(imported)
    grey_import.duplicate_count = len(duplicate_citekeys)
    grey_import.already_present_count = len(already_present)
    grey_import.skipped_count = skipped_no_citekey
    session.add(grey_import)
    session.commit()

    counts = package.get("counts") or {}
    return {
        "grey_import_id": grey_import.id,
        "engine": engine,
        "scope": package.get("scope"),
        "queries": len(package.get("runs") or []),
        # The four below partition this exactly. `test_the_four_outcomes_add_up`
        # holds them to it.
        "total_in_package": len(records),
        "imported_unique": len(imported),
        # Recognised as a duplicate *within this package* — a row was written
        # with dedup_status="duplicate", which is what a PRISMA "duplicates
        # removed" box counts.
        "imported_duplicates": len(duplicate_citekeys),
        # Already in the project from an earlier import. No row was written and
        # none should be: these were not newly identified, and folding them into
        # the duplicates above would inflate that box on every re-import.
        "already_present": len(already_present),
        "skipped_no_citekey": skipped_no_citekey,
        # Imported and not readable: identified by the search, excluded at the
        # retrieval stage rather than at screening. This is the number a PRISMA
        # "reports not retrieved" box wants, and the breakdown below is what
        # makes it defensible. Counts only records this import wrote a row for.
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
        "already_present_citekeys": already_present,
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


@router.get("/projects/{project_id}/retrievals")
def list_retrievals(project_id: int,
                    session: Session = Depends(get_session),
                    retrieval=Depends(get_retrieval_conn)):
    """The retrievals this project has made, as importable scopes.

    `/import/grey/from-retrieval` takes a run id or a batch id. Until now the
    only way to learn one was to read it off the CLI's output, which put a UUID
    between a user and their own corpus. This is what lets the interface offer
    the choice instead.

    Scoped to the project's own runs (D28). A shared installation's retrieval
    tables hold every project's corpus, and offering another review's runs here
    would let one project import the other's sources without either noticing.

    A batch is one entry, not one per run: `batch` issues a whole query set
    together and that set is the unit a methods section describes. Runs made
    outside a batch appear on their own.
    """
    _require_project(project_id, session)

    runs = retrieval.execute(
        """SELECT run_id, batch_id, query, engine, started_at_utc, status
           FROM runs WHERE project_id = ? ORDER BY started_at_utc""",
        (project_id,),
    ).fetchall()
    if not runs:
        return []

    # One grouped query rather than one per run. A batch of twenty queries is
    # ordinary, and this endpoint is called every time the import page opens.
    marks = ", ".join("?" for _ in runs)
    run_ids = [r["run_id"] for r in runs]
    counts = {
        row["run_id"]: row["n"]
        for row in retrieval.execute(
            f"""SELECT run_id, COUNT(DISTINCT document_id) AS n
                FROM serp_results WHERE run_id IN ({marks}) GROUP BY run_id""",
            run_ids,
        )
    }

    # Which scopes this project already took in. Recorded on `GreyImport`, so a
    # user is not offered a second import of the same batch without warning —
    # it would be counted as `already_present` and change nothing, but silently
    # doing nothing is worse than saying so.
    imported = {
        g.scope_id for g in session.exec(
            select(GreyImport).where(GreyImport.project_id == project_id)
        ).all() if g.scope_id
    }

    scopes: dict[tuple[str, str], dict] = {}
    for run in runs:
        kind, ident = (("batch", run["batch_id"]) if run["batch_id"]
                       else ("run", run["run_id"]))
        entry = scopes.setdefault((kind, ident), {
            "kind": kind, "scope_id": ident, "queries": [], "engines": set(),
            "started_at_utc": run["started_at_utc"], "documents": 0,
            "runs": 0, "incomplete": False,
        })
        entry["queries"].append(run["query"])
        entry["engines"].add(run["engine"])
        entry["documents"] += counts.get(run["run_id"], 0)
        entry["runs"] += 1
        # A batch whose last run died leaves a partial corpus. Importable, but
        # the number it contributes to "records identified" is not the number
        # the protocol asked for, and that belongs on screen.
        if run["status"] != "completed":
            entry["incomplete"] = True
        entry["started_at_utc"] = min(entry["started_at_utc"], run["started_at_utc"])

    return sorted(
        (
            {**e,
             "engines": sorted(e["engines"]),
             "already_imported": e["scope_id"] in imported}
            for e in scopes.values()
        ),
        key=lambda e: e["started_at_utc"],
        reverse=True,
    )


@router.get("/projects/{project_id}/papers/{paper_id}/grey-record")
def get_grey_record(project_id: int, paper_id: int,
                    session: Session = Depends(get_session)):
    """Everything held about one grey source: provenance, text, figures.

    One endpoint rather than three, because the three are read together and
    separately fetched halves are how a caller ends up rendering a full text
    without the status it was extracted under — which D31 forbids. `full_text`
    carries `retrieval_status` in the same object as `text`, so there is no
    shape of this response in which a consumer holds one and not the other.

    404 when the paper carries no `GreySource`: a formal paper has no retrieval
    to describe, and an empty envelope would invite a dataset view that renders
    blank fields as though the retrieval had simply found nothing.
    """
    _require_project(project_id, session)

    paper = session.get(Paper, paper_id)
    if not paper or paper.project_id != project_id:
        raise HTTPException(404, "Paper not found")

    source = session.exec(
        select(GreySource)
        .where(GreySource.project_id == project_id)
        .where(GreySource.paper_id == paper_id)
    ).first()
    if source is None:
        raise HTTPException(404, "This paper has no grey-literature provenance")

    full_text = session.exec(
        select(GreyFullText).where(GreyFullText.paper_id == paper_id)
    ).first()

    figures = session.exec(
        select(GreyFigure).where(GreyFigure.paper_id == paper_id)
    ).all()
    # Both queries are flat, not one per figure: a source may carry dozens of
    # images, and the listing beside this endpoint was already fixed for the
    # same reason.
    descriptions: dict[int, list[GreyFigureDescription]] = {}
    if figures:
        rows = session.exec(
            select(GreyFigureDescription)
            .where(GreyFigureDescription.grey_figure_id.in_([f.id for f in figures]))
        ).all()
        for row in rows:
            descriptions.setdefault(row.grey_figure_id, []).append(row)

    return {
        "paper_id": paper_id,
        "source": source,
        "full_text": full_text,
        "figures": [
            {**figure.model_dump(), "descriptions": descriptions.get(figure.id, [])}
            for figure in figures
        ],
    }


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

    # Disjoint outcomes again, and `unknown_citekey` is the one that matters
    # most here: without it, a decision file belonging to a different project
    # reports "0 decisions, 0 conflicts" — indistinguishable from a file that
    # had already been applied. A reviewer could not tell "nothing to do" from
    # "nothing matched".
    imported_count = 0
    updated_count = 0
    unknown_citekeys: list[str] = []
    skipped_incomplete = 0
    conflict_count = 0
    new_conflicts = []

    for dec in decisions_list:
        citekey = dec.get("paper_citekey")
        phase = dec.get("phase", "screening")
        decision = dec.get("decision")
        criterion_label = dec.get("criterion_label")
        rationale = dec.get("rationale")

        if not citekey or not decision:
            skipped_incomplete += 1
            continue

        paper = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == citekey)
        ).first()
        if not paper:
            unknown_citekeys.append(citekey)
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
            # Counted, unlike before. Re-importing a corrected file updated N
            # decisions and reported 0, which reads as "nothing happened" for
            # an operation that changed every one of them.
            updated_count += 1
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
        # These four partition the file exactly, so a reviewer can see where
        # every entry went. `test_the_decision_outcomes_add_up` holds them to it.
        "total_in_file": len(decisions_list),
        "imported_decisions": imported_count,
        "updated_decisions": updated_count,
        "unknown_citekey": len(unknown_citekeys),
        "skipped_incomplete": skipped_incomplete,
        # Capped: a file for the wrong project makes every entry unknown, and
        # the count already says so — the sample is for recognising *which*
        # project it belongs to.
        "unknown_citekeys": unknown_citekeys[:10],
        "new_conflicts_detected": conflict_count,
        "conflict_papers": new_conflicts,
    }


def _require_project(project_id: int, session: Session):
    from app.models import Project
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p
