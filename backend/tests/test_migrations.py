"""Schema migrations.

Until `run_migrations` took an engine argument, nothing in this suite ever
executed a migration: the function closed over the module-level engine and the
fixtures only ever called `SQLModel.metadata.create_all()`. A typo in the
statement list would have broken every existing installation on boot with all
130 tests green. These tests close that hole.
"""
import sqlite3

import pytest
from sqlalchemy import create_engine

from app.database import (
    MIGRATIONS, MLR_METHODOLOGY, WRONG_MLR_METHODOLOGY, run_migrations,
)

# The `paper` table as it stood before the stream columns existed. Built by
# hand rather than from the model, because the point is to migrate a database
# that predates the model.
LEGACY_SCHEMA = """
CREATE TABLE paper (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    citekey VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    dedup_status VARCHAR NOT NULL DEFAULT 'original'
);
CREATE TABLE inclusioncriterion (
    id INTEGER PRIMARY KEY, project_id INTEGER, label VARCHAR, description VARCHAR, phase VARCHAR
);
CREATE TABLE exclusioncriterion (
    id INTEGER PRIMARY KEY, project_id INTEGER, label VARCHAR, description VARCHAR, phase VARCHAR
);
"""

LEGACY_ROWS = [
    (1, 1, "smith2020", "A formal paper", "ieee", "original"),
    (2, 1, "jones2021", "A snowballed paper", "snowballing:1", "original"),
    (3, 1, "doe2019", "A second snowballed paper", "snowballing:12", "duplicate"),
    (4, 1, "roe2022", "Another database hit", "scopus", "original"),
]


@pytest.fixture
def legacy_db(tmp_path):
    """A pre-migration database on disk, with rows in it."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.executemany("INSERT INTO paper VALUES (?, ?, ?, ?, ?, ?)", LEGACY_ROWS)
    conn.commit()
    conn.close()
    return path


def columns(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(paper)")}
    finally:
        conn.close()


def rows(path) -> dict[str, tuple]:
    conn = sqlite3.connect(path)
    try:
        return {
            r[0]: (r[1], r[2])
            for r in conn.execute("SELECT citekey, stream, discovery FROM paper")
        }
    finally:
        conn.close()


class TestMigrationsApply:
    def test_new_columns_are_added(self, legacy_db):
        assert "stream" not in columns(legacy_db)
        run_migrations(create_engine(f"sqlite:///{legacy_db}"))
        assert {"stream", "discovery", "venue_category_override"} <= columns(legacy_db)

    def test_existing_rows_are_backfilled(self, legacy_db):
        """SQLite ADD COLUMN without a default leaves existing rows NULL, so
        every column needs its backfill or `stream_of` falls back forever."""
        run_migrations(create_engine(f"sqlite:///{legacy_db}"))
        assert rows(legacy_db) == {
            "smith2020": ("formal", "search"),
            "jones2021": ("formal", "snowball"),
            "doe2019": ("formal", "snowball"),
            "roe2022": ("formal", "search"),
        }

    def test_running_twice_changes_nothing(self, legacy_db):
        """`run_migrations` executes on every boot. The ALTERs fail and are
        swallowed; the backfills must match zero rows the second time."""
        engine = create_engine(f"sqlite:///{legacy_db}")
        run_migrations(engine)
        first = rows(legacy_db)
        run_migrations(engine)
        assert rows(legacy_db) == first

    def test_a_backfill_does_not_overwrite_a_later_value(self, legacy_db):
        """A grey paper imported after the migration must survive the next
        boot. The backfills are IS NULL-guarded precisely for this."""
        engine = create_engine(f"sqlite:///{legacy_db}")
        run_migrations(engine)

        conn = sqlite3.connect(legacy_db)
        conn.execute(
            "INSERT INTO paper (id, project_id, citekey, title, source, dedup_status,"
            " stream, discovery) VALUES (9, 1, 'web1', 'A web page', 'grey:google',"
            " 'original', 'grey', 'snowball')"
        )
        conn.commit()
        conn.close()

        run_migrations(engine)
        assert rows(legacy_db)["web1"] == ("grey", "snowball")


class TestMigrationList:
    def test_every_statement_is_additive(self):
        """No DROP, no DELETE, no destructive ALTER. This list runs
        unattended on every boot against the user's only copy of their data."""
        for stmt in MIGRATIONS:
            head = stmt.strip().upper()
            assert head.startswith(("ALTER TABLE", "UPDATE ", "CREATE INDEX",
                                    "CREATE UNIQUE INDEX")), stmt
            assert " DROP " not in f" {head} "
            assert not head.startswith("DELETE")

    def test_each_added_column_has_a_backfill(self):
        """An added column without a backfill leaves NULLs behind, which is
        how a stream test ends up relying on the legacy fallback forever."""
        added = {
            stmt.split("ADD COLUMN")[1].split()[0]
            for stmt in MIGRATIONS if "ADD COLUMN" in stmt and "paper" in stmt.lower()
        }
        backfilled = {
            stmt.split("SET")[1].split("=")[0].strip()
            for stmt in MIGRATIONS if stmt.strip().upper().startswith("UPDATE PAPER")
        }
        # venue_category_override is user-set and legitimately NULL by default.
        assert {"stream", "discovery"} <= backfilled
        assert added >= {"stream", "discovery"}


