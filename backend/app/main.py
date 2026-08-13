"""
FastAPI application entry point for the ReviQ backend.

Registers all routers under /api and runs schema migrations on startup.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables, ensure_retrieval_schema, run_migrations
from app.routers import projects, papers, import_, decisions, kappa, export, qa, snowballing, extraction, replication, report


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the one database up to date — both halves of it.

    The review tables come from SQLModel plus `run_migrations`; the retrieval
    tables come from `app/retrieval/schema.sql`, which owns its own upgrades so
    that the CLI — which never boots this app — gets them too.

    A `DATABASE_URL` the retrieval side cannot open stops the boot instead of
    degrading quietly: the API would otherwise accept retrieval work it has
    nowhere to record.
    """
    create_db_and_tables()
    ensure_retrieval_schema()
    run_migrations()
    yield


app = FastAPI(
    title="ReviQ API",
    description="SLR Workbench following Kitchenham & Charters (2007)",
    version="0.1.0",
    lifespan=lifespan,
)

# The frontend is the only intended client. `allow_origins=["*"]` combined
# with `allow_credentials=True` is rejected outright by browsers, so it never
# did what it looked like it did; worse, it let any page the user happened to
# be visiting read a ReviQ project from localhost. Credentials are not used
# anywhere in this API, so they stay off.
_ALLOWED_ORIGIN = os.environ.get("REVIQ_ALLOWED_ORIGIN", "http://localhost:3000")
ALLOWED_ORIGINS = [_ALLOWED_ORIGIN, _ALLOWED_ORIGIN.replace("localhost", "127.0.0.1")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(ALLOWED_ORIGINS)),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(import_.router, prefix="/api")
app.include_router(decisions.router, prefix="/api")
app.include_router(kappa.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(snowballing.router, prefix="/api")
app.include_router(extraction.router, prefix="/api")
app.include_router(replication.router, prefix="/api")
app.include_router(report.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
