"""SQLite access. Plain sqlite3, no ORM.

Every write helper here is safe to call twice: the schema's UNIQUE constraints
carry the idempotency, and these functions use INSERT ... ON CONFLICT so a
repeated run reuses rows instead of duplicating them.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utc_now() -> str:
    """ISO-8601 UTC with a trailing Z. The only timestamp format used anywhere."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # A long run holds this database for minutes at a time. Under the default
    # rollback journal any concurrent reader — a second terminal, or a UI
    # watching progress — gets "database is locked" for the whole write.
    # WAL lets readers proceed against the last committed state, which is
    # exactly the guarantee a progress display needs.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to the current schema.

    Every statement in schema.sql is `CREATE ... IF NOT EXISTS`, so applying it
    to a populated database only adds what is missing and touches nothing that
    is already there.

    This runs on *every* connection, including for read-only commands, because
    in this tool a database is routinely older than the binary opening it: a
    corpus retrieved months ago is exactly what a review comes back to, and the
    tables added in between should not make `export-json` or `report` fail with
    "no such table". Creating an empty table is the honest answer — the corpus
    genuinely has no figures in it.

    What this does NOT do is add *columns* to tables that already exist; SQLite
    has no `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Column-level changes stay
    manual and are called out in docs/decisions.md.
    """
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema. Kept distinct from `ensure_schema` so that `init`
    reads as a deliberate act rather than a side effect of connecting."""
    ensure_schema(conn)


# --- runs ---------------------------------------------------------------


def start_run(
    conn: sqlite3.Connection,
    run_id: str,
    query: str,
    engine: str,
    search_params_json: str,
    tool_version: str,
    batch_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO runs (run_id, query, engine, search_params_json,
                             started_at_utc, tool_version, status, batch_id)
           VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
        (run_id, query, engine, search_params_json, utc_now(), tool_version, batch_id),
    )
    conn.commit()


def finish_run(conn: sqlite3.Connection, run_id: str, status: str, notes: str | None = None) -> None:
    conn.execute(
        "UPDATE runs SET finished_at_utc = ?, status = ?, notes = ? WHERE run_id = ?",
        (utc_now(), status, notes, run_id),
    )
    conn.commit()


# --- documents ----------------------------------------------------------


def upsert_document(
    conn: sqlite3.Connection,
    canonical_url: str,
    host: str | None,
    run_id: str,
    discovery_source: str = "serp",
    discovery_depth: int = 0,
) -> int:
    """Return the document_id for a canonical URL, creating it only if new.

    This is where deduplication actually happens: the UNIQUE constraint on
    canonical_url means a URL seen in an earlier run keeps its identity, and
    first_seen_* keeps pointing at the run that discovered it.
    """
    conn.execute(
        """INSERT INTO documents (canonical_url, host, first_seen_run_id,
                                  first_seen_at_utc, discovery_source, discovery_depth)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (canonical_url) DO NOTHING""",
        (canonical_url, host, run_id, utc_now(), discovery_source, discovery_depth),
    )
    row = conn.execute(
        "SELECT document_id FROM documents WHERE canonical_url = ?", (canonical_url,)
    ).fetchone()
    return int(row["document_id"])


# --- serp results -------------------------------------------------------


def insert_serp_result(
    conn: sqlite3.Connection,
    run_id: str,
    page: int,
    position: int,
    global_rank: int,
    raw_url: str,
    canonical_url: str,
    title: str | None,
    snippet: str | None,
    displayed_link: str | None,
    retrieved_at_utc: str,
    searchapi_search_id: str | None,
    document_id: int,
) -> None:
    conn.execute(
        """INSERT INTO serp_results
             (run_id, page, position, global_rank, raw_url, canonical_url, title,
              snippet, displayed_link, retrieved_at_utc, searchapi_search_id, document_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (run_id, page, position) DO NOTHING""",
        (
            run_id, page, position, global_rank, raw_url, canonical_url, title,
            snippet, displayed_link, retrieved_at_utc, searchapi_search_id, document_id,
        ),
    )


# --- snapshots ----------------------------------------------------------


def has_snapshot(conn: sqlite3.Connection, document_id: int) -> bool:
    """True if this document was ever *usefully* fetched, in any run.

    Drives the default no-refetch behaviour: a document already archived does
    not cost ScrapingBee credits again. Failed fetches and block pages both
    fall through deliberately, so the next run retries them — that is how a
    later run with --premium-proxy picks up exactly the sources that were
    blocked, and nothing else.
    """
    row = conn.execute(
        """SELECT 1 FROM snapshots
           WHERE document_id = ? AND fetch_error IS NULL AND blocked_reason IS NULL
           LIMIT 1""",
        (document_id,),
    ).fetchone()
    return row is not None


def best_snapshot(conn: sqlite3.Connection, document_id: int) -> sqlite3.Row | None:
    """The snapshot that best represents this document, across all runs.

    A clean retrieval wins over a blocked or failed one, and the most recent
    wins among equals. Deliberately not restricted to any run: a document
    observed in one batch may have been archived by an earlier one (see
    `has_snapshot`), and reporting "not fetched" for a document sitting in the
    archive would be false. It is also what lets `refetch` improve an
    existing corpus — re-exporting the original batch afterwards picks up the
    snapshot the retry produced, without rewriting a single earlier row.

    Every reader must use this one rule. When the export resolved a document
    one way and the retrieval report another, the two disagreed about how large
    the corpus was.
    """
    return conn.execute(
        """SELECT * FROM snapshots
           WHERE document_id = ?
           ORDER BY (fetch_error IS NULL AND blocked_reason IS NULL) DESC,
                    fetched_at_utc DESC
           LIMIT 1""",
        (document_id,),
    ).fetchone()


def insert_snapshot(conn: sqlite3.Connection, **fields) -> int:
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO snapshots ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (document_id, run_id) DO NOTHING",
        tuple(fields.values()),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)
    row = conn.execute(
        "SELECT snapshot_id FROM snapshots WHERE document_id = ? AND run_id = ?",
        (fields["document_id"], fields["run_id"]),
    ).fetchone()
    return int(row["snapshot_id"])


# --- extractions --------------------------------------------------------


def insert_extraction(conn: sqlite3.Connection, **fields) -> None:
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO extractions ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (snapshot_id) DO NOTHING",
        tuple(fields.values()),
    )


EXTRACTION_FIELDS = (
    "extractor", "title", "author", "publication_date", "language",
    "text", "word_count", "extracted_at_utc", "extraction_error",
)


def replace_extraction(
    conn: sqlite3.Connection, snapshot_id: int, run_id: str, **fields
) -> bool:
    """Supersede a snapshot's extraction, keeping the one it replaces.

    Returns True when a previous extraction was archived to
    `extraction_history` first. The copy is not optional bookkeeping: this is
    the only operation in the tool that replaces a content-bearing row, and it
    is defensible only because the row it replaces is kept. A review that
    quoted the earlier text must still be able to find it.

    The fields are enumerated from `EXTRACTION_FIELDS` rather than written out,
    so a column added to `extractions` is carried into the history by default
    instead of being silently dropped on the next re-extraction — the failure
    D-numbered as the replication drift in ReviQ, in a different repository.
    """
    previous = conn.execute(
        "SELECT * FROM extractions WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()

    if previous is not None:
        columns = ["snapshot_id", *EXTRACTION_FIELDS,
                   "superseded_at_utc", "superseded_by_run"]
        values = [snapshot_id, *(previous[f] for f in EXTRACTION_FIELDS),
                  utc_now(), run_id]
        conn.execute(
            f"INSERT INTO extraction_history ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        conn.execute("DELETE FROM extractions WHERE snapshot_id = ?", (snapshot_id,))

    insert_extraction(conn, snapshot_id=snapshot_id, **fields)
    return previous is not None


# --- snowballing edges --------------------------------------------------


def insert_link(
    conn: sqlite3.Connection,
    from_document_id: int,
    to_document_id: int,
    discovered_in_snapshot: int,
    run_id: str,
    raw_href: str,
    anchor_text: str | None,
    depth: int,
) -> None:
    """Record that one document linked to another.

    Kept even when the target was already known: the edge is what makes the
    corpus a graph, and "reached from three different sources" is a signal a
    review may want to use.
    """
    conn.execute(
        """INSERT INTO document_links
             (from_document_id, to_document_id, discovered_in_snapshot, run_id,
              raw_href, anchor_text, depth, discovered_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (from_document_id, to_document_id, run_id) DO NOTHING""",
        (from_document_id, to_document_id, discovered_in_snapshot, run_id,
         raw_href, anchor_text, depth, utc_now()),
    )


# --- figures ------------------------------------------------------------


def insert_figure(conn: sqlite3.Connection, **fields) -> int:
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO figures ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (snapshot_id, resolved_url) DO NOTHING",
        tuple(fields.values()),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)
    row = conn.execute(
        "SELECT figure_id FROM figures WHERE snapshot_id = ? AND resolved_url = ?",
        (fields["snapshot_id"], fields["resolved_url"]),
    ).fetchone()
    return int(row["figure_id"])


def insert_description(conn: sqlite3.Connection, **fields) -> None:
    """Store a generated description. Versioned by (figure, model, prompt): a
    different model or a revised prompt adds a row rather than replacing one."""
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO figure_descriptions ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (figure_id, model, prompt) DO NOTHING",
        tuple(fields.values()),
    )
