"""Reading a `glr-interchange-v1` package into the grey literature stream.

glr (https://github.com/philipphaindl/glr) retrieves grey literature and emits
one record per document with its search observations nested inside, plus the
three things that make a grey source citable at all: when it was retrieved, the
SHA-256 of the bytes retrieved, and where those bytes are archived. A URL alone
does not survive the page changing, and grey literature changes and disappears
— that is the whole reason the format exists rather than BibTeX or RIS, neither
of which has a field for any of the three.

This module is deliberately free of FastAPI and SQLModel: everything that
decides what a record becomes is a pure function over dicts, so it can be
tested without a database or an HTTP client. The router does the I/O.

Three decisions worth knowing about before reading the code:

**Every record is imported, including the ones that could not be retrieved.**
A package reports blocked, failed and empty retrievals on purpose, so that a
consumer's "records identified" reconciles with glr's own retrieval report.
Dropping them here would silently shrink the PRISMA top box, and the reason a
source could not be read is itself a review finding — grey literature rots, and
a review that cannot say how much of it rotted is hiding a limitation. They
arrive with `full_text_inaccessible` set and their cause recorded.

**Deduplication is exact only.** Two records are the same source if they share
a canonical URL or a payload hash; nothing is matched on title. The BibTeX path
can match on title+venue because a journal name is a stable, curated string. A
grey title is whatever the page's `<title>` said — routinely carrying the site
name, a section, or "| LinkedIn" — and the venue is a hostname, so the same
document on two hosts and two different documents with a generic title are
indistinguishable by that test. A false duplicate removes a source from a
review silently; an undetected one is visible at screening. The conservative
direction is the right one here, and glr documents the same limit for its own
deduplication.

**The extracted text is not stored.** ReviQ screens on title and abstract, the
snippet takes the abstract's role, and a source's full text can run to tens of
thousands of words. The archive reference and the URL are the pointer to it.
"""
from __future__ import annotations

import json
import re
from typing import Any

SCHEMA = "glr-interchange-v1"

# The reserved `source` prefixes from app.services.streams. Repeated as a
# derivation rather than an import so the mapping stays a pure function, and
# asserted against the originals in the tests.
GREY_SEARCH_PREFIX = "grey:"
GREY_SNOWBALL_PREFIX = "grey-snowball:"

# glr's `discovery` vocabulary: how a document entered its corpus.
SERP = "serp"

# Grey literature is rarely older than the web and never newer than the run.
MIN_YEAR, MAX_YEAR = 1900, 2100


class GreyImportError(ValueError):
    """The uploaded file is not a package this importer can read."""


