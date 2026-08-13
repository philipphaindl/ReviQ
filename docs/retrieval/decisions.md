# Decisions

Short records of choices that are expensive to reverse or easy to undo by
accident. Each one states what was decided, why, and what would change it.

---

## D1 — Snapshots are stored as WARC

**Decision.** Raw retrieved bytes go into a per-run `snapshots.warc.gz`
(ISO 28500, WARC 1.1) written with `warcio`, gzipped one member per record.

**Why.** WARC keeps HTTP headers together with the payload, carries a payload
digest in-format, and is readable by existing tools (pywb, ReplayWeb.page). A
reviewer can open the archive and see the source as it was retrieved. Loose
files plus a JSON sidecar would have required reinventing all of that, badly.

**Caveat that must appear in any publication using this tool.** Retrieval goes
through ScrapingBee. The WARC `response` record therefore contains the
*proxy's* answer, not the origin server's raw answer. Mitigation: the origin
facts ScrapingBee reports (`Spb-Initial-Status-Code`, `Spb-Resolved-Url`,
`Spb-Cost`) plus the payload SHA-256 are written as a `metadata` record
concurrent to each response, so the WARC alone documents how the retrieval
happened.

**Resolved 2026-08-11.** `Spb-Initial-Status-Code` reports the **first** status
in the redirect chain. Verified directly: `http://github.com` returns
`Spb-Initial-Status-Code: 301` with `Spb-Resolved-Url: https://github.com/`.
ScrapingBee does not report the origin's *final* status at all, so the tool
does not claim it anywhere. Two consequences, both now implemented:

* the column is named `origin_status_first`, not `http_status` — see D8;
* the WARC response record's status line is always `200`, not the redirect
  status — see D8.

---

## D2 — PyMuPDF is not used, on licence grounds

**Decision.** PDF text extraction uses `pdfminer.six` (MIT). PyMuPDF must not
be introduced.

**Why.** PyMuPDF is AGPL-3.0. Linking it would force this tool to AGPL as well,
or require a commercial licence from Artifex. Either outcome defeats the point
of an open, reusable research artefact.

**Cost accepted.** PyMuPDF is roughly 10–50× faster. At ~50 PDFs per run that
is a few seconds, so the trade is not close.

**This is written down because it looks like an easy optimisation.** Anyone
profiling extraction will find PyMuPDF and reach for it. Don't.

---

## D3 — URL canonicalisation is hand-written, not delegated

**Decision.** `src/glr/urls.py` implements canonicalisation on `urllib.parse`,
with an explicit tracking-parameter blocklist, instead of using `courlan`.

**Why.** The failure mode of an over-eager canonicaliser is silent: strip a
content-bearing parameter (`?id=`, `?doc=`, `?report=`) and two distinct
sources merge into one, with no error and one fewer row in the results. In
grey literature those parameters are common. A hand-written canonicaliser is
~50 lines, can be quoted verbatim in a methods section, and is tested against
exactly the cases that must *not* collapse.

`raw_url` is stored next to `canonical_url` in every case, so no normalisation
decision is irreversible.

**Note.** This is a deliberate deviation from `docs/PLAN.md`, which named
`courlan`. The plan's own risk R7 is the reason.

---

## D4 — `host` is recorded, not the registered domain

**Decision.** `documents.host` stores the hostname minus a leading `www.`.

**Why.** Deriving a registered domain correctly requires the Public Suffix List
(`bbc.co.uk` has two suffix labels, `bbc.com` one). A two-label heuristic would
be quietly wrong for exactly the `.gov.uk`, `.co.uk` and `.org.au` domains that
grey literature lives on. Reporting the host is correct; reporting a guessed
registered domain would not be. Add `tldextract` if per-organisation grouping
is ever needed.

---

## D5 — `render_js` defaults to off

**Decision.** ScrapingBee is called with `render_js=false` unless `--render-js`
is passed.

**Why.** The API defaults `render_js` to **true**, which costs 5 credits per
request instead of 1. For a review that mostly retrieves articles, reports and
PDFs, rendering is usually unnecessary. At 50 URLs per run this is 50 credits
instead of 250 — the free tier covers ~20 runs instead of 4.

**Consequence.** JavaScript-heavy pages will extract as empty. That is why the
run prints a warning counting documents with no text: it turns an invisible
data problem into a visible prompt to re-run with `--render-js`.

---

## D6 — Media type comes from the payload, not the header

