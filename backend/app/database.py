"""
Database engine and session factory.

Uses SQLite by default (path from DATABASE_URL env var, defaults to /data/reviq.db).
run_migrations() applies additive ALTER TABLE statements idempotently on startup.
"""
import os
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/reviq.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


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