def parse_package(raw: bytes | str) -> dict:
    """Validate an uploaded package and return it.

    The schema check is not ceremony. Every field this importer reads is
    positioned by that contract, and a JSON file that merely happens to have a
    `records` key would import silently as nonsense — with a provenance trail
    that looks authoritative precisely because it came from a file.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        package = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GreyImportError(f"not valid JSON: {exc}") from exc

    if not isinstance(package, dict):
        raise GreyImportError("expected a JSON object at the top level")

    schema = package.get("_schema")
    if schema != SCHEMA:
        raise GreyImportError(
            f"expected a {SCHEMA} package, got {schema!r}. "
            f"Produce one with: glr export-json <run_id|batch_id> --out records.json"
        )
    if not isinstance(package.get("records"), list):
        raise GreyImportError("the package has no `records` list")
    return package


def engine_of(package: dict) -> str:
    """The search engine the package's runs used, for the `source` label.

    Taken from the package rather than asked of the user: the runs record which
    engine actually answered, and a hand-typed label could contradict it. A
    package whose runs used more than one engine reports `mixed` — the per-run
    detail stays in the retrieval report on the glr side.
    """
    engines = {
        (run or {}).get("engine")
        for run in package.get("runs", [])
        if (run or {}).get("engine")
    }
    # `none` is what a `glr refetch` run records: it issued no search. It says
    # nothing about where the documents came from, so it must not become the
    # label for them.
    engines.discard("none")
    if len(engines) == 1:
        return next(iter(engines))
    return "mixed" if engines else "unknown"


def source_label(record: dict, engine: str) -> str:
    """`grey:google` or `grey-snowball:google`.

    The prefixes are the reserved ones `app.services.streams` tests for, so a
    grey record is recognised as grey by every reader without this module being
    consulted.
    """
    prefix = GREY_SEARCH_PREFIX if is_search_discovered(record) else GREY_SNOWBALL_PREFIX
    return f"{prefix}{engine}"


def is_search_discovered(record: dict) -> bool:
    """True when a search engine returned this document, rather than a link.

    glr calls these `serp` and `link`; ReviQ calls them `search` and
    `snowball`. Both are the same distinction — two sampling mechanisms with
    different biases, which an MLR has to report separately (Wohlin 2014).
    """
    return (record.get("discovery") or SERP) == SERP


def year_of(publication_date: Any) -> int | None:
    """A four-digit year out of whatever the extractor produced.

    trafilatura returns the date as it found it: `2024`, `2024-03-15`,
    `March 2024`, and sometimes a string with no date in it at all. Parsing
    into a year here rather than storing the raw string is a loss, but `year`
    is what a review sorts and filters on; the verbatim string stays in the
    package the import came from.
    """
    if publication_date is None:
        return None
    for candidate in re.findall(r"\d{4}", str(publication_date)):
        year = int(candidate)
        if MIN_YEAR <= year <= MAX_YEAR:
            return year
    return None


def title_of(record: dict) -> str:
    """A title that is never empty.

    glr already falls back from the extracted title to the one the search
    engine displayed, which is what leaves even an unretrievable record
    screenable on title and snippet. When both are absent the URL is the
    honest remaining answer — `Paper.title` cannot be null, and inventing
    "Untitled" would put a placeholder where a reviewer expects a source.
    """
    title = (record.get("title") or "").strip()
    return title or (record.get("canonical_url") or "").strip() or "(no title)"


def is_retrievable(record: dict) -> bool:
    """True when the source was retrieved and yielded text."""
    return (record.get("retrieval_status") or "") == "ok"


def record_to_paper_dict(record: dict, engine: str) -> dict:
    """The `Paper` fields for one glr record.

    `venue` is the host. For grey literature the publishing organisation is
    the venue in every sense a review cares about — `oecd.org`, `gartner.com`,
    `who.int` is exactly the breakdown a source-type analysis needs — and
    leaving it empty would drop grey sources out of every venue table.
    """
    return {
        # Stable across databases: the same page yields the same key for two
        # people running the same protocol, which is what makes decisions about
        # a source exchangeable. Identity is still the canonical URL.
        "citekey": record.get("record_key") or "",
        "doi": None,                       # grey literature has none, by definition
        "title": title_of(record),
        "authors": record.get("author"),
        "year": year_of(record.get("publication_date")),
        "venue": record.get("host"),
        # The snippet, not the extracted text: it is what a screener saw in the
        # search results, which is the role an abstract plays at this phase.
        "abstract": record.get("snippet"),
        "keywords": None,
        "entry_type": "online",
        "source": source_label(record, engine),
        "stream": "grey",
        "discovery": "search" if is_search_discovered(record) else "snowball",
        "dedup_status": "original",
        # Declared by the document, never guessed — see glr's D24.
        "language": record.get("language"),
        "full_text_url": record.get("source_url") or record.get("canonical_url"),
        "full_text_inaccessible": not is_retrievable(record),
    }


def record_to_provenance_dict(record: dict) -> dict:
    """The `GreySource` fields: what makes this record citable and checkable.

    Kept beside `Paper` rather than inside it because it belongs to the
    retrieval, not to the review. A paper is a paper whether it came from
    Scopus or from a ministry's website; only the grey one has a payload
    digest and an archive offset, and only for the grey one does "when was this
    read" change what may be claimed about it.
    """
    warc = record.get("warc") or {}
    observations = record.get("observations") or []
    ranks = [o.get("global_rank") for o in observations if o.get("global_rank")]
    return {
        "record_key": record.get("record_key") or "",
        "canonical_url": record.get("canonical_url") or "",
        "source_url": record.get("source_url"),
        "host": record.get("host"),
        "retrieved_at_utc": record.get("retrieved_at_utc"),
        "sha256": record.get("sha256"),
        "media_type": record.get("media_type"),
        "content_length": record.get("content_length"),
        "word_count": record.get("word_count"),
        "archive_filename": warc.get("filename"),
        "archive_offset": warc.get("offset"),
        "archive_record_id": warc.get("record_id"),
        "retrieval_status": record.get("retrieval_status"),
        # Why a source yielded nothing, in glr's vocabulary: a publisher's
        # access control, a platform post that was never a document, a dead
        # link. Those are different exclusion criteria, and a review that
        # reports them as one number cannot defend any of them.
        "retrieval_reason": record.get("retrieval_reason"),
        "search_observations": len(observations),
        "best_rank": min(ranks) if ranks else None,
    }


def dedup_key_of(record: dict) -> tuple[str | None, str | None]:
    """The two exact identities a record can be recognised by."""
    url = (record.get("canonical_url") or "").strip().lower() or None
    sha = (record.get("sha256") or "").strip().lower() or None
    return url, sha


def partition(
    records: list[dict],
    known_urls: set[str],
    known_hashes: set[str],
) -> tuple[list[dict], list[dict]]:
    """Split records into new and duplicate, exactly.

    The two sets are mutated as the walk proceeds, so a package that contains
    the same source twice — glr deduplicates within a package, but two packages
    for overlapping query sets do not — resolves the second occurrence against
    the first rather than importing both.

    A record with neither a URL nor a hash cannot be recognised, and is treated
    as new: an unidentifiable record is not evidence of duplication.
    """
    unique: list[dict] = []
    duplicates: list[dict] = []
    for record in records:
        url, sha = dedup_key_of(record)
        if (url and url in known_urls) or (sha and sha in known_hashes):
            duplicates.append(record)
            continue
        if url:
            known_urls.add(url)
        if sha:
            known_hashes.add(sha)
        unique.append(record)
    return unique, duplicates


def package_metadata(package: dict, filename: str | None = None) -> dict:
    """The `GreyImport` fields: which package these papers came from.

    `canonicalization` is carried because glr pins the algorithm that produced
    every `canonical_url` in the package, and warns a consumer never to
    re-canonicalise with its own copy. Recording which version produced these
    keys is what lets a later ReviQ notice that two imports are not comparable
    instead of joining them anyway.
    """
    scope = package.get("scope") or {}
    counts = package.get("counts") or {}
    tool = package.get("tool") or {}
    return {
        "schema_version": package.get("_schema"),
        "canonicalization": package.get("canonicalization"),
        "tool_name": tool.get("name"),
        "tool_version": tool.get("version"),
        "exported_at_utc": package.get("_exported_at"),
        "scope_kind": scope.get("kind"),
        "scope_id": scope.get("id"),
        "filename": filename,
        "records_in_package": len(package.get("records") or []),
        "documents_reported": counts.get("documents"),
        "usable_reported": counts.get("ok"),
        "queries": len(package.get("runs") or []),
    }


def reason_breakdown(records: list[dict]) -> dict[str, int]:
    """How many records each retrieval cause accounts for, most frequent first.

    Reported back from the import so the number that lands in a PRISMA
    "not retrieved" box can be traced to its causes without opening the file
    again.
    """
    counts: dict[str, int] = {}
    for record in records:
        reason = record.get("retrieval_reason")
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
