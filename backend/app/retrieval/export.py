"""CSV export.

One row per document per run, from both discovery paths:

  * SERP hits — one row per observation, so a URL ranked at two positions
    yields two rows, each with its own rank;
  * snowballed documents — one row per document reached by following a link,
    which have no SERP observation at all.

Driving the export from `serp_results` alone would silently omit everything
snowballing found, so the two are unioned explicitly.

Every row is traceable down to the archived bytes: warc_path + warc_offset
locate the snapshot, sha256 verifies it.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

COLUMNS = [
    "run_id", "batch_id", "query", "engine",
    "discovery_source", "discovery_depth", "inbound_links",
    "global_rank", "retrieved_at_utc",
    "raw_url", "canonical_url", "final_url", "origin_status_first",
    "title", "snippet", "publication_date", "language",
    "media_type", "sha256", "word_count",
    "warc_path", "warc_offset", "content_duplicate_of", "fetch_error",
    "blocked_reason", "extraction_error",
]

# content_duplicate_of resolves the second dedup level: identical bytes reached
# under different URLs (mirrors, redirect targets). Both documents are kept —
# flagging is a reporting concern, not a storage one, so nothing is discarded.
_QUERY = """
WITH first_by_hash AS (
    SELECT sha256, MIN(document_id) AS canonical_document_id
    FROM snapshots
    WHERE sha256 IS NOT NULL
    GROUP BY sha256
),
inbound AS (
    SELECT to_document_id AS document_id, COUNT(DISTINCT from_document_id) AS n
    FROM document_links
    GROUP BY to_document_id
),
observations AS (
    -- Documents returned by a search engine: one row per SERP observation.
    SELECT
        sr.run_id            AS run_id,
        sr.document_id       AS document_id,
        sr.global_rank       AS global_rank,
        sr.retrieved_at_utc  AS retrieved_at_utc,
        sr.raw_url           AS raw_url,
        sr.canonical_url     AS canonical_url,
        sr.title             AS serp_title,
        sr.snippet           AS snippet
    FROM serp_results sr
    UNION ALL
    -- Documents reached by following a link: no SERP observation exists, so
    -- they would be invisible if the export were driven by serp_results.
    SELECT
        s.run_id, s.document_id, NULL, s.fetched_at_utc,
        s.requested_url, d.canonical_url, NULL, NULL
    FROM snapshots s
    JOIN documents d ON d.document_id = s.document_id
    WHERE NOT EXISTS (
        SELECT 1 FROM serp_results sr2
        WHERE sr2.run_id = s.run_id AND sr2.document_id = s.document_id
    )
)
SELECT
    o.run_id,
    r.batch_id,
    r.query,
    r.engine,
    d.discovery_source,
    d.discovery_depth,
    COALESCE(i.n, 0)                 AS inbound_links,
    o.global_rank,
    o.retrieved_at_utc,
    o.raw_url,
    o.canonical_url,
    s.final_url,
    s.origin_status_first,
    COALESCE(e.title, o.serp_title)  AS title,
    o.snippet,
    e.publication_date,
    e.language,
    s.media_type,
    s.sha256,
    e.word_count,
    s.warc_path,
    s.warc_offset,
    CASE
        WHEN fbh.canonical_document_id IS NOT NULL
             AND fbh.canonical_document_id <> d.document_id
        THEN fbh.canonical_document_id
    END                              AS content_duplicate_of,
    s.fetch_error,
    s.blocked_reason,
    e.extraction_error
FROM observations o
JOIN runs r        ON r.run_id = o.run_id
JOIN documents d   ON d.document_id = o.document_id
LEFT JOIN snapshots s   ON s.document_id = o.document_id AND s.run_id = o.run_id
LEFT JOIN extractions e ON e.snapshot_id = s.snapshot_id
LEFT JOIN first_by_hash fbh ON fbh.sha256 = s.sha256
LEFT JOIN inbound i ON i.document_id = o.document_id
WHERE {scope}
ORDER BY r.started_at_utc, d.discovery_depth, o.global_rank
"""


def _write(conn: sqlite3.Connection, scope: str, key: str, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(_QUERY.format(scope=scope), (key,)).fetchall()

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in COLUMNS})
    return len(rows)


def export_run(conn: sqlite3.Connection, run_id: str, out_path: Path) -> int:
    """One run's results. Returns the number of rows written."""
    return _write(conn, "o.run_id = ?", run_id, out_path)


def export_batch(conn: sqlite3.Connection, batch_id: str, out_path: Path) -> int:
    """Every run of one batch, in the order the queries were issued."""
    return _write(conn, "r.batch_id = ?", batch_id, out_path)
