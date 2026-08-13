"""Take a retrieval database written by an earlier, separate installation.

Retrieval used to keep its own SQLite file next to ReviQ's. It does not any
more — but the corpora written while it did are still there, and a pilot corpus
of 424 documents, 20 runs and 207 MB of WARC is not something to re-retrieve at
2 120 credits because the file moved. This is the bridge across.

What makes it more than `INSERT ... SELECT`:

  * **Integer keys are database-local.** `document_id`, `snapshot_id`,
    `extraction_id` and `figure_id` mean nothing outside the file that assigned
    them. Every one is remapped, and a row whose reference does not resolve is
    skipped and counted rather than written pointing at whatever row happens to
    hold that number in the target.

  * **`run_id` is a UUID and survives.** That is what makes this idempotent: a
    run the target already has is skipped whole, with everything hanging off
    it, so a second `adopt` after an interrupted first one adds nothing twice.

  * **`documents.canonical_url` is UNIQUE**, and a URL is a URL. A document the
    target already holds is reused rather than duplicated — the same rule the
    grey import applies, for the same reason.

  * **The archive is checked, not moved.** Every WARC a snapshot or figure
    points into has to be in place, and if one is not, nothing is written.
    `archive.read_payload` verifies digests later anyway, but a corpus that only
    announces its missing bytes on first read has already been adopted by then.
    Moving 207 MB is not this command's job: it would fail halfway on a full
    disk and leave a half-migrated archive behind.

The dry run is the real thing, rolled back. Writing a second implementation
that predicts what the first would do is how a report and an export ended up
disagreeing about the size of the same corpus; here the two cannot disagree,
because there is only one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


class Spec(NamedTuple):
    """One table's shape, as far as adopting it is concerned.

    `pk` is the integer primary key to remap. The `*_cols` name the references
    that have to resolve through the maps built so far; a row with an
    unresolvable reference is out of scope.
    """
    table: str
    pk: str
    run_cols: tuple[str, ...] = ()
    doc_cols: tuple[str, ...] = ()
    snap_cols: tuple[str, ...] = ()
    fig_cols: tuple[str, ...] = ()
    warc: bool = False


# Dependency order: every table is written after the ones it points at, so the
# foreign keys hold at each intermediate step.
SPECS: tuple[Spec, ...] = (
    Spec("serp_results", "serp_result_id", run_cols=("run_id",),
         doc_cols=("document_id",)),
    Spec("snapshots", "snapshot_id", run_cols=("run_id",),
         doc_cols=("document_id",), warc=True),
    Spec("extractions", "extraction_id", snap_cols=("snapshot_id",)),
    Spec("extraction_history", "history_id", snap_cols=("snapshot_id",),
         run_cols=("superseded_by_run",)),
    Spec("document_links", "link_id", run_cols=("run_id",),
         doc_cols=("from_document_id", "to_document_id"),
         snap_cols=("discovered_in_snapshot",)),
    Spec("figures", "figure_id", run_cols=("run_id",), doc_cols=("document_id",),
         snap_cols=("snapshot_id",), warc=True),
    Spec("figure_descriptions", "description_id", fig_cols=("figure_id",)),
)


class AdoptError(RuntimeError):
    """The source cannot be adopted as it stands. Nothing has been written."""


@dataclass
class TableCount:
    table: str
    adopted: int = 0
    skipped: int = 0        # a reference outside the adopted runs


@dataclass
class Result:
    """What an adoption did — or, for a dry run, would have done."""
    runs: list[str] = field(default_factory=list)
    runs_already_present: list[str] = field(default_factory=list)
    documents_new: int = 0
    documents_reused: int = 0
    tables: list[TableCount] = field(default_factory=list)
    # (stored path, path it was rewritten to) for every archive referenced.
    archives: list[tuple[str, str]] = field(default_factory=list)
    missing_archives: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return sum(t.adopted for t in self.tables)


# --- reading the source ---------------------------------------------------


def open_source(path: Path) -> sqlite3.Connection:
    """Open the old database read-only.

    Read-only in SQLite's sense, not by convention: `db.connect` would apply the
    current schema and add `runs.project_id` to it on the way in. A command that
    reads one database and writes another has no business modifying the one it
    reads.
    """
    if not path.exists():
        raise AdoptError(f"no such database: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """The table's columns, or [] when it does not exist.

    A corpus retrieved before `figures` or `extraction_history` existed is
    exactly what this command is for, so a missing table is a normal finding.
    """
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _shared_columns(src: sqlite3.Connection, dst: sqlite3.Connection,
                    table: str) -> list[str]:
    """Columns present in both — the source may predate some of them."""
    source = _columns(src, table)
    if not source:
        return []
    target = set(_columns(dst, table))
    return [c for c in source if c in target]


def _rewrite_warc(stored: str | None, run_id: str, runs_dir: Path) -> str | None:
    """Where the archive for `run_id` lives under this installation.

    Only the file name carries over. The directory is rebuilt from `runs_dir`
    and the run id, because the stored path was relative to whatever working
    directory the old tool ran in and would not resolve here.
    """
    if not stored:
        return None
    return str(runs_dir / run_id / Path(stored).name)


# --- the one implementation -----------------------------------------------


def adopt(src: sqlite3.Connection, dst: sqlite3.Connection, *,
          project_id: int | None, runs_dir: Path, dry_run: bool = False) -> Result:
    """Adopt every run the target does not already have.

    One transaction: the corpus arrives whole, or the target is untouched. A
    dry run does the same work and rolls it back, so what it reports is what
    would happen rather than a second opinion about it.
    """
    if not _columns(src, "runs"):
        raise AdoptError("the source has no `runs` table — not a retrieval database")

    result = Result()
    present = {r["run_id"] for r in dst.execute("SELECT run_id FROM runs")}
    for row in src.execute("SELECT run_id FROM runs ORDER BY started_at_utc"):
        target = (result.runs_already_present if row["run_id"] in present
                  else result.runs)
        target.append(row["run_id"])

    if not result.runs:
        return result

    adopted = set(result.runs)
    try:
        _copy_runs(src, dst, adopted, project_id)
        maps = {"documents": _copy_documents(src, dst, result)}
        for spec in SPECS:
            result.tables.append(
                _copy_table(src, dst, spec, adopted, maps, runs_dir, result)
            )
        if result.missing_archives:
            raise AdoptError(
                "the archive is not in place, so nothing was written. Move the "
                "WARC files into position and run this again. Missing:\n  "
                + "\n  ".join(result.missing_archives)
            )
    except Exception:
        dst.rollback()
        raise

    dst.rollback() if dry_run else dst.commit()
    return result


def _copy_runs(src: sqlite3.Connection, dst: sqlite3.Connection,
               adopted: set[str], project_id: int | None) -> None:
    """Copy the runs, filed under the review that is adopting them.

    `project_id` is overwritten rather than carried across: the source ran
    before runs belonged to reviews at all, and a project id from another
    installation would name a different project here.
    """
    columns = [c for c in _shared_columns(src, dst, "runs") if c != "project_id"]
    marks = ", ".join("?" for _ in columns)
    for row in src.execute("SELECT * FROM runs"):
        if row["run_id"] not in adopted:
            continue
        dst.execute(
            f"INSERT INTO runs ({', '.join(columns)}, project_id) VALUES ({marks}, ?)",
            [row[c] for c in columns] + [project_id],
        )


def _copy_documents(src: sqlite3.Connection, dst: sqlite3.Connection,
                    result: Result) -> dict[int, int]:
    """Map every source document to a target one, reusing by canonical URL.

    Every document is mapped, not only those the adopted runs reference: the
    map is what the tables below resolve against, and a document reached only
    through a link edge would otherwise drop that edge silently.

    `first_seen_run_id` is a foreign key into `runs`. For a document carried
    over by an earlier adoption it points at a run the target already has, so
    it resolves either way. When it does not, the source is internally
    inconsistent and says so here rather than through a foreign-key error three
    tables later.
    """
    columns = [c for c in _shared_columns(src, dst, "documents")
               if c != "document_id"]
    available = {r["run_id"] for r in dst.execute("SELECT run_id FROM runs")}
    mapping: dict[int, int] = {}

    for row in src.execute("SELECT * FROM documents"):
        found = dst.execute(
            "SELECT document_id FROM documents WHERE canonical_url = ?",
            (row["canonical_url"],),
        ).fetchone()
        if found is not None:
            mapping[row["document_id"]] = int(found["document_id"])
            result.documents_reused += 1
            continue

        if row["first_seen_run_id"] not in available:
            raise AdoptError(
                f"document {row['canonical_url']} was first seen in run "
                f"{row['first_seen_run_id']}, which is in neither database"
            )

        cur = dst.execute(
            f"INSERT INTO documents ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [row[c] for c in columns],
        )
        mapping[row["document_id"]] = int(cur.lastrowid)
        result.documents_new += 1

    return mapping


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, spec: Spec,
                adopted: set[str], maps: dict[str, dict[int, int]],
                runs_dir: Path, result: Result) -> TableCount:
    """Copy one table, remapping every reference through `maps`.

    A row is adopted only if all of its references resolve. That single rule
    replaces a per-table notion of scope: an extraction belongs to a snapshot
    and a description to a figure, and if the thing it belongs to was not
    adopted then neither is it.
    """
    count = TableCount(spec.table)
    columns = [c for c in _shared_columns(src, dst, spec.table) if c != spec.pk]
    if not columns:
        return count

    mapping: dict[int, int] = {}
    seen_archives = {stored for stored, _ in result.archives}

    for row in src.execute(f"SELECT * FROM {spec.table}"):
        if any(row[c] not in adopted for c in spec.run_cols if row[c] is not None):
            count.skipped += 1
            continue

        values: dict[str, object] = {c: row[c] for c in columns}
        resolved = True
        for group, table in ((spec.doc_cols, "documents"),
                             (spec.snap_cols, "snapshots"),
                             (spec.fig_cols, "figures")):
            for column in group:
                if row[column] is None:
                    continue
                new = maps.get(table, {}).get(row[column])
                if new is None:
                    resolved = False
                    break
                values[column] = new
            if not resolved:
                break
        if not resolved:
            count.skipped += 1
            continue

        if spec.warc and row["warc_path"]:
            values["warc_path"] = _rewrite_warc(row["warc_path"], row["run_id"],
                                                runs_dir)
            if row["warc_path"] not in seen_archives:
                seen_archives.add(row["warc_path"])
                result.archives.append((row["warc_path"], values["warc_path"]))
                if not Path(values["warc_path"]).exists():
                    result.missing_archives.append(values["warc_path"])

        cur = dst.execute(
            f"INSERT INTO {spec.table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [values[c] for c in columns],
        )
        mapping[row[spec.pk]] = int(cur.lastrowid)
        count.adopted += 1

    maps[spec.table] = mapping
    return count


# --- reporting ------------------------------------------------------------


def describe(result: Result, *, dry_run: bool) -> list[str]:
    """The lines the CLI prints, for a dry run and the real thing alike."""
    verb = "would adopt" if dry_run else "adopted"
    lines = [
        f"{verb} {len(result.runs)} run(s); "
        f"{len(result.runs_already_present)} already present",
        f"  documents: {result.documents_new} new, "
        f"{result.documents_reused} already held under the same URL",
    ]
    for table in result.tables:
        note = f", {table.skipped} outside the adopted runs" if table.skipped else ""
        lines.append(f"  {table.table}: {table.adopted}{note}")
    if result.archives:
        lines.append(f"  archives referenced: {len(result.archives)}")
    return lines