**Decision.** `detect_media_type()` sniffs the first bytes (`%PDF-`) rather
than trusting `Content-Type`.

**Why.** CMSes and download gateways routinely serve PDFs as `text/html` or
`application/octet-stream`. Trusting the header sends a PDF into the HTML
extractor, which returns nothing — indistinguishable in the output from a page
that genuinely had no content. Five bytes of sniffing removes a whole class of
silent errors.

---

## D7 — Failed retrievals are recorded, not raised

**Decision.** A failed fetch writes a `snapshots` row with `fetch_error` set
and the run continues. Failed fetches do not count as snapshots, so a later run
retries them.

**Why.** In a review, "this source could not be retrieved, here is the status
code and the timestamp" is itself a finding that belongs in the data. Aborting
the run on the first dead link would be both less useful and less honest.

---

## D8 — The redirect status is named for what it is, and kept out of the WARC record

**Decision.** The column is `origin_status_first`, not `http_status`. The WARC
response record's HTTP status line is always `200`.

**Why.** `Spb-Initial-Status-Code` reports the first status of a redirect
chain (D1). Two silent failures followed from treating it as "the status":

1. **A misnamed column corrupts filtering.** Anyone reading a CSV column called
   `http_status` will filter `= 200` to get successful retrievals. Every
   redirected source — DOI resolvers, shortlinks, `http://` → `https://`, the
   normal shape of grey literature references — carries `301` there and would
   vanish from the review with no error and no trace. Use
   `fetch_error IS NULL` to select successful retrievals.
2. **A misstamped WARC record is a malformed record.** Writing `301` into the
   response record's status line produced a record announcing a redirect above
   a full HTML body. The payload is the body served at the *resolved* URL, so
   the record must say `200`. The chain's first status lives in the concurrent
   metadata record as `origin-status-first`.

**Found by** the first real smoke run, not by the test suite — the stub used
during development returned a single status and could not surface either
problem. `test_redirected_response_is_not_stamped_with_the_redirect_status`
now pins the second one.

**Migration.** Databases created before this change:
`ALTER TABLE snapshots RENAME COLUMN http_status TO origin_status_first;`
WARC files written before it carry the wrong status line on redirected records;
re-fetch those documents with `--refetch` if the archive must be exact.

---

## D9 — Soft blocks are detected, flagged, and retried

**Decision.** After extraction, each payload is checked against a list of WAF
and bot-challenge signatures. A match sets `snapshots.blocked_reason`. The
snapshot is still archived, but the document does not count as retrieved and is
fetched again on the next run.

**Why.** A firewall page served with HTTP 200 is the most dangerous retrieval
failure in a review, because every layer reports success: status 200, content
present, SHA-256 computed, WARC record written, text extracted, row in the CSV.
Nothing distinguishes it from a real source. A hard 500 is honest by
comparison — it lands in `fetch_error` and can be counted. A soft block
*falsifies the corpus*.

Found in the first real run: a source returned
"The requested URL was rejected. Please consult with your administrator."
(F5 BIG-IP ASM) with HTTP 200, and the pipeline accepted it as a document.

**Why a length ceiling.** A signature match only counts when the extracted text
is under `MAX_BLOCK_PAGE_WORDS` (200). Block pages are short; a report that
happens to discuss "access denied" is not one. The asymmetry is deliberate:
missing a block page costs one flagged row on the next run, while discarding a
genuine source costs a source, silently — the exact failure this decision
exists to prevent.

**Why not reuse `fetch_error`.** The two mean different things and both belong
in the record. `fetch_error` means nothing was retrieved; `blocked_reason`
means something was retrieved and it was not the document. Keeping them apart
lets a methods section report retrieval failures and access denials separately,
which are different threats to validity.

**Why archive it anyway.** A block page evidences that the source was
unreachable at that timestamp. Discarding it would lose that. The WARC records
what was served; the database records what it means.

**Consequence for `has_snapshot()`.** Blocked documents are not treated as
archived, so a later run with `--premium-proxy` picks up exactly the blocked
sources and nothing else — the same flow that recovered the ResearchGate hit.

**Migration.** `ALTER TABLE snapshots ADD COLUMN blocked_reason TEXT;`
Existing rows are not re-examined; re-run the query to have them checked, or
apply `detect_block_page` to the archived payloads — the WARC makes
re-classification possible without spending credits.

