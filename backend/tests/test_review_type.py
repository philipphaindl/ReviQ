"""A project declares whether it is a systematic or a multivocal review.

The alternative was inferring it from whether grey literature had been
imported. That fails in both directions: the retrieval UI cannot be found
before it has been used, and a review's PRISMA figure would gain a third column
partway through, changing a published figure without anyone deciding to.

The regression that matters most here is the default. ReviQ is a published tool
with existing projects, every one of them a systematic review, and none of them
may start reporting itself as multivocal.
"""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from app.database import run_migrations


def create(instance, **body):
    payload = {"title": "P", "lead_researcher": "Alice", **body}
    r = instance.client.post("/api/projects", json=payload)
    return r


def fetch(instance, pid: int) -> dict:
    return instance.client.get(f"/api/projects/{pid}").json()


# --- the default ----------------------------------------------------------


def test_a_project_is_a_systematic_review_unless_it_says_otherwise(instance):
    create(instance, title="Default").raise_for_status()
    [p] = [p for p in instance.client.get("/api/projects").json()
           if p["title"] == "Default"]
    assert p["review_type"] == "slr"


def test_an_existing_row_without_the_column_becomes_slr(tmp_path):
    """The migration path, over a database that predates the column.

    Built by hand rather than from the model, following `test_migrations.py`:
    the point is a schema that never had `review_type`, which
    `SQLModel.metadata.create_all` cannot produce.
    """
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE project (
            id INTEGER PRIMARY KEY,
            title VARCHAR NOT NULL,
            methodology VARCHAR NOT NULL DEFAULT 'Kitchenham & Charters (2007)'
        );
    """)
    con.execute("INSERT INTO project (id, title) VALUES (1, 'A review from before')")
    con.commit(); con.close()

    run_migrations(create_engine(f"sqlite:///{path}"))

    con = sqlite3.connect(path)
    assert con.execute("SELECT review_type FROM project WHERE id = 1").fetchone()[0] == "slr"
    con.close()


# --- declaring it ---------------------------------------------------------


def test_a_multivocal_review_can_be_declared_at_creation(instance):
    create(instance, title="MLR", review_type="mlr").raise_for_status()
    [p] = [p for p in instance.client.get("/api/projects").json()
           if p["title"] == "MLR"]
    assert p["review_type"] == "mlr"


def test_the_type_can_be_changed_later(instance):
    create(instance, title="P").raise_for_status()
    pid = instance.client.get("/api/projects").json()[0]["id"]

    instance.client.put(f"/api/projects/{pid}", json={"review_type": "mlr"}).raise_for_status()

    assert fetch(instance, pid)["review_type"] == "mlr"


@pytest.mark.parametrize("bad", ["SLR", "multivocal", "", "systematic review"])
def test_an_unknown_type_is_refused_rather_than_stored(instance, bad):
    """This value gates the grey stream. A typo stored verbatim would leave a
    multivocal review quietly reporting itself as a systematic one."""
    assert create(instance, title="Bad", review_type=bad).status_code == 422


def test_an_unknown_type_is_refused_on_update_too(instance):
    create(instance, title="P").raise_for_status()
    pid = instance.client.get("/api/projects").json()[0]["id"]

    r = instance.client.put(f"/api/projects/{pid}", json={"review_type": "nonsense"})

    assert r.status_code == 422
    assert fetch(instance, pid)["review_type"] == "slr"


# --- methodology, dead until now ------------------------------------------


def test_the_methodology_can_finally_be_set(instance):
    """It was on the model and reachable through neither the API nor the UI, so
    every project claimed Kitchenham & Charters — including multivocal ones,
    which cite Garousi et al. instead."""
    create(instance, title="MLR", review_type="mlr",
           methodology="Garousi, Felizardo & Mäntylä (2019)").raise_for_status()
    [p] = [p for p in instance.client.get("/api/projects").json()
           if p["title"] == "MLR"]
    assert p["methodology"] == "Garousi, Felizardo & Mäntylä (2019)"


def test_omitting_the_methodology_keeps_the_default(instance):
    """`exclude_none` on create: an omitted field must not overwrite the
    model's default with null."""
    create(instance, title="P").raise_for_status()
    [p] = [p for p in instance.client.get("/api/projects").json()
           if p["title"] == "P"]
    assert p["methodology"] == "Kitchenham & Charters (2007)"


# --- it has to survive a replication round trip ---------------------------


def test_the_review_type_travels_in_a_replication_package(instance):
    """A co-reviewer opening the package must see the same kind of review. The
    project block is derived from the model rather than hand-listed, so this
    holds by construction — pinned because the hand-listed Paper block dropped
    `venue_category_override` exactly this way."""
    create(instance, title="MLR", review_type="mlr",
           methodology="Garousi et al.").raise_for_status()
    pid = instance.client.get("/api/projects").json()[0]["id"]

    package = instance.client.get(f"/api/projects/{pid}/replication/export")
    package.raise_for_status()

    import io, json, zipfile
    with zipfile.ZipFile(io.BytesIO(package.content)) as zf:
        project = json.loads(zf.read("project.json"))["project"]
    assert project["review_type"] == "mlr"
    assert project["methodology"] == "Garousi et al."
