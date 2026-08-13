"""Retrieval report — the per-source access log.

A review has to be able to say, for every source it cites: this URL, retrieved
at this moment, with this content, archived here. And for every source it
could *not* use: this URL, unreachable at this moment, for this reason. The
second list is not an appendix afterthought — it is the quantified limitation
that a methods section otherwise has to hand-wave.

Markdown, because that is what goes into an appendix, a repository, or a
supplementary file, and it renders everywhere without tooling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import __version__
from .db import project_of_runs, utc_now
from .outcome import LABELS, OK, REMEDIES, classify

# One row per document in scope, carrying its best snapshot from *any* run.
#
# Two subtleties, both of them things this query got wrong before:
#
#   * Documents come from three places (SERP observations, snapshots, link
#     targets) for the reasons `interchange.document_ids` sets out, and the
#     join to snapshots is a LEFT join — a document identified but never
#     fetched belongs in the report as such, not missing from it.
#
#   * The best snapshot is not restricted to the runs in scope. A retrieval
#     that failed in this batch and succeeded in a later `refetch` is one
#     document with a better snapshot, and reporting the stale failure would
#     contradict the export, which resolves it with `db.best_snapshot`. The
#     ordering below is that same rule, expressed as a window function so a few
#     hundred documents cost one query rather than one query each.
#
#     It is restricted to the scope's *project*, though, and by the same rule
#     `db.best_snapshot` applies — the `:project` parameter is computed once by
#     `db.project_of_runs` and bound here, rather than re-derived in SQL, so the
#     two cannot drift apart. A report and an export disagreeing about how large
#     the corpus is has happened once already.
_SOURCES = """
, scoped AS (
    SELECT document_id FROM serp_results
     WHERE run_id IN (SELECT run_id FROM scope) AND document_id IS NOT NULL
    UNION
    SELECT document_id FROM snapshots WHERE run_id IN (SELECT run_id FROM scope)
    UNION
    SELECT to_document_id FROM document_links WHERE run_id IN (SELECT run_id FROM scope)
)
, best AS (
    SELECT s.*, ROW_NUMBER() OVER (
        PARTITION BY s.document_id
        ORDER BY (s.fetch_error IS NULL AND s.blocked_reason IS NULL) DESC,
                 s.fetched_at_utc DESC
    ) AS rank_in_document
    FROM snapshots s
    WHERE s.document_id IN (SELECT document_id FROM scoped)
      AND (:project IS NULL
           OR s.run_id IN (SELECT run_id FROM runs WHERE project_id = :project))
)
SELECT
    d.document_id, d.canonical_url, d.host, d.discovery_source, d.discovery_depth,
    s.final_url, s.fetched_at_utc, s.sha256, s.media_type, s.origin_status_first,
    s.warc_path, s.warc_offset, s.fetch_error, s.blocked_reason, s.proxy_status,
    s.run_id AS snapshot_run_id,
    e.title, e.word_count, e.publication_date, e.extraction_error,
    (SELECT MIN(global_rank) FROM serp_results sr
      WHERE sr.document_id = d.document_id AND sr.run_id IN (SELECT run_id FROM scope)
    ) AS best_rank,
    (SELECT GROUP_CONCAT(DISTINCT r2.query) FROM serp_results sr2
      JOIN runs r2 ON r2.run_id = sr2.run_id
     WHERE sr2.document_id = d.document_id AND sr2.run_id IN (SELECT run_id FROM scope)
    ) AS found_by
FROM documents d
JOIN scoped ON scoped.document_id = d.document_id
LEFT JOIN best s ON s.document_id = d.document_id AND s.rank_in_document = 1
LEFT JOIN extractions e ON e.snapshot_id = s.snapshot_id
ORDER BY (s.snapshot_id IS NULL OR s.fetch_error IS NOT NULL OR s.blocked_reason IS NOT NULL),
         d.discovery_depth, best_rank IS NULL, best_rank, d.canonical_url
