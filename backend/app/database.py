"""
Database engine and session factory.

Uses SQLite by default (path from DATABASE_URL env var, defaults to /data/reviq.db).
run_migrations() applies additive ALTER TABLE statements idempotently on startup.

The retrieval side (`app/retrieval/`) opens the *same file* with plain sqlite3
rather than keeping a database of its own — see `retrieval_db_path` for why,
and for the one place that costs something.
"""
import os
from pathlib import Path

from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/reviq.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


# --- the retrieval side of the same file ---------------------------------


class RetrievalDatabaseUnavailable(RuntimeError):
    """`DATABASE_URL` names something the retrieval side cannot open."""


def retrieval_db_path(url: str | None = None) -> Path:
    """The file `app/retrieval` opens: the one the review already uses.

    One database rather than two, because a replication package documenting a
    review has to contain the retrieval it rests on; two files mean two backup
    stories and a package that omits half of its own evidence.

    Two access layers on one file — SQLAlchemy for the review, raw sqlite3 for
    the retrieval — are fine under WAL, which `retrieval.db.connect` sets and
    which lets a reader proceed while a 40-minute batch holds the writer.

    Raises rather than falling back when the URL is in-memory. The test suite
    builds its instances on `sqlite://` with a StaticPool, and a raw sqlite3
    connection cannot join that shared in-memory database; quietly opening some
    default file instead would hand a test a retrieval side belonging to
    nobody. `make_instance(db_path=...)` is how a test that needs both layers
    asks for a real file.
    """
    raw = DATABASE_URL if url is None else url
    scheme, sep, rest = raw.partition("://")
    if not sep or not scheme.startswith("sqlite"):
        raise RetrievalDatabaseUnavailable(
            f"retrieval needs a SQLite database; DATABASE_URL uses {scheme or raw!r}"
        )
    # SQLAlchemy puts an empty host between the scheme and the path, so what
    # follows always starts with the separating slash: `sqlite:///rel.db` is
    # relative, `sqlite:////abs.db` is absolute.
    rest = rest.split("?", 1)[0]
    path = rest[1:] if rest.startswith("/") else rest
    if path in ("", ":memory:"):
        raise RetrievalDatabaseUnavailable(
            "DATABASE_URL points at an in-memory SQLite database, which the "
            "retrieval side cannot open with sqlite3. Build the instance on a "
            "file instead — tests: make_instance(db_path=tmp_path / 'reviq.db')."
        )
    return Path(path)


def ensure_retrieval_schema() -> None:
    """Apply `app/retrieval/schema.sql` to the shared file.

    `retrieval.db.connect` runs `ensure_schema` on every connection (D20), so
    connecting once and closing again is the whole mechanism: no second
    migration system, and no SQLAlchemy translation of a schema already written
    as SQL.
    """
    from app.retrieval import db as retrieval_db

    retrieval_db.connect(retrieval_db_path()).close()


def get_retrieval_conn():
    """FastAPI dependency yielding a raw sqlite3 connection to the same file.

    A dependency rather than a module-level connection, so a test can override
    it the way it already overrides `get_session`, and so each request closes
    what it opened.
    """
    from app.retrieval import db as retrieval_db

    conn = retrieval_db.connect(retrieval_db_path())
    try:
        yield conn
    finally:
        conn.close()


MIGRATIONS = [
    "ALTER TABLE inclusioncriterion ADD COLUMN short_label VARCHAR",
    "ALTER TABLE exclusioncriterion ADD COLUMN short_label VARCHAR",
    "ALTER TABLE paper ADD COLUMN venue_category_override VARCHAR",
    # Stream separation. SQLite ADD COLUMN without a default leaves existing
    # rows NULL, so each column is followed by an IS NULL-guarded backfill —
    # which matches zero rows on every boot after the first.
    "ALTER TABLE paper ADD COLUMN stream VARCHAR",
    "ALTER TABLE paper ADD COLUMN discovery VARCHAR",
    "UPDATE paper SET stream = 'formal' WHERE stream IS NULL",
    "UPDATE paper SET discovery = 'snowball' "
    "WHERE discovery IS NULL AND source LIKE 'snowballing:%'",
    "UPDATE paper SET discovery = 'search' WHERE discovery IS NULL",
    # The two grey-import counts that were missing, so a stored import row adds
    # up to its package the way the response does. Defaulted rather than
    # backfilled: for an import made before these existed the honest value is
    # zero, since nothing recorded whether a record was skipped.
    "ALTER TABLE greyimport ADD COLUMN already_present_count INTEGER DEFAULT 0",
    "ALTER TABLE greyimport ADD COLUMN skipped_count INTEGER DEFAULT 0",
    # Grey sources gained real join keys once both sides share a file. They stay
    # nullable: a package from a co-reviewer names documents this installation
    # may not hold, and NULL is the honest answer there.
    #
    # The retrieval tables are NOT migrated from here. They belong to
    # `app/retrieval/schema.sql` and `retrieval.db.COLUMN_UPGRADES`, which run
    # on every connection — including from the CLI, which never boots this app.
    "ALTER TABLE greysource ADD COLUMN document_id INTEGER",
    "ALTER TABLE greysource ADD COLUMN snapshot_id INTEGER",
]


def run_migrations(target_engine=None):
    """Apply additive schema changes to existing databases.

    Every statement is tried independently and its failure swallowed: on a
    fresh database SQLModel has already created the columns, so the ALTERs
    fail and that is the expected path.

    `target_engine` exists so the migrations can be tested. Without it the
    function closes over the module-level engine, and a typo here would break
    every existing installation on boot with the whole suite still green.
    """
    from sqlalchemy import text
    with Session(target_engine or engine) as session:
        for stmt in MIGRATIONS:
            try:
                session.exec(text(stmt))
                session.commit()
            except Exception:
                session.rollback()


def get_session():
    with Session(engine) as session:
        yield session
