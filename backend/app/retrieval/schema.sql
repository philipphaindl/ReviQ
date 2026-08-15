-- Creel — schema for provenance-preserving grey-literature retrieval.
--
-- Design rule: observations and entities are separate.
--   * A `document` is a canonical URL. It exists exactly once, forever.
--   * A `serp_result` is the observation "this URL ranked at position N for
--     query Q on engine E at time T". It is written fresh on every run.
-- Idempotency follows from that split: re-running a query adds observations
-- and snapshots, never duplicate documents.
--
-- All timestamps are ISO-8601 UTC with a trailing Z. Never local time.

PRAGMA foreign_keys = ON;

-- One CLI invocation.
CREATE TABLE IF NOT EXISTS runs (
    run_id             TEXT PRIMARY KEY,
    query              TEXT NOT NULL,
    engine             TEXT NOT NULL,
    -- Full search parameters (gl, hl, pages, device, ...) so the run can be
    -- described exactly in a methods section.
    search_params_json TEXT NOT NULL,
    started_at_utc     TEXT NOT NULL,
    finished_at_utc    TEXT,
    tool_version       TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    notes              TEXT,
    -- Groups the runs of one `batch` invocation. A run is still exactly
    -- one query, so every existing guarantee holds unchanged; the batch is
    -- just the protocol that issued them together.
    batch_id           TEXT,
    -- The review this run was issued for, and the one place where this package
    -- admits that reviews exist. It is also the only workable place: a
    -- `document` is a URL and belongs to nobody, while a search is something a
    -- project carried out and has to be able to report.
    --
    -- No foreign key. The review side owns `project`, and a retrieval database
    -- lifted out for inspection must still open.
    --
    -- NULL means "issued outside a project" — what the CLI does without
    -- --project, and what every run predating this column is.
    --
    -- Deliberately not indexed: `runs` holds one row per query, and an index
    -- here would have to be created by this file, which cannot run against a
    -- database whose `runs` predates the column (see `db.COLUMN_UPGRADES`).
    project_id         INTEGER
);

-- The stable entity: one row per canonical URL.
CREATE TABLE IF NOT EXISTS documents (
    document_id        INTEGER PRIMARY KEY,
    canonical_url      TEXT NOT NULL UNIQUE,   -- the deduplication key
    host               TEXT,
    first_seen_run_id  TEXT NOT NULL REFERENCES runs(run_id),
    first_seen_at_utc  TEXT NOT NULL,
    -- How this document entered the corpus. 'serp' = returned by a search
    -- engine; 'link' = reached by following a link from another document.
    -- A review must be able to report these separately: they are different
    -- sampling mechanisms with different biases.
    discovery_source   TEXT NOT NULL DEFAULT 'serp'
                       CHECK (discovery_source IN ('serp', 'link')),
    -- 0 for a SERP hit, 1 for a document one link away, and so on.
    discovery_depth    INTEGER NOT NULL DEFAULT 0
);

-- The observation: one row per SERP hit, written fresh on every run.
CREATE TABLE IF NOT EXISTS serp_results (
    serp_result_id      INTEGER PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(run_id),
    page                INTEGER NOT NULL,
    position            INTEGER NOT NULL,   -- position within the page, as reported
    global_rank         INTEGER NOT NULL,   -- (page-1)*results_per_page + position
    raw_url             TEXT NOT NULL,      -- verbatim from the SERP, never normalised
    canonical_url       TEXT NOT NULL,
    title               TEXT,
    snippet             TEXT,
    displayed_link      TEXT,
    retrieved_at_utc    TEXT NOT NULL,      -- when the SERP page was fetched
    searchapi_search_id TEXT,               -- search_metadata.id, the provider-side receipt
    document_id         INTEGER REFERENCES documents(document_id),
    UNIQUE (run_id, page, position)
);

-- One actual retrieval. Versioned: a document may have many snapshots.
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id     INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(document_id),
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    requested_url   TEXT NOT NULL,
    final_url          TEXT,    -- Spb-Resolved-Url: after redirects
    -- Spb-Initial-Status-Code reports the FIRST status in the redirect chain,
    -- not the status of the document finally retrieved. Verified against a
    -- known 301: http://github.com -> 301, resolved to https://github.com/.
    -- Named accordingly, because a column called http_status holding 301 for a
    -- successfully retrieved document invites filtering redirected sources out
    -- of a review by accident.
    origin_status_first INTEGER,
    proxy_status       INTEGER, -- ScrapingBee's own HTTP status
    content_type    TEXT,
    content_length  INTEGER,
    sha256          TEXT,       -- over the raw bytes; NULL when the fetch failed
    media_type      TEXT,       -- html | pdf | other
    fetched_at_utc  TEXT NOT NULL,
    warc_path       TEXT,
    warc_offset     INTEGER,    -- byte offset of the gzip member, for random access
    warc_record_id  TEXT,
    credits_cost    INTEGER,    -- Spb-Cost
    fetch_error     TEXT,       -- retrieval failed outright; NULL on success
    -- Retrieval succeeded but returned a WAF or bot-challenge page instead of
    -- the document. Kept separate from fetch_error because the two mean
    -- different things and both belong in the record: the snapshot is still
    -- archived (it evidences that the source was unreachable at that time),
    -- but the row must not enter a corpus as a source.
    blocked_reason  TEXT,
    UNIQUE (document_id, run_id)
);