**Validated on real data (2026-08-11).** Nine documents from one query: two
flagged (MITRE behind F5 BIG-IP ASM at 17 words, ResearchGate behind a
Cloudflare challenge at 16 words), seven not flagged, no false positives. Both
flagged payloads sat an order of magnitude below the 200-word ceiling, so the
threshold has comfortable margin.

**Corollary: a block page is worth reading, not just counting.** The
ResearchGate payload said "Verification successful. Waiting for … to respond" —
the challenge had passed and the page was returned before the redirect to the
real content completed. That is a timing problem, not a wall, and it is fixed
by `--wait` at 25 credits rather than by escalating to stealth proxies at 75.
Storing the block page rather than discarding it is what made the distinction
visible.

---

## D10 — Snowballing selects links, it does not follow them

**Decision.** `--snowball-depth N` follows outgoing links, but only those that
survive four rules in `src/glr/links.py`: PDFs always; otherwise off-host only;
known noise dropped; capped per source document, PDFs first.

**Why not follow everything.** Snowballing in the Wohlin (2014) sense follows
*citations* — curated, semantically meaningful edges. An HTML link is not that.
A typical page carries 50–200 outgoing links, overwhelmingly navigation,
footers, social buttons and product pages. Following 10–20 arbitrary links from
100 seeds yields ~1,500 documents of which a small fraction are relevant; at
depth 2 the signal disappears. Cost is not the constraint here (1,500 fetches
is roughly €0.75) — the corpus is.

**Why these four rules.** They came from looking at a real result set. Project
and institutional pages (OWASP, AI.SE) carry high-value outgoing links; vendor
blogs (Gartner, Databricks) carry product links. The rules approximate that
distinction without reading the target:

* a linked PDF in grey literature is usually the document itself — the highest
  precision signal available before fetching;
* an off-host link is the closest structural analogue to a citation, while
  same-host links are navigation far more often than not;
* social platforms, shorteners and `/privacy`-style paths are never sources.

**The asymmetry, again.** Dropping a good link costs a source; keeping a bad
one costs one credit and a row that screening discards. So the rules are
permissive where the cost is low and strict only where the signal is clear.

**Not done, deliberately.** No relevance scoring of link targets before
fetching. That needs to read the target or the surrounding text, which is the
screening problem, and it should be decided on measured relevance rates rather
than assumed. Depth defaults to 0 for the same reason: measure first.

**What the data model records.** `documents.discovery_source` and
`discovery_depth` distinguish the two sampling mechanisms — a review must be
able to report search-engine hits and snowballed documents separately, because
they carry different biases. `document_links` stores each edge with the
snapshot it was read from, so the graph is reproducible from the archive
without re-fetching.

---

## D11 — Query sets are a file, not shell history

**Decision.** `glr batch queries.toml` runs a whole search protocol. One run
per query, grouped by a shared `batch_id`. Unknown keys in the file are errors.

**Why.** Beyond a handful of queries, invoking the CLI per query stops being
reproducible: the protocol lives in shell history instead of in an artefact
that can be read, cited and re-run. The TOML file is what you attach to a
paper.

**Why `tomllib`.** Standard library since 3.11, so the config system costs no
dependency.

**Why unknown keys are fatal.** A typo like `page` for `pages` in a search
protocol produces a silently different review. There is no safe way to ignore
it.

**Why a failed query does not abort the batch.** Nineteen of twenty queries
succeeding is a result worth keeping; the failure is recorded on its own run
row and reported in the summary.

---

## D12 — OCR is opt-in and isolated

**Decision.** `--ocr` OCRs PDFs that have no text layer, via `pypdfium2` for
rasterising and `pytesseract`. Both live in the `ocr` extra, and a missing
install degrades to a recorded extraction error.

**Why opt-in.** It needs a tesseract binary on the system, which no Python
package manager can install. Making it mandatory would break `uv sync` for
everyone who does not need it.

**Why pypdfium2.** PyMuPDF would be the obvious rasteriser and is excluded for
the same reason as D2: AGPL-3.0. pypdfium2 is BSD/Apache and ships wheels, so
it adds no further system dependency.

**Relevance.** Scanned PDFs are common in exactly the sources grey literature
review targets — government reports, older whitepapers, standards drafts.
Without OCR those are recorded as retrieved but empty.

**Unverified.** This is the one piece the offline test harness could not
exercise, because the packages are not installable in the build environment.
The dispatch path is tested; the OCR itself is not.

---

## D13 — Figure descriptions are model output, stored apart from source text

