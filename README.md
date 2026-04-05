# ReviQ — SLR Workbench

A locally-deployed, browser-based tool for conducting Systematic Literature Reviews (SLRs) following **Kitchenham & Charters (2007)**.

## Features (v0.1)

- **Phase 0 – Setup**: Project metadata, up to 5 reviewers, I/E criteria, QA schema, taxonomies, database search strings
- **Phase 1 – Import**: BibTeX upload per database, cross-database deduplication (DOI + title/venue), duplicate log, import co-reviewer decisions
- **Phase 2 – Screening**: I/E/U decisions with criterion + rationale, conflict detection, conflict resolution, Cohen's κ (95% CI + PABAK)
- **Phases 3–7**: Scaffolded — eligibility, snowballing, QA, extraction, results (next iterations)
- **Collaboration**: Async file exchange — export/import reviewer decision JSON

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API + docs: http://localhost:8000/docs

## Running Tests

```bash
cd backend && pip install -r requirements.txt && pytest
```

## Architecture

```
slr-frontend  (Nginx + React/Vite, :3000)
      ↓ /api/*
slr-backend   (FastAPI + SQLModel, :8000)
      ↓
SQLite        (Docker volume: reviq-db-data)
```

## License

MIT
