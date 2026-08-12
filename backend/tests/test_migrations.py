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

from app.database import MIGRATIONS, run_migrations

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