**Decision.** `--describe-figures` selects figures from a page, archives their
bytes in the run's WARC, and describes them with a vision model. Descriptions
go in `figure_descriptions` — never in `extractions.text`.

**Why the separation is the whole point.** A generated description is evidence
*about* a figure, not something the source wrote. Merging the two would let a
review quote a model's words as if a source had published them, and nothing
downstream could tell the difference. Two tables make that mistake impossible
rather than merely discouraged.

**What makes a description defensible.** Three properties, all enforced by the
schema:

* **The input is archived.** Figure bytes go into the WARC like any other
  retrieval, so a description can be re-generated, compared against another
  model, or simply looked at. A description whose input is gone is an
  unfalsifiable claim.
* **The generator is recorded** — exact model id, verbatim prompt, timestamp,
  token counts. A reader can see what the model was asked for.
* **It versions, never overwrites.** `UNIQUE (figure_id, model, prompt)` means
  re-describing with a different model or a revised prompt adds a row and
  leaves the old one intact — the same rule that governs snapshots.

**The prompt is part of the method.** It constrains the model to the
observable — figure type, labels, named levels, explicit values — and forbids
interpretation, because a review cannot cite "this figure suggests…" as
evidence. It also asks for the literal string `NO SUBSTANTIVE CONTENT` when the
image is a logo or decoration, so non-figures are filterable in SQL rather than
by guessing at prose.

**Selection, not description-of-everything.** A page carries far more images
than figures. `src/glr/figures.py` drops furniture by path marker, drops
declared-small images, drops vector and tiny payloads, and prefers images with
alt text or a `<figcaption>` — an author who captioned an image thought it
mattered. Same asymmetry as elsewhere: a missed figure costs one diagram; a
described logo costs one cheap call and a row saying `NO SUBSTANTIVE CONTENT`.

**Model default.** `claude-haiku-4-5` ($1/$5 per MTok), overridable with
`--vision-model`. At roughly 1,600 input tokens per image this is well under a
cent per figure; the tier is the user's decision, not the tool's.

**Opt-in.** This is the only feature that sends content to a third party and
costs money per item, so it sits behind its own extra and its own flag.

---

## D14 — The retrieval report is a deliverable, not a debug dump

**Decision.** `glr report <run_id|batch_id>` writes a Markdown access log: every
source with its retrieval timestamp, SHA-256 and archive location, every
unreachable source with its reason, and a method note.

**Why Markdown.** It is what goes into a paper appendix, a repository, or a
supplementary file, and it renders everywhere without tooling.

**Why the failures get their own section.** "These sources could not be
retrieved, here is when and why" is a quantified limitation. Reporting only
what worked turns a measurable threat to validity into an invisible one.

**Why the method note is generated, not written by hand.** The caveats that
must accompany these numbers — the WARC holds the proxy's answer, the status
column is the first of a redirect chain, canonicalisation stripped this
specific list of parameters, block pages were excluded — are properties of the
tool, not of the reviewer's memory. Generating them means they cannot be
forgotten, and they update when the tool does.

---

## D15 — Search-engine plumbing is filtered at the SERP boundary

**Decision.** `serp.is_non_source()` drops Google redirect wrappers
(`google.com/goto?url=…`, `/url?q=`, `/aclk`), ad-service hosts and cache URLs
before they ever become documents.

**Why.** They appeared three times in a single 20-query pilot. The target is an
opaque token, ScrapingBee rejects the host outright, and each one costs a wasted
fetch plus a permanent junk row in `documents`. They are not sources, so the
right place to drop them is where they enter — not downstream, where a reader
would have to work out why a document has no content.

## D16 — A separate, entity-shaped interchange format

`export.py` produces one CSV row per SERP observation. That is the right shape
for a spreadsheet of search results and the wrong shape for handing a corpus to
another tool: a URL that ranked for three queries would be imported as three
sources. `interchange.py` therefore has its own queries — one record per
document, observations nested — rather than reusing `export.py::_QUERY`.
Sharing them would reintroduce exactly the bug that query's docstring warns
about, one layer up.

JSON rather than BibTeX or RIS: neither carries a retrieval timestamp, a
payload digest and an archive offset without abusing `note`, and for a grey
source those three *are* the citation.

The WARC files do not travel with the package — a few hundred documents run to
hundreds of megabytes. `archive[]` lists them by basename with their own
SHA-256, so a reader can confirm they hold the file the records describe. The
path as recorded is carried too, but marked as a note: it is relative to the
machine that did the retrieval, and a consumer that opened it would be
following a path out of a data file into its own filesystem.