# ── The one migration that corrects a value rather than filling one in ────────

# `project` as it stood before the correction. Written by hand for the same
# reason as LEGACY_SCHEMA above: the point is a database that predates it.
PROJECT_SCHEMA = """
CREATE TABLE project (
    id INTEGER PRIMARY KEY,
    title VARCHAR NOT NULL,
    lead_researcher VARCHAR NOT NULL,
    methodology VARCHAR NOT NULL DEFAULT 'Kitchenham & Charters (2007)'
);
"""

PROJECT_ROWS = [
    # A multivocal review created before the citation was corrected.
    (1, "Grey pilot", "PH", WRONG_MLR_METHODOLOGY),
    # A systematic one, which never carried the string at all.
    (2, "Systematic", "PH", "Kitchenham & Charters (2007)"),
    # One where the reviewer wrote their own, and it happens to contain the
    # wrong spelling. Nothing here may touch it.
    (3, "Hand-written", "PH", "Garousi, Felizardo & Mäntylä (2019), adapted"),
    # And one created after the fix.
    (4, "Recent", "PH", MLR_METHODOLOGY),
]


@pytest.fixture
def projects_db(tmp_path):
    path = tmp_path / "projects.db"
    conn = sqlite3.connect(path)
    conn.executescript(PROJECT_SCHEMA)
    conn.executemany("INSERT INTO project VALUES (?, ?, ?, ?)", PROJECT_ROWS)
    conn.commit()
    conn.close()
    return path


