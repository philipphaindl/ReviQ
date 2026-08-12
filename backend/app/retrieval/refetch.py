"""Selecting the documents a second attempt could improve.

Two kinds of second attempt, and the difference is financial. A **refetch**
goes back to the network and spends ScrapingBee credits. A **reextract** runs
against bytes already sitting in the WARC and costs nothing but CPU. Both are
selected here, by the same rule — ask `outcome.classify` what it recorded —
and `action` picks which.

`db.has_snapshot` already gets most of this right: a failed or blocked
retrieval is not treated as archived, so simply re-running a query picks those
documents up again and leaves the ones that worked alone. What it cannot see is
the third case — a retrieval that succeeded, was archived, and yielded no text.
That row is clean by every column it checks, so it is skipped forever, and the
only way to reach it was `--refetch`, which re-fetches the entire corpus. In
the pilot corpus that meant paying for 424 documents to retry 22.

This module closes that gap by asking `outcome.classify` instead of looking at
columns: a document is a candidate when its best snapshot has no usable text
*and* the recorded cause is one a retry could plausibly change. A platform
video and a 404 are excluded, not because they succeeded, but because no
setting reachable from here would alter the result.

Two things it deliberately does not do:

  * **It does not re-run the search.** The SERP observations of the original
    run are what that run saw at that moment, and re-issuing the query would
    produce a different result set, quietly changing the sample a review is
    built on. A retry is about retrieval, not about sampling.

  * **It does not overwrite anything.** The retry writes a new run and new
    snapshots. The failed attempt stays exactly as recorded, which is what lets
    a report say "unreachable on the 11th, retrieved on the 12th" — and which
    keeps the original run reproducible after the corpus has been improved.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from . import db, interchange
from .outcome import LABELS, classify


class Candidate(NamedTuple):
    document_id: int
    url: str
    host: str | None
    reason: str
    hint: str


class Scope(NamedTuple):
    kind: str            # "run" or "batch"
    documents: int       # documents the original scope covers
    candidates: list[Candidate]


def for_scope(
    conn: sqlite3.Connection, ident: str, *, reasons: set[str] | None = None,
    action: str = "refetch",
) -> Scope:
    """Resolve a run or batch id to its retry candidates.

    Raises LookupError for an unknown id, same as `interchange.resolve_scope`.
    """
    kind, run_ids = interchange.resolve_scope(conn, ident)
    ids = interchange.document_ids(conn, run_ids)
    return Scope(kind, len(ids), select(conn, ids, reasons=reasons, action=action))


def select(
    conn: sqlite3.Connection,
    document_ids: list[int],
    *,
    reasons: set[str] | None = None,
    action: str = "refetch",
) -> list[Candidate]:
    """The documents in scope whose recorded cause `action` could change.

    `reasons`, when given, narrows the selection further — that is what backs
    `glr refetch --only`, for retrying one cause at a time rather than paying
    for every candidate at once.
    """
    out: list[Candidate] = []
    for document_id in document_ids:
        doc = conn.execute(
            "SELECT canonical_url, host FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if doc is None:
            continue

        snapshot = db.best_snapshot(conn, document_id)
        extraction = None
        if snapshot is not None:
            extraction = conn.execute(
                "SELECT * FROM extractions WHERE snapshot_id = ?",
                (snapshot["snapshot_id"],),
            ).fetchone()

        outcome = classify(snapshot, extraction, doc["host"])
        if outcome.retry_action != action:
            continue
        if reasons is not None and outcome.reason not in reasons:
            continue

        # The URL as requested, not the canonical form: canonicalisation drops
        # tracking parameters, and a URL that has to be fetched should be the
        # one the source actually served.
        url = (snapshot["requested_url"] if snapshot is not None else None) \
            or doc["canonical_url"]
        out.append(
            Candidate(document_id, url, doc["host"], outcome.reason, outcome.remedy.hint)
        )
    return out


class Archived(NamedTuple):
    document_id: int
    snapshot_id: int
    url: str
    host: str | None
    warc_path: str
    warc_offset: int
    sha256: str | None
    media_type: str | None


def archived(conn: sqlite3.Connection, document_ids: list[int]) -> list[Archived]:
    """Every document in scope whose bytes are in the archive, whatever its outcome.

    The selection for an extractor-wide re-run, as opposed to
    `select(action="reextract")`, which picks only the documents whose recorded
    cause says extraction is what failed. The two differ where it matters: a
    document that extracted perfectly well still has to be re-read when the
    extractor starts collecting a field it did not collect before, and there is
    no recorded cause on such a document at all. Filling `language` across a
    corpus is exactly that case.

    Blocked snapshots are excluded. Their bytes are archived on purpose — they
    evidence that the source was unreachable — but they are a firewall's page,
    and re-extracting one would only produce a cleaner rendering of a block
    notice for the corpus to trip over.
    """
    out: list[Archived] = []
    for document_id in document_ids:
        snapshot = db.best_snapshot(conn, document_id)
        if snapshot is None or not snapshot["warc_path"]:
            continue
        if snapshot["fetch_error"] or snapshot["blocked_reason"]:
            continue
        doc = conn.execute(
            "SELECT canonical_url, host FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        out.append(Archived(
            document_id=document_id,
            snapshot_id=snapshot["snapshot_id"],
            url=snapshot["requested_url"] or (doc["canonical_url"] if doc else ""),
            host=doc["host"] if doc else None,
            warc_path=snapshot["warc_path"],
            warc_offset=snapshot["warc_offset"] or 0,
            sha256=snapshot["sha256"],
            media_type=snapshot["media_type"],
        ))
    return out


def estimated_credits(
    *, render_js: bool = False, premium_proxy: bool = False,
    stealth_proxy: bool = False,
) -> int:
    """ScrapingBee's published price for one request with these settings.

    An estimate, not a measurement: what is actually charged comes back in
    `Spb-Cost` and is what gets stored (see fetch.py). This exists so
    `--dry-run` can put a number in front of a decision that spends money — the
    escalation from a plain fetch to a stealth proxy is a factor of 75, and
    that belongs in front of the run rather than in the invoice.

    It lives here rather than in fetch.py so that it stays testable without an
    HTTP client, and because the only caller is the retry that has to justify
    its own cost.
    """
    if stealth_proxy:
        return 75
    if premium_proxy:
        return 25 if render_js else 10
    return 5 if render_js else 1


def summarise(candidates: list[Candidate]) -> list[tuple[str, int, str]]:
    """(label, count, hint) per reason, most frequent first — for the dry run."""
    counts: dict[str, int] = {}
    hints: dict[str, str] = {}
    for candidate in candidates:
        counts[candidate.reason] = counts.get(candidate.reason, 0) + 1
        hints[candidate.reason] = candidate.hint
    return [
        (LABELS.get(reason, reason), count, hints[reason])
        for reason, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