Nothing is filtered out. Blocked and failed retrievals are exported with a
`retrieval_status`, because a consumer's "records identified" has to reconcile
with this tool's own retrieval report; deciding what to screen is a review
decision and belongs downstream.

The envelope pins `canonicalization` and `tool.version`. A consumer must
deduplicate on the `canonical_url` strings in the file and never re-derive them
with its own copy of `urls.py`, which may be a different version with different
`TRACKING_PARAMS`.

## D17 — `record_key`, not `citekey`

Each record carries `<host-slug>-<12 hex of sha256(canonical_url)>`, e.g.
`oecd-org-3f2a91c07be4`.

The requirement that rules out the alternatives is stability *across
databases*. Two people running the same protocol get different row ids, so a
sequential key would name different documents on each side — and a tool that
exchanges screening decisions by key would apply one person's judgement to the
other's unrelated source, silently. An author+year key moves whenever
extraction is re-run, because `author` is extractor output and often absent.
A title-based key collides constantly: grey literature is full of documents
called "Annual Report 2024".

Named `record_key` rather than `citekey` on purpose. This module knows nothing
about reviews, and the same export has to serve a consumer doing supplier or
topic research, where "cite key" would be the wrong word for the same string.

The key is a label; identity is the canonical URL. If canonicalisation ever
changes, the key moves for an unchanged document — which is why the envelope
pins the algorithm and why consumers deduplicate on the URL, so the change
surfaces as a rename rather than a duplicate.

## D18 — WAL, and SIGTERM marks a run failed

`db.connect` sets `journal_mode=WAL` and `busy_timeout=5000`. A long run holds
the database for minutes; under the default rollback journal any concurrent
reader gets "database is locked" for the duration. WAL lets a reader proceed
against the last committed state, which is what a progress display needs.

`cli.main` maps SIGTERM to `KeyboardInterrupt` so that a supervisor stopping
the process — a container shutting down, a UI cancelling a job — leaves the run
marked `failed` rather than `running` for ever. Note that the existing
`except Exception` would not have caught either signal path.

## D19 — Credentials scrubbed before an error string is stored

Error strings from this tool do not stay in a terminal: they reach
`snapshots.fetch_error`, the CSV, the Markdown report, and eventually a
browser. The ScrapingBee key travels as a query parameter, so it is part of a
request URL.

No leak is demonstrated: httpx does not put the URL into the string form of its
ordinary transport errors, and `raise_for_status()` is never called. `redact.py`
exists so the property does not depend on that continuing to hold, nor on what
a third party echoes back in an error body. Redaction is exact substring
replacement with a minimum length, because a smarter version would have cases
where it does not fire.

## D20 — Opening a database brings it up to the current schema

`db.connect` applies `schema.sql` on every connection, not only on `glr init`.

The failure that prompted it: a pilot corpus retrieved before `figures` and
`figure_descriptions` existed made both `glr export-json` and `glr report` die
with `no such table: figures`. Neither command has any business failing there —
the database's only fault was being older than the code reading it, and in this
tool that is the normal case. A corpus retrieved months ago is exactly what a
review comes back to.

Every statement in `schema.sql` is `CREATE ... IF NOT EXISTS`, so applying it to
a populated database only adds what is missing. An empty `figures` table is the
honest answer for a corpus retrieved before figures were collected: there really
are none.

