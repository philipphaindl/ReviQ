"""
Shared fixtures and helpers for the integration test suite.

`make_instance()` is the workhorse: every call returns an isolated FastAPI
TestClient backed by its own in-memory SQLite (StaticPool so requests handed
to FastAPI's threadpool see the same schema). Calling it twice in a single
test simulates two separate ReviQ deployments — exactly the topology
co-reviewers run when exchanging decision files.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_retrieval_conn, get_session
from app.main import app
from app.models import Reviewer


# A retrievable glr record with every field a real package carries. Tests
# override only the field under examination, so a new field in the format is
# added here once rather than in every fixture.
GREY_RECORD_DEFAULTS: dict[str, Any] = {
    "record_key": "oecd-org-3f2a91c07be4",
    "canonical_url": "https://oecd.org/ai-maturity",
    "host": "oecd.org",
    "discovery": "serp",
    "discovery_depth": 0,
    "retrieval_status": "ok",
    "retrieval_reason": None,
    "title": "AI Maturity in the Public Sector",
    "source_url": "https://www.oecd.org/ai-maturity/",
    "raw_url": "https://oecd.org/ai-maturity",
    "retrieved_at_utc": "2026-08-11T19:36:06Z",
    "sha256": "a" * 64,
    "media_type": "html",
    "content_length": 51234,
    "author": "OECD",
    "publication_date": "2024-03-15",
    "language": "en",
    "word_count": 4210,
    "snippet": "A five-level model for assessing AI maturity in government.",
    "warc": {
        "run_id": "r1", "filename": "snapshots.warc.gz", "offset": 56108,
        "record_id": "<urn:uuid:fefa3433>",
        "recorded_path": "data/runs/r1/snapshots.warc.gz",
    },
    "observations": [{"query": "AI maturity model", "global_rank": 3, "run_id": "r1"}],
}


@dataclass
class Instance:
    """One ReviQ deployment's HTTP-level handle. Backed by an in-memory DB."""
    client: TestClient
    session: Session
    label: str = "instance"

    # ── Project / setup helpers ──────────────────────────────────────────────

    def create_project(self, *, title: str = "P", lead: str = "Alice") -> dict:
        self.client.post("/api/projects", json={
            "title": title, "description": "fixture",
            "lead_researcher": lead,
        }).raise_for_status()
        # POST /projects returns an empty body in the current backend; list
        # afterwards and pick the row by title so callers get the assigned id.
        for p in self.client.get("/api/projects").json():
            if p["title"] == title:
                return p
        raise AssertionError(f"project {title!r} not visible after POST")

    def add_reviewer(self, pid: int, *, name: str, role: str = "R2") -> dict:
        r = self.client.post(f"/api/projects/{pid}/reviewers",
                             json={"name": name, "role": role})
        r.raise_for_status()
        return r.json()

    def reviewers(self, pid: int) -> list[dict]:
        return self.client.get(f"/api/projects/{pid}/reviewers").json()

    def add_qa_criterion(self, pid: int, *, label: str, description: str = "Q",
                         max_score: float = 1.0) -> dict:
        r = self.client.post(f"/api/projects/{pid}/qa-criteria", json={
            "label": label, "description": description, "max_score": max_score,
        })
        r.raise_for_status()
        return r.json()

    # ── Paper import (BibTeX is the only path) ───────────────────────────────

    def import_bib(self, pid: int, entries: list[dict], *, db_name: str = "acm") -> dict:
        """`entries` is a list of {citekey, title, year, doi?, venue?, authors?}."""
        bib = []
        for e in entries:
            fields = {
                "author": e.get("authors", "Author"),
                "title":  e["title"],
                "year":   str(e.get("year", 2020)),
                "booktitle": e.get("venue", "ICSE"),
                "doi":    e.get("doi", ""),
            }
            body = ",\n  ".join(f'{k} = {{{v}}}' for k, v in fields.items() if v)
            bib.append(f"@inproceedings{{{e['citekey']},\n  {body}\n}}")
        content = "\n\n".join(bib).encode("utf-8")
        r = self.client.post(
            f"/api/projects/{pid}/import/bib",
            data={"db_name": db_name},
            files={"file": ("fixture.bib", content, "application/x-bibtex")},
        )
        r.raise_for_status()
        return r.json()

    # ── Grey literature import (a glr-interchange-v1 package) ────────────────

    def import_grey(self, pid: int, records: list[dict], *,
                    engine: str = "google", counts: Optional[dict] = None,
                    schema: str = "glr-interchange-v1",
                    filename: str = "records.json") -> dict:
        """Post a glr package. `records` are partial; defaults fill the rest."""
        full = [{**GREY_RECORD_DEFAULTS, **r} for r in records]
        payload = {
            "_schema": schema,
            "_exported_at": "2026-08-12T13:41:52Z",
            "tool": {"name": "glr", "version": "0.1.0"},
            "canonicalization": "glr.urls.canonicalize/1",
            "runs": [{"run_id": "r1", "engine": engine, "query": "AI maturity model"}],
            "archive": [],
            "counts": counts or {
                "documents": len(full),
                "ok": sum(1 for r in full if r.get("retrieval_status") == "ok"),
            },
            "records": full,
            "scope": {"kind": "batch", "id": "batch-1"},
        }
        r = self.client.post(
            f"/api/projects/{pid}/import/grey",
            files={"file": (filename, json.dumps(payload).encode("utf-8"),
                            "application/json")},
        )
        r.raise_for_status()
        return r.json()

    def grey_sources(self, pid: int) -> list[dict]:
        return self.client.get(f"/api/projects/{pid}/grey-sources").json()

    def grey_imports(self, pid: int) -> list[dict]:
        return self.client.get(f"/api/projects/{pid}/grey-imports").json()

    def papers(self, pid: int) -> list[dict]:
        return self.client.get(f"/api/projects/{pid}/papers").json()

    def paper_by_citekey(self, pid: int, citekey: str) -> dict:
        for p in self.papers(pid):
            if p["citekey"] == citekey:
                return p
        raise AssertionError(f"paper {citekey!r} not found in {self.label}")

    # ── Decisions ────────────────────────────────────────────────────────────

    def decide(self, pid: int, paper_id: int, *, reviewer_id: int,
               phase: str = "screening", decision: str,
               criterion_label: Optional[str] = None) -> dict:
        r = self.client.post(
            f"/api/projects/{pid}/papers/{paper_id}/decisions",
            json={"reviewer_id": reviewer_id, "phase": phase,
                  "decision": decision, "criterion_label": criterion_label},
        )
        r.raise_for_status()
        return r.json()

    def export_decisions(self, pid: int, reviewer_id: int,
                         *, phase: str = "screening") -> dict:
        """Returns the parsed JSON payload reviewers actually share."""
        r = self.client.get(
            f"/api/projects/{pid}/export/decisions",
            params={"reviewer_id": reviewer_id, "phase": phase},
        )
        r.raise_for_status()
        return json.loads(r.content)

    def import_decisions(self, pid: int, payload: dict,
                         *, filename: str = "imported.json") -> dict:
        r = self.client.post(
            f"/api/projects/{pid}/import/reviewer-decisions",
            files={"file": (filename, json.dumps(payload).encode("utf-8"),
                            "application/json")},
        )
        r.raise_for_status()
        return r.json()

    # ── Derived statistics ───────────────────────────────────────────────────

    def kappa(self, pid: int, phase: str = "screening", **params) -> dict:
        r = self.client.get(f"/api/projects/{pid}/kappa",
                            params={"phase": phase, **params})
        r.raise_for_status()
        return r.json()

    def export_stats(self, pid: int) -> dict:
        return self.client.get(f"/api/projects/{pid}/export/stats").json()

    def conflicts(self, pid: int, **params) -> list[dict]:
        return self.client.get(f"/api/projects/{pid}/conflicts",
                               params=params).json()

    def qa_summary(self, pid: int) -> dict:
        return self.client.get(f"/api/projects/{pid}/qa-summary").json()

    def upsert_qa(self, pid: int, paper_id: int, *, reviewer_id: int,
                  criterion_id: int, score: float) -> dict:
        r = self.client.post(
            f"/api/projects/{pid}/papers/{paper_id}/qa-scores",
            json={"reviewer_id": reviewer_id, "criterion_id": criterion_id,
                  "score": score},
        )
        r.raise_for_status()
        return r.json()

    # ── Replication ──────────────────────────────────────────────────────────

    def export_replication(self, pid: int) -> bytes:
        r = self.client.get(f"/api/projects/{pid}/replication/export")
        r.raise_for_status()
        return r.content

    def import_replication(self, zip_bytes: bytes) -> dict:
        r = self.client.post(
            "/api/projects/replication/import",
            files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        )
        r.raise_for_status()
        return r.json()


