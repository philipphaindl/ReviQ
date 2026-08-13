# ReviQ

A locally-deployed workbench for conducting Systematic Literature Reviews following Kitchenham & Charters (2007). Runs in Docker, stores everything on your machine.

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

ReviQ walks you through the full SLR pipeline in eight phases:

| # | Phase | What happens |
|---|-------|-------------|
| 1 | **Setup** | Project metadata, up to 5 reviewers, inclusion/exclusion criteria, QA scoring schema, taxonomy categories, database search strings |
| 2 | **Import** | BibTeX upload per database, cross-database deduplication (DOI + normalised title/venue), duplicate override log; grey literature retrieved by `app/retrieval`, carrying its retrieval provenance |
| 3 | **Screening** | Title/abstract decisions (Include / Exclude / Uncertain), per-criterion rationale, automatic conflict detection, Cohen's κ with 95% CI and PABAK |
| 4 | **Eligibility** | Full-text assessment with the same decision workflow, full-text URL tracking |
| 5 | **Snowballing** | Iteration-based forward/backward citation chasing (Wohlin 2014), saturation tracking |
| 6 | **Quality Assessment** | Scoring against project-defined QA criteria (0 / 0.5 / 1), automatic quality-level classification (high/medium/low) |
| 7 | **Data Extraction** | Configurable extraction schema (text, number, boolean, dropdown), per-paper data entry, taxonomy integration |
| 8 | **Results** | PRISMA 2020 flow diagram (SVG, with colour and grayscale download), publication charts, venue breakdown, taxonomy distributions, PDF protocol report, BibTeX exports, replication package |

Collaboration is file-based: reviewers export decisions as JSON, share them however they like (email, shared drive), and import them on the other end.

## Quick start

```bash
cp .env.example .env    # adjust ports/paths if needed
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs

Data lives in a Docker volume (`reviq-db-data`) and persists across restarts.

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

### Grey literature

A multivocal literature review covers grey literature as well as peer-reviewed
work (Garousi, Felizardo & Mäntylä 2019), and the two are reported separately
throughout. The retrieval lives in `backend/app/retrieval/`: it queries a
search engine, canonicalises and deduplicates the hits, fetches each source
through a scraping proxy, and archives the bytes as a WARC snapshot with a
SHA-256 before a single word is extracted.

Retrieval writes into the same SQLite file as the review — the path comes from
`DATABASE_URL`, and `--db` overrides it. That is what lets a replication package
carry the retrieval it rests on, rather than pointing at a second database
somebody has to be sent separately.

```bash
cd backend
python -m app.retrieval batch queries.toml --project 1          # retrieve
python -m app.retrieval report <run_id|batch_id> --out report.md
```

Then `POST /api/projects/1/import/grey/from-retrieval` with
`{"scope_id": "<run_id|batch_id>"}`. No file changes hands: the package is built
and applied in one step, and the grey sources come out carrying join keys
straight into the retrieval tables.

`--project` records which review the runs belong to. It also confines snapshot
reuse to that review: a second project asking for the same URL retrieves it
again rather than inheriting a snapshot fetched months ago under someone else's
protocol. Without it the runs belong to no review and stay visible to all of
them, which is the behaviour that predates it.

Needs `SEARCHAPI_API_KEY` and `SCRAPINGBEE_API_KEY`; both have free tiers large
enough to try it out. A batch of twenty queries runs for tens of minutes — one
concurrent request, with a delay between fetches — so it is a command, not an
HTTP request, and `docs/retrieval/` explains why in detail.

**Handing a corpus to a co-reviewer**, or importing one from them, still goes
through the interchange format:

```bash
python -m app.retrieval export-json <run_id|batch_id> --out records.json
```

and `POST /api/projects/{id}/import/grey` with that file. The keys into the
retrieval tables stay empty for such an import — the integer ids in the package
belonged to the other installation — while the canonical URL and payload digest,
the identities that do travel, are carried across.

**Taking over a corpus retrieved before the databases were merged:**

```bash
python -m app.retrieval adopt data/glr.sqlite3 --project 1 --dry-run
python -m app.retrieval adopt data/glr.sqlite3 --project 1
```

Reads the old file read-only, remaps every integer key, reuses documents the
target already holds under the same URL, and refuses if a WARC file it points
into is not in place. Running it twice adds nothing twice. The dry run does the
identical work and rolls it back, so its counts are the outcome rather than a
prediction of it.

Every record is imported, including the ones that could not be retrieved. That
is deliberate on both sides: the package reports blocked, failed and empty
retrievals so a consumer's "records identified" reconciles with the retrieval
report, and a review that cannot say how much of its grey literature had rotted
or sat behind a publisher's wall is hiding a limitation rather than not having
one. Those papers arrive with `full_text_inaccessible` set, still
screenable on title and snippet, and the response breaks them down by cause:

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

The two layers are independent and parallelisable — neither talks to the
other in tests. Both can also be invoked through `make test` if you prefer
one entry point.

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
| PDF report — synthesis charts | `backend/tests/test_report_pdf_smoke.py` | End-to-end: builds a populated fixture, generates the PDF, parses it with `pypdf`, and asserts the *Figure 1 / 2 / 3* captions are present |

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
| Adopting a separate corpus | `backend/tests/retrieval/test_adopt.py` | Every row arrives, a shared URL stays one document, and no row points at a key from the other database — checked against a target seeded with colliding ids; adopting twice changes nothing; WARC paths are rewritten and a missing file refuses without writing; the source is not modified; a source predating a table still adopts; the dry run reports exactly what the real run does |
| The command line surface | `backend/tests/retrieval/test_cli_arguments.py` | `--project` parses after the three subcommands that record a run and is refused by the seven that would ignore it; `--db` stays global; and the subcommands offering `--project` are exactly the ones whose handler reads it — checked against `cli.py` itself, so a fourth reader breaks the test instead of silently seeing `None` forever |
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
  models.py            # SQLModel table definitions (16 tables)
  database.py          # SQLite engine, session factory, schema migrations
  routers/
    projects.py        # Project CRUD, criteria, taxonomies, search strings
    import_.py         # BibTeX import, deduplication, reviewer decision import
    papers.py          # Paper listing with decision enrichment
    decisions.py       # Reviewer decisions, conflict detection/resolution
    kappa.py           # Cohen's κ, PABAK, confidence intervals
    export.py          # BibTeX export, PRISMA counts, search metrics
    qa.py              # Quality assessment scores and summaries
    snowballing.py     # Iteration management, saturation tracking
    extraction.py      # Extraction schema and per-paper records
    replication.py     # ZIP-based replication package import/export
    report.py          # PDF report generation (fpdf2 + ReportLab for Section 10)
  services/
    bibtex_service.py  # BibTeX parsing, deduplication logic, language detection
    kappa_service.py   # Cohen's κ calculation, PABAK, Landis-Koch interpretation
```