The limit is worth stating: this adds tables and indexes, not *columns*. SQLite
has no `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so a column-level change (the
`http_status` → `origin_status_first` rename in D8) still has to be applied by
hand and called out in the release notes.

## D21 — Why a retrieval failed is derived, not stored

`retrieval_status` says a document is missing from the corpus. It does not say
why, and the difference decides both what a methods section may claim and what
is worth spending credits on again.

The pilot corpus made the cost of the omission concrete. Of 424 documents, 66
were unusable, reported as "39 failed, 22 empty, 5 blocked" — which reads as a
defective tool. The causes underneath were not one thing at all: 32 were
publisher access control (sciencedirect, researchgate, SSRN, Emerald, ACM), 7
were platform pages that never held a document (facebook, youtube, instagram),
13 were repository landing pages that delivered no article text, 4 were dead
links, 3 were requests the proxy itself declined. Those are four different
sentences in a paper and two different decisions about money, and none of them
could be written from the status alone.

`outcome.py` derives a `retrieval_reason` from facts already recorded — the
proxy's status, the block reason, the media type, the host, the extractor's
message. Deriving rather than storing has three consequences worth having:

* A corpus retrieved months ago reclassifies under a corrected rule without a
  byte being fetched again. This is the same property `extractions` already has
  against the WARC, and it is why the pilot corpus could be reclassified after
  the fact rather than re-run.
* It needs no new column, which matters because D20 leaves column-level
  upgrades manual.
* The recorded facts stay the record. A reason is an interpretation, and
  interpretations belong where they can be revised.

The classifier is conservative on purpose. It does not sniff archived bytes to
guess whether a page was client-rendered: a wrong guess would be laundered into
a methods section as a fact, and `no_main_content` — honest about not knowing —
is the better failure mode.

Each reason carries a remedy naming `refetch`, `reextract` or nothing. The
distinction is financial: `refetch` spends ScrapingBee credits, `reextract`
runs against bytes already in the WARC. A single "retryable" flag would invite
paying to download a scanned PDF again in order to OCR it.

## D22 — A retry is a new run, and it does not search again

`glr refetch <run_id|batch_id>` re-fetches only the documents whose recorded
cause a second attempt could change.

The gap it closes was invisible by construction. `db.has_snapshot` deliberately
treats failed and blocked retrievals as not archived, so re-running a query
picks those up and leaves what worked alone. What it cannot see is a retrieval
that *succeeded*, was archived, and yielded no text: that row is clean by every
column it checks, so it was skipped for ever. The only way to reach those 22
documents was `--refetch`, which re-fetches all 424.

Two constraints define the command:

**It issues no search.** The SERP observations of a run are what that engine
returned at that moment. Re-issuing the query to retry a retrieval would return
a different result set and quietly change the sample the review is built on. A
retry is about retrieval, not about sampling.

**It writes a new run and overwrites nothing.** The failed attempt stays as
recorded, which is what lets a report say "unreachable on the 11th, retrieved
on the 12th" and keeps the original run reproducible after the corpus improved.
Re-exporting the original scope picks up the better snapshot through
`db.best_snapshot`, so the improvement arrives without the run being rewritten.

`--dry-run` prints the candidates by cause and an estimated credit cost before
anything is spent. The escalation from a plain fetch to a stealth proxy is a
factor of 75, and that belongs in front of the decision rather than in the
invoice.

## D23 — One rule for which snapshot represents a document

`db.best_snapshot` — a clean retrieval beats a blocked or failed one, most
recent wins among equals — is now the only rule, used by `glr export-json`,
`glr report` and `glr refetch` alike.

It was not always one rule, and the two that existed disagreed. The export
resolved a document across all runs; the report took every snapshot whose run
was in scope. Three consequences, all of them wrong:

* A document that failed for query 1 and succeeded for query 5 of the same
  batch appeared twice in the report, counted twice in the total, and was
  listed as failed and usable at once.
* After a `glr refetch`, the export showed the recovered document and the
  report still showed the failure, because the retry's run was not in scope.
* The report joined snapshots inner, so a document the search identified but
  never fetched vanished from it entirely, while the export counted it as
  `not_fetched`.

The two documents describe the same corpus. A reviewer who counts sources in
the report and records in the export has to get the same number, and that
property is the reason unretrievable records are exported at all (D16).

The report's summary line is now "Total identified" rather than "Total
attempted": it includes documents that were identified and never fetched, and
it reconciles with `counts.documents` in the export by construction.

## D24 — Language is the one the document declares

`extractions.language` holds the language a document states about itself —
`<html lang>`, a `content-language` header equivalent, or `og:locale`, in that
order of precedence — and nothing else.

It was empty for all 358 usable documents of the pilot corpus. trafilatura
fills its `language` field only when a language-detection package is installed,
and this project does not depend on one, so the column existed and never held
anything. Language is a standard inclusion criterion for a multivocal review
(Garousi et al. 2019), which makes an always-empty column a silent hole in the
protocol rather than a cosmetic gap.

Detection was rejected in favour of declaration, and not only to avoid a
dependency. Mixing the two would put a detected value and a declared one in the
same column with no way to tell them apart, in a field that feeds an inclusion
decision. A declaration is weaker evidence, but it is evidence with a source: it
sits in the archived bytes, it is reproducible offline, and a methods section
can state exactly what it means. Adding detection later is a new field, not a
change to this one.

Junk declarations — empty values, `x-default` pasted from an `hreflang`, an
unrendered template placeholder — are rejected rather than stored. A junk value
would silently pass a "documents in English only" filter; an absent one shows
up as unknown.

PDFs carry a `/Lang` entry in their catalog that this does not read. They stay
unknown rather than guessed at: 71 of 424 documents in the pilot corpus.

## D25 — `archive[]` lists what the records point into

The archive listing in an interchange package is built from the snapshots the
records actually resolved to, not from the runs in scope.

The same shape of bug as D23, in a second place. Records resolve their snapshot
with `db.best_snapshot`, which looks across all runs on purpose; `archive[]`
was collected with `WHERE run_id IN (scope)`. A document observed in this batch
but archived by an earlier run — or by a later `glr refetch` — therefore carried
a `warc.recorded_path` to a file the package did not list. Eight of 424 records
in the pilot corpus did exactly that, and the package promises the opposite:
that a reader can verify they hold the right archive by its SHA-256.

Collecting the paths while the records are built, rather than by a second
query, makes the listing unable to drift from what the records reference.
Figures are included in the same pass, since figure bytes follow the same
snapshot and land in the same file.

`record_count` now means how many snapshots are stored in that file, whichever
run wrote them — a property of the file, like `sha256` and `byte_size` beside it.

## D26 — Re-extraction replaces, and keeps what it replaced

`glr reextract` re-reads documents out of the WARC and extracts them again. No
network access, no credits — the bytes are already owned.

This redeems a promise the design made from the start and never exercised: the
archive is written *before* anything is extracted, precisely so extraction can
run again later. Until now nothing could, and a corpus stayed frozen at
whatever the extractor of the day produced. The concrete cost: `language` was
empty for all 358 usable documents of the pilot corpus, and fixing the
extractor (D24) did nothing for them, because a fix to extraction only reaches
documents extracted after it.

**Two selections, because they answer different questions.** Without `--all`,
only documents whose recorded cause points at extraction — a scanned PDF, an
extractor crash. With `--all`, every archived document in scope. The second is
what an extractor change calls for, and it cannot be derived from the recorded
causes: a document that extracted perfectly well still has to be re-read when
the extractor starts collecting a field it did not collect before, and no cause
was ever recorded against it.

Block pages are excluded from both. Their bytes are archived on purpose — they
evidence that the source was unreachable — but they are a firewall's page, and
re-extracting one would only produce a cleaner rendering of a block notice for
the corpus to trip over.

**The replaced extraction is kept.** `extractions` has `UNIQUE(snapshot_id)`,
so re-extraction has to replace, and that is the only operation in this tool
that touches a content-bearing row. It is defensible only because the row it
replaces is copied to `extraction_history` first, with the run that superseded
it: a review that quoted the earlier text must still be able to find it.

A separate table rather than a wider unique key: SQLite cannot alter a
constraint in place, and D20 is explicit that schema.sql adds tables to an
existing database but not columns. This shape upgrades a corpus retrieved
months ago on the next connection, which is the normal case here. The columns
copied are enumerated from `db.EXTRACTION_FIELDS`, so a column added to
`extractions` is carried by default rather than silently dropped on the next
re-extraction — a test asserts the two stay in step.

**The archive read verifies the digest.** `archive.read_payload` is given the
`sha256` recorded beside the offset and refuses if the bytes do not match. The
point of storing a digest next to a location is that the pair can disagree: an
archive rewritten, truncated or restored from the wrong backup would otherwise
feed a corpus content the database describes incorrectly, and every claim
resting on that document would be quietly wrong. Refusing is the only safe
answer, and one document refusing must not stop the other 379 — so every
failure the archive layer can raise is wrapped into one error type the caller
reports and moves past.

**A re-extraction that loses text is reported as a warning, not a statistic.**
If a document had 2,400 words and now has none, the extractor has regressed on
it and the corpus just lost a source. That is louder than a changed count.

## D27 — One database, and the retrieval side upgrades its own columns

Retrieval kept its own SQLite file while it was a separate tool. It does not
any more: it opens ReviQ's, at the path derived from `DATABASE_URL`. The reason
is not tidiness. The replication package bundles `project.json` *plus the raw
`.bib` files* — it deliberately carries the source material, not only the
derived state. For grey literature the counterpart is the retrieval itself, and
two databases mean two backup stories and a package that omits the evidence it
exists to document.

Two access layers on one file — SQLAlchemy for the review, raw `sqlite3` for
the retrieval — are safe under WAL, which `db.connect` sets. The table names do
not collide: SQLModel names its tables from class names and gets `project`,
`paper`, `greysource`; `schema.sql` names its own and gets `runs`, `documents`,
`snapshots`.

**`retrieval_db_path` raises for an in-memory URL rather than falling back.**
The test suite builds instances on `sqlite://` with a StaticPool, which a raw
sqlite3 connection cannot join. Quietly opening some default file instead would
hand a test a retrieval side belonging to nobody, and the test would pass.
`make_instance(db_path=...)` is how a test that needs both halves asks for a
real file; `tests/test_integration_one_database.py` is the one that does.

