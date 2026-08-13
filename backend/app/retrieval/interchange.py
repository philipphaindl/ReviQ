"""A provenance-carrying export of a run or batch.

The CSV in `export.py` is *observation-shaped*: one row per SERP hit, so a URL
that ranked for three queries produces three rows. That is the right shape for
a spreadsheet of search results and the wrong shape for handing a corpus to
another tool, which needs one record per document with its observations nested
inside. The two queries are therefore separate on purpose — sharing them would
reintroduce exactly the bug `export.py`'s docstring warns about.

Why JSON and not BibTeX or RIS: no field in either carries a retrieval
timestamp, a payload digest and an archive offset without abusing `note`. For
grey literature those three *are* the citation — a URL alone does not survive
the page changing.

Nothing is filtered out here. Blocked and failed retrievals are exported with
a `retrieval_status`, because a consumer's "records identified" must reconcile
with this tool's own retrieval report; deciding what to screen is a review
decision and belongs downstream. Each carries a `retrieval_reason` as well —
the status says a document is missing, the reason says whether that was a
publisher's access control, a platform page that never held a document, or a
dead link, and those are three different exclusion criteria in a protocol.

`retrieval_reason` and `counts.reasons` were added after `glr-interchange-v1`
was first published. The schema string is unchanged because both are additive
and optional: a consumer written against the original shape reads these
packages unmodified, and one that wants the cause finds it. The version will
be bumped when a field changes meaning or disappears, not when one is added.

The WARC files do not travel with the package — a few hundred documents run to
hundreds of megabytes. `archive[]` lists them by basename with their own
SHA-256, so a reader can verify they hold the right file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from . import db, urls
from .outcome import BLOCKED, EMPTY, FAILED, NOT_FETCHED, OK, classify

SCHEMA = "glr-interchange-v1"

# Pins the algorithm that produced every `canonical_url` in the package. A
# consumer deduplicates on those strings and must never re-canonicalise with
# its own copy of `urls.py`, which may be a different version. Bump this
# whenever the canonicalisation rules or TRACKING_PARAMS change.
CANONICALIZATION = "glr.urls.canonicalize/1"

# Length of the hash half of a record key. 48 bits: at 10,000 records the
# probability of any collision is about 2e-10.
KEY_HASH_CHARS = 12
KEY_HOST_CHARS = 24

# The `retrieval_status` values are defined in outcome.py, next to the
# classifier that produces them, and re-exported here because they are part of
# this package's contract with a consumer.
__all__ = [
    "SCHEMA", "CANONICALIZATION", "OK", "BLOCKED", "FAILED", "EMPTY",
    "NOT_FETCHED", "record_key", "build_package", "write_package", "resolve_scope",
]


# --- record identity ------------------------------------------------------


def _host_slug(host: str | None) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in (host or "").lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:KEY_HOST_CHARS] or "unknown"


def record_key(canonical_url: str, host: str | None = None) -> str:
    """A stable, human-recognisable identifier for one document.

    `oecd-org-3f2a91c07be4`. Deliberately not called a citekey: this module
    knows nothing about reviews, and the same key serves any consumer.

    The hash is over the canonical URL, so the key is identical in two
    databases that retrieved the same page — which is what makes it usable as
    a join key between people working from the same protocol. A sequential id
    would differ per database and silently mis-join; a title- or author-based
    key would move when extraction is re-run.

    The key is a *label*. Identity is the canonical URL, and a consumer should
    deduplicate on that, so that a changed canonicalisation shows up as a
    renamed record rather than a duplicated one.
    """
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:KEY_HASH_CHARS]
    return f"{_host_slug(host or urls.host_of(canonical_url))}-{digest}"


# --- scope ----------------------------------------------------------------


def resolve_scope(conn: sqlite3.Connection, ident: str) -> tuple[str, list[str]]:
    """Return ("run"|"batch", run_ids) for a run id or a batch id."""
    row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (ident,)).fetchone()
    if row:
        return "run", [ident]

    rows = conn.execute(
        "SELECT run_id FROM runs WHERE batch_id = ? ORDER BY started_at_utc", (ident,)
    ).fetchall()
    if rows:
        return "batch", [r["run_id"] for r in rows]

    raise LookupError(f"no run or batch with id {ident!r}")


# --- assembly -------------------------------------------------------------


def _placeholders(values) -> str:
    return ", ".join("?" for _ in values)


def _runs(conn: sqlite3.Connection, run_ids: list[str]) -> list[dict]:
    rows = conn.execute(
        f"""SELECT r.run_id, r.batch_id, r.query, r.engine, r.search_params_json,
                   r.started_at_utc, r.finished_at_utc, r.tool_version, r.status,
                   r.notes,
                   (SELECT COUNT(*) FROM serp_results s WHERE s.run_id = r.run_id)
                       AS result_count
            FROM runs r
            WHERE r.run_id IN ({_placeholders(run_ids)})
            ORDER BY r.started_at_utc""",
        run_ids,
    ).fetchall()
    out = []
    for row in rows:
        run = dict(row)
        # Stored as a JSON string; inline it so a consumer does not have to
        # parse a string inside a parsed document.
        try:
            run["search_params"] = json.loads(run.pop("search_params_json") or "{}")
        except ValueError:
            run["search_params"] = {}
        out.append(run)
    return out


def document_ids(conn: sqlite3.Connection, run_ids: list[str]) -> list[int]:
    """Documents in scope: observed, retrieved, or linked to, in these runs.

    All three halves are needed, and each covers a case the others miss:

      * a snowballed document has no SERP observation at all;
      * a document archived by an earlier run is observed again here without
        being re-fetched, so it has no snapshot in scope;
      * a document reached by a link but never fetched — the snowball depth
        limit stopped there — has neither, yet the edge to it was recorded and
        a consumer counting identified records would otherwise be short.
    """
    marks = _placeholders(run_ids)
    rows = conn.execute(
        f"""SELECT DISTINCT document_id FROM (
                SELECT document_id             FROM serp_results   WHERE run_id IN ({marks})
                UNION
                SELECT document_id             FROM snapshots      WHERE run_id IN ({marks})
                UNION
                SELECT to_document_id          FROM document_links WHERE run_id IN ({marks})
            )
            WHERE document_id IS NOT NULL""",
        run_ids * 3,
    ).fetchall()
    return [r["document_id"] for r in rows]


def _observations(conn: sqlite3.Connection, document_id: int, run_ids: list[str]) -> list[dict]:
    rows = conn.execute(
        f"""SELECT s.run_id, r.query, r.engine, s.page, s.position, s.global_rank,
                   s.retrieved_at_utc, s.searchapi_search_id, s.displayed_link,
                   s.raw_url, s.title, s.snippet
            FROM serp_results s
            JOIN runs r ON r.run_id = s.run_id
            WHERE s.document_id = ? AND s.run_id IN ({_placeholders(run_ids)})
            ORDER BY s.global_rank""",
        [document_id] + run_ids,
    ).fetchall()
    return [dict(r) for r in rows]


def _figures(conn: sqlite3.Connection, snapshot_id: int) -> list[dict]:
    """Figures with their descriptions.

    `alt_text` and `caption` came from the page markup and are source content.
    `description` is model output. They travel in the same object because they
    describe the same image, and the `kind` marker exists so a consumer cannot
    treat the second as if it were the first.
    """
    figures = conn.execute(
        "SELECT * FROM figures WHERE snapshot_id = ? ORDER BY figure_id", (snapshot_id,)
    ).fetchall()

    out = []
    for fig in figures:
        descriptions = conn.execute(
            """SELECT description, model, prompt, input_tokens, output_tokens,
                      described_at_utc, error
               FROM figure_descriptions WHERE figure_id = ?
               ORDER BY described_at_utc""",
            (fig["figure_id"],),
        ).fetchall()
        out.append({
            "kind": "model_generated",
            "figure": {
                "raw_src": fig["raw_src"],
                "resolved_url": fig["resolved_url"],
                "alt_text": fig["alt_text"],
                "caption": fig["caption"],
                "sha256": fig["sha256"],
                "content_type": fig["content_type"],
                "byte_size": fig["byte_size"],
                "fetch_error": fig["fetch_error"],
                "warc": _warc_ref(fig),
            },
            "descriptions": [dict(d) for d in descriptions],
        })
    return out


def _warc_ref(row: sqlite3.Row) -> dict | None:
    """Locate an archived record.

    `filename` is a basename and `run_id` names the directory. The path as
    recorded is carried too, but only as a note: it is relative to the machine
    that did the retrieval, and a consumer that opened it would be following a
    path out of a data file straight into its own filesystem.
    """
    path = row["warc_path"]
    if not path:
        return None
    return {
        "run_id": row["run_id"],
        "filename": Path(path).name,
        "offset": row["warc_offset"],
        "record_id": row["warc_record_id"],
        "recorded_path": path,
    }


def _archive_entries(conn: sqlite3.Connection, referenced: set[tuple[str, str]]) -> list[dict]:
    """One entry per WARC file the records in this package actually point into.

    Built from the snapshots the records resolved to, not from the runs in
    scope. The two are not the same set: `db.best_snapshot` deliberately looks
    across all runs, so a document observed in this batch may carry a snapshot
    archived by an earlier run — or by a later `refetch`. Listing archives
    by run left those files out, and a reader following `warc.recorded_path`
    found a file with no digest to check it against. Eight of 424 records in
    the pilot corpus pointed at an unlisted file that way.

    `record_count` is a property of the file: how many snapshots are stored in
    it, whichever run they belong to — like `sha256` and `byte_size` beside it.
    """
    entries = []
    for run_id, warc_path in sorted(referenced):
        path = Path(warc_path)
        record_count = conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE warc_path = ?", (warc_path,)
        ).fetchone()[0]
        entry = {
            "run_id": run_id,
            "filename": path.name,
            "record_count": record_count,
            "sha256": None,
            "byte_size": None,
        }
        # Hashing the archive is what lets a reader confirm they hold the file
        # this package describes. A missing file is reported, not raised: the
        # records are still valid provenance without it.
        try:
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
            entry["byte_size"] = path.stat().st_size
        except OSError as exc:
            entry["unavailable"] = f"{type(exc).__name__}: {exc}"
        entries.append(entry)
    return entries


def build_package(
    conn: sqlite3.Connection,
    run_ids: list[str],
    *,
    include_text: bool = True,
    include_figures: bool = True,
    include_unretrievable: bool = True,
) -> dict:
    """Assemble the interchange document for a set of runs."""
    records = []
    counts = {OK: 0, BLOCKED: 0, FAILED: 0, EMPTY: 0, NOT_FETCHED: 0}
    reasons: dict[str, int] = {}
    figures_described = 0
    # Every archive a record points into, collected as the records are built so
    # the listing cannot drift from what they reference.
    referenced_archives: set[tuple[str, str]] = set()
    # Which review's snapshots count, derived from the runs asked for rather
    # than passed in — the same rule `report` applies, so the two go on
    # agreeing about how large the corpus is.
    project_id = db.project_of_runs(conn, run_ids)

    for document_id in document_ids(conn, run_ids):
        doc = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        if doc is None:
            continue

        snapshot = db.best_snapshot(conn, document_id, project_id)
        extraction = None
        if snapshot is not None:
            extraction = conn.execute(
                "SELECT * FROM extractions WHERE snapshot_id = ?",
                (snapshot["snapshot_id"],),
            ).fetchone()

        status, reason = classify(snapshot, extraction, doc["host"])
        if status != OK and not include_unretrievable:
            continue
        counts[status] += 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1

        observations = _observations(conn, document_id, run_ids)
        inbound = conn.execute(
            "SELECT COUNT(DISTINCT from_document_id) AS n FROM document_links WHERE to_document_id = ?",
            (document_id,),
        ).fetchone()["n"]

        record = {
            "record_key": record_key(doc["canonical_url"], doc["host"]),
            "canonical_url": doc["canonical_url"],
            "host": doc["host"],
            "discovery": doc["discovery_source"],
            "discovery_depth": doc["discovery_depth"],
            "first_seen_at_utc": doc["first_seen_at_utc"],
            "inbound_links": inbound,
            "retrieval_status": status,
            # Why, when the status is not `ok`. A consumer reporting exclusions
            # needs the cause, not just the count: a publisher wall, a platform
            # post and a 404 are three different exclusion criteria. See
            # outcome.py for the vocabulary.
            "retrieval_reason": reason,
            "observations": observations,
        }

        # Title falls back through the observations: trafilatura returns None
        # for a title often enough that dropping such records would lose real
        # sources, and a consumer that requires a title needs *something*.
        record["title"] = (
            (extraction["title"] if extraction else None)
            or (observations[0]["title"] if observations else None)
        )

        if snapshot is not None:
            record.update({
                "source_url": snapshot["final_url"] or snapshot["requested_url"],
                "raw_url": snapshot["requested_url"],
                "retrieved_at_utc": snapshot["fetched_at_utc"],
                "sha256": snapshot["sha256"],
                "media_type": snapshot["media_type"],
                "content_type": snapshot["content_type"],
                "content_length": snapshot["content_length"],
                "origin_status_first": snapshot["origin_status_first"],
                "blocked_reason": snapshot["blocked_reason"],
                "fetch_error": snapshot["fetch_error"],
                "credits_cost": snapshot["credits_cost"],
                "warc": _warc_ref(snapshot),
            })
            if snapshot["warc_path"]:
                referenced_archives.add((snapshot["run_id"], snapshot["warc_path"]))
        else:
            record.update({
                "source_url": observations[0]["raw_url"] if observations else None,
                "raw_url": observations[0]["raw_url"] if observations else None,
                "retrieved_at_utc": None,
                "sha256": None,
                "warc": None,
            })

        if extraction is not None:
            record.update({
                "author": extraction["author"],
                # The raw string trafilatura produced ("2024", "March 2024",
                # sometimes noise). Parsing it into a year is a consumer's
                # decision, and one it should be able to revisit.
                "publication_date": extraction["publication_date"],
                "language": extraction["language"],
                "word_count": extraction["word_count"],
                "extractor": extraction["extractor"],
                "extraction_error": extraction["extraction_error"],
            })
            if include_text:
                record["text"] = extraction["text"]

        record["snippet"] = observations[0]["snippet"] if observations else None

        if include_figures and snapshot is not None:
            figures = _figures(conn, snapshot["snapshot_id"])
            if figures:
                record["figures"] = figures
                figures_described += sum(len(f["descriptions"]) for f in figures)
                # Figure bytes are archived too, and follow the same snapshot,
                # so they can land in an out-of-scope file for the same reason.
                for entry in figures:
                    warc = entry["figure"]["warc"]
                    if warc:
                        referenced_archives.add((warc["run_id"], warc["recorded_path"]))

        records.append(record)

    records.sort(key=lambda r: r["record_key"])
    counts["documents"] = len(records)
    counts["figures_described"] = figures_described
    # Sorted by frequency: the first entry is the dominant reason a corpus is
    # smaller than the number of hits, which is the one a methods section has
    # to address.
    counts["reasons"] = dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))

    from .db import utc_now

    return {
        "_schema": SCHEMA,
        "_exported_at": utc_now(),
        "tool": {"name": "glr", "version": _tool_version()},
        "canonicalization": CANONICALIZATION,
        "runs": _runs(conn, run_ids),
        "archive": _archive_entries(conn, referenced_archives),
        "counts": counts,
        "records": records,
    }


def _tool_version() -> str:
    from . import __version__
    return __version__


def write_package(conn: sqlite3.Connection, ident: str, out_path: Path, **options) -> int:
    """Write the package for a run or batch. Returns the number of records."""
    _, run_ids = resolve_scope(conn, ident)
    package = build_package(conn, run_ids, **options)
    package["scope"] = {"kind": _scope_kind(conn, ident), "id": ident}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(package["records"])


def _scope_kind(conn: sqlite3.Connection, ident: str) -> str:
    kind, _ = resolve_scope(conn, ident)
    return kind
