from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routers import projects, papers, import_, decisions, kappa, export


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="ReviQ API",
    description="SLR Workbench following Kitchenham & Charters (2007)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(import_.router, prefix="/api")
app.include_router(decisions.router, prefix="/api")
app.include_router(kappa.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