def make_instance(label: str = "instance", db_path=None) -> Instance:
    """Build an isolated ReviQ deployment for cross-instance tests.

    Each call creates a fresh engine + session and registers a dependency
    override on the shared `app` object. Tests that need two instances at once
    should call this from inside a fixture that also clears
    `app.dependency_overrides` at teardown so the second instance's override
    doesn't leak into other tests.

    `db_path` builds the instance on a real file instead of in memory, which is
    what the retrieval side needs: it opens the database with plain sqlite3 and
    cannot join SQLAlchemy's shared in-memory connection. Only the tests that
    exercise both halves at once pay for the file; everything else stays in
    memory and fast.
    """
    if db_path is None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    app.dependency_overrides[get_session] = lambda: session
    if db_path is not None:
        # The other half of the same file. `retrieval.db.connect` applies
        # `schema.sql` on every connection, so this both creates the retrieval
        # tables and hands the request a connection to them.
        from app.retrieval import db as retrieval_db

        def retrieval_conn():
            conn = retrieval_db.connect(Path(db_path))
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_retrieval_conn] = retrieval_conn
    return Instance(client=TestClient(app), session=session, label=label)


@pytest.fixture
def reset_overrides():
    """Cleans dependency overrides after the test so we don't leak between tests."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def instance(reset_overrides):
    return make_instance("a")


@pytest.fixture
def two_instances(reset_overrides):
    """A pair of completely separate ReviQ deployments.

    Note: FastAPI dependency overrides are a single dict on `app`, so we
    cannot have two simultaneous overrides for the same dep. We work around
    this by re-pointing the override before each call via the `use()` helper
    instead of touching `app.dependency_overrides` directly inside tests.
    """
    a = make_instance("a")
    b_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(b_engine)
    b_session = Session(b_engine)
    b = Instance(client=TestClient(app), session=b_session, label="b")

    def use(inst: Instance):
        app.dependency_overrides[get_session] = lambda: inst.session

    use(a)  # default starting point
    return SimpleNamespace(a=a, b=b, use=use)


# A SimpleNamespace stand-in that doesn't need extra imports at call sites.
class SimpleNamespace:
    def __init__(self, **kw): self.__dict__.update(kw)
