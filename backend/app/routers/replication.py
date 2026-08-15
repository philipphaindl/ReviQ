"""
Replication package export / import  (reviq-replication-v2)

ZIP layout:
  project.json          – full SLR data in reviq-replication-v2 schema
  bibtex/
    <db_name>.bib       – one raw results file per database search string
  archives/<run_id>/*   – WARC files, only when exported with --with-archive

v2 adds the grey-literature side: `grey_sources`, `grey_imports`, and the
retrieval rows behind them (`retrieval` — runs, documents, snapshots, and so
on, scoped to this project's own runs — a run belongs to a review). v1
exported papers only, which
silently dropped a grey paper's provenance — the SHA-256, the archive pointer,
the retrieval timestamp — everything that makes it a citable grey source
rather than just a URL. A v1 package still imports; its papers arrive without
that provenance, exactly as before.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..database import (
    MLR_METHODOLOGY, RetrievalDatabaseUnavailable, WRONG_MLR_METHODOLOGY,
    get_session, retrieval_db_path,
)
from ..models import (
    ConflictLog, DatabaseSearchString, ExclusionCriterion, ExtractionField,
    ExtractionRecord, FinalDecision, GreyImport, GreySource, InclusionCriterion,
    Paper, PaperDatabaseLink, Project, QACriterion, QAScore, Reviewer,
    ReviewerDecision, SnowballingIteration, TaxonomyEntry,
)
from ..retrieval import adopt as retrieval_adopt
from ..retrieval import db as retrieval_db

router = APIRouter(prefix="/projects", tags=["replication"])

SCHEMA_VERSION = "reviq-replication-v2"

# Dependency order: every table after the ones it points at, so the retrieval
# schema's foreign keys (PRAGMA foreign_keys = ON) hold at each insert.
RETRIEVAL_TABLES = (
    "runs", "documents", "serp_results", "snapshots", "extractions",
    "extraction_history", "document_links", "figures", "figure_descriptions",
)

# Paper fields carried through an import. Derived from the model so that adding
# a column does not silently drop it from every replication package; the three
# excluded fields are re-assigned per import (identity and insert time).
PAPER_IMPORT_FIELDS = [
    f for f in Paper.model_fields if f not in {"id", "project_id", "created_at"}
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _row(obj) -> dict:
    """SQLModel → plain dict (excludes SQLAlchemy private attributes)."""
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def _runs_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data")) / "runs"


def _optional_retrieval_conn():
    """Like `app.database.get_retrieval_conn`, but yields None instead of
    raising when the retrieval side is not reachable — an in-memory
    `DATABASE_URL`, or a `DATA_DIR` this process cannot write to. The
    grey-literature side of a replication package is additive: a package with
    no grey papers, or built against a deployment where retrieval genuinely
    cannot open, is still a valid package for everything else in it.
    """
    try:
        path = retrieval_db_path()
        conn = retrieval_db.connect(path)
    except (RetrievalDatabaseUnavailable, OSError):
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


def _select_in(conn: sqlite3.Connection, table: str, column: str,
               values) -> list[dict]:
    """`SELECT * FROM table WHERE column IN (values)`, as plain dicts.

    `values` is checked for emptiness first: SQLite has no empty `IN ()`, and
    the values a caller here passes are usually the very set that has already
    been proven possibly-empty (a project with grey papers but no snapshots).
    """
    values = list(values)
    if not values:
        return []
    marks = ", ".join("?" for _ in values)
    return [dict(r) for r in
            conn.execute(f"SELECT * FROM {table} WHERE {column} IN ({marks})", values)]


def _export_retrieval(retrieval: Optional[sqlite3.Connection], pid: int) -> Optional[dict]:
    """The retrieval rows behind this project's grey sources.

    Scoped to `runs.project_id = pid` — a run belongs to a review, a document
    belongs to nobody. `retrieval` is one shared file across every
    project on this installation, and copying documents wholesale would leak
    another project's corpus into this one's package.

    Returns None when the retrieval side is not reachable at all, or when this
    project issued no runs of its own — the case for a project whose grey
    papers arrived as a package from a co-reviewer, with no local retrieval
    to export.
    """
    if retrieval is None:
        return None
    run_rows = [dict(r) for r in
                retrieval.execute("SELECT * FROM runs WHERE project_id = ?", (pid,))]
    if not run_rows:
        return None
    run_ids = [r["run_id"] for r in run_rows]

    serp_results = _select_in(retrieval, "serp_results", "run_id", run_ids)
    snapshots = _select_in(retrieval, "snapshots", "run_id", run_ids)
    extractions = _select_in(retrieval, "extractions", "snapshot_id",
                             [r["snapshot_id"] for r in snapshots])
    # Scoped like `adopt.SPECS` scopes it: by the run that superseded the
    # extraction, not the run that produced the snapshot it belongs to.
    extraction_history = _select_in(retrieval, "extraction_history",
                                    "superseded_by_run", run_ids)
    document_links = _select_in(retrieval, "document_links", "run_id", run_ids)
    figures = _select_in(retrieval, "figures", "run_id", run_ids)
    figure_descriptions = _select_in(retrieval, "figure_descriptions", "figure_id",
                                     [r["figure_id"] for r in figures])

    document_ids = {r["document_id"] for r in serp_results if r["document_id"]}
    document_ids.update(r["document_id"] for r in snapshots)
    document_ids.update(r["document_id"] for r in figures)
    for r in document_links:
        document_ids.add(r["from_document_id"])
        document_ids.add(r["to_document_id"])
    documents = _select_in(retrieval, "documents", "document_id", document_ids)

    return {
        "runs": run_rows, "documents": documents, "serp_results": serp_results,
        "snapshots": snapshots, "extractions": extractions,
        "extraction_history": extraction_history,
        "document_links": document_links, "figures": figures,
        "figure_descriptions": figure_descriptions,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{pid}/replication/export")
def export_replication_package(
    pid: int,
    with_archive: bool = Query(False, description=(
        "Bundle the WARC files behind this project's grey sources into the "
        "ZIP. Off by default: a few hundred megabytes for one batch. Without "
        "it, snapshots and figures still carry their SHA-256 and archive "
        "path — a citation, not the bytes — and the recipient's own installation "
        "can supply the archive if it happens to hold it."
    )),
    session: Session = Depends(get_session),
    retrieval: Optional[sqlite3.Connection] = Depends(_optional_retrieval_conn),
):
    project = session.get(Project, pid)
    if not project:
        raise HTTPException(404, "Project not found")

    def q(model):
        return session.exec(select(model).where(model.project_id == pid)).all()

    reviewers         = q(Reviewer)
    inc_criteria      = q(InclusionCriterion)
    exc_criteria      = q(ExclusionCriterion)
    qa_criteria       = q(QACriterion)
    taxonomy          = q(TaxonomyEntry)
    ext_fields        = q(ExtractionField)
    ext_records       = q(ExtractionRecord)
    search_strings    = q(DatabaseSearchString)
    papers            = q(Paper)
    rev_decisions     = q(ReviewerDecision)
    final_decisions   = q(FinalDecision)
    conflict_log      = q(ConflictLog)
    qa_scores         = q(QAScore)
    snow_iterations   = q(SnowballingIteration)
    db_links          = q(PaperDatabaseLink)
    grey_sources      = q(GreySource)
    grey_imports      = q(GreyImport)
    retrieval_pkg     = _export_retrieval(retrieval, pid)

    # Map db_name → path inside the ZIP
    bib_zip_paths: dict[str, str] = {}
    for ss in search_strings:
        if ss.db_name and ss.db_name not in bib_zip_paths:
            bib_zip_paths[ss.db_name] = f"bibtex/{_safe_name(ss.db_name.lower())}.bib"

    pkg = {
        "_schema":      SCHEMA_VERSION,
        "_exported_at": datetime.utcnow().isoformat() + "Z",
        "project":      _row(project),
        "reviewers":    [_row(r) for r in reviewers],
        "inclusion_criteria":  [_row(c) for c in inc_criteria],
        "exclusion_criteria":  [_row(c) for c in exc_criteria],
        "qa_criteria":         [_row(c) for c in qa_criteria],
        "taxonomy":            [_row(t) for t in taxonomy],
        "extraction_fields":   [_row(f) for f in ext_fields],
        "extraction_records":  [_row(r) for r in ext_records],
        "search_strings": [
            {**_row(ss), "bibtex_file": bib_zip_paths.get(ss.db_name)}
            for ss in search_strings
        ],
        "papers":            [_row(p) for p in papers],
        "reviewer_decisions": [_row(d) for d in rev_decisions],
        "final_decisions":    [_row(d) for d in final_decisions],
        "conflict_log":       [_row(c) for c in conflict_log],
        "qa_scores":          [_row(s) for s in qa_scores],
        "snowballing_iterations": [_row(it) for it in snow_iterations],
        "paper_database_links":   [_row(l) for l in db_links],
        "grey_sources":           [_row(g) for g in grey_sources],
        "grey_imports":           [_row(g) for g in grey_imports],
        "retrieval":              retrieval_pkg,
    }

    # Build the ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(pkg, indent=2, default=str))

        if with_archive and retrieval_pkg:
            runs_dir = _runs_dir()
            for run_id in {r["run_id"] for r in retrieval_pkg["runs"]}:
                run_dir = runs_dir / run_id
                if not run_dir.is_dir():
                    continue
                for fname in os.listdir(run_dir):
                    fpath = run_dir / fname
                    if fpath.is_file():
                        zf.write(fpath, f"archives/{run_id}/{fname}")

        bib_base = os.environ.get("BIB_BASE_DIR", "/bib_data")
        data_dir = os.environ.get("DATA_DIR", "/data")
        bib_import_dir = os.path.join(data_dir, "bib_data")
        included_bib_files: set[str] = set()

        # Two-pass BibTeX file discovery:
        # Pass 1: For each database in the search protocol, look for a matching
        #   .bib file by sanitised name in both BIB_BASE_DIR (Docker mount) and
        #   DATA_DIR/bib_data (writable volume from previous imports).
        # Pass 2: Sweep both directories for any .bib files not already included
        #   — catches manually-added files or those with non-standard names.
        # First pass: match bib files by db_name
        for db_name, zip_path in bib_zip_paths.items():
            safe = _safe_name(db_name.lower())
            candidates = [
                os.path.join(bib_base, f"{safe}.bib"),
                os.path.join(bib_base, f"{db_name}.bib"),
                os.path.join(bib_base, f"{db_name.lower()}.bib"),
                os.path.join(bib_import_dir, f"{safe}.bib"),
                os.path.join(bib_import_dir, f"{db_name}.bib"),
                os.path.join(bib_import_dir, f"{db_name.lower()}.bib"),
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    with open(cand, "rb") as fh:
                        zf.writestr(zip_path, fh.read())
                    included_bib_files.add(os.path.basename(cand))
                    break

        # Second pass: include any remaining .bib files not yet added
        for bib_dir in [bib_base, bib_import_dir]:
            if not os.path.isdir(bib_dir):
                continue
            for fname in os.listdir(bib_dir):
                if fname.endswith(".bib") and fname not in included_bib_files:
                    fpath = os.path.join(bib_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "rb") as fh:
                            zf.writestr(f"bibtex/{fname}", fh.read())
                        included_bib_files.add(fname)

    buf.seek(0)
    filename = f"reviq_replication_{_safe_name(project.title)}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# IMPORT
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/replication/import")
def import_replication_package(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    retrieval: Optional[sqlite3.Connection] = Depends(_optional_retrieval_conn),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Expected a .zip file")

    # Sync, not async, on purpose: FastAPI runs a sync endpoint and all of its
    # sync dependencies (`retrieval` above) in the same worker thread. An
    # `async def` here would resolve `retrieval` in a thread pool and then run
    # this body on the event loop's own thread — a different thread — and
    # sqlite3 refuses a connection used outside the thread that opened it.
    raw = file.file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Invalid zip file")

    if "project.json" not in zf.namelist():
        raise HTTPException(400, "Missing project.json in zip")

    pkg = json.loads(zf.read("project.json"))
    if not pkg.get("_schema", "").startswith("reviq-replication"):
        raise HTTPException(400, f"Unknown schema: {pkg.get('_schema')}")

    # ── Project ───────────────────────────────────────────────────────────────
    pd = {k: v for k, v in pkg["project"].items()
          if k not in ("id", "created_at") and not k.startswith("_")}
    # A package exported before the citation was corrected carries the wrong
    # co-author for the multivocal guidelines. The boot-time migration cannot
    # reach it — the row is written after boot — so the same correction happens
    # here. It rewrites one field of an imported package deliberately: that
    # string is ReviQ's own generated default, not something the exporting
    # review wrote, and reproducing a citation known to be wrong helps nobody.
    if pd.get("methodology") == WRONG_MLR_METHODOLOGY:
        pd["methodology"] = MLR_METHODOLOGY
    project = Project(**pd, created_at=datetime.utcnow())
    session.add(project)
    session.flush()
    pid = project.id

    # ID remapping tables: old (exported) ID -> new (imported) ID.
    # Every entity is re-created with a fresh auto-increment ID, so all
    # foreign-key references (paper_id, reviewer_id, criterion_id) in
    # downstream tables must be translated through these maps.
    reviewer_map:  dict[int, int] = {}
    qa_crit_map:   dict[int, int] = {}
    paper_map:     dict[int, int] = {}

    # ── Reviewers ─────────────────────────────────────────────────────────────
    for r in pkg.get("reviewers", []):
        nr = Reviewer(
            project_id=pid, name=r["name"],
            email=r.get("email"), role=r.get("role", "R1"),
        )
        session.add(nr); session.flush()
        reviewer_map[r["id"]] = nr.id

    # ── Criteria ──────────────────────────────────────────────────────────────
    for c in pkg.get("inclusion_criteria", []):
        session.add(InclusionCriterion(
            project_id=pid, label=c["label"],
            description=c["description"], phase=c.get("phase", "screening"),
            short_label=c.get("short_label"),
        ))
    for c in pkg.get("exclusion_criteria", []):
        session.add(ExclusionCriterion(
            project_id=pid, label=c["label"],
            description=c["description"], phase=c.get("phase", "screening"),
            short_label=c.get("short_label"),
        ))
    for c in pkg.get("qa_criteria", []):
        nc = QACriterion(
            project_id=pid, label=c["label"],
            description=c["description"], max_score=c.get("max_score", 1.0),
        )
        session.add(nc); session.flush()
        qa_crit_map[c["id"]] = nc.id

    # ── Taxonomy ──────────────────────────────────────────────────────────────
    for t in pkg.get("taxonomy", []):
        session.add(TaxonomyEntry(
            project_id=pid, taxonomy_type=t["taxonomy_type"],
            value=t["value"], sort_order=t.get("sort_order", 0),
        ))

    # ── Extraction fields ──────────────────────────────────────────────────────
    for f in pkg.get("extraction_fields", []):
        session.add(ExtractionField(
            project_id=pid, field_name=f["field_name"],
            field_label=f.get("field_label") or f.get("label", ""),
            field_type=f["field_type"],
            options=f.get("options"), sort_order=f.get("sort_order", 0),
        ))

    # ── Search strings ─────────────────────────────────────────────────────────
    for ss in pkg.get("search_strings", []):
        session.add(DatabaseSearchString(
            project_id=pid, db_name=ss["db_name"],
            query_string=ss.get("query_string"),
            filter_settings=ss.get("filter_settings"),
            search_date=ss.get("search_date"),
            results_count=ss.get("results_count"),
        ))
    session.flush()

    # ── Papers ────────────────────────────────────────────────────────────────
    # Fields come from the model, not from a hand-written list. The hand-written
    # list silently omitted `venue_category_override`, so every replication
    # import discarded it — and the round-trip test could not see it, because it
    # compared five fields. A package that claims to be the archival artefact
    # must not quietly drop provenance, so new columns are carried by default.
    for p in pkg.get("papers", []):
        np = Paper(
            project_id=pid,
            created_at=datetime.utcnow(),
            **{
                "source": "unknown",
                "dedup_status": "original",
                **{f: p[f] for f in PAPER_IMPORT_FIELDS if f in p},
            },
        )
        session.add(np); session.flush()
        paper_map[p["id"]] = np.id

    # ── Reviewer decisions ────────────────────────────────────────────────────
    for d in pkg.get("reviewer_decisions", []):
        pid_old = d.get("paper_id")
        rid_old = d.get("reviewer_id")
        if pid_old not in paper_map or rid_old not in reviewer_map:
            continue
        session.add(ReviewerDecision(
            project_id=pid,
            paper_id=paper_map[pid_old],
            reviewer_id=reviewer_map[rid_old],
            phase=d["phase"], decision=d["decision"],
            criterion_label=d.get("criterion_label"),
            rationale=d.get("rationale"),
            timestamp=datetime.utcnow(),
            source_file=d.get("source_file"),
        ))

    # ── Final decisions ───────────────────────────────────────────────────────
    for d in pkg.get("final_decisions", []):
        pid_old = d.get("paper_id")
        if pid_old not in paper_map:
            continue
        old_res = d.get("resolved_by_reviewer_id")
        session.add(FinalDecision(
            project_id=pid,
            paper_id=paper_map[pid_old],
            phase=d["phase"], decision=d["decision"],
            resolution_method=d.get("resolution_method"),
            resolution_note=d.get("resolution_note"),
            resolved_by_reviewer_id=reviewer_map.get(old_res) if old_res else None,
            timestamp=datetime.utcnow(),
        ))

    # ── Conflict log ──────────────────────────────────────────────────────────
    for c in pkg.get("conflict_log", []):
        pid_old = c.get("paper_id")
        if pid_old not in paper_map:
            continue
        session.add(ConflictLog(
            project_id=pid,
            paper_id=paper_map[pid_old],
            phase=c["phase"],
            r1_reviewer_id=reviewer_map.get(c.get("r1_reviewer_id")),
            r2_reviewer_id=reviewer_map.get(c.get("r2_reviewer_id")),
            r1_decision=c.get("r1_decision"), r2_decision=c.get("r2_decision"),
            r1_rationale=c.get("r1_rationale"), r2_rationale=c.get("r2_rationale"),
            resolved=c.get("resolved", False),
            resolution=c.get("resolution"),
            resolution_method=c.get("resolution_method"),
            resolved_by_reviewer_id=reviewer_map.get(c.get("resolved_by_reviewer_id")),
            resolved_at=None, created_at=datetime.utcnow(),
        ))

    # ── QA scores ─────────────────────────────────────────────────────────────
    for s in pkg.get("qa_scores", []):
        pid_old  = s.get("paper_id")
        cid_old  = s.get("criterion_id")
        rid_old  = s.get("scored_by_reviewer_id")
        if pid_old not in paper_map:
            continue
        new_cid = qa_crit_map.get(cid_old)
        new_rid = reviewer_map.get(rid_old)
        if not new_cid or not new_rid:
            continue
        session.add(QAScore(
            project_id=pid,
            paper_id=paper_map[pid_old],
            criterion_id=new_cid, score=s["score"],
            rationale=s.get("rationale"),
            scored_by_reviewer_id=new_rid,
            timestamp=datetime.utcnow(),
        ))

    # ── Extraction records ────────────────────────────────────────────────────
    for r in pkg.get("extraction_records", []):
        pid_old = r.get("paper_id")
        rid_old = r.get("extracted_by_reviewer_id")
        if pid_old not in paper_map or rid_old not in reviewer_map:
            continue
        session.add(ExtractionRecord(
            project_id=pid,
            paper_id=paper_map[pid_old],
            field_name=r["field_name"], field_value=r.get("field_value"),
            extracted_by_reviewer_id=reviewer_map[rid_old],
            timestamp=datetime.utcnow(),
        ))

    # ── Snowballing iterations ────────────────────────────────────────────────
    for it in pkg.get("snowballing_iterations", []):
        session.add(SnowballingIteration(
            project_id=pid,
            iteration_number=it["iteration_number"],
            iteration_type=it.get("iteration_type", "forward"),
            is_saturated=it.get("is_saturated", False),
            saturation_confirmed=it.get("saturation_confirmed", False),
            created_at=datetime.utcnow(),
        ))

    # ── Paper database links (multi-source tracking) ──────────────────────────
    for link in pkg.get("paper_database_links", []):
        pid_old = link.get("paper_id")
        if pid_old not in paper_map:
            continue
        session.add(PaperDatabaseLink(
            project_id=pid,
            paper_id=paper_map[pid_old],
            db_name=link["db_name"],
        ))

    # ── Write bib files to a writable directory ──────────────────────────────
    # BIB_BASE_DIR (/bib_data) is mounted read-only in docker-compose;
    # write imported bib files to /data/bib_data/ which is on the writable volume.
    data_dir = os.environ.get("DATA_DIR", "/data")
    bib_write_dir = os.path.join(data_dir, "bib_data")
    try:
        os.makedirs(bib_write_dir, exist_ok=True)
        for zip_path in zf.namelist():
            if zip_path.startswith("bibtex/") and zip_path.endswith(".bib"):
                bib_content = zf.read(zip_path)
                # Write with original filename
                dest = os.path.join(bib_write_dir, os.path.basename(zip_path))
                with open(dest, "wb") as fh:
                    fh.write(bib_content)
    except OSError:
        pass  # bib files are optional metadata; skip if filesystem is read-only

    # Committed here, before the grey-literature section below, rather than
    # once at the very end: `retrieval` is a second connection to the same
    # SQLite file, and `adopt.adopt` writes through it. A write on one
    # connection while `session` still holds this one's — from the flushes
    # above — deadlocks (`database is locked`), because SQLite serialises
    # writers across every connection to a file regardless of journal mode.
    # Committing first releases it. The cost: if the grey-literature section
    # below fails, this part of the import (papers, decisions, everything
    # else) stays committed rather than rolling back with it — an acceptable
    # trade against a guaranteed deadlock, and the one other place in this
    # codebase that mixes the two connections (`import_grey_from_retrieval`)
    # never writes through `retrieval`, so it never had to make this choice.
    session.commit()

    # ── Grey-literature retrieval (v2) ───────────────────────────────────────
    # The rows behind `grey_sources`' document_id/snapshot_id — scoped, on the
    # exporting side, to that project's own runs. Remapped through
    # `app.retrieval.adopt`, the same command this installation already uses
    # to bring in the pilot corpus, rather than a second implementation of the
    # same remapping.
    document_map: dict[int, int] = {}
    snapshot_map: dict[int, int] = {}
    retrieval_pkg = pkg.get("retrieval")
    if retrieval_pkg and retrieval is not None:
        runs_dir = _runs_dir()
        # Bundled WARC files, when this package was exported with --with-archive.
        for zip_path in zf.namelist():
            if zip_path.startswith("archives/") and not zip_path.endswith("/"):
                dest = runs_dir / Path(zip_path).relative_to("archives")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(zf.read(zip_path))

        tmp_dir = Path(tempfile.mkdtemp(prefix="reviq-replication-"))
        try:
            src = retrieval_db.connect(tmp_dir / "src.sqlite3")
            for table in RETRIEVAL_TABLES:
                rows = retrieval_pkg.get(table) or []
                if not rows:
                    continue
                columns = list(rows[0].keys())
                marks = ", ".join("?" for _ in columns)
                src.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})",
                    [[r[c] for c in columns] for r in rows],
                )
            src.commit()
            adopt_result = retrieval_adopt.adopt(
                src, retrieval, project_id=pid, runs_dir=runs_dir,
                require_archive=False,
            )
            document_map = adopt_result.document_map
            snapshot_map = adopt_result.snapshot_map
        finally:
            src.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── Grey imports ──────────────────────────────────────────────────────────
    grey_import_map: dict[int, int] = {}
    for gi in pkg.get("grey_imports", []):
        ngi = GreyImport(
            project_id=pid,
            schema_version=gi.get("schema_version"),
            canonicalization=gi.get("canonicalization"),
            tool_name=gi.get("tool_name"),
            tool_version=gi.get("tool_version"),
            exported_at_utc=gi.get("exported_at_utc"),
            scope_kind=gi.get("scope_kind"),
            scope_id=gi.get("scope_id"),
            filename=gi.get("filename"),
            queries=gi.get("queries"),
            records_in_package=gi.get("records_in_package"),
            documents_reported=gi.get("documents_reported"),
            usable_reported=gi.get("usable_reported"),
            imported_count=gi.get("imported_count", 0),
            duplicate_count=gi.get("duplicate_count", 0),
            already_present_count=gi.get("already_present_count", 0),
            skipped_count=gi.get("skipped_count", 0),
            imported_at=datetime.utcnow(),
        )
        session.add(ngi); session.flush()
        grey_import_map[gi["id"]] = ngi.id

    # ── Grey sources ──────────────────────────────────────────────────────────
    # `document_id`/`snapshot_id` resolve through the maps `adopt` just built.
    # When they miss — the retrieval data was not part of this package, or the
    # run was already present so nothing new was adopted for it this time — a
    # lookup by `canonical_url` (the identity that travels regardless of which
    # installation retrieved it) is the fallback, the same tolerance a package
    # from a co-reviewer already needs.
    for gs in pkg.get("grey_sources", []):
        pid_old = gs.get("paper_id")
        if pid_old not in paper_map:
            continue
        new_doc_id = document_map.get(gs.get("document_id"))
        if new_doc_id is None and gs.get("canonical_url") and retrieval is not None:
            row = retrieval.execute(
                "SELECT document_id FROM documents WHERE canonical_url = ?",
                (gs["canonical_url"],),
            ).fetchone()
            new_doc_id = row["document_id"] if row else None
        new_snap_id = snapshot_map.get(gs.get("snapshot_id"))
        if new_snap_id is None and new_doc_id is not None and retrieval is not None:
            if gs.get("sha256"):
                row = retrieval.execute(
                    "SELECT snapshot_id FROM snapshots WHERE document_id = ? AND sha256 = ?",
                    (new_doc_id, gs["sha256"]),
                ).fetchone()
                new_snap_id = row["snapshot_id"] if row else None
            else:
                # A failed retrieval has no SHA-256 to match on. Falling back
                # to "the document's only snapshot" is still safe when there
                # is exactly one — ambiguous only when a document was fetched
                # more than once, and this installation cannot then tell which
                # attempt the source described, so it leaves the field NULL
                # rather than guessing.
                rows = retrieval.execute(
                    "SELECT snapshot_id FROM snapshots WHERE document_id = ?",
                    (new_doc_id,),
                ).fetchall()
                new_snap_id = rows[0]["snapshot_id"] if len(rows) == 1 else None
        session.add(GreySource(
            project_id=pid,
            paper_id=paper_map[pid_old],
            grey_import_id=grey_import_map.get(gs.get("grey_import_id")),
            record_key=gs.get("record_key", ""),
            canonical_url=gs.get("canonical_url", ""),
            source_url=gs.get("source_url"),
            host=gs.get("host"),
            retrieved_at_utc=gs.get("retrieved_at_utc"),
            sha256=gs.get("sha256"),
            media_type=gs.get("media_type"),
            content_length=gs.get("content_length"),
            word_count=gs.get("word_count"),
            archive_filename=gs.get("archive_filename"),
            archive_offset=gs.get("archive_offset"),
            archive_record_id=gs.get("archive_record_id"),
            retrieval_status=gs.get("retrieval_status"),
            retrieval_reason=gs.get("retrieval_reason"),
            search_observations=gs.get("search_observations", 0),
            best_rank=gs.get("best_rank"),
            document_id=new_doc_id,
            snapshot_id=new_snap_id,
        ))

    session.commit()
    session.refresh(project)
    return {
        "id": pid,
        "title": project.title,
        "message": "Replication package imported successfully",
    }
