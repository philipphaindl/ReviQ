"""
Replication package export / import  (reviq-replication-v1)

ZIP layout:
  project.json          – full SLR data in reviq-replication-v1 schema
  bibtex/
    <db_name>.bib       – one raw results file per database search string
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..database import get_session
from ..models import (
    ConflictLog, DatabaseSearchString, ExclusionCriterion, ExtractionField,
    ExtractionRecord, FinalDecision, InclusionCriterion, Paper,
    PaperDatabaseLink, Project, QACriterion, QAScore, Reviewer,
    ReviewerDecision, SnowballingIteration, TaxonomyEntry,
)

router = APIRouter(prefix="/projects", tags=["replication"])

SCHEMA_VERSION = "reviq-replication-v1"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _row(obj) -> dict:
    """SQLModel → plain dict (excludes SQLAlchemy private attributes)."""
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{pid}/replication/export")
def export_replication_package(pid: int, session: Session = Depends(get_session)):
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
    }

    # Build the ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(pkg, indent=2, default=str))

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
async def import_replication_package(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Expected a .zip file")

    raw = await file.read()
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
    for p in pkg.get("papers", []):
        np = Paper(
            project_id=pid, citekey=p["citekey"],
            doi=p.get("doi"), title=p["title"],
            authors=p.get("authors"), year=p.get("year"),
            venue=p.get("venue"), abstract=p.get("abstract"),
            keywords=p.get("keywords"), entry_type=p.get("entry_type"),
            source=p.get("source", "unknown"),
            dedup_status=p.get("dedup_status", "original"),
            language=p.get("language"),
            full_text_url=p.get("full_text_url"),
            full_text_inaccessible=p.get("full_text_inaccessible", False),
            created_at=datetime.utcnow(),
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

    session.commit()
    session.refresh(project)
    return {
        "id": pid,
        "title": project.title,
        "message": "Replication package imported successfully",
    }