"""


def _scope_cte(scope: str) -> str:
    return f"WITH scope AS (SELECT run_id FROM runs WHERE {scope})\n"


def _rows(
    conn: sqlite3.Connection, scope: str, key: str, project_id: int | None
) -> list[sqlite3.Row]:
    """One row per document in scope, with the snapshot that best represents it.

    A document can hold more than one snapshot even within a single batch: a
    retrieval that failed in the run for query 1 is retried when query 5
    returns the same URL, because `db.has_snapshot` deliberately does not treat
    a failure as archived. Returning both would count that document twice and
    list it as failed and usable at once.
    """
    return conn.execute(
        _scope_cte(scope) + _SOURCES, {"key": key, "project": project_id}
    ).fetchall()


def _runs(conn: sqlite3.Connection, scope: str, key: str) -> list[sqlite3.Row]:
    return conn.execute(
        f"""SELECT run_id, query, engine, search_params_json, started_at_utc,
                   finished_at_utc, status, tool_version, project_id
            FROM runs WHERE {scope} ORDER BY started_at_utc""",
        {"key": key},
    ).fetchall()


def _escape(value) -> str:
    """Keep a pipe in a URL or title from breaking the table."""
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _build(conn: sqlite3.Connection, scope: str, key: str, title: str) -> str:
    runs = _runs(conn, scope, key)
    # Derived from the runs in scope, not passed in: see `db.project_of_runs`.
    project_id = project_of_runs(conn, [r["run_id"] for r in runs])
    rows = _rows(conn, scope, key, project_id)

    # `_rows` returns one row per document, joining its best snapshot to that
    # snapshot's extraction — so the same row answers both of `classify`'s
    # arguments. Earlier versions treated every row without a fetch error as
    # usable, which silently counted documents that were retrieved and turned
    # out to contain no text — 22 of 424 in the pilot corpus — as sources a
    # review could cite.
    # `snapshot_run_id` is NOT NULL in the snapshots table, so it is NULL here
    # exactly when the LEFT JOIN found no snapshot — a document identified by
    # the search but never fetched. Passing the row on regardless would have it
    # classified as "retrieved, no text", which is a different claim.
    outcomes = {
        r["document_id"]: classify(
            r if r["snapshot_run_id"] is not None else None, r, r["host"]
        )
        for r in rows
    }

    usable = [r for r in rows if outcomes[r["document_id"]].status == OK]
    unusable = [r for r in rows if outcomes[r["document_id"]].status != OK]
    from_serp = [r for r in usable if r["discovery_source"] == "serp"]
    from_link = [r for r in usable if r["discovery_source"] == "link"]

    by_reason: dict[str, list] = {}
    for row in unusable:
        by_reason.setdefault(outcomes[row["document_id"]].reason, []).append(row)
    ranked_reasons = sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    figures = conn.execute(
        _scope_cte(scope)
        + """SELECT COUNT(*) FROM figure_descriptions fd
             JOIN figures f ON f.figure_id = fd.figure_id
             WHERE f.run_id IN (SELECT run_id FROM scope) AND fd.error IS NULL""",
        {"key": key},
    ).fetchone()[0]

    out: list[str] = []
    w = out.append

    w(f"# {title}\n")
    w(f"Generated {utc_now()} by glr {__version__}.\n")

    # --- summary ---------------------------------------------------------
    w("## Summary\n")
    total = len(rows)
    w(f"| Measure | Count | Share |")
    w("|---|---:|---:|")

    def share(n: int) -> str:
        return f"{100 * n / total:.1f}%" if total else "—"

    w(f"| Sources retrieved and usable | {len(usable)} | {share(len(usable))} |")
    w(f"| &nbsp;&nbsp;of which from search results | {len(from_serp)} | {share(len(from_serp))} |")
    w(f"| &nbsp;&nbsp;of which reached by following links | {len(from_link)} | {share(len(from_link))} |")
    for reason, group in ranked_reasons:
        w(f"| {LABELS.get(reason, reason)} | {len(group)} | {share(len(group))} |")
    # "Identified", not "attempted": a document the search returned but that
    # was never fetched belongs in this total too, and it reconciles with
    # `counts.documents` in the interchange export by construction.
    w(f"| **Total identified** | **{total}** | |")
    if figures:
        w(f"| Figure descriptions generated | {figures} | |")
    w("")

    # --- searches issued -------------------------------------------------
    w("## Searches issued\n")
    w("| Query | Engine | Issued (UTC) | Parameters |")
    w("|---|---|---|---|")
    for run in runs:
        w(f"| `{_escape(run['query'])}` | {run['engine']} | {run['started_at_utc']} "
          f"| `{_escape(run['search_params_json'])}` |")
    w("")

    # --- usable sources --------------------------------------------------
    w("## Sources retrieved\n")
    w("Each row is one source as retrieved at the stated moment. `sha256` is over "
      "the archived bytes; the archive locates the snapshot the hash refers to.\n")
    w("| # | Source | Accessed (UTC) | Rank | SHA-256 | Type | Words | Archive |")
    w("|---:|---|---|---:|---|---|---:|---|")
    for index, row in enumerate(usable, start=1):
        rank = row["best_rank"] if row["discovery_source"] == "serp" else f"link d{row['discovery_depth']}"
        archive = (f"`{Path(row['warc_path']).name}` @ {row['warc_offset']}"
                   if row["warc_path"] else "—")
        w(f"| {index} | [{_escape(row['title'] or row['canonical_url'])}]({_escape(row['canonical_url'])}) "
          f"| {row['fetched_at_utc']} | {rank} | `{(row['sha256'] or '')[:16]}` "
          f"| {row['media_type'] or '—'} | {row['word_count'] or 0} | {archive} |")
    w("")

    # --- not retrieved ---------------------------------------------------
    if unusable:
        w("## Sources that could not be used\n")
        w("These were returned by the search but yielded no usable document. They "
          "are reported rather than dropped: an unreachable source is a documented "
          "limitation, not a gap. Grouped by cause, because the causes are "
          "different exclusion criteria — a publisher's access control, a platform "
          "post that was never a document, and a dead link do not belong in one "
          "number.\n")

        for reason, group in ranked_reasons:
            remedy = REMEDIES.get(reason)
            w(f"### {LABELS.get(reason, reason)} — {len(group)}\n")
            if remedy and remedy.action == "refetch":
                w(f"Retrievable in principle: {remedy.hint}. "
                  f"`refetch` selects exactly these.\n")
            elif remedy and remedy.action == "reextract":
                w(f"Recoverable from the archive without re-fetching: {remedy.hint}.\n")
            else:
                w(f"Not recoverable by retrying: {remedy.hint if remedy else '—'}.\n")

            hosts: dict[str, int] = {}
            for row in group:
                hosts[row["host"] or "—"] = hosts.get(row["host"] or "—", 0) + 1
            top = sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
            w("Hosts: " + ", ".join(f"{_escape(h)} ({n})" for h, n in top) + "\n")

            w("| # | Source | Attempted (UTC) | Recorded detail |")
            w("|---:|---|---|---|")
            for index, row in enumerate(group, start=1):
                detail = (row["blocked_reason"] or row["fetch_error"]
                          or row["extraction_error"] or "—")
                w(f"| {index} | {_escape(row['canonical_url'])} | {row['fetched_at_utc']} "
                  f"| {_escape(detail[:120])} |")
            w("")

    # --- method note -----------------------------------------------------
    w("## How these sources were retrieved\n")
    w("- Search results came from SearchApi.io; the query, engine, parameters and "
      "the moment of retrieval are recorded per result in the table above.")
    w("- Pages were retrieved through ScrapingBee. The WARC `response` record "
      "therefore holds the answer as delivered by that proxy, not the origin "
      "server's raw answer; the origin facts the proxy reports are stored "
      "alongside it in a concurrent `metadata` record.")
    w("- `origin_status_first` is the **first** status in any redirect chain, not "
      "the status of the document finally retrieved. Successful retrieval is "
      "identified by the absence of an error, not by a status of 200.")
    w("- URLs were canonicalised before deduplication: scheme and host lowercased, "
      "`www.` and fragments dropped, a fixed list of tracking parameters removed. "
      "Every other query parameter was preserved, and the URL as returned by the "
      "search engine is stored unchanged alongside the canonical form.")
    w("- Pages served with a firewall or bot-challenge page instead of the "
      "document were detected, archived as evidence, and excluded from the corpus.")
    w("- A source counts as usable only if text was extracted from it. A page "
      "that was retrieved successfully and contained no article text is reported "
      "as unusable with that as its cause, not counted among the sources.")
    w("- The causes above are derived from what was recorded at retrieval time — "
      "the proxy's status, the block reason, the media type and the extractor's "
      "message — and not from re-inspecting the archived bytes. They are "
      "reproducible from the database, and re-derived whenever this report is "
      "generated, so a corpus reclassifies under a corrected rule without being "
      "retrieved again.")
    if figures:
        w("- Figure descriptions were **generated by a vision model** from the "
          "archived image bytes. They are model output, not text written by the "
          "source, and are stored separately from extracted text together with the "
          "model identifier, the verbatim prompt and the generation timestamp.")
    w("")
    return "\n".join(out)


def report_run(conn: sqlite3.Connection, run_id: str, out_path: Path) -> Path:
    row = conn.execute("SELECT query FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    query = row["query"] if row else run_id
    text = _build(conn, "run_id = :key", run_id, f"Retrieval report — “{query}”")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def report_batch(conn: sqlite3.Connection, batch_id: str, out_path: Path) -> Path:
    text = _build(conn, "batch_id = :key", batch_id, "Retrieval report")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path