-- Extracted text for one snapshot. Re-runnable offline from the WARC.
CREATE TABLE IF NOT EXISTS extractions (
    extraction_id    INTEGER PRIMARY KEY,
    snapshot_id      INTEGER NOT NULL UNIQUE REFERENCES snapshots(snapshot_id),
    extractor        TEXT NOT NULL,   -- e.g. "trafilatura-2.2.0": swapping extractors stays traceable
    title            TEXT,
    author           TEXT,
    publication_date TEXT,
    language         TEXT,
    text             TEXT,
    word_count       INTEGER,
    extracted_at_utc TEXT NOT NULL,
    extraction_error TEXT
);

-- Superseded extractions.
--
-- `extractions` holds one row per snapshot, so re-running extraction against
-- the archived bytes — after an extractor upgrade, or to fill a field that was
-- not being collected before — has to replace it. The replaced row is copied
-- here first, because "nothing is ever overwritten" is the property this tool
-- is built on and a review that quoted the earlier text must still be able to
-- find it.
--
-- A separate table rather than a wider UNIQUE key on `extractions`: SQLite
-- cannot alter a constraint in place, and this file adds tables to an existing
-- database but never columns — it is `CREATE ... IF NOT EXISTS` throughout.
-- This shape upgrades a corpus retrieved months ago on the next connection,
-- which is the normal case here.
CREATE TABLE IF NOT EXISTS extraction_history (
    history_id        INTEGER PRIMARY KEY,
    snapshot_id       INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    extractor         TEXT NOT NULL,
    title             TEXT,
    author            TEXT,
    publication_date  TEXT,
    language          TEXT,
    text              TEXT,
    word_count        INTEGER,
    extracted_at_utc  TEXT NOT NULL,   -- when the superseded extraction ran
    extraction_error  TEXT,
    superseded_at_utc TEXT NOT NULL,
    -- The run that replaced it. `extractions` has no run_id and cannot gain
    -- one, so this is where the chain from an extraction back to the command
    -- that produced it is kept.
    superseded_by_run TEXT NOT NULL REFERENCES runs(run_id)
);

-- The snowballing edge. Kept as its own table rather than a column on
-- documents because a document can be reached from many others, and the
-- provenance of *each* path matters: which snapshot contained the link, and
-- what the anchor text said.
CREATE TABLE IF NOT EXISTS document_links (
    link_id                INTEGER PRIMARY KEY,
    from_document_id       INTEGER NOT NULL REFERENCES documents(document_id),
    to_document_id         INTEGER NOT NULL REFERENCES documents(document_id),
    -- The snapshot the link was read from: the edge is reproducible from the
    -- archive, without re-fetching anything.
    discovered_in_snapshot INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    run_id                 TEXT NOT NULL REFERENCES runs(run_id),
    raw_href               TEXT NOT NULL,   -- verbatim, before resolution
    anchor_text            TEXT,
    depth                  INTEGER NOT NULL,
    discovered_at_utc      TEXT NOT NULL,
    UNIQUE (from_document_id, to_document_id, run_id)
);

-- Figures found in a document, archived like any other retrieval.
CREATE TABLE IF NOT EXISTS figures (
    figure_id       INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(document_id),
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    raw_src         TEXT NOT NULL,   -- verbatim from the markup
    resolved_url    TEXT NOT NULL,
    alt_text        TEXT,
    caption         TEXT,
    sha256          TEXT,
    content_type    TEXT,
    byte_size       INTEGER,
    warc_path       TEXT,
    warc_offset     INTEGER,
    warc_record_id  TEXT,
    credits_cost    INTEGER,
    fetched_at_utc  TEXT NOT NULL,
    fetch_error     TEXT,
    UNIQUE (snapshot_id, resolved_url)
);

-- MODEL OUTPUT, NOT SOURCE CONTENT.
--
-- A description in this table was generated by a vision model from the figure
-- bytes. It is evidence about the figure, not text extracted from the source,
-- and must never be merged into `extractions.text` or quoted as if the source
-- had written it. Everything needed to audit or reproduce a description is
-- stored with it: the exact model id, the verbatim prompt, the timestamp and
-- the token counts. The figure bytes stay in the WARC, so any description can
-- be re-generated, compared against a different model, or checked by hand.
--
-- The UNIQUE constraint versions rather than overwrites: re-describing with a
-- different model or a revised prompt adds a row and leaves the old one intact.
CREATE TABLE IF NOT EXISTS figure_descriptions (
    description_id   INTEGER PRIMARY KEY,
    figure_id        INTEGER NOT NULL REFERENCES figures(figure_id),
    description      TEXT,
    model            TEXT NOT NULL,   -- exact model id, e.g. claude-haiku-4-5
    prompt           TEXT NOT NULL,   -- verbatim, so the output is auditable
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    described_at_utc TEXT NOT NULL,
    error            TEXT,
    UNIQUE (figure_id, model, prompt)
);

CREATE INDEX IF NOT EXISTS idx_figures_document      ON figures (document_id);
CREATE INDEX IF NOT EXISTS idx_figures_snapshot      ON figures (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_descriptions_figure   ON figure_descriptions (figure_id);
CREATE INDEX IF NOT EXISTS idx_document_links_from ON document_links (from_document_id);
CREATE INDEX IF NOT EXISTS idx_document_links_to   ON document_links (to_document_id);
CREATE INDEX IF NOT EXISTS idx_runs_batch          ON runs (batch_id);
CREATE INDEX IF NOT EXISTS idx_documents_discovery ON documents (discovery_source, discovery_depth);
CREATE INDEX IF NOT EXISTS idx_serp_results_run       ON serp_results (run_id);
CREATE INDEX IF NOT EXISTS idx_serp_results_document  ON serp_results (document_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_document     ON snapshots (document_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run          ON snapshots (run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_sha256       ON snapshots (sha256);
CREATE INDEX IF NOT EXISTS idx_extraction_history_snapshot
                                                      ON extraction_history (snapshot_id);
