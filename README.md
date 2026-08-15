# ReviQ

A locally-deployed workbench for conducting Systematic Literature Reviews
following Kitchenham & Charters (2007), and Multivocal Literature Reviews
following Garousi, Felderer & Mäntylä (2019). Runs in Docker, stores everything
on your machine.

If you use ReviQ in your research, please cite:

> Philipp Haindl, *ReviQ: A systematic literature review workbench*, SoftwareX, Volume 35, 2026 ([https://doi.org/10.1016/j.softx.2026.102814](https://doi.org/10.1016/j.softx.2026.102814))

```bibtex
@article{Haindl2026ReviQ,
  author  = {Haindl, Philipp},
  title   = {ReviQ: A systematic literature review workbench},
  journal = {SoftwareX},
  volume  = {35},
  year    = {2026},
  doi     = {10.1016/j.softx.2026.102814},
  url     = {https://doi.org/10.1016/j.softx.2026.102814}
}
```

## What it does

A project declares itself a **systematic** or a **multivocal** review when it is
created. Both walk the same eight phases; a multivocal review adds a grey
stream, counted and reported separately throughout:

| # | Phase | What happens |
|---|-------|-------------|
| 1 | **Setup** | Project metadata, up to 5 reviewers, inclusion/exclusion criteria, QA scoring schema, taxonomy categories, database search strings |
| 2 | **Import** | BibTeX upload per database, cross-database deduplication (DOI + normalised title/venue), duplicate override log; in a multivocal review, grey literature imported from a retrieval this project made, carrying its provenance |
| 3 | **Screening** | Title/abstract decisions (Include / Exclude / Uncertain), per-criterion rationale, automatic conflict detection, Cohen's κ with 95% CI and PABAK |
| 4 | **Eligibility** | Full-text assessment with the same decision workflow, full-text URL tracking |
| 5 | **Snowballing** | Iteration-based forward/backward citation chasing (Wohlin 2014), saturation tracking |
| 6 | **Quality Assessment** | Scoring against project-defined QA criteria (0 / 0.5 / 1), automatic quality-level classification (high/medium/low) |
| 7 | **Data Extraction** | Configurable extraction schema (text, number, boolean, dropdown), per-paper data entry, taxonomy integration |
| 8 | **Results** | PRISMA 2020 flow diagram (SVG, colour and grayscale) with one column per stream that contributed — databases, snowballing, grey literature — publication charts, venue breakdown, taxonomy distributions, PDF protocol report, BibTeX exports, replication package |

Throughout, the interface counts what PRISMA 2020 counts: **records** while
screening titles and abstracts, **reports** while assessing full texts,
**studies** once a review has included them. The database, the API and the
replication package keep saying `paper`, so existing exports and packages stay
readable.

Collaboration is file-based: reviewers export decisions as JSON, and a whole
grey corpus travels the same way — shared however you like, imported on the
other end.

## Quick start

```bash
cp .env.example .env    # adjust ports/paths if needed
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

Data lives in a Docker volume (`reviq-db-data`) and persists across restarts.
Both ports are bound to loopback: ReviQ has no authentication, so anyone who can
reach the port can read every project and resolve every conflict.

### Configuration

Everything is set through the environment; `.env.example` documents each one and
`docker-compose.yml` supplies the defaults for the container.

| Variable | Default | What reads it |
|---|---|---|
| `BIND_HOST` | `127.0.0.1` | Both containers. Change only for a deployment you have secured some other way |
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Both containers |
| `REVIQ_ALLOWED_ORIGIN` | `http://localhost:3000` | The backend's CORS allow-list |
| `BIB_BASE_DIR` | `./bib_data` | Mounted read-only; where `.bib` files are looked for |
| `DATABASE_URL` | `sqlite:////data/reviq.db` | The API **and** the retrieval CLI — one file holds both halves |
| `DATA_DIR` | `/data` | Where the WARC archive lives, under `DATA_DIR/runs/` |
| `SEARCHAPI_API_KEY` | — | The retrieval CLI only, for grey literature |
| `SCRAPINGBEE_API_KEY` | — | The retrieval CLI only, for grey literature |
| `ANTHROPIC_API_KEY` | — | `--describe-figures` only, off by default |

Outside Docker, `DATABASE_URL` unset means `DATA_DIR/reviq.db` relative to the
working directory — which is not the Docker volume. That distinction matters
most when running a retrieval; the walkthrough below says so again where it
bites.

### BibTeX files

Place your `.bib` files in the directory pointed to by `BIB_BASE_DIR` (defaults to `./bib_data`). Expected layout:

```
bib_data/
  db_search/
    ieee.bib
    acm.bib
    scopus.bib
  snowballing/
    iteration_01/
      forward_citations.bib
```

## Grey literature and multivocal reviews

A multivocal literature review covers grey literature — practitioner reports,
standards, white papers, vendor documentation — alongside peer-reviewed work
(Garousi, Felderer & Mäntylä 2019). ReviQ screens the two together and counts,
reports and publishes them apart.

### Declaring a review multivocal

A project says which kind it is when it is created, and defaults to a systematic
review. The declaration is what switches the grey half on; it is never inferred
from the data, because a review whose PRISMA figure grew a third column halfway
through would be describing a method nobody chose.

A multivocal project gets three things a systematic one never sees:

- the **grey-literature import** on the Import page, described below;
- a **third column** in the PRISMA figure — drawn only once grey records exist,
  exactly as the snowballing column is;
- the **retrieval provenance** beside each grey record during screening: when it
  was fetched, the digest of the bytes fetched, and where the archived copy is.

### Running a retrieval

The retrieval lives in `backend/app/retrieval/`: it queries a search engine,
canonicalises and deduplicates the hits, fetches each source through a scraping
proxy, and archives the bytes as a WARC snapshot with a SHA-256 before a single
word is extracted.

It is a command rather than a button, and stays one. A batch of twenty queries
runs for tens of minutes — one concurrent request, with a delay between fetches
— and spends API credits that are billed to you. `docs/retrieval/decisions.md`
records the reasoning, decision by decision.

**1 — Two API keys.** [SearchApi.io](https://www.searchapi.io) issues the search
queries; [ScrapingBee](https://www.scrapingbee.com) fetches and archives what
they return. Both have free tiers large enough to try this out.

**2 — Into the environment, never into the browser.**

```bash
cp .env.example .env      # then fill in the two keys
set -a && source .env && set +a
```

They are read from the process environment and nowhere else: never written to
the database, never returned by the API, never accepted over HTTP, and scrubbed
out of stored error strings (`app/retrieval/redact.py`). The interface offers no
field to type them into, deliberately — a tool that accepted a key through a
browser would also have to store it somewhere. In Docker they are passed through
from your shell rather than baked into the image; `docker-compose.yml` says how.

`ANTHROPIC_API_KEY` is optional and used by nothing except `--describe-figures`.

**3 — The review's id.** The next command needs it and the interface does not
show it anywhere:

```bash
curl -s http://localhost:8000/api/projects | python3 -m json.tool | grep -E '"(id|title)"'
```

**4 — Write the search protocol down.**

```bash
cd backend
python -m app.retrieval init-config queries.toml
```

That writes a starter query set. Edit it — the format is
[below](#the-query-set) — and keep it: the file *is* the protocol, citable and
re-runnable, rather than a shell history nobody else can read.

**5 — Retrieve.**

```bash
python -m app.retrieval batch queries.toml --project 1
```

`--project 1` records which review the runs belong to, and confines snapshot
reuse to it: a second project asking for the same URL retrieves it again rather
than inheriting a snapshot fetched months ago under someone else's protocol.
Without it the runs belong to no review and stay visible to all of them, which
is the behaviour that predates the flag.

One query at a time, and a failing query does not abort the batch. The progress
lines name the run id you will need later; `report` and `export-json` also
accept the batch id, which covers the whole set at once.

**What it costs, stated plainly.** There is no budget ceiling in the tool. A
`quota_exhausted` response is recorded per source rather than stopping the run,
so the guards are the defaults, not a limit you can set:

| Setting — as a flag on `run`/`refetch`, or a key in the query set | Credits per fetch |
|---|---|
| the default: neither | 1 |
| `--render-js` / `render_js = true` | 5 |
| `--premium-proxy` / `premium_proxy = true` | 10 |
| both together | 25 |
| `--stealth-proxy` / `stealth_proxy = true` | 75 |

Already-archived documents are skipped unless `--refetch` is given, duplicate
queries in one file are a hard error because they silently double the bill, and
snowballing is off until you turn it on. Actual spend is read back from
ScrapingBee's own `Spb-Cost` header, stored per snapshot and printed as
`credits used:` when the run ends. For scale: the pilot corpus behind ReviQ's
grey-literature support is 20 queries returning 424 documents, for roughly
2 120 credits and 207 MB of archive.

**Mind which database it writes to.** Without `--db` the target comes from
`DATABASE_URL`, and without that from `DATA_DIR/reviq.db` — relative to the
working directory. If ReviQ runs in Docker, its database is inside the volume
and *not* the same file, so the retrieval belongs in the container:

```bash
docker compose exec slr-backend \
  python -m app.retrieval batch /data/queries.toml --project 1
```

Inside the container `DATABASE_URL` and `DATA_DIR` are already set by
`docker-compose.yml`, and the keys are forwarded from your shell. Check that
they arrived before spending anything:

```bash
docker compose exec slr-backend printenv SEARCHAPI_API_KEY
```

**6 — Read the retrieval report.**

```bash
python -m app.retrieval report <run_id|batch_id> --out report.md
```

A per-source access log: what was found, what was read, and what could not be —
each with its cause. This is the document a methods section cites, and the
number in its "not retrieved" column is the one the PRISMA figure will show.

**7 — Import it, in the interface.** Open the review's **Import** page. Under
*Import Grey Literature* every retrieval this project made is listed with its
queries, engine, document count and start time, and marked if it is already
imported or was left incomplete. One button imports it: the package is built
from the database it is imported into, so nothing passes through disk and no id
is typed anywhere.

The same is available over HTTP, which is what the button calls:

```
POST /api/projects/1/import/grey/from-retrieval   {"scope_id": "<run_id|batch_id>"}
```

### The query set

`init-config` writes this; every key in `[defaults]` can be overridden per query.

```toml
[defaults]
pages = 10          # 10 results per page, so 10 pages = 100 hits
gl = "at"           # country; changes the results, so report it
hl = "en"           # interface language
render_js = false   # 1 ScrapingBee credit instead of 5

# Snowballing: follow selected outgoing links one level deep.
# 0 disables it. Start at 0, measure relevance, then decide.
snowball_depth = 0
snowball_max_links = 20

[[query]]
q = "AI maturity assessment model"

[[query]]
q = "artificial intelligence maturity framework"

[[query]]
q = "AI readiness assessment organisation"
pages = 5
```

The twelve keys it accepts are `q`, `pages`, `engine`, `gl`, `hl`, `location`,
`render_js`, `premium_proxy`, `stealth_proxy`, `wait_ms`, `snowball_depth` and
`snowball_max_links`. Anything else — an unknown key, an unknown section, a
blank query, the same query twice — is refused rather than ignored: a typo that
is silently dropped from a search protocol is a silently wrong review.

### Repairing what could not be read

The report's causes divide into two kinds: those a second attempt could change
and those it cannot. A dead link stays dead; a bot challenge often does not.

```bash
python -m app.retrieval refetch <run_id|batch_id> --dry-run
python -m app.retrieval refetch <run_id|batch_id> --render-js
```

`refetch` issues no search. It retries only the documents whose recorded cause a
retry could change, and the retry is a new run rather than an edit of the old
one. The dry run prints the candidates and the credits they would cost, so
escalate deliberately: `--render-js` is five times a plain fetch,
`--premium-proxy` ten, the two together twenty-five, and `--stealth-proxy`
seventy-five.

Re-extraction is the free repair — no network, no credits — and it keeps the
extraction it replaces, so the two stay comparable:

```bash
python -m app.retrieval reextract <run_id|batch_id> --all
```

Afterwards, export or import the *original* scope id rather than the retry's.
The retry is a run of its own; the original is what the protocol describes.

### A corpus from a co-reviewer

Handing a corpus to somebody else, or taking one from them, goes through the
interchange format:

```bash
python -m app.retrieval export-json <run_id|batch_id> --out records.json
```

They import that file with *Choose package file* on the same Import page (or
`POST /api/projects/{id}/import/grey`). The keys into the retrieval tables stay
empty for such an import — the integer ids in the package belonged to the other
installation — while the canonical URL and payload digest, the identities that
do travel, are carried across.

### What an import counts

Every record is imported, including the ones that could not be retrieved. That
is deliberate on both sides: the package reports blocked, failed and empty
retrievals so a consumer's "records identified" reconciles with the retrieval
report, and a review that cannot say how much of its grey literature had rotted
or sat behind a publisher's wall is hiding a limitation rather than not having
one. Those records arrive with `full_text_inaccessible` set, still screenable on
title and snippet, and the response breaks them down by cause:

```json
{
  "total_in_package": 424,
  "imported_unique": 423,
  "imported_duplicates": 1,
  "already_present": 0,
  "skipped_no_citekey": 0,
  "imported_unretrievable": 66,
  "unretrievable_by_reason": {
    "origin_unreachable": 32, "no_main_content": 14, "no_article_text": 7,
    "bot_challenge": 5, "not_found": 4, "bad_request": 3, "unsupported_media": 1
  }
}
```

Those are seven different exclusion criteria, not one failure count — a
publisher's access control, a platform post that was never a document and a
dead link do not belong in the same PRISMA box.

The first four counts partition the package exactly, and a test holds them to
it: this response is where a PRISMA "records identified" and "duplicates
removed" come from, so a record that fell out of every bucket could not be
reconciled by anyone reading the diagram later. `imported_duplicates` is a
duplicate *within this package* — a row was written and marked as such.
`already_present` is a document an earlier import already brought in: no row is
written, and it is deliberately not counted as a removed duplicate, because it
was never newly identified.

### What is kept for each grey source

What a `Paper` has no column for is kept beside it in `GreySource`: the
retrieval timestamp, the SHA-256 over the bytes retrieved, and the WARC file
and offset holding them. For a grey source those three *are* the citation —
the page may be edited or gone by the time anyone checks — which is also why
the format is not BibTeX or RIS, neither of which has a field for any of them.

Deduplication is exact: canonical URL or payload hash, never a title. A grey
title is whatever a page's `<title>` said, so a title test would merge two
different documents with a generic name, and a false duplicate removes a source
from a review silently. The consequence, stated rather than hidden: a grey copy
of a formal paper is not recognised as a duplicate of it.

### Taking over a corpus retrieved before the databases merged

```bash
python -m app.retrieval adopt data/glr.sqlite3 --project 1 --dry-run
python -m app.retrieval adopt data/glr.sqlite3 --project 1
```

Reads the old file read-only, remaps every integer key, reuses documents the
target already holds under the same URL, and refuses if a WARC file it points
into is not in place. Running it twice adds nothing twice. The dry run does the
identical work and rolls it back, so its counts are the outcome rather than a
prediction of it.

In Docker the archive has to reach the volume first, because its path is what
the database stores and every later read resolves that string. Rebuild before
you start: an image built before the retrieval package moved in has no
`app.retrieval` to run.

```bash
docker compose build slr-backend

# 1. the archive into the volume
docker compose run --rm -v "$PWD/backend/data:/import:ro" slr-backend \
  sh -c 'mkdir -p /data/runs && cp -rn /import/runs/. /data/runs/'

# 2. then the corpus, with --runs-dir at its default of /data/runs
docker compose run --rm -v "$PWD/backend/data:/import:ro" slr-backend \
  python -m app.retrieval adopt /import/glr.sqlite3 --project 1 --dry-run
```

`adopt` refuses a target that holds no reviews, or one without the project you
named, so pointing it at the wrong file fails loudly rather than succeeding into
a database nobody reads. It also says so when `--runs-dir` is outside
`DATA_DIR` — those paths are stored, and a directory that only exists for the
duration of the command leaves every snapshot pointing nowhere.

### Command reference

```bash
python -m app.retrieval [--db PATH] <command> [options]
```

| Command | Does | Costs credits |
|---|---|---|
| `init` | Creates the database. Rarely needed: every command brings the schema up to date when it opens one | no |
| `run QUERY` | The whole pipeline for a single query, for trying something out | yes |
| `batch CONFIG` | The same, for a whole query set — one run per query, grouped under one batch id | yes |
| `refetch ID` | Retries only the documents whose recorded cause a second attempt could change. Issues no search; the retry is a new run | yes |
| `reextract ID` | Re-runs text extraction against the archived bytes. No network, and the extraction it replaces is kept | no |
| `init-config [PATH]` | Writes a starter query set. Refuses to overwrite one | no |
| `report ID` | Markdown retrieval report for a run or a batch | no |
| `adopt SOURCE` | Takes a corpus from a separate retrieval database into this one | no |
| `export RUN_ID` | Re-exports an earlier run as CSV | no |
| `export-json ID` | Writes the `reviq-grey-v1` package for a run or a batch | no |

`--project` is accepted by `run`, `batch` and `adopt` — the three that record
new runs. The others derive the review from the runs they are pointed at, so
passing it there would be a flag that quietly does nothing; they refuse it
instead. `--db` is global and overrides `DATABASE_URL`.

## Development

### Backend (FastAPI + SQLModel + SQLite)

```bash
cd backend
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Python 3.12, not whatever `python` points at.** `scipy` and `pandas` are
pinned to versions from early 2024, which predate Python 3.13 and ship no
wheels for it — on a newer interpreter `pip` falls back to building `scipy`
from source, which needs a Fortran toolchain. The pins stay as they are on
purpose: ReviQ's published results were computed with these versions, so the
interpreter is what gets pinned, not the libraries. `backend/.python-version`
and the `python:3.12-slim` base image say the same thing.

Without `uv`: `python3.12 -m venv .venv && source .venv/bin/activate && pip
install -r requirements.txt`.

For OCR and figure descriptions, add `uv pip install -r
requirements-optional.txt` — both are off by default.

### Frontend (React 18 + TypeScript + Vite + Tailwind CSS)

```bash
cd frontend
npm install
npm run dev        # dev server on :5173 with HMR
npm run build      # production build into dist/
```

### Running tests

ReviQ ships with two test suites — `pytest` for the backend (statistics,
aggregation, API endpoints, cross-instance integration) and `vitest` for the
frontend chart-data helpers + component snapshots.

```bash
# Backend (FastAPI + SQLModel) — needs the 3.12 venv from above
cd backend
pytest                                # full suite — review + retrieval
pytest tests/retrieval/              # grey literature retrieval only
pytest tests/test_integration_*.py   # integration tests only
pytest -k "not integration"          # unit tests only

# Frontend (TypeScript)
cd frontend
npm test                     # one-shot
npm run test:watch           # interactive watch mode
npm run test:coverage        # coverage report under coverage/
```

The two layers are independent and parallelisable — neither talks to the other
in tests. As of the current commit: 719 backend tests, 209 frontend.

#### Unit-level coverage

| Area | Test file | Coverage |
|------|-----------|----------|
| Cohen's κ — formula, CI, edge cases | `backend/tests/test_kappa.py` | Perfect/zero/partial agreement, `U` as a distinct category, CI ordering, PABAK = 2·Pₒ − 1, range invariants |
| Cohen's κ — published examples | `backend/tests/test_kappa_pabak_examples.py` | Byrt, Bishop & Carlin (1993) PABAK = 0.60 worked example; full Landis & Koch (1977) cut-points; all-agree / all-disagree / single-category edge cases |
| Quality-score aggregation | `backend/tests/test_qa_aggregation.py` | Per-paper percentage = ∑scores / max\_total · 100; band assignment under default and project-custom thresholds (high ≥ 75 %, medium ≥ 50 %) |
| PRISMA flow counts | `backend/tests/test_prisma_counts.py` | Deduplication invariant, screening/full-text partitioning, DB and snowballing streams stay disjoint and non-additive |
| Deduplication | `backend/tests/test_bibtex.py` | DOI-first matching, fuzzy title+venue fallback, cross-session deduplication, normalisation (case, punctuation, whitespace) |
| Grey-package mapping | `backend/tests/test_grey_service.py` | Schema refusal for a foreign or future-versioned file; engine taken from the package and `refetch` runs excluded from it; the reserved `grey:`/`grey-snowball:` prefixes checked against `streams`; year parsing from free-form dates; title fallback; unretrievable records flagged and counted by cause; exact deduplication on canonical URL and payload hash, with a shared title deliberately *not* matching |
| Replication round-trip (schema) | `backend/tests/test_replication_roundtrip.py` | Export → ZIP → re-import → deep-equal on the resulting project state (modulo timestamps and re-assigned IDs); `reviq-replication-v1` schema check |
| Synthesis-chart helpers (backend) | `backend/tests/test_report_charts.py` | Binning, threshold-band assignment with custom thresholds, taxonomy aggregation including empty categories, extraction-field aggregation, first-`select`-field selection |
| Synthesis-chart helpers (frontend) | `frontend/src/utils/charts.test.ts` | Same surface as the backend helpers — keeps the web charts and the PDF report numerically in lock-step |
| Chart component render | `frontend/src/components/charts/charts.test.tsx` | RTL+jsdom render of QA distribution, taxonomy bars, κ cards, extraction-field chart; pins the muted-status palette via inline snapshot |
| PDF report — charts and vocabulary | `backend/tests/test_report_pdf_smoke.py` | End-to-end: builds a populated fixture, generates the PDF, parses it with `pypdf`, asserts the *Figure 1 / 2 / 3* captions, and that the headings count records, reports and studies rather than "papers" |
| Which stream a record belongs to | `backend/tests/test_streams.py`, `frontend/src/components/streams.test.ts` | The two implementations of the same rule, kept in lock-step: formal vs grey, search vs snowball, and the pre-migration fallback to the source prefix |
| PRISMA per-stream counts (frontend) | `frontend/src/utils/prisma.test.ts` | One definition per quantity across all three streams — the drift this replaced had "full texts assessed" meaning two different things in one figure — and which streams the diagram may draw |
| The PRISMA figure itself | `frontend/src/pages/PrismaFlowDiagram.test.tsx` | A column per contributing stream and none for an empty one; geometry derived from their number; the same nouns the pages use |
| Review type and its gating | `backend/tests/test_review_type.py`, `frontend/src/pages/Search.test.tsx` | `slr`/`mlr` validated and backfilled; the grey import appears for a multivocal review only, and an absent or misspelled value degrades to `slr` |
| Display vocabulary | `frontend/src/utils/vocabulary.test.ts`, `sourceLabel.test.ts`, `retrievalReasons.test.ts` | Which noun each phase counts; source keys named for readers; the retrieval-cause map kept complete against `outcome.LABELS` |
| Retrieval, end to end offline | `backend/tests/retrieval/` (21 files) | The query-set parser, SERP parsing, URL canonicalisation, extraction, WARC round-trip, idempotency, the failure classifier against the pilot corpus's distribution, refetch/re-extract candidate selection, the interchange package, adoption, project scoping, schema upgrade, credential scrubbing, and the CLI's own argument surface |

#### Integration coverage

Integration tests stitch multiple endpoints together so refactors that touch
one route can't silently break the numbers downstream. They share fixtures
from `backend/tests/conftest.py` (`instance` / `two_instances`) that spin up
isolated FastAPI `TestClient`s against in-memory SQLite databases.

| Scenario | Test file | What it asserts |
|----------|-----------|-----------------|
| Cross-instance reviewer decision exchange | `backend/tests/test_integration_decision_exchange.py` | Reviewer A exports their JSON file from instance A → reviewer B imports it into instance B; Cohen's κ + 95 % CI + PABAK + Pₒ on B match a monolithic reference; PRISMA partition stays self-consistent (`included + excluded + undecided = unique`); conflicts are logged for disagreements only; re-importing the same file is idempotent (no duplicate decisions, no duplicate conflicts); a corrected re-export propagates correctly through κ; foreign citekeys are skipped; importing for a new reviewer name auto-creates the reviewer; malformed payloads are rejected with HTTP 400 |
| End-to-end SLR pipeline | `backend/tests/test_integration_slr_pipeline.py` | Walks Setup → BibTeX Import → Screening (with conflicts) → Conflict Resolution → Full-Text → Quality Assessment → Data Extraction → Results; verifies κ at each stage, that per-phase κ is independent of other phases, that conflict resolution clears the open-conflict count, that QA summary only lists included papers, that custom QA thresholds reclassify papers correctly, that the extraction summary reflects only filled values |
| Grey literature import | `backend/tests/test_integration_grey_import.py` | A retrieval package becomes grey papers that stay out of the formal stream and out of the PRISMA database box; search hits and snowballed documents separate; unretrievable records import flagged, stay screenable on title and snippet, and keep their cause per source; the retrieval timestamp, payload digest and archive offset survive the round trip and join to their paper; the package's own counts are kept for reconciliation; re-importing an overlapping package creates no second paper; byte-identical content under two URLs is one source while two documents sharing a generic title are two; a package predating `retrieval_reason` still imports; foreign and future-versioned files are refused with HTTP 400 |
| One database, both halves | `backend/tests/test_integration_one_database.py` | The only test that runs on a real file rather than in memory, because that is the only way the retrieval side can be opened at all: a retrieval written with plain `sqlite3` is visible to a request served through SQLAlchemy; importing it needs no file passing through disk; the resulting grey source carries join keys into the retrieval tables, so the archived text is one join away; an uploaded package from elsewhere leaves those keys empty; one project's import does not pick up another's runs |
| Adopting a separate corpus | `backend/tests/retrieval/test_adopt.py` | Every row arrives, a shared URL stays one document, and no row points at a key from the other database — checked against a target seeded with colliding ids; adopting twice changes nothing; WARC paths are rewritten and a missing file refuses without writing; the source is not modified; a source predating a table still adopts; the dry run reports exactly what the real run does; and a target holding no reviews, or not the project named, is refused rather than adopted into |
| The command line surface | `backend/tests/retrieval/test_cli_arguments.py` | `--project` parses after the three subcommands that record a run and is refused by the seven that would ignore it; `--db` stays global; the subcommands offering `--project` are exactly the ones whose handler reads it — checked against `cli.py` itself, so a fourth reader breaks the test instead of silently seeing `None` forever; and which file a retrieval writes to without `--db`, including that an unset `DATABASE_URL` stays relative instead of taking the container path literally |
| One review's retrieval is its own | `backend/tests/retrieval/test_project_scope.py` | A project does not see another's snapshot through either reader — including the case where its own attempt was blocked and the other project's is clean; the cross-run rule survives the narrowing, so a refetch still improves the corpus it repairs; the project is derived from the runs in scope, and a hand-assembled mix falls back to the global view; report, export and refetch agree on what the corpus is |
| Replication round-trip — derived numbers | `backend/tests/test_integration_replication_drift.py` | Builds a fully populated project (taxonomy, extraction schema, screening + full-text decisions with conflicts resolved, QA scores, extraction values), exports the replication ZIP, re-imports into a fresh instance, then asserts every reviewer-visible derived statistic (PRISMA counts, both κ phases with CI/PABAK/Pₒ, QA aggregation by level, extraction value distributions) matches the source bit-for-bit within numerical tolerance — including after a double round-trip |

The backend uses `pytest` 8 with FastAPI's `TestClient`; the frontend uses
`vitest` 4 + `@testing-library/react`. Database-touching backend tests run
against an in-memory SQLite bound to a `StaticPool` so requests handled in
FastAPI's threadpool share the same schema. Cross-instance integration tests
re-point the `get_session` dependency override between two parallel sessions
to simulate two separate ReviQ deployments exchanging files.

## Architecture

```
┌──────────────────────────────────┐
│  Nginx  (serves React SPA, :80)  │
│  proxies /api/* to backend       │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│  FastAPI + Uvicorn (:8000)       │
│  routers/ → services/            │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│  SQLite (Docker volume)          │
└──────────────────────────────────┘
```

Both containers are defined in `docker-compose.yml`. The frontend Dockerfile runs a multi-stage build (Node → Nginx), so neither `node_modules` nor `dist` are checked into version control.

### Backend structure

```
backend/app/
  main.py              # FastAPI app, CORS, lifespan, router registration
  models.py            # SQLModel table definitions (21 tables)
  database.py          # SQLite engine, session factory, migrations; the one file
                       #   both halves open, review side and retrieval side
  routers/
    projects.py        # Project CRUD, review type, criteria, taxonomies, search strings
    import_.py         # BibTeX and grey import, deduplication, retrieval listing
    papers.py          # Paper listing with decision enrichment
    decisions.py       # Reviewer decisions, conflict detection/resolution
    kappa.py           # Cohen's κ, PABAK, confidence intervals
    export.py          # BibTeX export, PRISMA counts, search metrics
    qa.py              # Quality assessment scores and summaries
    snowballing.py     # Iteration management, saturation tracking
    extraction.py      # Extraction schema and per-paper records
    replication.py     # ZIP replication package, retrieval rows included
    report.py          # PDF report (fpdf2 + ReportLab for the included-studies section)
  services/
    bibtex_service.py  # BibTeX parsing, deduplication, language detection
    decision_service.py# Decision state, conflicts
    grey_service.py    # A retrieval package mapped into the grey stream
    kappa_service.py   # Cohen's κ, PABAK, Landis-Koch interpretation
    paper_import.py    # The one import loop both BibTeX paths use
    streams.py         # Formal vs grey, search vs snowball — mirrored in the frontend
  retrieval/           # The grey-literature retrieval tool: CLI, SERP, fetch,
                       #   WARC archive, extraction, figures, interchange, adoption.
                       #   Knows nothing about reviews; see docs/retrieval/
```

### Frontend structure

```
frontend/src/
  main.tsx                  # Entry point, React Query client
  App.tsx                   # Router, project/reviewer context
  api/
    client.ts               # Axios wrapper, one function per endpoint
    types.ts                # TypeScript interfaces for all domain objects
  components/
    ui/index.tsx            # Shared primitives (Card, Modal, Badge, Form)
    databases.tsx           # Database branding, key normalisation, badges
    streams.ts              # Mirror of services/streams.py
    GreyImportPanel.tsx     # Retrieval listing and grey import (multivocal only)
    GreyRecordPanel.tsx     # Provenance, archived text and figures for one source
    charts/                 # Recharts panels, palette, export settings
    layout/                 # NavBar, Sidebar
  utils/
    prisma.ts               # Per-stream PRISMA counts, one definition each
    vocabulary.ts           # Records, reports, studies — which phase counts what
    reviewType.ts           # slr / mlr, read through isMlr and never compared raw
    sourceLabel.ts          # What a source key is called on screen
    retrievalReasons.ts     # Why a source could not be read, in a reader's words
    charts.ts               # Chart aggregation, mirrored in the PDF report
  pages/
    Overview.tsx            # Project list, create (with review type), import, delete
    Settings.tsx            # Phase 1 — project configuration and protocol
    Search.tsx              # Phase 2 — BibTeX import, dedup, grey import
    Screening.tsx           # Phase 3 — title/abstract screening + κ
    Eligibility.tsx         # Phase 4 — full-text eligibility
    Snowballing.tsx         # Phase 5 — citation snowballing iterations
    Quality.tsx             # Phase 6 — QA scoring
    Extraction.tsx          # Phase 7 — data extraction
    Results.tsx             # Phase 8 — PRISMA, charts, exports, PDF report
```

## Replication packages

ReviQ can export and import full project snapshots as ZIP archives (schema
version `reviq-replication-v2`). A replication package contains:

- `project.json` — all project data, reviewers, criteria, decisions, scores,
  extraction records, and for a multivocal review the grey provenance and the
  retrieval rows behind it, scoped to this project's own runs
- `bibtex/` — the original `.bib` files, preserving the database names
- `archives/<run_id>/` — the WARC files, only when exported with the archive

A package carries the retrieval its grey half rests on, rather than pointing at
a second database somebody has to be sent separately. A `v1` package still
imports; its papers simply arrive without that provenance.

Useful for archiving with a publication or handing a review to another team.

## References

**Conducting the review**

- Kitchenham, B. & Charters, S. (2007). *Guidelines for performing Systematic Literature Reviews in Software Engineering.* EBSE Technical Report EBSE-2007-01.
- Wohlin, C. (2014). Guidelines for snowballing in systematic literature studies in software engineering. *EASE '14*, 1–10.
- Page, M. J., McKenzie, J. E., Bossuyt, P. M. et al. (2021). The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. *BMJ, 372*, n71.

**Multivocal reviews and grey literature**

- Ogawa, R. T. & Malen, B. (1991). Towards rigor in reviews of multivocal literatures: applying the exploratory case study method. *Review of Educational Research, 61*(3), 265–286.
- Garousi, V., Felderer, M. & Mäntylä, M. V. (2016). The need for multivocal literature reviews in software engineering: complementing systematic literature reviews with grey literature. *EASE '16*, article 26.
- Adams, R. J., Smart, P. & Huff, A. S. (2017). Shades of grey: guidelines for working with the grey literature in systematic reviews for management and organizational studies. *International Journal of Management Reviews, 19*(4), 432–454.
- Garousi, V., Felderer, M. & Mäntylä, M. V. (2019). Guidelines for including grey literature and conducting multivocal literature reviews in software engineering. *Information and Software Technology, 106*, 101–121.

**Agreement statistics**

- Landis, J. R. & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics, 33*(1), 159–174.
- Byrt, T., Bishop, J. & Carlin, J. B. (1993). Bias, prevalence and kappa. *Journal of Clinical Epidemiology, 46*(5), 423–429.

## License

GNU General Public License (GPL) v3
