# ReviQ

A locally-deployed workbench for conducting Systematic Literature Reviews following Kitchenham & Charters (2007). Runs in Docker, stores everything on your machine.

If you use ReviQ in your research, please cite:

> Haindl, Philipp (submitted). *ReviQ: A Systematic Literature Review Workbench.* SoftwareX.

## What it does

ReviQ walks you through the full SLR pipeline in eight phases:

| # | Phase | What happens |
|---|-------|-------------|
| 1 | **Setup** | Project metadata, up to 5 reviewers, inclusion/exclusion criteria, QA scoring schema, taxonomy categories, database search strings |
| 2 | **Import** | BibTeX upload per database, cross-database deduplication (DOI + normalised title/venue), duplicate override log |
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

## Development

### Backend (FastAPI + SQLModel + SQLite)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

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
# Backend (FastAPI + SQLModel)
cd backend
pytest                                # full suite, ~4 s — runs unit + integration
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
