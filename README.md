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

```bash
cd backend
pytest
```

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