def methodologies(path) -> dict[int, str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT id, methodology FROM project")}
    finally:
        conn.close()


class TestMethodologyCorrection:
    """The multivocal guidelines are Garousi, *Felderer* & Mäntylä. ReviQ
    offered the wrong co-author as a project's default methodology, and the
    interface has no field to correct it in — so this boot-time correction is
    the only thing a reviewer with an existing project has."""

    def test_the_wrong_citation_is_corrected(self, projects_db):
        run_migrations(create_engine(f"sqlite:///{projects_db}"))
        assert methodologies(projects_db)[1] == MLR_METHODOLOGY

    def test_the_umlaut_survives(self, projects_db):
        """Asserted as the literal string rather than through the constant: the
        statement carries an ä, and it has to match what is stored byte for
        byte or it matches nothing — and `run_migrations` swallows failures."""
        run_migrations(create_engine(f"sqlite:///{projects_db}"))
        assert methodologies(projects_db)[1] == "Garousi, Felderer & Mäntylä (2019)"

    def test_what_a_reviewer_wrote_is_left_alone(self, projects_db):
        """Guarded by the whole wrong string, so a methodology that merely
        contains it — someone citing the paper and saying what they changed —
        is not rewritten under them."""
        run_migrations(create_engine(f"sqlite:///{projects_db}"))
        after = methodologies(projects_db)
        assert after[2] == "Kitchenham & Charters (2007)"
        assert after[3] == "Garousi, Felizardo & Mäntylä (2019), adapted"

    def test_running_twice_changes_nothing(self, projects_db):
        engine = create_engine(f"sqlite:///{projects_db}")
        run_migrations(engine)
        once = methodologies(projects_db)
        run_migrations(engine)
        assert methodologies(projects_db) == once

    def test_a_project_created_after_the_fix_is_untouched(self, projects_db):
        run_migrations(create_engine(f"sqlite:///{projects_db}"))
        assert methodologies(projects_db)[4] == MLR_METHODOLOGY

    def test_the_two_strings_differ_in_exactly_the_co_author(self):
        """If these drift into two unrelated strings the guard stops matching
        and the correction quietly becomes a no-op."""
        assert WRONG_MLR_METHODOLOGY.replace("Felizardo", "Felderer") == MLR_METHODOLOGY


DISCOVERY_SCHEMA = """
CREATE TABLE paper (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    citekey VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    dedup_status VARCHAR NOT NULL DEFAULT 'original',
    stream VARCHAR NOT NULL DEFAULT 'formal',
    discovery VARCHAR NOT NULL DEFAULT 'search'
);
CREATE TABLE inclusioncriterion (
    id INTEGER PRIMARY KEY, project_id INTEGER, label VARCHAR, description VARCHAR, phase VARCHAR
);
CREATE TABLE exclusioncriterion (
    id INTEGER PRIMARY KEY, project_id INTEGER, label VARCHAR, description VARCHAR, phase VARCHAR
);
"""

DISCOVERY_ROWS = [
    # The bug: a snowballed paper mistagged as search-discovered.
    (1, 1, "smith2020", "A mistagged snowball hit", "snowballing:1", "original", "formal", "search"),
    # Grey literature's own snowballing arm, mistagged the same way.
    (2, 1, "jones2021", "A mistagged grey-snowball hit", "grey-snowball:1", "original", "formal", "search"),
    # A normal database hit: source and discovery already agree.
    (3, 1, "doe2019", "An ordinary database hit", "ieee", "original", "formal", "search"),
    # A snowballed paper already correctly tagged — must stay untouched.
    (4, 1, "roe2022", "An already-correct snowball hit", "snowballing:2", "original", "formal", "snowball"),
    # A reviewer's deliberate override: a database-sourced paper hand-marked as
    # snowball-discovered. Not a reserved source prefix, so must be left alone.
    (5, 1, "lee2023", "A hand-marked database hit", "scopus", "original", "formal", "snowball"),
]


@pytest.fixture
def discovery_db(tmp_path):
    path = tmp_path / "discovery.db"
    conn = sqlite3.connect(path)
    conn.executescript(DISCOVERY_SCHEMA)
    conn.executemany(
        "INSERT INTO paper VALUES (?, ?, ?, ?, ?, ?, ?, ?)", DISCOVERY_ROWS
    )
    conn.commit()
    conn.close()
    return path


def discoveries(path) -> dict[str, str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT citekey, discovery FROM paper")}
    finally:
        conn.close()


class TestDiscoveryCorrection:
    """Rows whose `discovery` disagreed with a reserved snowball source prefix
    were invisible to the IS NULL-guarded backfill, which is how a stream's
    dedup count could exceed its own retrieved count — see PRISMA diagram bug."""

    def test_a_mistagged_snowball_hit_is_corrected(self, discovery_db):
        run_migrations(create_engine(f"sqlite:///{discovery_db}"))
        assert discoveries(discovery_db)["smith2020"] == "snowball"

    def test_a_mistagged_grey_snowball_hit_is_corrected(self, discovery_db):
        run_migrations(create_engine(f"sqlite:///{discovery_db}"))
        assert discoveries(discovery_db)["jones2021"] == "snowball"

    def test_an_ordinary_database_hit_is_untouched(self, discovery_db):
        run_migrations(create_engine(f"sqlite:///{discovery_db}"))
        assert discoveries(discovery_db)["doe2019"] == "search"

    def test_an_already_correct_snowball_hit_is_untouched(self, discovery_db):
        run_migrations(create_engine(f"sqlite:///{discovery_db}"))
        assert discoveries(discovery_db)["roe2022"] == "snowball"

    def test_a_reviewers_deliberate_override_is_left_alone(self, discovery_db):
        """Guarded by the reserved source prefix, not by the discovery value
        alone — a database-sourced paper a reviewer hand-marked as snowball
        must not be touched, since its source is not one ReviQ reserves."""
        run_migrations(create_engine(f"sqlite:///{discovery_db}"))
        assert discoveries(discovery_db)["lee2023"] == "snowball"

    def test_running_twice_changes_nothing(self, discovery_db):
        engine = create_engine(f"sqlite:///{discovery_db}")
        run_migrations(engine)
        once = discoveries(discovery_db)
        run_migrations(engine)
        assert discoveries(discovery_db) == once