**Columns are upgraded by `db.COLUMN_UPGRADES`, not by `schema.sql` and not by
ReviQ's `MIGRATIONS`.** D20 left column changes manual, which held while there
were none; `runs.project_id` is the first. Neither obvious home works:

* `schema.sql` cannot express it — it is `CREATE ... IF NOT EXISTS` throughout,
  and any statement referencing a column an older database lacks (an index, most
  obviously) raises inside `executescript` and abandons the rest of the script.
  A missing column would become missing tables.
* ReviQ's `MIGRATIONS` runs only when the API boots. The CLI is still how a
  batch is run, and a corpus only ever opened that way would never get the
  column.

So the retrieval side owns its own upgrades, applied on every connection like
the rest of `ensure_schema`, guarded by `PRAGMA table_info`. Deliberately small:
a table, a column, a type. Anything with a backfill or a rewrite belongs in a
real migration and should be visible as one.

## D28 — A run belongs to a review; a document belongs to nobody

`runs.project_id` is the only place this package admits that reviews exist, and
it is the only workable place. A `document` is a canonical URL: it is the same
URL for every review that finds it, and it exists once, forever (D3). A *search*
is something a project carried out and has to be able to report.

**Snapshot reuse is confined to the project's own runs.** Checked globally,
project B would silently inherit the snapshot project A pulled six months ago:
one credit saved, and B's retrieval report naming a date on which nothing was
retrieved for B, citing bytes fetched under someone else's protocol. One credit
against the one thing the credit buys. Reversible with a `WHERE` clause if it
proves too expensive in practice.