### Frontend structure

```
frontend/src/
  main.tsx                  # Entry point, React Query client
  App.tsx                   # Router, project/reviewer context
  api/
    client.ts               # Axios wrapper (43 API functions)
    types.ts                # TypeScript interfaces for all domain objects
  components/
    ui/index.tsx             # Shared primitives (Card, Modal, Badge, Form)
    databases.tsx            # Database branding, key normalisation, badges
    layout/
      NavBar.tsx             # Top bar with project title + reviewer selector
      Sidebar.tsx            # Phase navigation (9 phases)
  pages/
    Overview.tsx             # Project list, create/import/delete
    Settings.tsx             # Phase 0 — full project configuration
    Search.tsx               # Phase 1 — BibTeX import + dedup management
    Screening.tsx            # Phase 2 — title/abstract screening + kappa
    Eligibility.tsx          # Phase 3 — full-text eligibility
    Snowballing.tsx          # Phase 4 — citation snowballing iterations
    Quality.tsx              # Phase 5 — QA scoring
    Extraction.tsx           # Phase 6 — data extraction
    Results.tsx              # Phase 7 — PRISMA, charts, exports, PDF report
```

## Replication packages

ReviQ can export and import full project snapshots as ZIP archives (schema version `reviq-replication-v1`). A replication package contains:

- `project.json` — all project data, reviewers, criteria, decisions, scores, extraction records
- `bibtex/` — the original `.bib` files, preserving the database names

Useful for archiving with a publication or handing a review to another team.

## References

- Kitchenham, B. & Charters, S. (2007). *Guidelines for performing Systematic Literature Reviews in Software Engineering.* EBSE Technical Report.
- Wohlin, C. (2014). Guidelines for snowballing in systematic literature studies. *EASE '14.*
- Landis, J. R. & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics, 33*(1), 159–174.
- Byrt, T., Bishop, J. & Carlin, J. B. (1993). Bias, prevalence and kappa. *J. Clinical Epidemiology, 46*(5), 423–429.

## License

GNU General Public License (GPL) v3