**Both snapshot readers take the scope, not just `has_snapshot`.** Scoping only
the reuse check leaves the leak open in a worse form: B pays for its own fetch,
B's fetch is blocked, and `best_snapshot` hands B project A's clean snapshot
with A's date on it. D23 still holds — one rule for all readers — it now takes
one more parameter.

**Readers derive the project from what they were asked to read.** `report
<batch_id>` confines itself to that batch's own review without the caller naming
it again, because naming it again is a chance to name it wrong. Runs spanning
more than one project cannot come from one run id or one batch id, so a mix
means the ids were assembled by hand; the global view is the answer there, since
showing a few rows too many beats silently dropping another project's.

The report expresses `best_snapshot` as a window function for speed. The project
is computed once by `db.project_of_runs` and *bound* into that query rather than
re-derived in SQL, so the two cannot drift apart. A report and an export
disagreeing about the size of one corpus has happened once already.

## D29 — Adoption remaps, never renumbers; the dry run is the real run

`adopt` brings a corpus out of a database written by the standalone tool. What
makes it more than `INSERT ... SELECT` is that integer keys are database-local:
a `snapshot_id` copied verbatim lands on whatever row holds that number in the
target, and the extraction attached to it now describes a stranger's document.
Every integer key is remapped, and a row whose reference does not resolve is
skipped and counted rather than written pointing somewhere plausible.

`run_id` is a UUID and survives, which is what makes the command idempotent: a
run the target already holds is skipped whole, with everything hanging off it.
An interrupted first attempt is safe to repeat. `documents.canonical_url` is
UNIQUE and a URL is a URL, so a document the target already holds is reused —
the same rule the grey import applies.

**The dry run performs the work and rolls it back.** A second implementation
that predicts what the first would do is exactly how a report and an export came
to disagree about one corpus; here the two cannot disagree, because there is
only one.

**The archive is verified, never moved.** Every WARC a snapshot or figure points
into must be in place, and if one is not, nothing is written.
`archive.read_payload` verifies digests on read, so a wrong path is loud
eventually — but by then the corpus has been adopted and the review has moved
on. Copying 207 MB is not an import command's job: it would fail halfway on a
full disk and leave a half-migrated archive behind. The source is opened
read-only in SQLite's sense rather than by convention, because `db.connect`
would otherwise apply the current schema to it on the way in.
